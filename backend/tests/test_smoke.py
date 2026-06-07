import io

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.core.dependencies import get_store
from app.main import create_app


def test_upload_detect_edit_and_export(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")
    monkeypatch.setenv("RUN_TASKS_INLINE", "true")
    get_settings.cache_clear()
    get_store.cache_clear()

    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    image = Image.new("RGB", (640, 360), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    upload = client.post(
        "/api/assets/upload",
        files={"file": ("rail.png", buffer.getvalue(), "image/png")},
    )
    assert upload.status_code == 200
    asset = upload.json()
    assert asset["type"] == "image"
    assert asset["width"] == 640

    task_response = client.post(
        "/api/tasks/detect",
        json={"asset_id": asset["id"], "confidence": 0.25, "iou": 0.7, "frame_stride": 1},
    )
    assert task_response.status_code == 202
    task = task_response.json()
    assert task["status"] == "completed"

    annotations_response = client.get(f"/api/assets/{asset['id']}/annotations")
    assert annotations_response.status_code == 200
    annotations = annotations_response.json()
    assert annotations["frames"][0]["objects"][0]["label"] == "railway_target"

    annotations["frames"][0]["objects"][0]["label"] = "confirmed_target"
    annotations["frames"][0]["objects"][0]["status"] = "edited"
    save_response = client.put(f"/api/assets/{asset['id']}/annotations", json=annotations)
    assert save_response.status_code == 200
    assert save_response.json()["frames"][0]["objects"][0]["label"] == "confirmed_target"

    export_response = client.get(f"/api/assets/{asset['id']}/export?format=json")
    assert export_response.status_code == 200
    assert export_response.json()["frames"][0]["objects"][0]["label"] == "confirmed_target"

    yolo_response = client.get(f"/api/assets/{asset['id']}/export?format=yolo")
    assert yolo_response.status_code == 200
    assert "confirmed_target" in yolo_response.text
