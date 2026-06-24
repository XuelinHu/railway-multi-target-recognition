<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import {
  Boxes,
  ChevronLeft,
  ChevronRight,
  Download,
  Image as ImageIcon,
  Loader2,
  Maximize2,
  RefreshCw,
  RotateCcw,
  Save,
  Sparkles,
  Upload,
  ZoomIn,
} from "@lucide/vue";
import {
  type ImageAsset,
  type ImageTaskResult,
  type ImageTaskResultVersion,
  type ImageTaskStatus,
  type ImageTaskType,
  assetUrl,
  createImageTask,
  getTaskResult,
  getTaskResultVersion,
  inferImageTask,
  listTaskResultVersions,
  listImages,
  restoreTaskResultVersion,
  saveTaskResult,
  updateAnnotation,
  uploadImage,
} from "./api";

type TaskConfig = {
  type: ImageTaskType;
  title: string;
  description: string;
  models: string[];
};

type TaskState = {
  currentImageId: string | null;
  imageUrl: string;
  imageInfo: ImageAsset | null;
  taskId: string | null;
  resultImageUrl: string;
  resultJson: Record<string, unknown> | null;
  annotationJson: Record<string, unknown> | null;
  descriptionText: string;
  status: ImageTaskStatus;
  versions: ImageTaskResultVersion[];
  activeVersionId: string | null;
  latestVersionNo: number | null;
  isViewingHistory: boolean;
};

const taskConfigs: TaskConfig[] = [
  {
    type: "detection",
    title: "目标检测",
    description: "检测框、类别与置信度",
    models: ["yolo11n", "yolov8n"],
  },
  {
    type: "segmentation",
    title: "实例分割",
    description: "区域 mask、轮廓与类别",
    models: ["yolo11n-seg"],
  },
  {
    type: "pose",
    title: "姿态识别",
    description: "关键点与骨架连线",
    models: ["yolo11n-pose"],
  },
  {
    type: "classification",
    title: "图像分类",
    description: "分类标签与概率",
    models: ["yolo11n-cls"],
  },
  {
    type: "caption",
    title: "图像描述",
    description: "生成图片描述文本",
    models: ["blip-image-captioning-base", "yolo-cls-fallback"],
  },
];

const currentTaskType = ref<ImageTaskType>("detection");
const selectedModelByTask = reactive<Record<ImageTaskType, string>>({
  detection: "yolo11n",
  segmentation: "yolo11n-seg",
  pose: "yolo11n-pose",
  classification: "yolo11n-cls",
  caption: "blip-image-captioning-base",
});
const imageHistoryList = ref<ImageAsset[]>([]);
const loading = ref(false);
const message = ref("");
const historyCollapsed = ref(false);
const thumbnailCollapsed = ref(false);
const originalPreview = ref<ImageAsset | null>(null);

const sessionId = getSessionId();
const taskStates = reactive<Record<ImageTaskType, TaskState>>({
  detection: createDefaultTaskState(),
  segmentation: createDefaultTaskState(),
  pose: createDefaultTaskState(),
  classification: createDefaultTaskState(),
  caption: createDefaultTaskState(),
});

const currentState = computed(() => taskStates[currentTaskType.value]);
const currentConfig = computed(() => taskConfigs.find((item) => item.type === currentTaskType.value) ?? taskConfigs[0]);
const currentImageUrl = computed(() => assetUrl(currentState.value.imageUrl));

const view = reactive({ zoom: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, originX: 0, originY: 0 });

onMounted(async () => {
  await loadImageHistory();
  const first = imageHistoryList.value[0];
  if (first) await selectImage(first);
});

