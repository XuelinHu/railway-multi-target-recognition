# Railway Multi-Target Recognition

<p align="center">
  <img height="20" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&amp;logoColor=white" />
  <img height="20" src="https://img.shields.io/badge/fastapi-0.115%2B-009688?logo=fastapi&amp;logoColor=white" />
  <img height="20" src="https://img.shields.io/badge/vue-3.5%2B-42B883?logo=vuedotjs&amp;logoColor=white" />
  <img height="20" src="https://img.shields.io/badge/vite-7.2-646CFF?logo=vite&amp;logoColor=white" />
  <img height="20" src="https://img.shields.io/badge/typescript-5.9-3178C6?logo=typescript&amp;logoColor=white" />
  <img height="20" src="https://img.shields.io/badge/postgresql-16-4169E1?logo=postgresql&amp;logoColor=white" />
  <img height="20" src="https://img.shields.io/badge/tensorrt-optional-76B900?logo=nvidia&amp;logoColor=white" />
  <img height="20" src="https://img.shields.io/badge/docker_compose-configured-2496ED?logo=docker&amp;logoColor=white" />
</p>

铁路多目标识别与人工复核系统骨架。系统支持上传图片或视频，先抽取图片帧或视频逐帧图像，调用通用目标检测模型自动标注，保存标注结果与帧图片，再通过 Vue Web 页面进行人工校验、编辑和导出，适合作为后续接入 RTX 3090 GPU、YOLO 权重和铁路场景专用数据集的基础工程。

## 功能范围

- 图片、视频资源上传与基础元数据提取。
- 图片统一保存为第 0 帧，视频按 `frame_stride` 逐帧抽取并保存帧图。
- FastAPI 任务接口，支持创建识别任务、查询任务状态。
- 可替换推理层，默认 `mock` 后端用于本地冒烟测试。
- 可选 Ultralytics YOLO 推理后端，用于接入真实 GPU 权重。
- PostgreSQL 持久化资产、任务、标注和人工校验状态。
- PostgreSQL 任务表作为推理队列，使用行锁领取任务，不依赖 Redis。
- 人工校验支持通过、驳回、目标级确认、编辑和剔除。
- 检测框支持新增、拖动和四角缩放。
- JSON、COCO、YOLO 三种格式导出。
- Vue 前端工作台，提供上传、逐帧预览、检测框叠加、人工校验和导出入口。

## 技术架构

```text
Vue + Vite Web
  上传资源、触发逐帧标注、查看任务、预览帧图、人工校验、导出结果
        |
FastAPI Backend
  API 路由、文件管理、标注保存、格式导出
        |
PostgreSQL
  资产/标注存储 + queued 任务表 + SKIP LOCKED worker
        |
Inference Service
  抽帧 -> mock / Ultralytics YOLO / TensorRT engine -> 帧级标注
        |
Local Storage
  data/uploads 保存原始资源和帧图
```

当前版本使用 PostgreSQL 同时承担业务存储和任务队列。FastAPI 启动后会自动创建数据表，并启动数据库任务 worker。

## 目录结构

```text
backend/
  app/
    api/              FastAPI 路由
    core/             配置与依赖注入
    models/           Pydantic 数据模型
    repositories/     PostgreSQL 存储与任务领取
    services/         上传、推理、数据库任务 worker、导出服务
  tests/              后端冒烟测试
frontend/
  src/
    App.vue           Vue Web 工作台
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
cp .env.example .env
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

默认访问：

```text
Frontend: http://localhost:4004
Backend:  http://localhost:8000
API Docs: http://localhost:8000/docs
```

FRP 映射时保持内网端口不变：

按 `frp` skill 的端口范围，前端使用本机 `4000-4010`，后端使用本机 `8000-8010`。例如本项目使用本地前端 `4004`、本地后端 `8000`：

```bash
VITE_API_BASE_URL=http://47.120.48.245:18000 npm run dev -- --host 0.0.0.0 --port 4004
```

对应外网地址：

```text
Frontend: http://47.120.48.245:14004
Backend:  http://47.120.48.245:18000
```

后端跨域放行前端地址：

```bash
CORS_ORIGINS=http://localhost:4004,http://127.0.0.1:4004,http://47.120.48.245:14004
```

也可以使用脚本：

```bash
./scripts/dev-backend.sh
./scripts/dev-frontend.sh
```

## PostgreSQL

创建数据库：

```sql
CREATE DATABASE railway_recognition;
```

本地 `.env` 配置：

```text
DATABASE_URL=postgresql+psycopg://deipss:<PASSWORD>@127.0.0.1:5432/railway_recognition
TASK_WORKER_ENABLED=true
TASK_POLL_INTERVAL_SECONDS=1
```

密码只写入未提交的 `backend/.env`，不要写入源码或 README。

任务创建后先以 `queued` 状态写入 `detect_tasks`。后台 worker 使用 `FOR UPDATE SKIP LOCKED` 原子领取任务，执行完成后更新为 `completed` 或 `failed`。

## YOLO 与 TensorRT

默认 `INFERENCE_BACKEND=mock` 会生成稳定的模拟检测框，便于测试上传、任务、标注和导出流程。接入真实模型时安装可选依赖，并设置模型路径：

```bash
cd backend
uv sync --dev
uv pip install -r requirements-gpu.txt
INFERENCE_BACKEND=ultralytics MODEL_PATH=/path/to/best.pt DEVICE=0 uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

