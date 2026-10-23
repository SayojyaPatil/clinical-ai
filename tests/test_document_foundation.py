"""Offline regression tests for source storage and immutable extraction baselines."""
import asyncio
import hashlib
import io

import pytest
from PIL import Image
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError

from app.database import (get_db, NoteRecord, DocumentSource, ReviewState,
                          ReviewRevision, ReviewEvent)
from app.main import app
from app.routers import notes
from test_note_security import client, headers

RESPONSE_KEYS = {"id", "patient_id", "diagnoses", "medications", "follow_ups", "urgency", "confidence", "warning", "created_at"}


def inspect_note(note_id):
    async def read():
        async for session in app.dependency_overrides[get_db]():
            note = await session.get(NoteRecord, note_id)
            source = (await session.execute(select(DocumentSource).where(DocumentSource.note_id == note_id))).scalar_one()
            state = await session.get(ReviewState, note_id)
            return note, source, state
    return asyncio.run(read())


def counts():
    async def read():
        async for session in app.dependency_overrides[get_db]():
            return [await session.scalar(select(func.count()).select_from(model)) for model in (NoteRecord, DocumentSource, ReviewState, ReviewRevision, ReviewEvent)]
    return asyncio.run(read())


def create_text(client):
    original = "  Synthetic source only.\nExact punctuation, Unicode café, and spacing.  "
    response = client.post('/notes/analyze-text', headers=headers('user_a'), json={'patient_id':'SYN-FOUNDATION','note_text':original})
    assert response.status_code == 200, response.text
    return response, original


def test_text_source_json_and_response_contract(client):
    response, original = create_text(client)
    assert set(response.json()) == RESPONSE_KEYS
    note, source, state = inspect_note(response.json()['id'])
    assert note.note_text == original
    assert note.owner_username == 'user_a'
    assert note.ai_result_json == {'diagnoses':['Example condition'],'medications':['Example medication'],'follow_ups':['Follow up with clinician'],'urgency':'routine','confidence':0.9}
    assert note.model_name == 'gpt-4o'
    assert note.prompt_version and note.extraction_schema_version == 1
    assert (source.kind, source.availability, source.provenance) == ('text','available','submitted')
    assert source.content is None
    assert source.byte_size == len(original.encode('utf-8'))
    assert source.sha256 == hashlib.sha256(original.encode('utf-8')).hexdigest()
    assert source.mime_type == 'text/plain' and source.stored_at
    assert (state.status,state.version,state.current_revision_id,state.approved_revision_id) == ('unreviewed',0,None,None)
    assert counts() == [1,1,1,0,0]
    # Preserve the existing SQLite timezone behavior: POST retains UTC tzinfo,
    # while a later SQLite read returns the same wall time without a suffix.
    expected = {**response.json(), 'created_at': response.json()['created_at'].removesuffix('Z')}
    assert client.get('/notes/'+note.id,headers=headers('user_a')).json() == expected
    assert client.get('/notes',headers=headers('user_a')).json() == [expected]
    assert client.get('/notes/'+note.id,headers=headers('user_b')).status_code == 404
    assert client.get('/notes',headers=headers('user_b')).json() == []


@pytest.mark.parametrize('format,mime', [('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp')])
def test_image_bytes_are_exact_private_blobs(client,format,mime):
    stream=io.BytesIO();Image.new('RGB',(10,10)).save(stream,format=format)
    data=stream.getvalue()
    response=client.post('/notes/analyze-image',params={'patient_id':'SYN-IMAGE'},headers=headers('user_a'),files={'file':('../../untrusted-name',data,mime)})
    assert response.status_code == 200,response.text
    assert set(response.json()) == RESPONSE_KEYS
    note,source,state=inspect_note(response.json()['id'])
    assert source.content == data
    assert (source.kind,source.availability,source.provenance)==('image','available','submitted')
    assert source.original_filename == '../../untrusted-name'  # Metadata, never a filesystem path.
    assert source.mime_type == mime and source.byte_size == len(data)
    assert source.sha256 == hashlib.sha256(data).hexdigest()
    assert note.ai_result_json['diagnoses']==['Example condition']
    assert state.status=='unreviewed'
    assert 'content' not in response.json()
    assert client.get('/notes/'+note.id,headers=headers('user_b')).status_code==404


@pytest.mark.parametrize('data,mime,status',[(b'fake','image/png',400),(b'x'*(5*1024*1024+1),'image/png',413),(b'','image/png',400),(b'not pdf','application/pdf',400)], ids=['invalid-content','oversized','empty','unsupported-type'])
def test_rejected_uploads_create_no_persistence(client,data,mime,status):
    response=client.post('/notes/analyze-image',params={'patient_id':'SYN'},headers=headers('user_a'),files={'file':('invalid',data,mime)})
    assert response.status_code==status
    assert counts()==[0,0,0,0,0]


def test_failed_ai_creates_no_source_or_review_state(client,monkeypatch):
    async def fail(_):raise ValueError('synthetic failure')
    monkeypatch.setattr(notes,'analyze_note',fail)
    response,_=create_text_without_assert(client)
    assert response.status_code==502
    assert counts()==[0,0,0,0,0]


def create_text_without_assert(client):
    original='Synthetic source note for failure tests only.'
    return client.post('/notes/analyze-text',headers=headers('user_a'),json={'patient_id':'SYN','note_text':original}),original


