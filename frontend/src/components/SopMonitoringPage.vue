<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { AlertTriangle, Check, Film, Play, RefreshCw, ShieldCheck, Waypoints } from "@lucide/vue";
import {
  assetUrl,
  listVideoCaptionBatches,
  listVideoCaptionFrames,
  listVideoCaptionVideos,
  type VideoCaptionBatch,
  type VideoCaptionFrame,
  type VideoCaptionVideo,
} from "../api";

const props = defineProps<{ language: "zh" | "en" }>();
const isZh = computed(() => props.language === "zh");
const batches = ref<VideoCaptionBatch[]>([]);
const videos = ref<VideoCaptionVideo[]>([]);
const frames = ref<VideoCaptionFrame[]>([]);
const selectedBatchId = ref("");
const selectedVideoId = ref("");
const selectedFrameId = ref("");
const loading = ref(false);
const error = ref("");
const videoQuery = ref("");
const playerOpen = ref(false);

const selectedBatch = computed(() => batches.value.find((item) => item.batchId === selectedBatchId.value) ?? null);
const selectedVideo = computed(() => videos.value.find((item) => item.videoId === selectedVideoId.value) ?? null);
const selectedFrame = computed(() => frames.value.find((item) => item.frameId === selectedFrameId.value) ?? null);
const filteredVideos = computed(() => {
  const query = videoQuery.value.trim().toLocaleLowerCase();
  if (!query) return videos.value;
  return videos.value.filter((video) => `${video.displayName} ${video.filename} ${video.keywords.join(" ")}`.toLocaleLowerCase().includes(query));
});

const representativeFrames = computed(() => {
  if (!frames.value.length) return [];
  const count = Math.min(6, frames.value.length);
  const indexes = Array.from({ length: count }, (_, index) => Math.round(index * (frames.value.length - 1) / Math.max(count - 1, 1)));
  return [...new Set(indexes)].map((index) => frames.value[index]);
});

const sopSteps = computed(() => {
  const checkpoints = [
    { title: isZh.value ? "进入作业区域并确认环境" : "Enter work area and check surroundings", cue: /进入|现场|人员|作业区|环境|轨道|巡视|检查/i },
    { title: isZh.value ? "接近目标设备或作业点" : "Approach the equipment or work point", cue: /接近|靠近|设备|钢轨|道岔|接触网|工具|目标/i },
    { title: isZh.value ? "检查设备状态与关键部位" : "Inspect equipment and critical components", cue: /检查|观察|查看|确认|状态|部件|连接|螺栓|扣件/i },
    { title: isZh.value ? "执行规定操作并保持安全姿态" : "Perform the operation with a safe posture", cue: /操作|作业|安装|拆卸|维修|调整|弯腰|伸手|接触/i },
    { title: isZh.value ? "复核结果并结束作业" : "Verify the result and finish the task", cue: /复核|完成|离开|收工|结束|归还|恢复|结果/i },
  ];
  let previousMatchedTimestamp: number | null = null;
  return checkpoints.map((step, index) => {
    const matchedFrame = representativeFrames.value.find((frame) => step.cue.test(frame.descriptionManual || frame.descriptionText));
    const evidence = matchedFrame ?? representativeFrames.value[Math.min(index, representativeFrames.value.length - 1)] ?? null;
    const orderIssue = Boolean(matchedFrame && previousMatchedTimestamp !== null && matchedFrame.timestampMs < previousMatchedTimestamp);
    if (matchedFrame) previousMatchedTimestamp = matchedFrame.timestampMs;
    return {
      ...step,
      index,
      evidence,
      matched: Boolean(matchedFrame),
      orderIssue,
      statusText: orderIssue
        ? (isZh.value ? "疑似顺序异常" : "Possible order issue")
        : matchedFrame
          ? (isZh.value ? "顺序候选正常" : "Order candidate OK")
          : (isZh.value ? "待人工核验" : "Needs review"),
    };
  });
});

