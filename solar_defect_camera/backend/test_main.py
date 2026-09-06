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

