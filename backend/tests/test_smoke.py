import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.core.dependencies import get_store
from app.main import create_app
from app.api.ai import _result_from_analysis


def test_upload_detect_edit_and_export(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
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
    assert annotations["frames"][0]["image_url"] == f"/api/assets/{asset['id']}/frames/0/image"

    frame_response = client.get(annotations["frames"][0]["image_url"])
    assert frame_response.status_code == 200
    assert frame_response.headers["content-type"] == "image/jpeg"

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

    review_response = client.post(
        f"/api/assets/{asset['id']}/annotations/review",
        json={"status": "approved"},
    )
    assert review_response.status_code == 200
    reviewed = review_response.json()
    assert reviewed["review_status"] == "approved"
    assert reviewed["frames"][0]["review_status"] == "approved"


def test_video_upload_extracts_frames_and_detects(monkeypatch, tmp_path):
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")
    monkeypatch.setenv("RUN_TASKS_INLINE", "true")
    get_settings.cache_clear()
    get_store.cache_clear()

    video_path = tmp_path / "rail.mp4"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5,
        (160, 90),
    )
    for value in (40, 90, 140):
        writer.write(np.full((90, 160, 3), value, dtype=np.uint8))
    writer.release()

    client = TestClient(create_app())
    upload = client.post(
        "/api/assets/upload",
        files={"file": ("rail.mp4", video_path.read_bytes(), "video/mp4")},
    )
    assert upload.status_code == 200
    asset = upload.json()
    assert asset["type"] == "video"
    assert asset["frame_count"] == 3

    task_response = client.post(
        "/api/tasks/detect",
        json={"asset_id": asset["id"], "confidence": 0.25, "iou": 0.7, "frame_stride": 1},
    )
    assert task_response.status_code == 202
    assert task_response.json()["status"] == "completed"

    annotations_response = client.get(f"/api/assets/{asset['id']}/annotations")
    assert annotations_response.status_code == 200
    annotations = annotations_response.json()
    assert [frame["frame_index"] for frame in annotations["frames"]] == [0, 1, 2]
    assert all(frame["objects"] for frame in annotations["frames"])
    assert client.get(annotations["frames"][1]["image_url"]).status_code == 200


def test_database_queue_claims_queued_task(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'queue.db'}")
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")
    monkeypatch.setenv("RUN_TASKS_INLINE", "false")
    monkeypatch.setenv("TASK_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    get_store.cache_clear()

    image = Image.new("RGB", (160, 90), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    client = TestClient(create_app())
    upload = client.post(
        "/api/assets/upload",
        files={"file": ("queued.png", buffer.getvalue(), "image/png")},
    )
    asset = upload.json()
    response = client.post("/api/tasks/detect", json={"asset_id": asset["id"]})
    assert response.status_code == 202
    assert response.json()["status"] == "queued"

    claimed = get_store().claim_next_task()
    assert claimed is not None
    assert claimed.id == response.json()["id"]
    assert claimed.status == "running"


def test_label_config_crud_uses_zero_based_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'labels.db'}")
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")
    monkeypatch.setenv("RUN_TASKS_INLINE", "true")
    get_settings.cache_clear()
    get_store.cache_clear()

    client = TestClient(create_app())

    created = client.post(
        "/api/labels",
        json={"englishName": "person", "chineseName": "行人", "description": "可见人体目标"},
    )
    assert created.status_code == 200
    assert created.json()["data"]["labelId"] == 0

    copied = client.post("/api/labels/0/copy")
    assert copied.status_code == 200
    assert copied.json()["data"]["labelId"] == 1
    assert copied.json()["data"]["englishName"] == "person"
    assert copied.json()["data"]["chineseName"] == "行人"

    updated = client.put(
        "/api/labels/1",
        json={"englishName": "worker", "chineseName": "工作人员", "description": "现场作业人员"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["description"] == "现场作业人员"

    listed = client.get("/api/labels")
    assert listed.status_code == 200
    assert [label["labelId"] for label in listed.json()["data"]] == [0, 1]

    deleted = client.delete("/api/labels/0")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True


def test_real_vision_result_keeps_general_model_labels():
    result = _result_from_analysis(
        "detection",
        {
            "objects": [
                {
                    "label": "person",
                    "confidence": 0.91,
                    "bbox": {"x": 10, "y": 20, "width": 30, "height": 40},
                },
                {
                    "label": "car",
                    "confidence": 0.82,
                    "bbox": {"x": 50, "y": 60, "width": 70, "height": 80},
                },
            ]
        },
    )

    assert [box["label"] for box in result["boxes"]] == ["person", "car"]
    assert all(box["label"] != "railway_target" for box in result["boxes"])
