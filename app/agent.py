import os
import base64
import json
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from openai import AsyncOpenAI

load_dotenv()


class ClinicalResult(BaseModel):
    diagnoses: list[str] = Field(description="List of diagnoses found")
    medications: list[str] = Field(description="List of medications mentioned")
    follow_ups: list[str] = Field(description="List of follow-up actions")
    urgency: str = Field(description="routine, urgent, or emergent")
    confidence: float = Field(
        description="How confident you are in this extraction, 0.0 to 1.0. "
                    "Low if note is vague, incomplete, or hard to read. "
                    "High if note is clear and detailed."
    )


agent = Agent(
    model=OpenAIChatModel("gpt-4o"),
    output_type=ClinicalResult,
    system_prompt="""
    You are a medical assistant specializing in clinical documentation.

    When given a doctor's note:
    - Extract ALL diagnoses and symptoms mentioned
    - Extract ALL medications with dose and frequency if mentioned
    - Extract ALL follow-up actions or appointments
    - Classify urgency as:
        - routine: stable patient, scheduled follow-up
        - urgent: needs attention within 24-48 hours
        - emergent: immediate intervention required
    - Rate your confidence 0.0 to 1.0:
        - Low if note is vague, incomplete, or hard to read
        - High if note is clear and detailed

    Be concise and accurate. Never invent information not present in the note.
    """,
)


async def analyze_note(note_text: str) -> ClinicalResult:
    result = await agent.run(note_text)
    return result.output


async def analyze_image(image_bytes: bytes, image_type: str) -> ClinicalResult:
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    client = AsyncOpenAI()

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_type};base64,{base64_image}"
                        }
                    },
                    {
                        "type": "text",
                        "text": """
                        You are a medical assistant specializing in reading handwritten doctor notes.
                        The handwriting may be messy or unclear — do your best to interpret it.

                        Extract and return a JSON object with exactly these fields:
                        - diagnoses: list of strings
                        - medications: list of strings (include dose and frequency if visible)
                        - follow_ups: list of strings
                        - urgency: one of routine, urgent, or emergent
                        - confidence: float between 0.0 and 1.0

                        If something is unreadable, skip it — never guess critical medical information.
                        Return only valid JSON, nothing else.
                        """
                    }
                ]
            }
        ]
    )

    raw = response.choices[0].message.content
    raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
    data = json.loads(raw)
    return ClinicalResult(**data)