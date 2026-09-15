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


# ---- dashboard API (fake camera) -------------------------------------------

from backend import camera as camera_module


class FakeCamera:
    def __init__(self, save_error=None, reachable=True):
        self.statuses, self.saved = [], []
        self.save_error, self.reachable = save_error, reachable

    def install(self, monkeypatch):
        def need():
            if not self.reachable:
                raise camera_module.NOT_FOUND
        monkeypatch.setattr(camera_module, "capture", lambda: (need(), (jpeg(), "7"))[1])
        monkeypatch.setattr(camera_module, "show_status", self.statuses.append)
        monkeypatch.setattr(camera_module, "save_record", self.save)
        monkeypatch.setattr(camera_module, "address", lambda search=False: (need(), "192.168.1.20")[1])
        monkeypatch.setattr(camera_module, "health", lambda: {"rssi": -60, "firmware": "3.3.0", "sd": {"present": True}})
        return self

    def save(self, capture_id, result, thumbnail, client_time):
        if self.save_error:
            raise self.save_error
        self.saved.append((capture_id, result, thumbnail, client_time))
        return "000042"


def stages(response):
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_health_uses_plain_mode_label(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "openai")
    assert client.get("/health").json()["mode_label"] == "Vision model"
    monkeypatch.setenv("ANALYSIS_MODE", "mock")
    assert client.get("/health").json()["mode_label"] == "Demo mode"


def test_inspect_streams_real_stages_and_saves(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "mock")
    fake = FakeCamera().install(monkeypatch)
    events = stages(client.post("/api/inspect"))
    assert [e["stage"] for e in events] == ["capturing", "analyzing", "saving", "done"]
    done = events[-1]
    assert done["record_id"] == "000042" and done["save_error"] is None
    assert done["result"]["meta"]["mode_label"] == "Demo mode"
    capture_id, result, thumbnail, client_time = fake.saved[0]
    assert capture_id == "7" and result["inspected_at"] == client_time
    assert Image.open(io.BytesIO(thumbnail)).size == (320, 240)
    assert fake.statuses[0] == {"state": "analyzing"}
    assert fake.statuses[-1]["state"] == "result" and fake.statuses[-1]["defects"] == 2
    held = client.get(f"/api/captures/{done['capture']}.jpg")
    assert held.status_code == 200 and held.headers["content-type"] == "image/jpeg"


def test_inspect_reports_unreachable_camera(monkeypatch):
    FakeCamera(reachable=False).install(monkeypatch)
    events = stages(client.post("/api/inspect"))
    assert [e["stage"] for e in events] == ["capturing", "error"]
    assert events[-1]["error"]["code"] == "camera_not_found"


def test_result_still_returned_when_saving_fails(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "mock")
    FakeCamera(save_error=camera_module.CameraError("no_sd_card", "No SD card.", 503)).install(monkeypatch)
    done = stages(client.post("/api/inspect"))[-1]
    assert done["stage"] == "done" and done["record_id"] is None
    assert done["save_error"]["code"] == "no_sd_card" and done["result"]["defects"]


def test_record_images_pass_etag_through(monkeypatch):
    calls = []
    def record_file(record_id, name, etag=None):
        calls.append(etag)
        return (304, {"etag": '"abc-000001-t"'}, b"") if etag else (200, {"etag": '"abc-000001-t"'}, b"jpegbytes")
    monkeypatch.setattr(camera_module, "record_file", record_file)
    first = client.get("/api/records/000001/thumb.jpg")
    assert first.status_code == 200 and first.headers["etag"] == '"abc-000001-t"'
    assert first.headers["cache-control"] == "private, no-cache"
    again = client.get("/api/records/000001/thumb.jpg", headers={"If-None-Match": '"abc-000001-t"'})
    assert again.status_code == 304 and calls == [None, '"abc-000001-t"']
    assert client.get("/api/records/000001/secrets.txt").status_code == 404


def test_delete_only_from_this_computer(monkeypatch):
    deleted = []
    monkeypatch.setattr(camera_module, "delete_record", deleted.append)
    assert client.delete("/api/records/000003").json() == {"deleted": True}
    async def from_lan_device(scope, receive, send):
        await main.app({**scope, "client": ("192.168.1.50", 50000)}, receive, send)
    remote = TestClient(from_lan_device)
    assert remote.delete("/api/records/000004").status_code == 403
    assert deleted == ["000003"]