async function setTaskType(taskType: ImageTaskType) {
  currentTaskType.value = taskType;
  message.value = "";
  await loadImageHistory();
  const state = currentState.value;
  if (!state.currentImageId && imageHistoryList.value[0]) {
    await selectImage(imageHistoryList.value[0]);
  }
}

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;

  const error = validateImage(file);
  if (error) {
    message.value = error;
    return;
  }

  await runBusy(async () => {
    const image = await uploadImage(file, currentTaskType.value, sessionId);
    await bindImageToCurrentTask(image);
    await loadImageHistory();
    message.value = "上传完成，原图已保存";
  }, "图片上传失败，请稍后重试");
}

async function loadImageHistory() {
  await runBusy(async () => {
    const data = await listImages({ taskType: currentTaskType.value, page: 1, pageSize: 80, sessionId });
    imageHistoryList.value = data.records;
  }, "历史图片加载失败");
}

async function selectImage(image: ImageAsset) {
  await runBusy(async () => {
    await bindImageToCurrentTask(image);
    const result = await getTaskResult({ imageId: image.imageId, taskType: currentTaskType.value, sessionId });
    applyTaskResult(result);
    await loadCurrentVersions();
    message.value = result ? "任务结果已加载" : "当前图片暂无该任务结果";
    resetView();
  }, "图片或任务结果加载失败");
}

async function runCurrentTask() {
  if (!currentState.value.currentImageId) {
    message.value = "请先上传或选择图片";
    return;
  }
  await runBusy(async () => {
    currentState.value.status = "processing";
    const result = await inferImageTask({
      imageId: currentState.value.currentImageId!,
      taskType: currentTaskType.value,
      sessionId,
      modelName: selectedModelByTask[currentTaskType.value],
    });
    applyTaskResult(result);
    await loadCurrentVersions();
    await loadImageHistory();
    message.value = "AI 结果已生成并保存";
  }, "AI 任务执行失败");
}

async function saveCurrentResult() {
  const state = currentState.value;
  if (!state.currentImageId) {
    message.value = "请先上传或选择图片";
    return;
  }
  await runBusy(async () => {
    const task = state.taskId
      ? { taskId: state.taskId }
      : await createImageTask({ imageId: state.currentImageId!, taskType: currentTaskType.value, sessionId });
    state.taskId = task.taskId;
    await saveTaskResult({
      taskId: state.taskId,
      imageId: state.currentImageId,
      taskType: currentTaskType.value,
      resultImageUrl: state.resultImageUrl,
      resultJson: state.resultJson,
      annotationJson: state.annotationJson,
      descriptionText: state.descriptionText,
      source: "edited",
      modelId: selectedModelByTask[currentTaskType.value],
    });
    await loadCurrentVersions();
    await loadImageHistory();
    message.value = "当前任务结果已保存";
  }, "保存当前结果失败");
}

async function saveAnnotationSnapshot() {
  const state = currentState.value;
  if (!state.taskId || !state.currentImageId || !state.annotationJson) {
    message.value = "当前没有可保存的标注";
    return;
  }
  await runBusy(async () => {
    const result = await updateAnnotation({
      taskId: state.taskId!,
      imageId: state.currentImageId!,
      taskType: currentTaskType.value,
      annotationJson: state.annotationJson!,
    });
    applyTaskResult(result);
    await saveTaskResult({
      taskId: state.taskId!,
      imageId: state.currentImageId!,
      taskType: currentTaskType.value,
      resultImageUrl: state.resultImageUrl,
      resultJson: state.resultJson,
      annotationJson: state.annotationJson,
      descriptionText: state.descriptionText,
      source: "edited",
      modelId: selectedModelByTask[currentTaskType.value],
    });
    await loadCurrentVersions();
    message.value = "标注已保存";
  }, "标注保存失败");
}

