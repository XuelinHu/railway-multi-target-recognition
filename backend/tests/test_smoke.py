import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.core.dependencies import get_store
from app.main import create_app
from app.api.ai import _result_from_analysis
from app.models.schemas import VideoCaptionBatch, VideoCaptionFrame, VideoCaptionVideo


def _register_student(client: TestClient, username: str = "student001") -> dict:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "displayName": f"学生 {username}", "password": "railway123"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_upload_detect_edit_and_export(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")
    monkeypatch.setenv("RUN_TASKS_INLINE", "true")
    get_settings.cache_clear()
    get_store.cache_clear()

    client = TestClient(create_app())
    _register_student(client)

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
    _register_student(client)
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
    _register_student(client)
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
    _register_student(client)

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


def test_image_history_defaults_to_all_backend_sessions(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'image_history.db'}")
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")
    monkeypatch.setenv("TASK_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    get_store.cache_clear()

    client = TestClient(create_app())
    _register_student(client)
    image = Image.new("RGB", (160, 90), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    payload = buffer.getvalue()

    for session_id in ("browser-a", "browser-b"):
        response = client.post(
            "/api/images/upload",
            data={"taskType": "detection", "sessionId": session_id},
            files={"file": (f"{session_id}.png", payload, "image/png")},
        )
        assert response.status_code == 200

    all_history = client.get("/api/images/list?taskType=detection&pageSize=200")
    assert all_history.status_code == 200
    assert all_history.json()["data"]["total"] == 2
    assert {item["sessionId"] for item in all_history.json()["data"]["records"]} == {"browser-a", "browser-b"}

    scoped_history = client.get("/api/images/list?taskType=detection&pageSize=200&sessionId=browser-a")
    assert scoped_history.status_code == 200
    assert scoped_history.json()["data"]["total"] == 1
    assert scoped_history.json()["data"]["records"][0]["sessionId"] == "browser-a"


def test_login_session_persists_and_student_images_are_isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")
    monkeypatch.setenv("TASK_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    get_store.cache_clear()

    app = create_app()
    first_client = TestClient(app)
    first_user = _register_student(first_client, "student-a")
    session_cookie = first_client.cookies.get("railway_session")
    assert session_cookie

    image = Image.new("RGB", (160, 90), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    upload = first_client.post(
        "/api/images/upload",
        data={"taskType": "detection", "sessionId": "default"},
        files={"file": ("owned.png", buffer.getvalue(), "image/png")},
    )
    assert upload.status_code == 200

    restored_client = TestClient(app)
    restored_client.cookies.set("railway_session", session_cookie)
    me = restored_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["userId"] == first_user["userId"]

    assert restored_client.post("/api/auth/logout").status_code == 200
    assert first_client.get("/api/images/list").status_code == 401

    second_user = _register_student(first_client, "student-b")
    assert second_user["userId"] != first_user["userId"]
    second_history = first_client.get("/api/images/list?taskType=detection&pageSize=200")
    assert second_history.status_code == 200
    assert second_history.json()["data"]["total"] == 0


def test_student_submission_requires_reviewer_and_approved_result_is_locked(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'review.db'}")
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")
    monkeypatch.setenv("TASK_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    get_store.cache_clear()

    app = create_app()
    admin_client = TestClient(app)
    admin = _register_student(admin_client, "admin-user")
    assert admin["role"] == "admin"

    student_client = TestClient(app)
    student = _register_student(student_client, "student-user")
    assert student["role"] == "student"

    reviewer_client = TestClient(app)
    reviewer = _register_student(reviewer_client, "reviewer-user")
    promoted = admin_client.put(f"/api/auth/users/{reviewer['userId']}/role", json={"role": "reviewer"})
    assert promoted.status_code == 200
    assert promoted.json()["data"]["role"] == "reviewer"

    image = Image.new("RGB", (160, 90), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    uploaded = student_client.post(
        "/api/images/upload",
        data={"taskType": "detection", "sessionId": "default"},
        files={"file": ("review.png", buffer.getvalue(), "image/png")},
    ).json()["data"]
    task = student_client.post(
        "/api/image-tasks/create",
        json={"imageId": uploaded["imageId"], "taskType": "detection", "sessionId": "default"},
    ).json()["data"]
    saved = student_client.post(
        "/api/image-tasks/result/save",
        json={
            "taskId": task["taskId"],
            "imageId": uploaded["imageId"],
            "taskType": "detection",
            "annotationJson": {"shapes": []},
        },
    )
    assert saved.status_code == 200

    submitted = student_client.post(f"/api/image-tasks/result/{task['taskId']}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["data"]["reviewStatus"] == "pending_review"

    reviewer_history = reviewer_client.get("/api/images/list?taskType=detection&pageSize=200")
    assert reviewer_history.status_code == 200
    assert reviewer_history.json()["data"]["total"] == 1
    reviewer_result = reviewer_client.get(
        f"/api/image-tasks/result?imageId={uploaded['imageId']}&taskType=detection&sessionId=default"
    )
    assert reviewer_result.status_code == 200
    assert reviewer_result.json()["data"]["taskId"] == task["taskId"]
    reviewer_edit = reviewer_client.put(
        "/api/image-tasks/annotation",
        json={
            "taskId": task["taskId"],
            "imageId": uploaded["imageId"],
            "taskType": "detection",
            "annotationJson": {"shapes": []},
        },
    )
    assert reviewer_edit.status_code == 403
    assert student_client.post(
        f"/api/image-tasks/result/{task['taskId']}/review",
        json={"status": "approved", "comment": "student cannot review"},
    ).status_code == 403

    approved = admin_client.post(
        f"/api/image-tasks/result/{task['taskId']}/review",
        json={"status": "approved", "comment": "标注符合要求"},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["reviewStatus"] == "approved"
    assert approved.json()["data"]["reviewComment"] == "标注符合要求"

    locked = student_client.post(
        "/api/image-tasks/result/save",
        json={
            "taskId": task["taskId"],
            "imageId": uploaded["imageId"],
            "taskType": "detection",
            "annotationJson": {"shapes": []},
        },
    )
    assert locked.status_code == 409


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


def test_video_caption_results_are_queryable(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'video_captions.db'}")
    monkeypatch.setenv("INFERENCE_BACKEND", "mock")
    monkeypatch.setenv("RUN_TASKS_INLINE", "true")
    get_settings.cache_clear()
    get_store.cache_clear()

    client = TestClient(create_app())
    _register_student(client)
    store = get_store()
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    frame_path = frame_dir / "frame_000000.jpg"
    Image.new("RGB", (120, 80), color="white").save(frame_path, format="JPEG")

    batch = store.create_or_update_video_caption_batch(
        VideoCaptionBatch(
            name="railway-multi-target-recognition",
            source_dir="/videos",
            output_dir=str(frame_dir),
            status="success",
        )
    )
    video = store.create_or_update_video_caption_video(
        VideoCaptionVideo(
            batch_id=batch.batch_id,
            filename="DJI_0001.MP4",
            source_path="/videos/DJI_0001.MP4",
            frame_dir=str(frame_dir),
            status="success",
        )
    )
    frame = store.save_video_caption_frame(
        VideoCaptionFrame(
            batch_id=batch.batch_id,
            video_id=video.video_id,
            frame_index=0,
            timestamp_ms=0,
            image_path=str(frame_path),
            image_url="/api/video-captions/frames/test/image",
            width=120,
            height=80,
            description_text="画面中可见铁路轨道和作业人员",
            status="success",
        )
    )
    store.update_video_caption_batch_counts(batch.batch_id, status="success")

    batches = client.get("/api/video-captions/batches")
    assert batches.status_code == 200
    assert batches.json()["data"][0]["totalVideos"] == 1
    assert batches.json()["data"][0]["totalFrames"] == 1

    videos = client.get(f"/api/video-captions/batches/{batch.batch_id}/videos")
    assert videos.status_code == 200
    assert videos.json()["data"][0]["filename"] == "DJI_0001.MP4"

    frames = client.get(f"/api/video-captions/videos/{video.video_id}/frames?query=人员")
    assert frames.status_code == 200
    assert frames.json()["data"]["records"][0]["frameId"] == frame.frame_id

    image_response = client.get(f"/api/video-captions/frames/{frame.frame_id}/image")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/jpeg"