const reviewSummary = computed(() => {
  const descriptions = representativeFrames.value.map((frame) => frame.descriptionManual || frame.descriptionText).filter(Boolean);
  return descriptions.length
    ? (isZh.value ? "已根据抽帧描述生成步骤候选，需人工核验动作与先后关系。" : "Step candidates were generated from frame captions; verify actions and order manually.")
    : (isZh.value ? "该视频尚无可用画面描述，当前仅展示 SOP 检查清单。" : "No frame captions are available; showing the SOP checklist only.");
});

function formatTime(value?: number | null) {
  const seconds = Math.max(0, Math.floor((value ?? 0) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remain = seconds % 60;
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remain).padStart(2, "0")}` : `${minutes}:${String(remain).padStart(2, "0")}`;
}

async function loadBatches() {
  loading.value = true;
  error.value = "";
  try {
    batches.value = await listVideoCaptionBatches();
    if (!selectedBatchId.value || !batches.value.some((item) => item.batchId === selectedBatchId.value)) {
      selectedBatchId.value = batches.value[0]?.batchId ?? "";
    }
    await loadVideos();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
}

async function loadVideos() {
  videos.value = selectedBatchId.value ? await listVideoCaptionVideos(selectedBatchId.value) : [];
  if (!videos.value.some((item) => item.videoId === selectedVideoId.value)) selectedVideoId.value = "";
}

async function selectBatch() {
  selectedVideoId.value = "";
  frames.value = [];
  selectedFrameId.value = "";
  loading.value = true;
  error.value = "";
  try {
    await loadVideos();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
}

async function selectVideo(videoId: string) {
  selectedVideoId.value = videoId;
  selectedFrameId.value = "";
  frames.value = [];
  loading.value = true;
  error.value = "";
  try {
    const firstPage = await listVideoCaptionFrames({ videoId, page: 1, pageSize: 500 });
    frames.value = firstPage.records;
    const pageCount = Math.min(10, Math.ceil(firstPage.total / 500));
    if (pageCount > 1) {
      const rest = await Promise.all(Array.from({ length: pageCount - 1 }, (_, index) => listVideoCaptionFrames({ videoId, page: index + 2, pageSize: 500 })));
      frames.value = [...firstPage.records, ...rest.flatMap((page) => page.records)].sort((a, b) => a.timestampMs - b.timestampMs);
    }
    selectedFrameId.value = representativeFrames.value[0]?.frameId ?? frames.value[0]?.frameId ?? "";
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
}

watch(selectedBatchId, () => { videoQuery.value = ""; });
onMounted(loadBatches);
</script>

<template>
  <main class="sop-page">
    <header class="sop-header">
      <div>
        <span class="sop-eyebrow">{{ isZh ? "视频作业流程分析" : "VIDEO WORKFLOW ANALYSIS" }}</span>
        <h2><Waypoints :size="22" />{{ isZh ? "SOP 行为监控" : "SOP Behavior Monitor" }}</h2>
      </div>
      <button class="sop-refresh" :disabled="loading" @click="loadBatches"><RefreshCw :size="16" />{{ isZh ? "刷新视频" : "Refresh videos" }}</button>
    </header>

    <div v-if="error" class="sop-error"><AlertTriangle :size="18" /><span>{{ error }}</span><button @click="loadBatches">{{ isZh ? "重试" : "Retry" }}</button></div>

    <section class="sop-layout">
      <aside class="sop-video-rail">
        <div class="sop-filter-row">
          <label>{{ isZh ? "解帧批次" : "Frame batch" }}
            <select v-model="selectedBatchId" :disabled="loading" @change="selectBatch">
              <option v-for="batch in batches" :key="batch.batchId" :value="batch.batchId">{{ batch.name }}</option>
            </select>
          </label>
          <input v-model="videoQuery" :placeholder="isZh ? '筛选视频名称' : 'Filter videos'" />
        </div>
        <div class="sop-video-list">
          <button v-for="video in filteredVideos" :key="video.videoId" class="sop-video-item" :class="{ selected: video.videoId === selectedVideoId }" @click="selectVideo(video.videoId)">
            <span class="sop-video-icon"><Film :size="17" /></span>
            <span class="sop-video-copy"><strong>{{ video.displayName || video.filename }}</strong><small>{{ formatTime(video.durationMs) }} · {{ video.frameCount ?? 0 }} {{ isZh ? "帧" : "frames" }}</small></span>
            <Play :size="15" />
          </button>
          <div v-if="!filteredVideos.length" class="sop-empty">{{ loading ? (isZh ? "加载中…" : "Loading…") : (isZh ? "当前批次没有视频记录" : "No videos in this batch") }}</div>
        </div>
        <footer v-if="selectedBatch" class="sop-batch-foot"><span>{{ selectedBatch.name }}</span><small>{{ selectedBatch.totalVideos }} {{ isZh ? "个视频" : "videos" }} · {{ selectedBatch.totalFrames }} {{ isZh ? "个抽帧" : "frames" }}</small></footer>
      </aside>

      <section class="sop-main">
        <template v-if="selectedVideo">
          <header class="sop-video-heading">
            <div><span class="sop-eyebrow">{{ isZh ? "当前分析对象" : "SELECTED VIDEO" }}</span><h3>{{ selectedVideo.displayName || selectedVideo.filename }}</h3><p>{{ selectedVideo.filename }} <span>·</span> {{ formatTime(selectedVideo.durationMs) }} <span>·</span> {{ selectedVideo.width ?? "-" }} × {{ selectedVideo.height ?? "-" }}</p></div>
            <button class="sop-play-button" :disabled="!selectedVideo.sourceUrl" @click="playerOpen = true"><Play :size="16" />{{ isZh ? "播放原视频" : "Play source" }}</button>
          </header>

          <div class="sop-stat-row">
            <div><span>{{ isZh ? "视频时长" : "Duration" }}</span><strong>{{ formatTime(selectedVideo.durationMs) }}</strong></div>
            <div><span>{{ isZh ? "抽取画面" : "Extracted frames" }}</span><strong>{{ frames.length || selectedVideo.frameCount || 0 }}</strong></div>
            <div><span>{{ isZh ? "代表画面" : "Key frames" }}</span><strong>{{ representativeFrames.length }}</strong></div>
            <div class="sop-review-state"><span>{{ isZh ? "评估状态" : "Assessment" }}</span><strong><ShieldCheck :size="17" />{{ isZh ? "待人工复核" : "Needs review" }}</strong></div>
          </div>

          <section class="sop-assessment">
            <div class="sop-section-heading"><div><h4>{{ isZh ? "SOP 步骤评估" : "SOP step assessment" }}</h4><p>{{ reviewSummary }}</p></div><span class="sop-demo-tag">{{ isZh ? "演示规则" : "DEMO RULES" }}</span></div>
            <ol class="sop-step-list">
              <li v-for="step in sopSteps" :key="step.index" class="sop-step">
                <span class="sop-step-number">{{ String(step.index + 1).padStart(2, "0") }}</span>
                <div class="sop-step-body"><strong>{{ step.title }}</strong><small v-if="step.evidence">{{ formatTime(step.evidence.timestampMs) }} · {{ step.evidence.descriptionManual || step.evidence.descriptionText || (isZh ? "该帧尚无描述，需人工判定" : "No caption; manual review required") }}</small><small v-else>{{ isZh ? "等待抽帧数据" : "Waiting for frame data" }}</small></div>
                <span :class="['sop-step-status', step.orderIssue ? 'order-issue' : step.matched ? 'order-ok' : '']"><AlertTriangle v-if="!step.matched || step.orderIssue" :size="14" /><Check v-else :size="14" />{{ step.statusText }}</span>
              </li>
            </ol>
          </section>

          <section class="sop-frames-section">
            <div class="sop-section-heading"><div><h4>{{ isZh ? "关键画面与动作描述" : "Key frames and action captions" }}</h4><p>{{ isZh ? "从视频时间轴均匀选取代表帧，逐帧对应描述" : "Representative frames sampled across the timeline with their captions" }}</p></div><span>{{ representativeFrames.length }} / {{ frames.length }} {{ isZh ? "帧" : "frames" }}</span></div>
            <div class="sop-frame-strip">
              <button v-for="(frame, index) in representativeFrames" :key="frame.frameId" class="sop-frame-card" :class="{ selected: frame.frameId === selectedFrameId }" @click="selectedFrameId = frame.frameId">
                <div class="sop-frame-image"><img :src="assetUrl(frame.imageUrl)" :alt="`${isZh ? '关键画面' : 'Key frame'} ${index + 1}`" /><span>{{ formatTime(frame.timestampMs) }}</span></div>
                <div class="sop-frame-copy"><strong>{{ isZh ? `画面 ${String(index + 1).padStart(2, "0")}` : `Frame ${String(index + 1).padStart(2, "0")}` }}</strong><p>{{ frame.descriptionManual || frame.descriptionText || (isZh ? "暂无描述，建议补充画面动作说明。" : "No caption available; add a frame description.") }}</p></div>
              </button>
              <div v-if="loading" class="sop-empty">{{ isZh ? "正在读取视频帧…" : "Loading video frames…" }}</div>
              <div v-else-if="!representativeFrames.length" class="sop-empty">{{ isZh ? "该视频暂无抽帧记录" : "No extracted frames for this video" }}</div>
            </div>
          </section>
        </template>
        <div v-else class="sop-welcome"><div class="sop-welcome-mark"><Waypoints :size="28" /></div><h3>{{ isZh ? "选择一个视频开始 SOP 评估" : "Choose a video to assess its SOP" }}</h3><p>{{ isZh ? "系统将展示视频时长、时间轴关键画面、逐帧描述和待核验的作业步骤。" : "Review duration, timeline keyframes, captions, and SOP checkpoints." }}</p><span>{{ loading ? (isZh ? "正在连接视频数据…" : "Connecting to video data…") : (isZh ? "从左侧视频列表选择" : "Select a video from the list") }}</span></div>
      </section>

      <aside class="sop-evidence-panel">
        <template v-if="selectedVideo">
          <div class="sop-evidence-head"><span class="sop-eyebrow">{{ isZh ? "画面证据" : "FRAME EVIDENCE" }}</span><h4>{{ isZh ? "选中画面" : "Selected frame" }}</h4></div>
          <template v-if="selectedFrame">
            <img class="sop-evidence-image" :src="assetUrl(selectedFrame.imageUrl)" alt="" />
            <dl class="sop-evidence-meta"><dt>{{ isZh ? "时间点" : "Timestamp" }}</dt><dd>{{ formatTime(selectedFrame.timestampMs) }}</dd><dt>{{ isZh ? "帧序号" : "Frame index" }}</dt><dd>{{ selectedFrame.frameIndex }}</dd><dt>{{ isZh ? "识别模型" : "Model" }}</dt><dd>{{ selectedFrame.modelId || "-" }}</dd></dl>
            <div class="sop-evidence-caption"><strong>{{ isZh ? "画面描述" : "Frame caption" }}</strong><p>{{ selectedFrame.descriptionManual || selectedFrame.descriptionText || (isZh ? "暂无描述" : "No caption") }}</p></div>
          </template>
          <div v-else class="sop-evidence-empty">{{ isZh ? "选择关键画面查看证据" : "Select a key frame to inspect evidence" }}</div>
          <div class="sop-review-note"><AlertTriangle :size="16" /><p>{{ isZh ? "当前为演示级时序辅助评估。动作是否完成、顺序是否合规仍需结合姿态/目标识别结果与人工复核；不能作为安全生产判定。" : "Demo-level temporal assessment only. Completion and compliance require pose/object evidence and human review; do not use as a safety decision." }}</p></div>
        </template>
        <div v-else class="sop-evidence-empty">{{ isZh ? "选择视频后显示帧证据" : "Frame evidence appears after selecting a video" }}</div>
      </aside>
    </section>

    <div v-if="playerOpen && selectedVideo?.sourceUrl" class="sop-player-backdrop" @click.self="playerOpen = false">
      <section class="sop-player-modal"><header><strong>{{ selectedVideo.displayName || selectedVideo.filename }}</strong><button @click="playerOpen = false">{{ isZh ? "关闭" : "Close" }}</button></header><video :src="assetUrl(selectedVideo.sourceUrl)" controls autoplay playsinline /></section>
    </div>
  </main>
</template>
