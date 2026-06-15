<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Check, Download, MousePointer2, Play, Plus, RefreshCw, Save, Upload, X } from "@lucide/vue";
import {
  type AnnotationsDocument,
  type Asset,
  type DetectTask,
  createDetectionTask,
  exportAnnotations,
  frameImageUrl,
  getAnnotations,
  getTask,
  listAssets,
  reviewAnnotations,
  saveAnnotations,
  uploadAsset,
} from "./api";

const assets = ref<Asset[]>([]);
const selectedAssetId = ref("");
const task = ref<DetectTask | null>(null);
const annotations = ref<AnnotationsDocument | null>(null);
const selectedFrameIndex = ref(0);
const exportText = ref("");
const busy = ref(false);
const message = ref("");
const frameStride = ref(1);
const maxFrames = ref<number | null>(null);
const stageRef = ref<HTMLElement | null>(null);
const editMode = ref<"select" | "add">("select");
const selectedObjectIndex = ref<number | null>(null);

type ResizeHandle = "nw" | "ne" | "sw" | "se";
const resizeHandles: ResizeHandle[] = ["nw", "ne", "sw", "se"];
type Interaction = {
  mode: "move" | "resize" | "create";
  pointerId: number;
  objectIndex: number;
  handle?: ResizeHandle;
  startX: number;
  startY: number;
  original: { x: number; y: number; width: number; height: number };
};

const interaction = ref<Interaction | null>(null);

const selectedAsset = computed(() => assets.value.find((asset) => asset.id === selectedAssetId.value) ?? null);
const selectedFrame = computed(() => {
  if (!annotations.value) return null;
  return annotations.value.frames[selectedFrameIndex.value] ?? annotations.value.frames[0] ?? null;
});
const selectedFrameObjects = computed(() => selectedFrame.value?.objects ?? []);
const frameImage = computed(() => frameImageUrl(selectedFrame.value?.image_url));

onMounted(() => {
  refreshAssets();
});

async function refreshAssets() {
  runBusy(async () => {
    const data = await listAssets();
    assets.value = data;
    if (!selectedAssetId.value && data.length > 0) {
      selectedAssetId.value = data[0].id;
    }
  }, "资源加载失败");
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  await runBusy(async () => {
    const asset = await uploadAsset(file);
    assets.value = [asset, ...assets.value.filter((item) => item.id !== asset.id)];
    selectedAssetId.value = asset.id;
    annotations.value = null;
    exportText.value = "";
    selectedFrameIndex.value = 0;
    message.value = "上传完成";
  }, "上传失败");
  input.value = "";
}

async function startDetection() {
  if (!selectedAssetId.value) return;
  await runBusy(async () => {
    const nextTask = await createDetectionTask(
      selectedAssetId.value,
      frameStride.value,
      maxFrames.value || undefined,
    );
    task.value = nextTask;
    const latestTask = await waitForTask(nextTask.id);
    if (latestTask.status === "completed") {
      await loadAnnotations(latestTask.asset_id);
    }
  }, "识别任务创建失败");
}

async function pollTask() {
  if (!task.value) return;
  await runBusy(async () => {
    const latestTask = await getTask(task.value!.id);
    task.value = latestTask;
    if (latestTask.status === "completed") {
      await loadAnnotations(latestTask.asset_id);
    }
  }, "任务刷新失败");
}

