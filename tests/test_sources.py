"""Synthetic, read-only source retrieval and authorization regressions."""
import asyncio
import hashlib
import io
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from PIL import Image
from sqlalchemy import text

from app.database import DocumentSource, NoteRecord, ReviewState, get_db
from app.main import app
from app.security import ALGORITHM, SECRET_KEY, create_token
from test_note_security import client, headers


def source_text(client):
    original = '  Synthetic source café\nwith exact spacing and <literal markup>.  '
    response = client.post('/notes/analyze-text', headers=headers('user_a'), json={
        'patient_id': 'SYN-SOURCE', 'note_text': original,
    })
    assert response.status_code == 200
    return response.json()['id'], original


def historical_note(note_id='legacy-image', *, owner='user_a', marker=True, metadata=True):
    async def seed():
        async for db in app.dependency_overrides[get_db]():
            db.add(NoteRecord(id=note_id, owner_username=owner, patient_id='SYN-LEGACY',
                              note_text='[Image upload] old.png' if marker else 'Original synthetic legacy text.\nNo reconstruction.',
                              diagnoses='First, qualifier, Second', medications='', follow_ups='Return, if needed',
                              urgency='routine', confidence=0.8, warning='Original legacy warning',
                              created_at=datetime(2020, 1, 2, 3, 4, 5)))
            await db.flush()
            if metadata:
                original='Original synthetic legacy text.\nNo reconstruction.'
                db.add(DocumentSource(note_id=note_id, kind='unknown' if marker else 'text',
                                      availability='unavailable' if marker else 'available', provenance='legacy_inferred',
                                      mime_type=None if marker else 'text/plain',
                                      byte_size=None if marker else len(original.encode()),
                                      sha256=None if marker else hashlib.sha256(original.encode()).hexdigest()))
            db.add(ReviewState(note_id=note_id))
            await db.commit()
    asyncio.run(seed())
    return note_id


def database_snapshot():
    async def read():
        async for db in app.dependency_overrides[get_db]():
            return {table:(await db.execute(text('SELECT * FROM '+table))).fetchall() for table in
                    ('notes','users','document_sources','note_review_states','note_review_revisions','note_review_events')}
    return asyncio.run(read())


def test_text_source_preserves_original_and_structured_ai(client):
    note_id, original = source_text(client)
    response = client.get(f'/notes/{note_id}/source', headers=headers('user_a'))
    assert response.status_code == 200
    data = response.json()
    assert (data['note_id'], data['kind'], data['availability'], data['provenance']) == (note_id,'text','available','submitted')
    assert data['original_text'] == original
    assert data['mime_type'] == 'text/plain'
    assert data['byte_size'] == len(original.encode())
    assert data['sha256'] == hashlib.sha256(original.encode()).hexdigest()
    assert data['review_status'] == 'unreviewed'
    assert data['ai_result']['diagnoses'] == ['Example condition']
    assert data['model_name'] == 'gpt-4o'
    assert data['stored_at'] and data['source_id']
    assert data['unavailable_reason'] is None
    assert 'content' not in data and 'owner_username' not in data
    assert response.headers['cache-control'] == 'private, no-store'
    assert client.get(f'/notes/{note_id}/source/content', headers=headers('user_a')).status_code == 404


@pytest.mark.parametrize('format,mime',[('PNG','image/png'),('JPEG','image/jpeg'),('WEBP','image/webp')])
def test_exact_image_bytes_type_and_private_headers(client,format,mime):
    output=io.BytesIO();Image.new('RGB',(15,10)).save(output,format=format)
    original=output.getvalue()
    created=client.post('/notes/analyze-image',headers=headers('user_a'),params={'patient_id':'SYN-SOURCE'},files={'file':('synthetic.'+format.lower(),original,mime)})
    assert created.status_code==200
    note_id=created.json()['id']
    metadata=client.get(f'/notes/{note_id}/source',headers=headers('user_a')).json()
    assert metadata['kind']=='image' and metadata['availability']=='available'
    assert metadata['original_text'] is None
    assert metadata['original_filename']=='synthetic.'+format.lower()
    assert metadata['byte_size']==len(original) and metadata['sha256']==hashlib.sha256(original).hexdigest()
    response=client.get(f'/notes/{note_id}/source/content',headers=headers('user_a'))
    assert response.status_code==200 and response.content==original
    assert response.headers['content-type']==mime
    assert response.headers['cache-control']=='private, no-store'
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['vary']=='Authorization'
    assert response.headers['content-disposition']=='inline'
    for suffix in ('/source','/source/content'):
        assert client.get('/notes/'+note_id+suffix,headers=headers('user_b')).status_code==404


