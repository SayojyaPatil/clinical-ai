"""SQLite connection settings and append-only baseline protection."""
from sqlalchemy import DDL, event

IMMUTABLE_TABLES = (
    "notes", "document_sources", "note_review_revisions", "note_review_events",
)


def immutable_sql(table, operation):
    return (
        f'CREATE TRIGGER "{table}_no_{operation.lower()}" '
        f'BEFORE {operation} ON "{table}" BEGIN '
        f"SELECT RAISE(ABORT, '{table} is immutable'); END"
    )


def protect_table(table):
    for operation in ("UPDATE", "DELETE"):
        event.listen(
            table, "after_create",
            DDL(immutable_sql(table.name, operation)).execute_if(dialect="sqlite"),
        )


def configure_sqlite_engine(engine, *, immediate=False):
    """Enforce FKs; migration connections also use explicit transactional DDL."""
    target = getattr(engine, "sync_engine", engine)

    @event.listens_for(target, "connect")
    def connect(dbapi_connection, _):
        # Preserve normal application transaction behavior. Starting explicit
        # read transactions would hold SQLite locks during slow AI requests.
        if immediate:
            dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    if immediate:
        @event.listens_for(target, "begin")
        def begin(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")


def insert_guards(table):
    name = table.name
    duplicate = f"id=NEW.id"
    if name == "document_sources":
        duplicate += " OR note_id=NEW.note_id"
    elif name == "note_review_revisions":
        duplicate += " OR (note_id=NEW.note_id AND revision_number=NEW.revision_number)"
    event.listen(table, "after_create", DDL(
        f'CREATE TRIGGER "{name}_no_replace" BEFORE INSERT ON "{name}" '
        f'WHEN EXISTS (SELECT 1 FROM "{name}" WHERE {duplicate}) '
        f"BEGIN SELECT RAISE(ABORT, '{name} is immutable'); END"
    ).execute_if(dialect="sqlite"))
    if name == "document_sources":
        event.listen(table, "after_create", DDL(
            'CREATE TRIGGER "document_sources_available_mime" '
            'BEFORE INSERT ON document_sources '
            "WHEN NEW.availability='available' AND NEW.mime_type IS NULL "
            "BEGIN SELECT RAISE(ABORT, 'Available source requires MIME type'); END"
        ).execute_if(dialect="sqlite"))
    if name in {"note_review_revisions", "note_review_events"}:
        event.listen(table, "after_create", DDL(
            f'CREATE TRIGGER "{name}_owner" BEFORE INSERT ON "{name}" '
            'WHEN NOT EXISTS (SELECT 1 FROM notes JOIN users '
            'ON users.username=notes.owner_username '
            'WHERE notes.id=NEW.note_id AND users.id=NEW.actor_user_id) '
            "BEGIN SELECT RAISE(ABORT, 'Review actor must own the note'); END"
        ).execute_if(dialect="sqlite"))
