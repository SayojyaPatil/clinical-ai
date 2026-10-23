"""Safe SQLite migration entry point. No application secrets or AI imports."""
import argparse
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[1]
HEAD = "0003_integrity_guards"
_migration_lock = threading.Lock()
LEGACY_COLUMNS = {
    "notes": {"id", "patient_id", "note_text", "diagnoses", "medications", "follow_ups", "urgency", "confidence", "warning", "created_at"},
    "users": {"id", "username", "hashed_password", "created_at"},
}


def validate_legacy(connection):
    schema = inspect(connection)
    tables = set(schema.get_table_names()) - {"alembic_version"}
    if not tables:
        return
    if tables != {"notes", "users"}:
        raise RuntimeError("Unrecognized unversioned database; refusing automatic adoption.")
    for table, required in LEGACY_COLUMNS.items():
        columns = {c["name"]: c for c in schema.get_columns(table)}
        allowed = required | ({"owner_username"} if table == "notes" else set())
        if not required <= columns.keys() or columns.keys() - allowed:
            raise RuntimeError(f"Unrecognized {table} schema; migration requires manual review.")
        if schema.get_pk_constraint(table)["constrained_columns"] != ["id"]:
            raise RuntimeError(f"Invalid {table} primary key; refusing adoption.")
        for name, column in columns.items():
            expected = "FLOAT" if name == "confidence" else "DATETIME" if name == "created_at" else "VARCHAR" if name in {"id", "patient_id", "username", "owner_username", "hashed_password", "urgency", "warning"} else "TEXT"
            if column["type"].__class__.__name__ != expected:
                raise RuntimeError(f"Unexpected type for {table}.{name}; refusing adoption.")
        required_nonnull = {"id", "patient_id", "note_text"} if table == "notes" else {"id", "username", "hashed_password"}
        if any(columns[name]["nullable"] for name in required_nonnull):
            raise RuntimeError(f"Unexpected nullable columns in {table}; refusing adoption.")
    unique = schema.get_unique_constraints("users") + schema.get_indexes("users")
    if not any(item.get("column_names") == ["username"] and item.get("unique", True) for item in unique):
        raise RuntimeError("Missing unique username constraint; refusing adoption.")


def backup_database(path, directory=None):
    """SQLite's backup API includes committed WAL data; never overwrite a backup."""
    path = Path(path).resolve()
    directory = Path(directory) if directory else path.parent / "backups"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    name = f"{path.stem}.pre-migration.{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.sqlite3"
    target = directory / name
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
        if dest.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("Backup integrity check failed; migration aborted.")
    return target


def upgrade_database(path=ROOT / "clinical_notes.db"):
    path = Path(path).resolve()
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = path
    # Alembic uses process-global operation proxies; serialize callers in this
    # process as well as the cross-process SQLite write reservation in env.py.
    with _migration_lock:
        command.upgrade(config, "head")
    return config.attributes.get("backup_path")


def ensure_database_ready(path):
    """Only empty databases initialize automatically; existing data needs a CLI upgrade."""
    path = Path(path).resolve()
    if not path.exists() or path.stat().st_size == 0:
        upgrade_database(path)
        return
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables:
            upgrade_database(path)
            return
        current = None
        if "alembic_version" in tables:
            rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
            current = rows[0][0] if len(rows) == 1 else None
    if current != HEAD:
        raise RuntimeError(
            "Database migration required. Run `python -m app.migrate --database "
            f"{path}` before starting the application. The command creates a verified backup."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "clinical_notes.db")
    args = parser.parse_args()
    backup = upgrade_database(args.database)
    print(f"Database at {HEAD}." + (f" Verified backup: {backup}" if backup else " No upgrade needed or database was empty."))