def test_source_failure_rolls_back_entire_note(client,monkeypatch):
    from sqlalchemy import event
    def fail(*_):raise RuntimeError('synthetic persistence failure')
    event.listen(DocumentSource,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError,match='synthetic persistence'):
            create_text_without_assert(client)
    finally:
        event.remove(DocumentSource,'before_insert',fail)
    assert counts()==[0,0,0,0,0]


@pytest.mark.parametrize('statement',[
    "UPDATE notes SET note_text='changed' WHERE id=:id",
    "UPDATE notes SET diagnoses='changed' WHERE id=:id",
    "UPDATE notes SET ai_result_json='{}' WHERE id=:id",
    "UPDATE notes SET owner_username='user_b' WHERE id=:id",
    "DELETE FROM notes WHERE id=:id",
    "UPDATE document_sources SET sha256='changed' WHERE note_id=:id",
    "DELETE FROM document_sources WHERE note_id=:id",
])
def test_baselines_cannot_be_modified(client,statement):
    response,original=create_text(client)
    async def mutate():
        async for session in app.dependency_overrides[get_db]():
            with pytest.raises(IntegrityError,match='immutable'):
                await session.execute(text(statement),{'id':response.json()['id']})
            await session.rollback()
    asyncio.run(mutate())
    assert inspect_note(response.json()['id'])[0].note_text==original


def test_structured_arrays_do_not_lose_original_boundaries(client,monkeypatch):
    from app.agent import ClinicalResult
    result=ClinicalResult(diagnoses=['First, with qualifier','Second'],medications=['Drug 1,000 mg, with food'],follow_ups=[],urgency='urgent',confidence=0.123456789)
    async def analyze(_):return result
    monkeypatch.setattr(notes,'analyze_note',analyze)
    response,_=create_text(client)
    record,_,_=inspect_note(response.json()['id'])
    assert record.ai_result_json==result.model_dump(mode='json')
    assert response.json()['diagnoses']=='First, with qualifier, Second'
    assert response.json()['medications']=='Drug 1,000 mg, with food'
    assert response.json()['follow_ups']==''
    assert response.json()['confidence']==0.123456789


def test_state_failure_rolls_back_note_and_image_blob(client):
    from sqlalchemy import event
    stream=io.BytesIO();Image.new('RGB',(10,10)).save(stream,format='PNG')
    def fail(*_):raise RuntimeError('synthetic review-state failure')
    event.listen(ReviewState,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError,match='review-state failure'):
            client.post('/notes/analyze-image',params={'patient_id':'SYN'},headers=headers('user_a'),files={'file':('synthetic.png',stream.getvalue(),'image/png')})
    finally:
        event.remove(ReviewState,'before_insert',fail)
    assert counts()==[0,0,0,0,0]


def test_existing_signup_login_and_jwt_contracts(client):
    response=client.post('/auth/signup',json={'username':'synthetic_signup','password':'synthetic-password-123'})
    assert response.status_code==200
    assert set(response.json())=={'message'}
    token=client.post('/auth/token',data={'username':'synthetic_signup','password':'synthetic-password-123'})
    assert token.status_code==200
    assert set(token.json())=={'access_token','token_type'}
    assert token.json()['token_type']=='bearer'
    auth={'Authorization':'Bearer '+token.json()['access_token']}
    response=client.post('/notes/analyze-text',headers=auth,json={'patient_id':'SYN-SIGNUP','note_text':'Synthetic note for signup regression testing only.'})
    assert response.status_code==200
    assert inspect_note(response.json()['id'])[0].owner_username=='synthetic_signup'
    assert client.post('/auth/token',data={'username':'synthetic_signup','password':'wrong'}).status_code==401
    assert client.get('/notes',headers={'Authorization':'Bearer invalid-token'}).status_code==401


def test_analysis_works_against_actual_alembic_schema(client,tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.db_integrity import configure_sqlite_engine
    from app.migrate import upgrade_database
    from app.database import UserRecord
    path=tmp_path/'endpoint-migrated.db'
    upgrade_database(path)
    engine=create_async_engine('sqlite+aiosqlite:///'+str(path))
    configure_sqlite_engine(engine)
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    async def seed():
        async with sessions() as session:
            session.add_all([UserRecord(username='user_a',hashed_password='synthetic-only'),UserRecord(username='user_b',hashed_password='synthetic-only')])
            await session.commit()
    async def override():
        async with sessions() as session:yield session
    previous=app.dependency_overrides[get_db]
    asyncio.run(seed())
    app.dependency_overrides[get_db]=override
    try:
        response,original=create_text(client)
        record,source,state=inspect_note(response.json()['id'])
        assert record.note_text==original and source.sha256 and state.status=='unreviewed'
        stream=io.BytesIO();Image.new('RGB',(10,10)).save(stream,format='PNG')
        image=client.post('/notes/analyze-image',headers=headers('user_a'),params={'patient_id':'SYN'},files={'file':('synthetic.png',stream.getvalue(),'image/png')})
        assert image.status_code==200,image.text
        assert inspect_note(image.json()['id'])[1].content==stream.getvalue()
        assert counts()==[2,2,2,0,0]
        assert client.get('/notes',headers=headers('user_b')).json()==[]
    finally:
        app.dependency_overrides[get_db]=previous
        asyncio.run(engine.dispose())
