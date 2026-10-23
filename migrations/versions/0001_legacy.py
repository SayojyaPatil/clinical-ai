"""Create or validate/adopt the existing legacy schema without resetting it."""
from alembic import op
import sqlalchemy as sa

revision = "0001_legacy"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    conn = op.get_bind()
    existing = set(sa.inspect(conn).get_table_names()) - {"alembic_version"}
    if existing:
        # Preflight in env.py has verified the full legacy shape.
        columns = {c["name"] for c in sa.inspect(conn).get_columns("notes")}
        if "owner_username" not in columns:
            op.add_column("notes", sa.Column("owner_username", sa.String(), nullable=True))
        indexes = {i["name"] for i in sa.inspect(conn).get_indexes("notes")}
        if "ix_notes_owner_username" not in indexes:
            op.create_index("ix_notes_owner_username", "notes", ["owner_username"])
        return
    op.create_table(
        "users", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_table(
        "notes", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_username", sa.String(), nullable=True),
        sa.Column("patient_id", sa.String(), nullable=False),
        sa.Column("note_text", sa.Text(), nullable=False),
        sa.Column("diagnoses", sa.Text()), sa.Column("medications", sa.Text()),
        sa.Column("follow_ups", sa.Text()), sa.Column("urgency", sa.String()),
        sa.Column("confidence", sa.Float()), sa.Column("warning", sa.String()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_notes_owner_username", "notes", ["owner_username"])


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a verified backup instead.")
