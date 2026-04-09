from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Text, DateTime, Float, select
import uuid
from datetime import datetime, timezone

engine = create_async_engine("sqlite+aiosqlite:///./clinical_notes.db")
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class NoteRecord(Base):
    __tablename__ = "notes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
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


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def get_all_notes(session: AsyncSession, patient_id: str | None = None) -> list[NoteRecord]:
    query = select(NoteRecord).order_by(NoteRecord.created_at.desc())
    
    if patient_id:
        query = query.where(NoteRecord.patient_id == patient_id)
    
    result = await session.execute(query)
    return result.scalars().all()