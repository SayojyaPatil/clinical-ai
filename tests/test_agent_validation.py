
import pytest
from pydantic import ValidationError

from app.agent import ClinicalResult


def valid_result():
    return {
        "diagnoses": ["Example diagnosis"],
        "medications": ["Example medication"],
        "follow_ups": ["Follow up with clinician"],
        "urgency": "routine",
        "confidence": 0.85,
    }


def test_valid_clinical_result():
    result = ClinicalResult(**valid_result())
    assert result.urgency == "routine"
    assert result.confidence == 0.85


@pytest.mark.parametrize(
    "urgency",
    ["critical", "unknown", ""],
)
def test_invalid_urgency(urgency):
    data = valid_result()
    data["urgency"] = urgency

    with pytest.raises(ValidationError):
        ClinicalResult(**data)


@pytest.mark.parametrize(
    "confidence",
    [-0.1, 1.5],
)
def test_invalid_confidence(confidence):
    data = valid_result()
    data["confidence"] = confidence

    with pytest.raises(ValidationError):
        ClinicalResult(**data)


def test_missing_required_field():
    data = valid_result()
    del data["diagnoses"]

    with pytest.raises(ValidationError):
        ClinicalResult(**data)


def test_extra_field_rejected():
    data = valid_result()
    data["unverified_advice"] = "Example"

    with pytest.raises(ValidationError):
        ClinicalResult(**data)
