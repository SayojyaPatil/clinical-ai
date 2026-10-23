"""Online-only, transactional SQLite migrations with mandatory legacy preflight/backup."""
from pathlib import Path
import os
import sqlite3

from alembic import context
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.db_integrity import configure_sqlite_engine
from app.migrate import backup_database, validate_legacy
from app.database import Base

config = context.config
if context.is_offline_mode():
    raise RuntimeError("Offline migration is disabled: preflight and a verified backup are required.")
if config.cmd_opts and getattr(getattr(config.cmd_opts, "cmd", (None,))[0], "__name__", "") == "stamp":
    raise RuntimeError("Blind stamping is disabled; use upgrade so existing schemas are validated.")
path = config.attributes.get("database_path")
if path is None:
    url = make_url(config.get_main_option("sqlalchemy.url"))
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("Only file-backed SQLite databases are supported.")
    path = Path(url.database).resolve()
else:
    path = Path(path).resolve()
if not path.exists():
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(path))
configure_sqlite_engine(engine, immediate=True)
try:
    with engine.connect() as connection:
        # Acquire a write reservation before backup, preventing writes between
        # the snapshot and migration. No DDL is executed until backup succeeds.
        connection.begin()
        current = MigrationContext.configure(connection).get_current_revision()
        if current in (None, "0001_legacy"):
            validate_legacy(connection)
        head = ScriptDirectory.from_config(config).get_current_head()
        if current != head:
            config.attributes["backup_path"] = backup_database(path)
            os.chmod(path, 0o600)
        context.configure(connection=connection, target_metadata=Base.metadata, transactional_ddl=True, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("Foreign-key validation failed; migration rolled back.")
        connection.commit()
finally:
    engine.dispose()
