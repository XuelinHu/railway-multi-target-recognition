# Railway Multi-Target Recognition

<p align="center">
  <img height="20" src="https://img.shields.io/badge/fastapi-%3E%3D0.115.0-009688" />
  <img height="20" src="https://img.shields.io/badge/python-%3E%3D3.11-3776AB" />
  <img height="20" src="https://img.shields.io/badge/react-19.2.0-61DAFB" />
  <img height="20" src="https://img.shields.io/badge/vite-7.2.0-646CFF" />
  <img height="20" src="https://img.shields.io/badge/typescript-5.9.0-3178C6" />
  <img height="20" src="https://img.shields.io/badge/node.js-24-5FA04E" />
  <img height="20" src="https://img.shields.io/badge/ultralytics-optional-111F68" />
  <img height="20" src="https://img.shields.io/badge/docker_compose-configured-2496ED" />
</p>

铁路多目标识别与人工复核系统骨架。系统支持上传图片或视频，自动生成目标检测结果，再通过 Web 页面进行人工检查、编辑和导出，适合作为后续接入 RTX 3090 GPU、YOLO 权重和铁路场景专用数据集的基础工程。

## 功能范围

- 图片、视频资源上传与基础元数据提取。
- FastAPI 任务接口，支持创建识别任务、查询任务状态。
- 可替换推理层，默认 `mock` 后端用于本地冒烟测试。
- 可选 Ultralytics YOLO 推理后端，用于接入真实 GPU 权重。
- 标注结果读取、人工编辑保存。
- JSON、COCO、YOLO 三种格式导出。
- React 前端工作台，提供上传、识别、标注 JSON 编辑和导出入口。

## 技术架构

```text
React + Vite Web
  上传资源、触发识别、查看任务、编辑标注、导出结果
        |
FastAPI Backend
  API 路由、任务编排、文件管理、标注保存、格式导出
        |
Inference Service
  mock 冒烟测试后端 / Ultralytics YOLO 真实推理后端
        |
Local Storage
  data/uploads 保存资源，data/db.json 保存任务和标注
```

当前版本使用本地 JSON 文件作为轻量存储，便于快速跑通闭环。后续可替换为 PostgreSQL、Redis 队列和 MinIO 对象存储。

## 目录结构

```text
backend/
  app/
    api/              FastAPI 路由
    core/             配置与依赖注入
    models/           Pydantic 数据模型
    repositories/     本地 JSON 存储适配
    services/         上传、推理、任务、导出服务
  tests/              后端冒烟测试
frontend/
  src/
    App.tsx           Web 工作台
    api.ts            后端 API 客户端
scripts/
  dev-backend.sh      后端开发启动脚本
  dev-frontend.sh     前端开发启动脚本
  smoke.sh            后端冒烟测试脚本
```

## 快速启动

后端：

```bash
cd backend
uv sync --dev
DATA_DIR=./data INFERENCE_BACKEND=mock uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

默认访问：

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8000
API Docs: http://localhost:8000/docs
```

也可以使用脚本：

```bash
./scripts/dev-backend.sh
./scripts/dev-frontend.sh
```

## 真实 YOLO 推理

默认 `INFERENCE_BACKEND=mock` 会生成稳定的模拟检测框，便于测试上传、任务、标注和导出流程。接入真实模型时安装可选依赖，并设置模型路径：

```bash
cd backend
uv sync --dev
uv pip install -r requirements-gpu.txt
INFERENCE_BACKEND=ultralytics MODEL_PATH=/path/to/best.pt DEVICE=0 uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

参数说明：

```text
INFERENCE_BACKEND=mock|ultralytics
MODEL_PATH=/path/to/best.pt
DEVICE=0
DATA_DIR=./data
RUN_TASKS_INLINE=false
```

RTX 3090 环境下建议先使用 `.pt` 权重跑通推理闭环，再按性能需求导出 ONNX 或 TensorRT engine。

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

## 标注 JSON

系统内部标注结果使用帧级结构，图片默认只有一帧，视频可扩展到多帧和目标跟踪。

```json
{
  "asset_id": "asset_xxx",
  "type": "image",
  "model": "mock",
  "frames": [
    {
      "frame_index": 0,
      "timestamp_ms": 0,
      "width": 640,
      "height": 360,
      "objects": [
        {
          "id": "obj_xxx",
          "label": "railway_target",
          "confidence": 0.88,
          "bbox": {
            "x": 224,
            "y": 100.8,
            "width": 192,
            "height": 151.2
          },
          "track_id": null,
          "source": "auto",
          "status": "auto"
        }
      ]
    }
  ]
}
```

人工复核时可把 `status` 更新为 `confirmed`、`edited` 或 `rejected`。

## Docker Compose

```bash
docker compose up --build
```

Compose 默认启动：

```text
backend  -> http://localhost:8000
frontend -> http://localhost:5173
```

当前 Compose 使用 `mock` 推理后端。真实 GPU 推理建议在宿主机或带 NVIDIA Runtime 的容器中单独配置。

## 测试

```bash
cd backend
uv run pytest
```

或：

```bash
./scripts/smoke.sh
```

冒烟测试覆盖健康检查、图片上传、识别任务、标注读取、人工编辑保存和 YOLO 导出。

## 后续计划

- 增加视频抽帧、帧列表和目标跟踪展示。
- 将本地 JSON 存储替换为 PostgreSQL。
- 引入 Redis + Celery/RQ，避免长视频推理阻塞 API。
- 增加画布式框选、拖拽和类别选择组件。
- 增加数据集版本管理和训练集导出目录。
- 接入 TensorRT FP16 推理加速。