async function waitForTask(taskId: string) {
  for (let attempt = 0; attempt < 600; attempt += 1) {
    const latestTask = await getTask(taskId);
    task.value = latestTask;
    if (latestTask.status === "completed" || latestTask.status === "failed") {
      return latestTask;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  }
  throw new Error("任务等待超时");
}

async function loadAnnotations(assetId = selectedAssetId.value) {
  if (!assetId) return;
  await runBusy(async () => {
    annotations.value = await getAnnotations(assetId);
    selectedFrameIndex.value = 0;
    exportText.value = "";
  }, "标注加载失败");
}

async function saveCurrentAnnotations() {
  if (!selectedAssetId.value || !annotations.value) return;
  await runBusy(async () => {
    annotations.value = await saveAnnotations(selectedAssetId.value, annotations.value!);
    message.value = "保存完成";
  }, "保存失败");
}

async function review(status: "approved" | "rejected" | "in_review") {
  if (!selectedAssetId.value) return;
  await runBusy(async () => {
    annotations.value = await reviewAnnotations(selectedAssetId.value, status);
    message.value = status === "approved" ? "校验通过" : status === "rejected" ? "已驳回" : "进入校验";
  }, "校验状态更新失败");
}

async function runExport(format: "json" | "coco" | "yolo") {
  if (!selectedAssetId.value) return;
  await runBusy(async () => {
    exportText.value = await exportAnnotations(selectedAssetId.value, format);
  }, "导出失败");
}

function selectAsset(assetId: string) {
  selectedAssetId.value = assetId;
  task.value = null;
  annotations.value = null;
  selectedFrameIndex.value = 0;
  exportText.value = "";
  selectedObjectIndex.value = null;
}

function markObject(index: number, status: "confirmed" | "edited" | "rejected") {
  const object = selectedFrame.value?.objects[index];
  if (!object) return;
  object.status = status;
}

function beginCanvasInteraction(event: PointerEvent) {
  if (editMode.value !== "add" || !selectedFrame.value || !stageRef.value) return;
  if ((event.target as HTMLElement).closest(".bbox")) return;
  const point = framePoint(event);
  if (!point) return;
  const object = {
    id: `obj_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`,
    label: "new_target",
    confidence: 1,
    bbox: { x: point.x, y: point.y, width: 1, height: 1 },
    track_id: null,
    source: "manual" as const,
    status: "edited" as const,
  };
  selectedFrame.value.objects.push(object);
  const objectIndex = selectedFrame.value.objects.length - 1;
  selectedObjectIndex.value = objectIndex;
  interaction.value = {
    mode: "create",
    pointerId: event.pointerId,
    objectIndex,
    startX: point.x,
    startY: point.y,
    original: { ...object.bbox },
  };
  stageRef.value.setPointerCapture(event.pointerId);
}

function beginMove(event: PointerEvent, objectIndex: number) {
  if (editMode.value !== "select") return;
  const point = framePoint(event);
  const object = selectedFrame.value?.objects[objectIndex];
  if (!point || !object || !stageRef.value) return;
  event.stopPropagation();
  selectedObjectIndex.value = objectIndex;
  interaction.value = {
    mode: "move",
    pointerId: event.pointerId,
    objectIndex,
    startX: point.x,
    startY: point.y,
    original: { ...object.bbox },
  };
  stageRef.value.setPointerCapture(event.pointerId);
}

function beginResize(event: PointerEvent, objectIndex: number, handle: ResizeHandle) {
  const point = framePoint(event);
  const object = selectedFrame.value?.objects[objectIndex];
  if (!point || !object || !stageRef.value) return;
  event.stopPropagation();
  selectedObjectIndex.value = objectIndex;
  interaction.value = {
    mode: "resize",
    pointerId: event.pointerId,
    objectIndex,
    handle,
    startX: point.x,
    startY: point.y,
    original: { ...object.bbox },
  };
  stageRef.value.setPointerCapture(event.pointerId);
}

function updateInteraction(event: PointerEvent) {
  const active = interaction.value;
  const frame = selectedFrame.value;
  const point = framePoint(event);
  if (!active || !frame || !point) return;
  const object = frame.objects[active.objectIndex];
  if (!object) return;
  const frameWidth = frame.width || 1;
  const frameHeight = frame.height || 1;
  const minSize = 4;
  const dx = point.x - active.startX;
  const dy = point.y - active.startY;

  if (active.mode === "move") {
    object.bbox.x = clamp(active.original.x + dx, 0, frameWidth - active.original.width);
    object.bbox.y = clamp(active.original.y + dy, 0, frameHeight - active.original.height);
  } else if (active.mode === "create") {
    object.bbox.x = Math.min(active.startX, point.x);
    object.bbox.y = Math.min(active.startY, point.y);
    object.bbox.width = Math.max(Math.abs(point.x - active.startX), minSize);
    object.bbox.height = Math.max(Math.abs(point.y - active.startY), minSize);
  } else {
    resizeObject(object.bbox, active, point.x, point.y, frameWidth, frameHeight, minSize);
  }
  object.status = "edited";
}

function endInteraction(event: PointerEvent) {
  if (!interaction.value || !stageRef.value) return;
  if (stageRef.value.hasPointerCapture(event.pointerId)) {
    stageRef.value.releasePointerCapture(event.pointerId);
  }
  interaction.value = null;
  if (editMode.value === "add") editMode.value = "select";
}

function framePoint(event: PointerEvent) {
  const frame = selectedFrame.value;
  const stage = stageRef.value;
  if (!frame || !stage) return null;
  const rect = stage.getBoundingClientRect();
  return {
    x: clamp(((event.clientX - rect.left) / rect.width) * (frame.width || 1), 0, frame.width || 1),
    y: clamp(((event.clientY - rect.top) / rect.height) * (frame.height || 1), 0, frame.height || 1),
  };
}

function resizeObject(
  bbox: { x: number; y: number; width: number; height: number },
  active: Interaction,
  x: number,
  y: number,
  frameWidth: number,
  frameHeight: number,
  minSize: number,
) {
  const right = active.original.x + active.original.width;
  const bottom = active.original.y + active.original.height;
  if (active.handle?.includes("w")) {
    bbox.x = clamp(x, 0, right - minSize);
    bbox.width = right - bbox.x;
  }
  if (active.handle?.includes("e")) {
    bbox.width = clamp(x - active.original.x, minSize, frameWidth - active.original.x);
  }
  if (active.handle?.includes("n")) {
    bbox.y = clamp(y, 0, bottom - minSize);
    bbox.height = bottom - bbox.y;
  }
  if (active.handle?.includes("s")) {
    bbox.height = clamp(y - active.original.y, minSize, frameHeight - active.original.y);
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

async function runBusy(action: () => Promise<void>, fallback: string) {
  busy.value = true;
  message.value = "";
  try {
    await action();
  } catch (error) {
    message.value = error instanceof Error ? error.message : fallback;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div>
        <h1>铁路多目标识别校验台</h1>
        <span>{{ busy ? "处理中" : "就绪" }}</span>
      </div>
      <div class="toolbar">
        <label class="icon-button file-button" title="上传图片或视频">
          <Upload :size="18" />
          <input type="file" accept="image/*,video/*" @change="onFileChange" />
        </label>
        <button class="icon-button" title="刷新资源" :disabled="busy" @click="refreshAssets">
          <RefreshCw :size="18" />
        </button>
      </div>
    </header>

    <section class="workspace">
      <aside class="asset-pane">
        <div class="pane-title">资源</div>
        <div class="asset-list">
          <button
            v-for="asset in assets"
            :key="asset.id"
            :class="['asset-row', { active: asset.id === selectedAssetId }]"
            @click="selectAsset(asset.id)"
          >
            <strong>{{ asset.filename }}</strong>
            <span>
              {{ asset.type }}
              <template v-if="asset.width && asset.height"> · {{ asset.width }}x{{ asset.height }}</template>
              <template v-if="asset.frame_count"> · {{ asset.frame_count }} 帧</template>
            </span>
          </button>
        </div>
      </aside>

      <section class="review-pane">
        <div class="action-strip">
          <select v-model="selectedAssetId">
            <option value="">选择资源</option>
            <option v-for="asset in assets" :key="asset.id" :value="asset.id">{{ asset.filename }}</option>
          </select>
          <label class="number-field">
            <span>步长</span>
            <input v-model.number="frameStride" type="number" min="1" />
          </label>
          <label class="number-field">
            <span>最多帧</span>
            <input v-model.number="maxFrames" type="number" min="1" placeholder="全部" />
          </label>
          <button :disabled="!selectedAssetId || busy" @click="startDetection">
            <Play :size="17" />
            标注
          </button>
          <button :disabled="!task || busy" @click="pollTask">
            <RefreshCw :size="17" />
            任务
          </button>
          <button :disabled="!selectedAssetId || busy" @click="loadAnnotations()">
            <RefreshCw :size="17" />
            结果
          </button>
          <button :disabled="!annotations || busy" @click="saveCurrentAnnotations">
            <Save :size="17" />
            保存
          </button>
          <button
            :class="{ active: editMode === 'select' }"
            :disabled="!selectedFrame"
            title="选择并拖动检测框"
            @click="editMode = 'select'"
          >
            <MousePointer2 :size="17" />
            选择
          </button>
          <button
            :class="{ active: editMode === 'add' }"
            :disabled="!selectedFrame"
            title="在图像上拖动新增检测框"
            @click="editMode = 'add'"
          >
            <Plus :size="17" />
            新增框
          </button>
          <button :disabled="!annotations || busy" @click="review('approved')">
            <Check :size="17" />
            通过
          </button>
          <button :disabled="!annotations || busy" @click="review('rejected')">
            <X :size="17" />
            驳回
          </button>
        </div>

        <div class="status-line">
          <span>{{ selectedAsset ? selectedAsset.filename : "未选择资源" }}</span>
          <span>{{ task ? `${task.status} · ${Math.round(task.progress * 100)}% · ${task.model_name}` : "无任务" }}</span>
          <span>{{ annotations ? `校验：${annotations.review_status}` : "未加载标注" }}</span>
          <span>{{ message }}</span>
        </div>

        <section class="frame-workspace">
          <div class="frame-list">
            <button
              v-for="(frame, index) in annotations?.frames ?? []"
              :key="frame.frame_index"
              :class="['frame-row', { active: index === selectedFrameIndex }]"
              @click="selectedFrameIndex = index"
            >
              <strong>#{{ frame.frame_index }}</strong>
              <span>{{ frame.objects.length }} 个目标 · {{ frame.review_status }}</span>
            </button>
          </div>

          <div class="preview-area">
            <div
              v-if="selectedFrame && frameImage"
              ref="stageRef"
              :class="['image-stage', { drawing: editMode === 'add' }]"
              @pointerdown="beginCanvasInteraction"
              @pointermove="updateInteraction"
              @pointerup="endInteraction"
              @pointercancel="endInteraction"
            >
              <img :src="frameImage" alt="frame" draggable="false" />
              <div
                v-for="(object, objectIndex) in selectedFrameObjects"
                :key="object.id"
                :class="['bbox', { selected: objectIndex === selectedObjectIndex }]"
                :style="{
                  left: `${(object.bbox.x / (selectedFrame.width || 1)) * 100}%`,
                  top: `${(object.bbox.y / (selectedFrame.height || 1)) * 100}%`,
                  width: `${(object.bbox.width / (selectedFrame.width || 1)) * 100}%`,
                  height: `${(object.bbox.height / (selectedFrame.height || 1)) * 100}%`,
                }"
                @pointerdown="beginMove($event, objectIndex)"
              >
                <span>{{ object.label }} {{ Math.round(object.confidence * 100) }}%</span>
                <template v-if="objectIndex === selectedObjectIndex">
                  <i
                    v-for="handle in resizeHandles"
                    :key="handle"
                    :class="['resize-handle', handle]"
                    @pointerdown="beginResize($event, objectIndex, handle)"
                  />
                </template>
              </div>
            </div>
            <div v-else class="empty-state">上传资源并执行自动标注后显示帧图</div>
          </div>

          <div class="object-table">
            <div class="table-head">
              <span>类别</span>
              <span>置信度</span>
              <span>状态</span>
              <span>操作</span>
            </div>
            <div
              v-for="(object, index) in selectedFrameObjects"
              :key="object.id"
              :class="['table-row', { selected: index === selectedObjectIndex }]"
              @click="selectedObjectIndex = index"
            >
              <input v-model="object.label" @change="markObject(index, 'edited')" />
              <span>{{ object.confidence.toFixed(3) }}</span>
              <select v-model="object.status">
                <option value="auto">auto</option>
                <option value="confirmed">confirmed</option>
                <option value="edited">edited</option>
                <option value="rejected">rejected</option>
              </select>
              <div class="row-actions">
                <button title="确认" @click="markObject(index, 'confirmed')"><Check :size="16" /></button>
                <button title="驳回" @click="markObject(index, 'rejected')"><X :size="16" /></button>
              </div>
            </div>
          </div>
        </section>

        <div class="export-strip">
          <button :disabled="!selectedAssetId || busy" @click="runExport('json')">
            <Download :size="17" />
            JSON
          </button>
          <button :disabled="!selectedAssetId || busy" @click="runExport('coco')">
            <Download :size="17" />
            COCO
          </button>
          <button :disabled="!selectedAssetId || busy" @click="runExport('yolo')">
            <Download :size="17" />
            YOLO
          </button>
        </div>

        <pre class="export-view">{{ exportText }}</pre>
      </section>
    </section>
  </main>
</template>
