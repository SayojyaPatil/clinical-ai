"""Prevent replacement writes and enforce review actor ownership.

Separate from the foundation revision so databases already initialized at that
revision can receive the final guards without table reconstruction or row edits.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_integrity_guards"
down_revision = "0002_document_foundation"
branch_labels = depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.execute(sa.text(
        "SELECT count(*) FROM document_sources WHERE availability='available' AND mime_type IS NULL"
    )).scalar_one():
        raise RuntimeError("Source metadata requires manual review; refusing to infer MIME types.")
    op.execute(
        'CREATE TRIGGER "document_sources_available_mime" '
        'BEFORE INSERT ON document_sources '
        "WHEN NEW.availability='available' AND NEW.mime_type IS NULL "
        "BEGIN SELECT RAISE(ABORT, 'Available source requires MIME type'); END"
    )
    for table in ("notes", "document_sources", "note_review_revisions", "note_review_events"):
        duplicate = "id=NEW.id"
        if table == "document_sources":
            duplicate += " OR note_id=NEW.note_id"
        elif table == "note_review_revisions":
            duplicate += " OR (note_id=NEW.note_id AND revision_number=NEW.revision_number)"
        op.execute(
            f'CREATE TRIGGER "{table}_no_replace" BEFORE INSERT ON "{table}" '
            f'WHEN EXISTS (SELECT 1 FROM "{table}" WHERE {duplicate}) '
            f"BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END"
        )
        if table in {"note_review_revisions", "note_review_events"}:
            op.execute(
                f'CREATE TRIGGER "{table}_owner" BEFORE INSERT ON "{table}" '
                'WHEN NOT EXISTS (SELECT 1 FROM notes JOIN users '
                'ON users.username=notes.owner_username '
                'WHERE notes.id=NEW.note_id AND users.id=NEW.actor_user_id) '
                "BEGIN SELECT RAISE(ABORT, 'Review actor must own the note'); END"
            )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a verified backup instead.")
