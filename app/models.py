from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Literal, Optional


class NoteRequest(BaseModel):
    patient_id: str = Field(min_length=1, description="Patient ID e.g. P-001")
    note_text: str = Field(min_length=20, description="The clinical note text")


class NoteResponse(BaseModel):
    id: str
    patient_id: str
    diagnoses: str
    medications: str
    follow_ups: str
    urgency: str
    confidence: float
    warning: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class AIExtractionSnapshot(BaseModel):
    diagnoses: list[str]
    medications: list[str]
    follow_ups: list[str]
    urgency: Literal["routine", "urgent", "emergent"]
    confidence: float = Field(ge=0, le=1)


class SourceResponse(BaseModel):
    note_id: str
    source_id: Optional[str] = None
    kind: Literal["text", "image", "unknown"]
    availability: Literal["available", "unavailable"]
    provenance: Optional[Literal["submitted", "legacy_inferred"]] = None
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    byte_size: Optional[int] = None
    sha256: Optional[str] = None
    stored_at: Optional[datetime] = None
    original_text: Optional[str] = None
    unavailable_reason: Optional[str] = None
    ai_result: Optional[AIExtractionSnapshot] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    extraction_schema_version: Optional[int] = None
    review_status: Optional[Literal["unreviewed", "draft", "approved"]] = None
