# Railway Multi-Target Recognition

铁路多目标识别与人工复核系统骨架，包含 FastAPI 后端、React 前端、上传识别流程、JSON/YOLO/COCO 导出接口。

## 后端启动

```bash
cd backend
uv sync --dev
DATA_DIR=./data INFERENCE_BACKEND=mock uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

真实 YOLO 推理时安装可选依赖，并设置模型路径：

```bash
cd backend
uv pip install -r requirements-gpu.txt
INFERENCE_BACKEND=ultralytics MODEL_PATH=/path/to/best.pt DEVICE=0 uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

默认访问 `http://localhost:5173`，后端为 `http://localhost:8000`。

## 冒烟测试

```bash
cd backend
uv run pytest
```

测试覆盖：健康检查、图片上传、创建识别任务、读取标注、人工编辑保存、JSON/YOLO 导出。

## API 概览

```text
GET  /health
POST /api/assets/upload
GET  /api/assets
GET  /api/assets/{asset_id}
POST /api/tasks/detect
GET  /api/tasks
GET  /api/tasks/{task_id}
GET  /api/assets/{asset_id}/annotations
PUT  /api/assets/{asset_id}/annotations
GET  /api/assets/{asset_id}/export?format=json|coco|yolo
```