function applyTaskResult(result: ImageTaskResult | null) {
  const state = currentState.value;
  if (!result) {
    state.taskId = null;
    state.resultImageUrl = "";
    state.resultJson = null;
    state.annotationJson = null;
    state.descriptionText = "";
    state.status = "idle";
    state.activeVersionId = null;
    state.latestVersionNo = null;
    state.isViewingHistory = false;
    return;
  }
  state.taskId = result.taskId;
  state.resultImageUrl = result.resultImageUrl || "";
  state.resultJson = (result.resultJson as Record<string, unknown> | null) ?? null;
  state.annotationJson = (result.annotationJson as Record<string, unknown> | null) ?? null;
  state.descriptionText = result.descriptionText || "";
  state.status = result.status || "success";
  state.activeVersionId = result.latestVersionId || null;
  state.latestVersionNo = result.latestVersionNo || null;
  state.isViewingHistory = false;
}

async function loadCurrentVersions() {
  const state = currentState.value;
  if (!state.currentImageId) {
    state.versions = [];
    return;
  }
  state.versions = await listTaskResultVersions({
    imageId: state.currentImageId,
    taskType: currentTaskType.value,
    sessionId,
  });
  if (!state.activeVersionId && state.versions[0]) {
    state.activeVersionId = state.versions[0].versionId;
    state.latestVersionNo = state.versions[0].versionNo;
  }
}

async function viewVersion(versionId: string) {
  await runBusy(async () => {
    const version = await getTaskResultVersion(versionId);
    const state = currentState.value;
    state.taskId = version.taskId;
    state.resultImageUrl = version.resultImageUrl || "";
    state.resultJson = (version.resultJson as Record<string, unknown> | null) ?? null;
    state.annotationJson = (version.annotationJson as Record<string, unknown> | null) ?? null;
    state.descriptionText = version.descriptionText || "";
    state.status = "success";
    state.activeVersionId = version.versionId;
    state.isViewingHistory = state.latestVersionNo !== version.versionNo;
    message.value = `正在查看历史版本 v${version.versionNo}`;
  }, "历史版本加载失败");
}

async function restoreVersion(versionId: string) {
  await runBusy(async () => {
    const result = await restoreTaskResultVersion(versionId);
    applyTaskResult(result);
    await loadCurrentVersions();
    await loadImageHistory();
    message.value = `已恢复为新版本 v${currentState.value.latestVersionNo || ""}`;
  }, "恢复历史版本失败");
}

async function bindImageToCurrentTask(image: ImageAsset) {
  const state = currentState.value;
  state.currentImageId = image.imageId;
  state.imageUrl = image.imageUrl || image.fileUrl;
  state.imageInfo = image;
  state.resultImageUrl = "";
  state.resultJson = null;
  state.annotationJson = null;
  state.descriptionText = "";
  state.status = "idle";
  state.versions = [];
  state.activeVersionId = null;
  state.latestVersionNo = null;
  state.isViewingHistory = false;
}

async function runBusy(action: () => Promise<void>, fallback: string) {
  loading.value = true;
  message.value = "";
  try {
    await action();
  } catch (error) {
    message.value = error instanceof Error ? error.message : fallback;
  } finally {
    loading.value = false;
  }
}

function validateImage(file: File): string {
  const allowed = ["image/jpeg", "image/png", "image/webp", "image/bmp"];
  const extAllowed = /\.(jpe?g|png|webp|bmp)$/i.test(file.name);
  if (!allowed.includes(file.type) && !extAllowed) return "图片格式不支持，请上传 jpg、jpeg、png、webp 或 bmp";
  if (file.size > 20 * 1024 * 1024) return "图片大小超过 20MB 限制";
  return "";
}

function createDefaultTaskState(): TaskState {
  return {
    currentImageId: null,
    imageUrl: "",
    imageInfo: null,
    taskId: null,
    resultImageUrl: "",
    resultJson: null,
    annotationJson: null,
    descriptionText: "",
    status: "idle",
    versions: [],
    activeVersionId: null,
    latestVersionNo: null,
    isViewingHistory: false,
  };
}

function getSessionId() {
  const key = "railway-image-session-id";
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const uuid =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
  const created = `session_${uuid}`;
  window.localStorage.setItem(key, created);
  return created;
}

