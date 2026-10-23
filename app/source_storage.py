"""Persist a baseline, source provenance and initial state in one transaction.

Images are BLOBs, never paths or public static files. Original filenames are
untrusted metadata only and must be escaped if displayed by a future endpoint.
"""
import hashlib

from sqlalchemy.ext.asyncio import AsyncSession
from app.database import NoteRecord, DocumentSource, ReviewState


async def persist_note(
    db: AsyncSession, record: NoteRecord, *, image_bytes: bytes | None = None,
    filename: str | None = None, mime_type: str | None = None,
) -> None:
    is_image = image_bytes is not None
    source_bytes = image_bytes if is_image else record.note_text.encode("utf-8")
    try:
        db.add(record)
        await db.flush()
        db.add(DocumentSource(
            note_id=record.id, kind="image" if is_image else "text",
            availability="available", provenance="submitted",
            content=image_bytes, original_filename=filename,
            mime_type=mime_type if is_image else "text/plain",
            byte_size=len(source_bytes), sha256=hashlib.sha256(source_bytes).hexdigest(),
        ))
        db.add(ReviewState(note_id=record.id, status="unreviewed", version=0))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
