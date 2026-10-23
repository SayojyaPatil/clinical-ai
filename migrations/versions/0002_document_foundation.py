"""Persist source provenance, structured AI results, and review foundations."""
from alembic import op
import sqlalchemy as sa
import hashlib
import uuid
from datetime import datetime, timezone

revision = "0002_document_foundation"
down_revision = "0001_legacy"
branch_labels = depends_on = None


def upgrade():
    op.create_table('document_sources',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('note_id', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('availability', sa.String(), nullable=False),
    sa.Column('provenance', sa.String(), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=True),
    sa.Column('original_filename', sa.Text(), nullable=True),
    sa.Column('mime_type', sa.String(), nullable=True),
    sa.Column('byte_size', sa.Integer(), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('stored_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("(availability='unavailable' AND content IS NULL AND byte_size IS NULL AND sha256 IS NULL AND mime_type IS NULL) OR (availability='available' AND byte_size IS NOT NULL AND sha256 IS NOT NULL AND length(sha256)=64 AND ((kind='text' AND content IS NULL AND mime_type='text/plain') OR (kind='image' AND content IS NOT NULL AND length(content)=byte_size AND byte_size BETWEEN 1 AND 5242880 AND mime_type IN ('image/png','image/jpeg','image/webp'))))", name='source_content'),
    sa.CheckConstraint("availability IN ('available','unavailable')", name='source_availability'),
    sa.CheckConstraint("kind IN ('text','image','unknown')", name='source_kind'),
    sa.CheckConstraint("provenance IN ('submitted','legacy_inferred')", name='source_provenance'),
    sa.CheckConstraint('byte_size IS NULL OR byte_size >= 0', name='source_size'),
    sa.ForeignKeyConstraint(['note_id'], ['notes.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('note_id')
    )
    op.create_table('note_review_revisions',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('note_id', sa.String(), nullable=False),
    sa.Column('revision_number', sa.Integer(), nullable=False),
    sa.Column('parent_revision_id', sa.String(), nullable=True),
    sa.Column('corrected_json', sa.JSON(), nullable=False),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.Column('actor_user_id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("json_valid(corrected_json) AND json_type(corrected_json)='object'", name='revision_json_object'),
    sa.CheckConstraint('revision_number > 0 AND schema_version > 0', name='revision_versions'),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['note_id', 'parent_revision_id'], ['note_review_revisions.note_id', 'note_review_revisions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['note_id'], ['notes.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('note_id', 'id', name='uq_revision_note_id'),
    sa.UniqueConstraint('note_id', 'revision_number', name='uq_revision_number')
    )
    op.create_index(op.f('ix_note_review_revisions_note_id'), 'note_review_revisions', ['note_id'], unique=False)
    op.create_table('note_review_events',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('note_id', sa.String(), nullable=False),
    sa.Column('revision_id', sa.String(), nullable=False),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('actor_user_id', sa.String(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("action IN ('draft_saved','approved')", name='review_action'),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['note_id', 'revision_id'], ['note_review_revisions.note_id', 'note_review_revisions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['note_id'], ['notes.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_note_review_events_note_id'), 'note_review_events', ['note_id'], unique=False)
    op.create_table('note_review_states',
    sa.Column('note_id', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('current_revision_id', sa.String(), nullable=True),
    sa.Column('approved_revision_id', sa.String(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("(status='unreviewed' AND current_revision_id IS NULL AND approved_revision_id IS NULL) OR (status='draft' AND current_revision_id IS NOT NULL) OR (status='approved' AND current_revision_id IS NOT NULL AND approved_revision_id IS NOT NULL AND current_revision_id=approved_revision_id)", name='review_status'),
    sa.CheckConstraint('version >= 0', name='review_version'),
    sa.ForeignKeyConstraint(['note_id', 'approved_revision_id'], ['note_review_revisions.note_id', 'note_review_revisions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['note_id', 'current_revision_id'], ['note_review_revisions.note_id', 'note_review_revisions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['note_id'], ['notes.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('note_id')
    )
    op.add_column('notes', sa.Column('ai_result_json', sa.JSON(none_as_null=True), nullable=True))
    op.add_column('notes', sa.Column('model_name', sa.String(), nullable=True))
    op.add_column('notes', sa.Column('prompt_version', sa.String(), nullable=True))
    op.add_column('notes', sa.Column('extraction_schema_version', sa.Integer(), nullable=True))
    connection = op.get_bind()
    # Stream only required source columns. Never parse flattened historical AI
    # strings into fabricated arrays or assign ownership to ownerless notes.
    rows = connection.execute(sa.text("SELECT id, note_text FROM notes"))
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    for row in rows:
        ambiguous = row.note_text.startswith("[Image upload]")
        encoded = row.note_text.encode("utf-8")
        connection.execute(sa.text(
            "INSERT INTO document_sources "
            "(id,note_id,kind,availability,provenance,mime_type,byte_size,sha256,stored_at) "
            "VALUES (:id,:note_id,:kind,:availability,'legacy_inferred',:mime,:size,:sha,:now)"
        ), {"id":str(uuid.uuid4()),"note_id":row.id,
            "kind":"unknown" if ambiguous else "text",
            "availability":"unavailable" if ambiguous else "available",
            "mime":None if ambiguous else "text/plain",
            "size":None if ambiguous else len(encoded),
            "sha":None if ambiguous else hashlib.sha256(encoded).hexdigest(),"now":now})
        connection.execute(sa.text(
            "INSERT INTO note_review_states (note_id,status,version,updated_at) "
            "VALUES (:id,'unreviewed',0,:now)"
        ), {"id":row.id,"now":now})
    # Frozen trigger definitions. Existing baseline values and all human
    # snapshots/audit events are append-only; only review state is mutable.
    for table in ("notes", "document_sources", "note_review_revisions", "note_review_events"):
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f'CREATE TRIGGER "{table}_no_{operation.lower()}" '
                f'BEFORE {operation} ON "{table}" BEGIN '
                f"SELECT RAISE(ABORT, '{table} is immutable'); END"
            )



def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a verified backup instead.")