function formatBytes(value?: number | null) {
  if (!value) return "-";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function statusText(status: ImageTaskStatus) {
  return {
    idle: "未处理",
    pending: "待处理",
    processing: "处理中",
    success: "已完成",
    failed: "失败",
  }[status];
}

function resultBoxes() {
  return ((currentState.value.resultJson?.boxes as Array<Record<string, number | string>> | undefined) ?? []) as Array<{
    x: number;
    y: number;
    width: number;
    height: number;
    label: string;
    score: number;
  }>;
}

function resultSegments() {
  return ((currentState.value.resultJson?.segments as Array<Record<string, unknown>> | undefined) ?? []) as Array<{
    label: string;
    score: number;
    polygon: number[][];
  }>;
}

function resultKeypoints() {
  return ((currentState.value.resultJson?.keypoints as Array<Record<string, number | string>> | undefined) ?? []) as Array<{
    name: string;
    x: number;
    y: number;
    score: number;
  }>;
}

function resultLabels() {
  return ((currentState.value.resultJson?.labels as Array<Record<string, number | string>> | undefined) ?? []) as Array<{
    label: string;
    score: number;
  }>;
}

function onWheel(event: WheelEvent) {
  if (!currentState.value.imageUrl) return;
  event.preventDefault();
  const direction = event.deltaY > 0 ? -0.12 : 0.12;
  view.zoom = Math.min(4, Math.max(0.25, Number((view.zoom + direction).toFixed(2))));
}

function startDrag(event: PointerEvent) {
  if (!currentState.value.imageUrl) return;
  view.dragging = true;
  view.startX = event.clientX;
  view.startY = event.clientY;
  view.originX = view.x;
  view.originY = view.y;
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function drag(event: PointerEvent) {
  if (!view.dragging) return;
  view.x = view.originX + event.clientX - view.startX;
  view.y = view.originY + event.clientY - view.startY;
}

function stopDrag() {
  view.dragging = false;
}

function resetView() {
  view.zoom = 1;
  view.x = 0;
  view.y = 0;
}

function fitView() {
  view.zoom = 0.9;
  view.x = 0;
  view.y = 0;
}

function originalView() {
  view.zoom = 1;
  view.x = 0;
  view.y = 0;
}
</script>

<template>
  <main class="app-shell image-task-workspace">
    <header class="topbar">
      <div class="brand">
        <img :src="'/favicon.svg'" alt="" />
        <div>
          <h1>铁路多目标识别平台</h1>
          <span>{{ loading ? "处理中" : "就绪" }}<template v-if="message"> · {{ message }}</template></span>
        </div>
      </div>
      <nav class="task-tabs" aria-label="图像任务">
        <button
          v-for="task in taskConfigs"
          :key="task.type"
          :class="{ active: currentTaskType === task.type }"
          @click="setTaskType(task.type)"
        >
          {{ task.title }}
        </button>
      </nav>
    </header>

    <section class="workspace-body">
      <aside class="history-panel" :class="{ collapsed: historyCollapsed }">
        <div class="panel-head">
          <strong v-if="!historyCollapsed">历史图片</strong>
          <button :title="historyCollapsed ? '展开历史列表' : '收起历史列表'" @click="historyCollapsed = !historyCollapsed">
            <ChevronRight v-if="historyCollapsed" :size="16" />
            <ChevronLeft v-else :size="16" />
          </button>
        </div>
        <template v-if="!historyCollapsed">
          <label class="upload-zone compact">
            <Upload :size="18" />
            <span>上传图片</span>
            <input type="file" accept="image/jpeg,image/png,image/webp,image/bmp" @change="handleUpload" />
          </label>
          <button class="ghost-button" :disabled="loading" @click="loadImageHistory">
            <RefreshCw :size="16" /> 刷新历史
          </button>
          <div class="history-list">
            <button
              v-for="image in imageHistoryList"
              :key="image.imageId"
              class="history-item"
              :class="{ selected: image.imageId === currentState.currentImageId }"
              @click="selectImage(image)"
            >
              <img :src="assetUrl(image.imageUrl)" alt="" />
              <span>
                <strong>{{ image.originalName }}</strong>
                <small>{{ formatTime(image.createdAt) }}</small>
                <small>{{ statusText(image.taskStatus) }} · {{ image.hasCurrentTaskResult ? "已有结果" : "暂无结果" }}</small>
              </span>
            </button>
            <div v-if="imageHistoryList.length === 0" class="empty-state">暂无历史图片</div>
          </div>
        </template>
      </aside>

      <section class="editor-panel">
        <div class="editor-toolbar">
          <div>
            <strong>{{ currentConfig.title }}</strong>
            <span>{{ currentConfig.description }}</span>
        </div>
        <div class="toolbar-actions">
          <label class="model-select">
            <span>模型</span>
            <select v-model="selectedModelByTask[currentTaskType]" :disabled="loading">
              <option v-for="model in currentConfig.models" :key="model" :value="model">
                {{ model }}
              </option>
            </select>
          </label>
          <button :disabled="!currentState.currentImageId || loading" @click="runCurrentTask">
            <Loader2 v-if="loading" class="spin" :size="16" />
            <Sparkles v-else :size="16" />
              开始处理
            </button>
            <button :disabled="!currentState.currentImageId || loading" @click="saveCurrentResult">
              <Save :size="16" /> 保存当前结果
            </button>
            <button :disabled="!currentState.annotationJson || loading" @click="saveAnnotationSnapshot">
              <Download :size="16" /> 保存标注
            </button>
          </div>
        </div>

        <div
          class="canvas-stage"
          @wheel="onWheel"
          @pointerdown="startDrag"
          @pointermove="drag"
          @pointerup="stopDrag"
          @pointerleave="stopDrag"
        >
          <div v-if="!currentState.imageUrl" class="empty-canvas">
            <ImageIcon :size="40" />
            <label class="upload-zone">
              <Upload :size="20" />
              <span>选择图片开始</span>
              <input type="file" accept="image/jpeg,image/png,image/webp,image/bmp" @change="handleUpload" />
            </label>
          </div>

          <div
            v-else
            class="canvas-content"
            :style="{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})` }"
          >
            <img class="base-image" :src="currentImageUrl" alt="原始图片" />
            <svg
              v-if="currentState.imageInfo?.width && currentState.imageInfo?.height"
              class="overlay-layer"
              :viewBox="`0 0 ${currentState.imageInfo.width} ${currentState.imageInfo.height}`"
            >
              <template v-if="currentTaskType === 'detection'">
                <g v-for="(box, index) in resultBoxes()" :key="index">
                  <rect class="box-shape" :x="box.x" :y="box.y" :width="box.width" :height="box.height" />
                  <text class="box-label" :x="box.x + 4" :y="Math.max(box.y - 8, 16)">
                    {{ box.label }} {{ Math.round(box.score * 100) }}%
                  </text>
                </g>
              </template>
              <template v-if="currentTaskType === 'segmentation'">
                <polygon
                  v-for="(segment, index) in resultSegments()"
                  :key="index"
                  class="segment-shape"
                  :points="segment.polygon.map((point) => point.join(',')).join(' ')"
                />
              </template>
              <template v-if="currentTaskType === 'pose'">
                <circle v-for="point in resultKeypoints()" :key="point.name" class="keypoint" :cx="point.x" :cy="point.y" r="8" />
              </template>
            </svg>
          </div>
        </div>

        <div class="view-controls">
          <button @click="fitView"><Maximize2 :size="15" /> 适应窗口</button>
          <button @click="originalView"><ZoomIn :size="15" /> 原始比例</button>
          <button @click="resetView"><RotateCcw :size="15" /> 重置视图</button>
          <span>缩放 {{ Math.round(view.zoom * 100) }}%</span>
        </div>
      </section>

      <aside class="thumbnail-panel" :class="{ collapsed: thumbnailCollapsed }">
        <div class="panel-head">
          <strong v-if="!thumbnailCollapsed">原图缩略图</strong>
          <button :title="thumbnailCollapsed ? '展开原图信息' : '收起原图信息'" @click="thumbnailCollapsed = !thumbnailCollapsed">
            <ChevronLeft v-if="thumbnailCollapsed" :size="16" />
            <ChevronRight v-else :size="16" />
          </button>
        </div>
        <template v-if="!thumbnailCollapsed">
          <button v-if="currentState.imageInfo" class="thumbnail-card" @click="originalPreview = currentState.imageInfo">
            <img :src="currentImageUrl" alt="原图缩略图" />
          </button>
          <div v-else class="empty-state">暂无原图</div>

          <dl v-if="currentState.imageInfo" class="image-info">
            <dt>文件名</dt>
            <dd>{{ currentState.imageInfo.originalName }}</dd>
            <dt>分辨率</dt>
            <dd>{{ currentState.imageInfo.width || "-" }} x {{ currentState.imageInfo.height || "-" }}</dd>
            <dt>大小</dt>
            <dd>{{ formatBytes(currentState.imageInfo.fileSize) }}</dd>
            <dt>上传时间</dt>
            <dd>{{ formatTime(currentState.imageInfo.createdAt) }}</dd>
          </dl>

          <section class="result-summary">
            <h2>任务结果</h2>
            <div v-if="currentState.isViewingHistory" class="history-viewing">
              正在查看历史版本，恢复后会生成一个新版本。
            </div>
            <div v-if="currentState.status === 'idle'" class="empty-state">当前图片暂无该任务结果</div>
            <template v-else-if="currentTaskType === 'classification'">
              <div v-for="item in resultLabels()" :key="item.label" class="result-row">
                <strong>{{ item.label }}</strong><span>{{ Math.round(item.score * 100) }}%</span>
              </div>
            </template>
            <p v-else-if="currentTaskType === 'caption'" class="caption-text">{{ currentState.descriptionText || "暂无描述" }}</p>
            <template v-else>
              <div class="result-row">
                <strong>{{ currentConfig.title }}</strong>
                <span>
                  {{
                    currentTaskType === "detection"
                      ? `${resultBoxes().length} 个目标`
                      : currentTaskType === "segmentation"
                        ? `${resultSegments().length} 个区域`
                        : `${resultKeypoints().length} 个关键点`
                  }}
                </span>
              </div>
            </template>
          </section>

          <section class="result-summary version-summary">
            <h2>历史版本</h2>
            <div v-if="currentState.versions.length === 0" class="empty-state">暂无保存版本</div>
            <div v-else class="version-list">
              <button
                v-for="version in currentState.versions"
                :key="version.versionId"
                class="version-row"
                :class="{ selected: version.versionId === currentState.activeVersionId }"
                @click="viewVersion(version.versionId)"
              >
                <span>
                  <strong>v{{ version.versionNo }}</strong>
                  <small>{{ version.source }} · {{ version.modelId || "-" }}</small>
                </span>
                <small>{{ formatTime(version.createdAt) }}</small>
              </button>
            </div>
            <button
              class="ghost-button restore-button"
              :disabled="!currentState.activeVersionId || !currentState.isViewingHistory || loading"
              @click="restoreVersion(currentState.activeVersionId!)"
            >
              恢复此版本
            </button>
          </section>
        </template>
      </aside>
    </section>

    <div v-if="originalPreview" class="modal-backdrop" @click="originalPreview = null">
      <div class="original-modal" @click.stop>
        <img :src="assetUrl(originalPreview.imageUrl)" alt="原图预览" />
        <button @click="originalPreview = null">关闭</button>
      </div>
    </div>
  </main>
</template>
