from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_all_notes , NoteRecord
from app.models import NoteRequest, NoteResponse
from app.agent import analyze_note, analyze_image, ClinicalResult
from app.security import get_current_user

router = APIRouter(prefix="/notes", tags=["notes"])


def get_warning(confidence: float) -> str | None:
    if confidence < 0.5:
        return "Low confidence — please review manually before use"
    if confidence < 0.75:
        return "Moderate confidence — verify key fields with original note"
    return None


@router.post("/analyze-text", response_model=NoteResponse)
async def analyze(
    request: NoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    result: ClinicalResult = await analyze_note(request.note_text)
    warning = get_warning(result.confidence)

    record = NoteRecord(
        patient_id=request.patient_id,
        note_text=request.note_text,
        diagnoses=", ".join(result.diagnoses),
        medications=", ".join(result.medications),
        follow_ups=", ".join(result.follow_ups),
        urgency=result.urgency,
        confidence=result.confidence,
        warning=warning,
    )
    db.add(record)
    await db.commit()
    return record


@router.post("/analyze-image", response_model=NoteResponse)
async def analyze_from_image(
    patient_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    allowed_types = ["image/jpeg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG or WebP images allowed")

    image_bytes = await file.read()
    result: ClinicalResult = await analyze_image(image_bytes, file.content_type)
    warning = get_warning(result.confidence)

    record = NoteRecord(
        patient_id=patient_id,
        note_text=f"[Image upload] {file.filename}",
        diagnoses=", ".join(result.diagnoses),
        medications=", ".join(result.medications),
        follow_ups=", ".join(result.follow_ups),
        urgency=result.urgency,
        confidence=result.confidence,
        warning=warning,
    )
    db.add(record)
    await db.commit()
    return record


@router.get("", response_model=list[NoteResponse])
async def list_notes(
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
    patient_id: str | None = None
):
    records = await get_all_notes(db, patient_id)
    return records


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    record = await db.get(NoteRecord, note_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return record