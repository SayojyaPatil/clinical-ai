"""Read-only, account-scoped access to immutable document sources."""
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import DocumentSource, NoteRecord, ReviewState, get_db
from app.image_validation import ALLOWED_FORMATS
from app.models import SourceResponse
from app.security import get_current_user

router = APIRouter(prefix="/notes", tags=["sources"])
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Vary": "Authorization"}


async def owned_note(db: AsyncSession, note_id: str, username: str) -> NoteRecord:
    record = await db.scalar(select(NoteRecord).where(
        NoteRecord.id == note_id, NoteRecord.owner_username == username,
    ))
    if record is None:
        raise HTTPException(status_code=404, detail="Note not found", headers=PRIVATE_HEADERS)
    return record


@router.get("/{note_id}/source", response_model=SourceResponse)
async def get_source(
    note_id: str, response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    note = await owned_note(db, note_id, current_user)
    # Metadata requests never load the image BLOB.
    source = await db.scalar(select(DocumentSource).options(defer(DocumentSource.content)).where(
        DocumentSource.note_id == note.id,
    ))
    state = await db.get(ReviewState, note.id)
    result = {
        "note_id": note.id, "source_id": source.id if source else None,
        "kind": source.kind if source else "unknown",
        "availability": source.availability if source else "unavailable",
        "provenance": source.provenance if source else None,
        "original_filename": source.original_filename if source else None,
        "mime_type": source.mime_type if source else None,
        "byte_size": source.byte_size if source else None,
        "sha256": source.sha256 if source else None,
        "stored_at": source.stored_at if source else None,
        "original_text": note.note_text if source and source.kind == "text" and source.availability == "available" else None,
        "unavailable_reason": None,
        "ai_result": note.ai_result_json,
        "model_name": note.model_name, "prompt_version": note.prompt_version,
        "extraction_schema_version": note.extraction_schema_version,
        "review_status": state.status if state else None,
    }
    if result["availability"] == "unavailable":
        result["unavailable_reason"] = (
            "Original source unavailable. Historical image uploads were not retained; "
            "no original document is available for this record."
            if source and source.provenance == "legacy_inferred"
            else "Original source metadata is unavailable for this analysis."
        )
    response.headers.update(PRIVATE_HEADERS)
    return result


@router.get("/{note_id}/source/content")
async def get_source_content(
    note_id: str, db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    note = await owned_note(db, note_id, current_user)
    source = await db.scalar(select(DocumentSource).where(DocumentSource.note_id == note.id))
    # Bytes were validated on ingestion. Never guess MIME types, serve text as an
    # image, or substitute a filename marker for a missing historical original.
    if (source is None or source.kind != "image" or source.availability != "available"
            or source.mime_type not in ALLOWED_FORMATS.values() or not source.content
            or len(source.content) != source.byte_size
            or hashlib.sha256(source.content).hexdigest() != source.sha256):
        raise HTTPException(status_code=404, detail="Original image unavailable", headers=PRIVATE_HEADERS)
    return Response(content=source.content, media_type=source.mime_type,
                    headers={**PRIVATE_HEADERS, "Content-Disposition": "inline"})
