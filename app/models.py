from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


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

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str