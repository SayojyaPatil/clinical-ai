
import io

from PIL import Image

from test_note_security import client, headers, valid_png


def upload(client, data, mime="image/png"):
    return client.post(
        "/notes/analyze-image",
        params={"patient_id": "SYN-IMAGE"},
        files={"file": ("sample.png", data, mime)},
        headers=headers("user_a"),
    )


def test_valid_image(client):
    response = upload(client, valid_png())
    assert response.status_code == 200, response.text


def test_invalid_image_content(client):
    response = upload(client, b"not a real image")
    assert response.status_code == 400


def test_oversized_image(client):
    response = upload(client, b"x" * (5 * 1024 * 1024 + 1))
    assert response.status_code == 413


def test_mime_mismatch(client):
    response = upload(client, valid_png(), "image/jpeg")
    assert response.status_code == 400


def test_unsupported_image_type(client):
    response = upload(client, valid_png(), "application/pdf")
    assert response.status_code == 400
