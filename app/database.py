from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import (Column, String, Text, DateTime, Float, Integer, LargeBinary,
                        JSON, ForeignKey, ForeignKeyConstraint, UniqueConstraint,
                        CheckConstraint, select)
from pathlib import Path
import asyncio
from app.db_integrity import configure_sqlite_engine, protect_table, insert_guards
import uuid
from datetime import datetime, timezone

engine = create_async_engine("sqlite+aiosqlite:///./clinical_notes.db")
configure_sqlite_engine(engine)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class NoteRecord(Base):
    __tablename__ = "notes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ai_result_json = Column(JSON(none_as_null=True), nullable=True)
    model_name = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    extraction_schema_version = Column(Integer, nullable=True)
    owner_username = Column(String, nullable=True, index=True)
    patient_id = Column(String, nullable=False)
    note_text = Column(Text, nullable=False)
    diagnoses = Column(Text)
    medications = Column(Text)
    follow_ups = Column(Text)
    urgency = Column(String)
    confidence = Column(Float, default=0.0)
    warning = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UserRecord(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DocumentSource(Base):
    __tablename__ = "document_sources"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id = Column(String, ForeignKey("notes.id", ondelete="RESTRICT"), nullable=False, unique=True)
    kind = Column(String, nullable=False)
    availability = Column(String, nullable=False)
    provenance = Column(String, nullable=False)
    # Text remains in notes.note_text. Only validated image bytes are stored here.
    content = Column(LargeBinary, nullable=True)
    original_filename = Column(Text, nullable=True)
    mime_type = Column(String, nullable=True)
    byte_size = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True)
    stored_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        CheckConstraint("kind IN ('text','image','unknown')", name="source_kind"),
        CheckConstraint("availability IN ('available','unavailable')", name="source_availability"),
        CheckConstraint("provenance IN ('submitted','legacy_inferred')", name="source_provenance"),
        CheckConstraint("byte_size IS NULL OR byte_size >= 0", name="source_size"),
        CheckConstraint("(availability='unavailable' AND content IS NULL AND byte_size IS NULL AND sha256 IS NULL AND mime_type IS NULL) OR (availability='available' AND byte_size IS NOT NULL AND sha256 IS NOT NULL AND length(sha256)=64 AND ((kind='text' AND content IS NULL AND mime_type='text/plain') OR (kind='image' AND content IS NOT NULL AND length(content)=byte_size AND byte_size BETWEEN 1 AND 5242880 AND mime_type IN ('image/png','image/jpeg','image/webp'))))", name="source_content"),
    )


class ReviewRevision(Base):
    __tablename__ = "note_review_revisions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id = Column(String, ForeignKey("notes.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision_number = Column(Integer, nullable=False)
    parent_revision_id = Column(String, nullable=True)
    corrected_json = Column(JSON, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    actor_user_id = Column(String, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        UniqueConstraint("note_id", "id", name="uq_revision_note_id"),
        UniqueConstraint("note_id", "revision_number", name="uq_revision_number"),
        ForeignKeyConstraint(["note_id", "parent_revision_id"], ["note_review_revisions.note_id", "note_review_revisions.id"], ondelete="RESTRICT"),
        CheckConstraint("revision_number > 0 AND schema_version > 0", name="revision_versions"),
        CheckConstraint("json_valid(corrected_json) AND json_type(corrected_json)='object'", name="revision_json_object"),
    )


class ReviewState(Base):
    __tablename__ = "note_review_states"
    note_id = Column(String, ForeignKey("notes.id", ondelete="RESTRICT"), primary_key=True)
    status = Column(String, nullable=False, default="unreviewed")
    version = Column(Integer, nullable=False, default=0)
    current_revision_id = Column(String, nullable=True)
    approved_revision_id = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        ForeignKeyConstraint(["note_id", "current_revision_id"], ["note_review_revisions.note_id", "note_review_revisions.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["note_id", "approved_revision_id"], ["note_review_revisions.note_id", "note_review_revisions.id"], ondelete="RESTRICT"),
        CheckConstraint("version >= 0", name="review_version"),
        CheckConstraint("(status='unreviewed' AND current_revision_id IS NULL AND approved_revision_id IS NULL) OR (status='draft' AND current_revision_id IS NOT NULL) OR (status='approved' AND current_revision_id IS NOT NULL AND approved_revision_id IS NOT NULL AND current_revision_id=approved_revision_id)", name="review_status"),
    )


class ReviewEvent(Base):
    __tablename__ = "note_review_events"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    note_id = Column(String, ForeignKey("notes.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    actor_user_id = Column(String, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        ForeignKeyConstraint(["note_id", "revision_id"], ["note_review_revisions.note_id", "note_review_revisions.id"], ondelete="RESTRICT"),
        CheckConstraint("action IN ('draft_saved','approved')", name="review_action"),
    )


for model in (NoteRecord, DocumentSource, ReviewRevision, ReviewEvent):
    protect_table(model.__table__)
    insert_guards(model.__table__)


async def init_db():
    # Initialize fresh databases, but never migrate existing data on hot reload.
    from app.migrate import ensure_database_ready
    await asyncio.to_thread(ensure_database_ready, Path(engine.url.database))


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def get_all_notes(
    session: AsyncSession,
    owner_username: str,
    patient_id: str | None = None
) -> list[NoteRecord]:

    query = (
        select(NoteRecord)
        .where(NoteRecord.owner_username == owner_username)
        .order_by(NoteRecord.created_at.desc())
    )

    if patient_id:
        query = query.where(NoteRecord.patient_id == patient_id)

    result = await session.execute(query)
    return result.scalars().all()