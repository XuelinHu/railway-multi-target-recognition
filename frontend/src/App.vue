<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Check, Download, Play, RefreshCw, Save, Upload, X } from "@lucide/vue";
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
    const latestTask = await getTask(nextTask.id);
    task.value = latestTask;
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
}

function markObject(index: number, status: "confirmed" | "edited" | "rejected") {
  const object = selectedFrame.value?.objects[index];
  if (!object) return;
  object.status = status;
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
            <div v-if="selectedFrame && frameImage" class="image-stage">
              <img :src="frameImage" alt="frame" />
              <div
                v-for="object in selectedFrameObjects"
                :key="object.id"
                class="bbox"
                :style="{
                  left: `${(object.bbox.x / (selectedFrame.width || 1)) * 100}%`,
                  top: `${(object.bbox.y / (selectedFrame.height || 1)) * 100}%`,
                  width: `${(object.bbox.width / (selectedFrame.width || 1)) * 100}%`,
                  height: `${(object.bbox.height / (selectedFrame.height || 1)) * 100}%`,
                }"
              >
                <span>{{ object.label }} {{ Math.round(object.confidence * 100) }}%</span>
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
            <div v-for="(object, index) in selectedFrameObjects" :key="object.id" class="table-row">
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
