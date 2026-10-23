
import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import Base, get_db
from app.security import create_token
from app.routers import notes


@pytest.fixture
def client(tmp_path, monkeypatch):
    # A separate SQLite database for every test.
    db_path = tmp_path / "test_clinical.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False
    )

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def fake_analyze_note(text):
        return SimpleNamespace(
            diagnoses=["Example condition"],
            medications=["Example medication"],
            follow_ups=["Follow up with clinician"],
            urgency="routine",
            confidence=0.9,
        )

    async def fake_analyze_image(data, content_type):
        return await fake_analyze_note("synthetic image")

    monkeypatch.setattr(notes, "analyze_note", fake_analyze_note)
    monkeypatch.setattr(notes, "analyze_image", fake_analyze_image)

    app.dependency_overrides[get_db] = override_get_db

    # Do not enter TestClient as a context manager here:
    # that would run the application's lifespan and initialize
    # its normal database, which must remain untouched.
    test_client = TestClient(app)

    yield test_client

    test_client.close()
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def headers(username):
    return {
        "Authorization": f"Bearer {create_token(username)}"
    }


def create_note(client, username, patient_id="SYN-001"):
    return client.post(
        "/notes/analyze-text",
        headers=headers(username),
        json={
            "patient_id": patient_id,
            "note_text": (
                "Synthetic clinical note for authorization "
                "testing only. No real patient information."
            ),
        },
    )


def test_owner_can_create_and_retrieve_note(client):
    created = create_note(client, "user_a")
    assert created.status_code == 200, created.text

    note_id = created.json()["id"]

    response = client.get(
        f"/notes/{note_id}",
        headers=headers("user_a"),
    )

    assert response.status_code == 200
    assert response.json()["id"] == note_id


def test_other_user_cannot_retrieve_note(client):
    created = create_note(client, "user_a")
    assert created.status_code == 200, created.text

    note_id = created.json()["id"]

    response = client.get(
        f"/notes/{note_id}",
        headers=headers("user_b"),
    )

    assert response.status_code == 404


def test_users_only_list_their_own_notes(client):
    assert create_note(client, "user_a").status_code == 200
    assert create_note(client, "user_b").status_code == 200

    a = client.get("/notes", headers=headers("user_a"))
    b = client.get("/notes", headers=headers("user_b"))

    assert a.status_code == 200
    assert b.status_code == 200
    assert len(a.json()) == 1
    assert len(b.json()) == 1
    assert a.json()[0]["id"] != b.json()[0]["id"]


def test_unauthenticated_access_is_rejected(client):
    assert client.get("/notes").status_code == 401
    assert client.get("/notes/nonexistent").status_code == 401


def test_patient_filter_does_not_bypass_ownership(client):
    assert create_note(client, "user_a", "SYN-001").status_code == 200
    assert create_note(client, "user_b", "SYN-001").status_code == 200
    assert create_note(client, "user_a", "SYN-002").status_code == 200

    response = client.get(
        "/notes",
        params={"patient_id": "SYN-001"},
        headers=headers("user_a"),
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["patient_id"] == "SYN-001"


def test_image_note_is_owned_by_creator(client):
    response = client.post(
        "/notes/analyze-image",
        params={"patient_id": "SYN-IMAGE"},
        files={
            "file": (
                "synthetic.png",
                b"mocked-image-content",
                "image/png",
            )
        },
        headers=headers("user_a"),
    )

    assert response.status_code == 200, response.text
    note_id = response.json()["id"]

    assert client.get(
        f"/notes/{note_id}",
        headers=headers("user_a"),
    ).status_code == 200

    assert client.get(
        f"/notes/{note_id}",
        headers=headers("user_b"),
    ).status_code == 404
