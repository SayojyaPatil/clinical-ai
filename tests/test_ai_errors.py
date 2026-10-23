
from fastapi.testclient import TestClient

from app.routers import notes
from test_note_security import client, headers, valid_png


def test_text_ai_failure_returns_502(client, monkeypatch):
    async def failing_analyze(text):
        raise ValueError("Simulated invalid AI response")

    monkeypatch.setattr(notes, "analyze_note", failing_analyze)

    response = client.post(
        "/notes/analyze-text",
        headers=headers("user_a"),
        json={
            "patient_id": "SYN-001",
            "note_text": "Synthetic clinical note for offline testing only.",
        },
    )

    assert response.status_code == 502
    assert "Simulated" not in response.text

    notes_response = client.get(
        "/notes", headers=headers("user_a")
    )
    assert notes_response.status_code == 200
    assert notes_response.json() == []


def test_image_ai_failure_returns_502(client, monkeypatch):
    async def failing_analyze(data, mime):
        raise ValueError("Simulated image parsing failure")

    monkeypatch.setattr(notes, "analyze_image", failing_analyze)

    response = client.post(
        "/notes/analyze-image",
        params={"patient_id": "SYN-IMAGE"},
        files={
            "file": ("sample.png", valid_png(), "image/png")
        },
        headers=headers("user_a"),
    )

    assert response.status_code == 502
    assert "Simulated" not in response.text

    notes_response = client.get(
        "/notes", headers=headers("user_a")
    )
    assert notes_response.status_code == 200
    assert notes_response.json() == []