参数说明：

```text
INFERENCE_BACKEND=mock|ultralytics|tensorrt
MODEL_PATH=/path/to/best.pt
DEVICE=0
DATA_DIR=./data
RUN_TASKS_INLINE=false
```

识别任务支持 `frame_stride` 和 `max_frames` 参数。`frame_stride=1` 表示视频逐帧处理，`max_frames` 留空表示处理全部抽取帧。

导出 TensorRT FP16 engine：

```bash
cd backend
uv pip install -r requirements-gpu.txt
uv run python scripts/export_tensorrt.py /path/to/best.pt --device 0 --imgsz 640
```

加载 TensorRT engine：

```bash
INFERENCE_BACKEND=tensorrt MODEL_PATH=/path/to/best.engine DEVICE=0 \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

TensorRT engine 与构建机器的 GPU、CUDA 和 TensorRT 版本相关，建议直接在 RTX 3090 运行环境中生成。

## 人工框选

- 点击“选择”后拖动检测框可调整位置。
- 选中检测框后拖动四角手柄可缩放。
- 点击“新增框”后在图像上拖动可创建人工检测框。
- 新增或修改的目标会标记为 `edited`，点击“保存”写入 PostgreSQL。

## API 概览

```text
GET  /health
POST /api/assets/upload
GET  /api/assets
GET  /api/assets/{asset_id}
POST /api/tasks/detect
GET  /api/tasks
GET  /api/tasks/{task_id}
GET  /api/assets/{asset_id}/frames/{frame_index}/image
GET  /api/assets/{asset_id}/annotations
PUT  /api/assets/{asset_id}/annotations
POST /api/assets/{asset_id}/annotations/review
GET  /api/assets/{asset_id}/export?format=json|coco|yolo
```

## 标注 JSON

系统内部标注结果使用帧级结构，图片默认只有一帧，视频可扩展到多帧和目标跟踪。

```json
{
  "asset_id": "asset_xxx",
  "type": "image",
  "model": "mock",
  "review_status": "pending_review",
  "frames": [
    {
      "frame_index": 0,
      "timestamp_ms": 0,
      "width": 640,
      "height": 360,
      "image_url": "/api/assets/asset_xxx/frames/0/image",
      "review_status": "pending_review",
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

人工复核时可把目标级 `status` 更新为 `confirmed`、`edited` 或 `rejected`，也可调用 `/annotations/review` 更新整份标注的 `review_status`。

## Docker Compose

```bash
docker compose up --build
```

Compose 默认启动：

```text
backend  -> http://localhost:8000
frontend -> http://localhost:4004
```

启动 Compose 前需在根目录环境中提供 `DATABASE_URL`。当前 Compose 使用 `mock` 推理后端；真实 TensorRT 推理建议在带 NVIDIA Container Runtime 的容器或宿主机中运行。

## 测试

```bash
cd backend
uv run pytest
```

或：

```bash
./scripts/smoke.sh
```

冒烟测试覆盖健康检查、图片上传、图片帧访问、视频逐帧抽取、识别任务、标注读取、人工编辑保存、人工校验和 YOLO 导出。

## 后续计划

- 增加数据集版本管理和训练集导出目录。
- 增加任务失败重试、超时回收和 worker 监控。
- 增加 TensorRT 性能基准测试。
