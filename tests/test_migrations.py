"""Use only synthetic SQLite files. Never touch the application's local DB."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.autogenerate import compare_metadata

from app.database import Base
from app.db_integrity import configure_sqlite_engine
from app.migrate import ROOT, HEAD, upgrade_database


@pytest.fixture
def legacy_db(tmp_path):
    path=tmp_path/'legacy.db'
    spec=importlib.util.spec_from_file_location('baseline',ROOT/'migrations/versions/0001_legacy.py')
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    engine=sa.create_engine('sqlite:///'+str(path))
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):baseline.upgrade()
        conn.exec_driver_sql("INSERT INTO users VALUES ('user-id','synthetic-user','unchanged-hash','2020-01-02 03:04:05.123456')")
        for note_id,source,owner in [('text','  Original synthetic text café\nwith whitespace.  ','synthetic-user'),('image','[Image upload] old.png','synthetic-user'),('ownerless','Legacy ownerless synthetic note.',None),('ambiguous','[Image upload] could also be typed text',None)]:
            conn.exec_driver_sql("INSERT INTO notes (id,owner_username,patient_id,note_text,diagnoses,medications,follow_ups,urgency,confidence,warning,created_at) VALUES (?,?,?,?,'one, two','1,000 mg, another','a, b','routine',0.85,'Original warning','2020-02-03 04:05:06.654321')",(note_id,owner,'SYN',source))
    engine.dispose()
    return path


def snapshot(path):
    with sqlite3.connect(path) as conn:
        return {table:(conn.execute('PRAGMA table_info('+table+')').fetchall(),conn.execute('SELECT * FROM '+table+' ORDER BY id').fetchall()) for table in ('notes','users')}


def test_legacy_upgrade_preserves_every_value_and_verified_backup(legacy_db):
    before=snapshot(legacy_db)
    backup=upgrade_database(legacy_db)
    assert backup and snapshot(backup)==before
    assert os.stat(backup).st_mode & 0o777 == 0o600
    with sqlite3.connect(legacy_db) as conn:
        for table,(columns,rows) in before.items():
            names=','.join(c[1] for c in columns)
            assert conn.execute('SELECT '+names+' FROM '+table+' ORDER BY id').fetchall()==rows
        assert conn.execute('SELECT version_num FROM alembic_version').fetchone()==(HEAD,)
        assert conn.execute('SELECT count(*) FROM notes WHERE ai_result_json IS NOT NULL OR model_name IS NOT NULL OR prompt_version IS NOT NULL OR extraction_schema_version IS NOT NULL').fetchone()==(0,)
        assert conn.execute('SELECT count(*) FROM note_review_states WHERE status="unreviewed" AND version=0').fetchone()==(4,)
        for table in ('note_review_revisions','note_review_events'):assert conn.execute('SELECT count(*) FROM '+table).fetchone()==(0,)
        assert conn.execute('PRAGMA integrity_check').fetchone()==('ok',)
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        text_source=conn.execute("SELECT kind,availability,provenance,content,byte_size,sha256 FROM document_sources WHERE note_id='text'").fetchone()
        original=conn.execute("SELECT note_text FROM notes WHERE id='text'").fetchone()[0]
        assert text_source==('text','available','legacy_inferred',None,len(original.encode()),hashlib.sha256(original.encode()).hexdigest())
        for note_id in ('image','ambiguous'):
            assert conn.execute('SELECT kind,availability,content,mime_type,byte_size,sha256 FROM document_sources WHERE note_id=?',(note_id,)).fetchone()==('unknown','unavailable',None,None,None,None)
    files=list(backup.parent.iterdir())
    assert upgrade_database(legacy_db) is None
    assert list(backup.parent.iterdir())==files


def test_fresh_upgrade_matches_orm_schema(tmp_path):
    path=tmp_path/'new.db';upgrade_database(path)
    engine=sa.create_engine('sqlite:///'+str(path));configure_sqlite_engine(engine)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn),Base.metadata)==[]
    engine.dispose()


def test_pre_ownership_database_is_not_assigned_to_any_user(legacy_db):
    with sqlite3.connect(legacy_db) as conn:
        conn.execute('DROP INDEX ix_notes_owner_username')
        conn.execute('ALTER TABLE notes DROP COLUMN owner_username')
    upgrade_database(legacy_db)
    with sqlite3.connect(legacy_db) as conn:
        assert conn.execute('SELECT count(*) FROM notes WHERE owner_username IS NOT NULL').fetchone()==(0,)
        assert conn.execute('SELECT count(*) FROM notes').fetchone()==(4,)


def test_unknown_unversioned_schema_is_rejected_unchanged(tmp_path):
    path=tmp_path/'unexpected.db'
    with sqlite3.connect(path) as conn:conn.execute('CREATE TABLE unrelated (id INTEGER)')
    before=path.read_bytes()
    with pytest.raises(RuntimeError,match='Unrecognized'):upgrade_database(path)
    assert path.read_bytes()==before


def test_backup_failure_aborts_without_schema_changes(legacy_db,monkeypatch):
    import app.migrate
    before=legacy_db.read_bytes()
    def fail(*_):raise OSError('synthetic backup error')
    monkeypatch.setattr(app.migrate,'backup_database',fail)
    with pytest.raises(OSError,match='backup error'):upgrade_database(legacy_db)
    assert legacy_db.read_bytes()==before


def test_mid_migration_failure_rolls_back_ddl_and_rows(legacy_db,monkeypatch):
    import sqlalchemy.engine
    before=legacy_db.read_bytes()
    execute=sqlalchemy.engine.Connection.execute
    def failing(self,statement,*args,**kwargs):
        if str(statement).startswith('INSERT INTO document_sources'):raise RuntimeError('synthetic backfill failure')
        return execute(self,statement,*args,**kwargs)
    monkeypatch.setattr(sqlalchemy.engine.Connection,'execute',failing)
    with pytest.raises(RuntimeError,match='backfill failure'):upgrade_database(legacy_db)
    assert legacy_db.read_bytes()==before


def test_destructive_downgrade_is_disabled(legacy_db):
    upgrade_database(legacy_db);before=legacy_db.read_bytes()
    config=Config(str(ROOT/'alembic.ini'));config.attributes['database_path']=legacy_db
    with pytest.raises(RuntimeError,match='Destructive downgrade'):command.downgrade(config,'0001_legacy')
    assert legacy_db.read_bytes()==before


def test_immutable_triggers_and_review_constraints(legacy_db):
    upgrade_database(legacy_db)
    with sqlite3.connect(legacy_db) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        for sql in ["UPDATE notes SET confidence=1", "DELETE FROM notes", "DELETE FROM document_sources"]:
            with pytest.raises(sqlite3.IntegrityError,match='immutable'):conn.execute(sql)
        conn.execute("INSERT INTO note_review_revisions VALUES ('r1','text',1,NULL,?,1,'user-id','2026-01-01')",(json.dumps({'diagnoses':['Human correction']}),))
        conn.execute("INSERT INTO note_review_events VALUES ('e1','text','r1','draft_saved','user-id',NULL,'2026-01-01')")
        for table in ('note_review_revisions','note_review_events'):
            for operation in ('UPDATE '+table+" SET actor_user_id='user-id'",'DELETE FROM '+table):
                with pytest.raises(sqlite3.IntegrityError,match='immutable'):conn.execute(operation)
        for sql in ["UPDATE note_review_states SET status='approved' WHERE note_id='text'", "UPDATE note_review_states SET version=-1 WHERE note_id='text'", "UPDATE note_review_states SET status='draft',current_revision_id='r1' WHERE note_id='image'"]:
            with pytest.raises(sqlite3.IntegrityError):conn.execute(sql)
        conn.execute("UPDATE note_review_states SET status='draft',current_revision_id='r1',version=1 WHERE note_id='text'")
        with pytest.raises(sqlite3.IntegrityError):conn.execute("INSERT INTO note_review_revisions VALUES ('r2','text',1,NULL,'{}',1,'user-id','2026-01-01')")
        with pytest.raises(sqlite3.IntegrityError):conn.execute("INSERT INTO note_review_events VALUES ('e2','image','r1','approved','user-id',NULL,'2026-01-01')")


def test_wal_backup_includes_committed_rows(legacy_db):
    # Keep a WAL connection open so the rows are not implicitly checkpointed.
    with sqlite3.connect(legacy_db) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()==('wal',)
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute("INSERT INTO users VALUES ('wal-user','synthetic-wal','hash','2021-01-01')")
        writer.commit()
        backup=upgrade_database(legacy_db)
        with sqlite3.connect(backup) as restored:
            assert restored.execute("SELECT count(*) FROM users WHERE id='wal-user'").fetchone()==(1,)
            assert restored.execute('PRAGMA integrity_check').fetchone()==('ok',)


@pytest.mark.parametrize('alteration',[
    'ALTER TABLE users ADD COLUMN unrecognized TEXT',
    'ALTER TABLE notes DROP COLUMN warning',
])
def test_modified_legacy_schema_is_rejected_without_writes(legacy_db,alteration):
    with sqlite3.connect(legacy_db) as conn:conn.execute(alteration)
    before=legacy_db.read_bytes()
    with pytest.raises(RuntimeError,match='Unrecognized'):upgrade_database(legacy_db)
    assert legacy_db.read_bytes()==before


def test_replacements_cannot_bypass_immutability(legacy_db):
    upgrade_database(legacy_db)
    with sqlite3.connect(legacy_db) as conn:
        for table in ('notes','document_sources'):
            with pytest.raises(sqlite3.IntegrityError,match='immutable'):
                conn.execute(f'INSERT OR REPLACE INTO {table} SELECT * FROM {table}')
        # A new ID must not replace the unique source link either.
        with pytest.raises(sqlite3.IntegrityError,match='immutable'):
            conn.execute("INSERT OR REPLACE INTO document_sources (id,note_id,kind,availability,provenance,stored_at) VALUES ('replacement','text','unknown','unavailable','legacy_inferred','2026-01-01')")


def test_review_actors_must_own_parent_note(legacy_db):
    upgrade_database(legacy_db)
    with sqlite3.connect(legacy_db) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute("INSERT INTO users VALUES ('other-id','other-account','synthetic-hash','2026-01-01')")
        with pytest.raises(sqlite3.IntegrityError,match='must own'):
            conn.execute("INSERT INTO note_review_revisions VALUES ('bad','text',1,NULL,'{}',1,'other-id','2026-01-01')")
        with pytest.raises(sqlite3.IntegrityError,match='must own'):
            conn.execute("INSERT INTO note_review_revisions VALUES ('ownerless-draft','ownerless',1,NULL,'{}',1,'user-id','2026-01-01')")
        conn.execute("INSERT INTO note_review_revisions VALUES ('good','text',1,NULL,'{}',1,'user-id','2026-01-01')")
        with pytest.raises(sqlite3.IntegrityError,match='must own'):
            conn.execute("INSERT INTO note_review_events VALUES ('bad-event','text','good','approved','other-id',NULL,'2026-01-01')")


def test_application_startup_migrates_fresh_database_idempotently(tmp_path,monkeypatch):
    import asyncio
    import app.database
    from sqlalchemy.ext.asyncio import create_async_engine
    path=tmp_path/'startup.db'
    engine=create_async_engine('sqlite+aiosqlite:///'+str(path))
    monkeypatch.setattr(app.database,'engine',engine)
    asyncio.run(app.database.init_db())
    before=path.read_bytes()
    asyncio.run(app.database.init_db())
    assert path.read_bytes()==before
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT version_num FROM alembic_version').fetchone()==(HEAD,)
    asyncio.run(engine.dispose())


def test_existing_legacy_startup_requires_explicit_upgrade_without_writes(legacy_db):
    from app.migrate import ensure_database_ready
    before=legacy_db.read_bytes()
    with pytest.raises(RuntimeError,match='Database migration required'):
        ensure_database_ready(legacy_db)
    assert legacy_db.read_bytes()==before


def test_followup_guards_upgrade_does_not_rewrite_foundation_data(legacy_db):
    config=Config(str(ROOT/'alembic.ini'));config.attributes['database_path']=legacy_db
    command.upgrade(config,'0002_document_foundation')
    with sqlite3.connect(legacy_db) as conn:
        tables=('notes','users','document_sources','note_review_states')
        before={table:conn.execute('SELECT * FROM '+table).fetchall() for table in tables}
    backup=upgrade_database(legacy_db)
    assert backup
    with sqlite3.connect(legacy_db) as conn:
        for table,rows in before.items():assert conn.execute('SELECT * FROM '+table).fetchall()==rows
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()==(15,)
        # SQLite CHECK accepts NULL expressions; the follow-up trigger closes
        # the nullable MIME loophole without rebuilding the source table.
        with pytest.raises(sqlite3.IntegrityError,match='MIME'):
            conn.execute("INSERT INTO document_sources (id,note_id,kind,availability,provenance,content,byte_size,sha256,stored_at) VALUES ('invalid','not-a-note','image','available','submitted',X'00',1,?,'2026-01-01')",('0'*64,))


def test_normal_connections_preserve_read_transaction_behavior(tmp_path):
    engine=sa.create_engine('sqlite:///'+str(tmp_path/'connection.db'))
    configure_sqlite_engine(engine)
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar()==1
            conn.exec_driver_sql('SELECT 1')
            # Authentication reads must not hold a database read lock while
            # an endpoint awaits an external AI request.
            assert not conn.connection.driver_connection.in_transaction
            conn.exec_driver_sql('CREATE TABLE synthetic (id INTEGER)')
            conn.exec_driver_sql('INSERT INTO synthetic VALUES (1)')
            assert conn.connection.driver_connection.in_transaction
            conn.rollback()
            assert conn.exec_driver_sql('SELECT count(*) FROM synthetic').scalar()==0
    finally:
        engine.dispose()