@pytest.mark.parametrize('suffix',['/source','/source/content'])
def test_source_endpoints_hide_other_account_and_unknown_records(client,suffix):
    note_id,_=source_text(client)
    denied=client.get('/notes/'+note_id+suffix,headers=headers('user_b'))
    missing=client.get('/notes/not-a-record'+suffix,headers=headers('user_b'))
    assert denied.status_code==missing.status_code==404
    assert denied.json()==missing.json()=={'detail':'Note not found'}


@pytest.mark.parametrize('suffix',['/source','/source/content'])
@pytest.mark.parametrize('auth',['missing','malformed','expired','nonexistent-user'])
def test_source_endpoints_require_valid_existing_account(client,suffix,auth):
    note_id,_=source_text(client)
    request_headers={}
    if auth=='malformed':request_headers={'Authorization':'Bearer malformed'}
    elif auth=='expired':
        token=jwt.encode({'sub':'user_a','exp':datetime.now(timezone.utc)-timedelta(minutes=1)},SECRET_KEY,algorithm=ALGORITHM)
        request_headers={'Authorization':'Bearer '+token}
    elif auth=='nonexistent-user':request_headers={'Authorization':'Bearer '+create_token('no-such-account')}
    assert client.get('/notes/'+note_id+suffix,headers=request_headers).status_code==401


def test_historical_image_has_explicit_unavailable_source_without_fabrication(client):
    note_id=historical_note()
    response=client.get(f'/notes/{note_id}/source',headers=headers('user_a'))
    assert response.status_code==200
    data=response.json()
    assert data['availability']=='unavailable' and data['kind']=='unknown'
    assert 'not retained' in data['unavailable_reason']
    for field in ('original_text','original_filename','mime_type','byte_size','sha256','ai_result','model_name'):
        assert data[field] is None
    assert client.get(f'/notes/{note_id}/source/content',headers=headers('user_a')).status_code==404
    assert client.get(f'/notes/{note_id}',headers=headers('user_a')).json()['diagnoses']=='First, qualifier, Second'


def test_legacy_text_and_ownerless_records_remain_safe(client):
    note_id=historical_note('legacy-text',marker=False)
    data=client.get(f'/notes/{note_id}/source',headers=headers('user_a')).json()
    assert data['availability']=='available'
    assert data['original_text']=='Original synthetic legacy text.\nNo reconstruction.'
    assert data['ai_result'] is None
    orphan=historical_note('ownerless',owner=None)
    for suffix in ('/source','/source/content'):
        assert client.get('/notes/'+orphan+suffix,headers=headers('user_a')).status_code==404


def test_missing_source_metadata_is_not_reconstructed_from_note_marker(client):
    note_id=historical_note('missing-metadata',metadata=False)
    data=client.get(f'/notes/{note_id}/source',headers=headers('user_a')).json()
    assert data['source_id'] is None and data['availability']=='unavailable'
    assert data['original_text'] is None
    assert 'metadata' in data['unavailable_reason']


def test_source_reads_make_no_changes_to_any_records(client):
    note_id,_=source_text(client)
    old=historical_note()
    before=database_snapshot()
    for _ in range(2):
        for id in (note_id,old):
            client.get(f'/notes/{id}/source',headers=headers('user_a'))
            client.get(f'/notes/{id}/source/content',headers=headers('user_a'))
    assert database_snapshot()==before
