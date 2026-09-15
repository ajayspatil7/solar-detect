import io

from fastapi.testclient import TestClient
from PIL import Image

from backend import main


client = TestClient(main.app)


def jpeg(width: int = 1600, height: int = 1200) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (74, 90, 104)).save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def test_health_never_exposes_key():
    response = client.get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["service"] == "solar-inspector-backend"
    assert "OPENAI_API_KEY" not in response.text
    assert "sk-" not in response.text


def test_rejects_non_jpeg():
    response = client.post("/analyze", content=b"not an image", headers={"Content-Type": "text/plain"})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_rejects_wrong_resolution():
    response = client.post("/analyze", content=jpeg(640, 480), headers={"Content-Type": "image/jpeg"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_image"


def test_mock_analysis_returns_pixel_boxes(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "mock")
    response = client.post("/analyze", content=jpeg(), headers={"Content-Type": "image/jpeg"})
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "defect_suspected"
    assert body["image_width"] == 1600
    assert body["image_height"] == 1200
    assert len(body["defects"]) == 2
    assert body["defects"][0]["bounding_box"] == {
        "x_min": 904,
        "y_min": 294,
        "x_max": 1264,
        "y_max": 630,
    }
    assert body["meta"]["boxes_are_approximate"] is True


def test_model_box_is_clamped_and_ordered():
    box = main.NormalizedBoundingBox(x_min=1100, y_min=700, x_max=-20, y_max=700)
    assert main.to_pixel_box(box, 1600, 1200) == {
        "x_min": 0,
        "y_min": 840,
        "x_max": 1600,
        "y_max": 841,
    }



# ---- root cause analysis -------------------------------------------------

import json

import pytest


def model_defect(defect_type="burn_mark", cause="bypass_diode_failure",
                 severity="high", confidence="high", cause_confidence="high"):
    return main.ModelDefect(
        defect_type=main.DefectType(defect_type),
        severity=main.Level(severity),
        confidence=main.Level(confidence),
        description="test",
        bounding_box=main.NormalizedBoundingBox(x_min=100, y_min=100, x_max=200, y_max=200),
        probable_cause=main.RootCauseId(cause),
        cause_evidence="Damage confined to one third of the module.",
        cause_confidence=main.Level(cause_confidence),
    )


def test_every_cause_is_offered_to_the_model():
    for cause_id in main.ROOT_CAUSES:
        assert cause_id in main.SYSTEM_INSTRUCTIONS


def test_valid_cause_is_enriched_from_knowledge_base():
    cause = main.root_cause_for(model_defect())
    entry = main.ROOT_CAUSES["bypass_diode_failure"]
    assert cause["id"] == "bypass_diode_failure"
    assert cause["title"] == entry["title"]
    assert cause["action"] == entry["action"]
    assert cause["verify_with"] == entry["verify_with"]
    assert cause["urgency"] == "urgent"
    assert cause["corrected"] is False


def test_cause_inconsistent_with_defect_type_is_corrected():
    # Bird droppings cannot explain a crack; the model must not get away with it.
    cause = main.root_cause_for(model_defect(defect_type="possible_surface_crack",
                                             cause="bird_droppings"))
    assert cause["id"] == "undetermined"
    assert cause["corrected"] is True
    assert cause["confidence"] == "low"


def test_cause_confidence_never_exceeds_defect_confidence():
    cause = main.root_cause_for(model_defect(confidence="low", cause_confidence="high"))
    assert cause["confidence"] == "low"


def test_undetermined_urgency_follows_severity():
    cause = main.root_cause_for(model_defect(defect_type="other_visible_anomaly",
                                             cause="undetermined", severity="medium"))
    assert cause["urgency"] == "medium"


def test_priority_is_the_most_urgent_cause():
    defects = [{"root_cause": {"urgency": "low"}}, {"root_cause": {"urgency": "urgent"}},
               {"root_cause": {"urgency": "medium"}}]
    assert main.inspection_priority(main.InspectionStatus.defect_suspected, defects) == "urgent"
    assert main.inspection_priority(main.InspectionStatus.no_visible_defect, []) == "none"
    assert main.inspection_priority(main.InspectionStatus.retake_required, defects) == "none"


def test_mock_analysis_includes_root_cause_and_priority(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "mock")
    body = client.post("/analyze", content=jpeg(), headers={"Content-Type": "image/jpeg"}).json()
    assert body["priority"] == "medium"
    first = body["defects"][0]["root_cause"]
    assert first["id"] == "encapsulant_browning"
    assert first["verify_with"] and first["action"] and first["explanation"]


@pytest.mark.parametrize("mutation, message", [
    (lambda c: c["dust_accumulation"].__setitem__("applies_to", ["not_a_type"]), "unknown types"),
    (lambda c: c["dust_accumulation"].pop("action"), "missing 'action'"),
    (lambda c: c["dust_accumulation"].__setitem__("urgency", "critical"), "invalid urgency"),
    (lambda c: c.pop("undetermined"), "undetermined"),
])
def test_broken_knowledge_base_fails_at_startup(tmp_path, mutation, message):
    data = json.loads(main.ROOT_CAUSE_FILE.read_text())
    mutation(data["causes"])
    broken = tmp_path / "root_causes.json"
    broken.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=message):
        main.load_root_causes(broken)
