<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from "vue";
import { Camera, CameraOff, Hand, Loader2, RefreshCw, ShieldCheck } from "@lucide/vue";
import {
  FilesetResolver,
  HandLandmarker,
  type HandLandmarkerResult,
  type NormalizedLandmark,
} from "@mediapipe/tasks-vision";

type CameraState = "idle" | "loading" | "running" | "error";
type HandReading = {
  side: string;
  confidence: number;
  fingers: number;
  gesture: string;
};

const videoRef = ref<HTMLVideoElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const cameraState = ref<CameraState>("idle");
const statusMessage = ref("摄像头尚未启动");
const readings = ref<HandReading[]>([]);
const fps = ref(0);

let stream: MediaStream | null = null;
let landmarker: HandLandmarker | null = null;
let animationFrame = 0;
let lastVideoTime = -1;
let frameCount = 0;
let fpsStartedAt = 0;

const isSecureCameraContext = computed(
  () => window.isSecureContext || ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname),
);

const stateText = computed(() => {
  if (cameraState.value === "loading") return "模型与摄像头初始化中";
  if (cameraState.value === "running") return "实时识别中";
  if (cameraState.value === "error") return "摄像头不可用";
  return "未启动";
});

async function startCamera() {
  if (cameraState.value === "loading" || cameraState.value === "running") return;
  if (!isSecureCameraContext.value || !navigator.mediaDevices?.getUserMedia) {
    cameraState.value = "error";
    statusMessage.value = "浏览器仅允许在 HTTPS 或 localhost 页面调用摄像头，请改用安全访问地址";
    return;
  }

  cameraState.value = "loading";
  statusMessage.value = "正在加载手部关键点模型";
  readings.value = [];
  try {
    await ensureLandmarker();
    statusMessage.value = "正在请求摄像头权限";
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
    });
    await nextTick();
    const video = videoRef.value;
    if (!video) throw new Error("视频组件尚未就绪");
    video.srcObject = stream;
    await video.play();
    cameraState.value = "running";
    statusMessage.value = "请将手掌置于画面中央";
    lastVideoTime = -1;
    frameCount = 0;
    fpsStartedAt = performance.now();
    animationFrame = requestAnimationFrame(predictFrame);
  } catch (error) {
    stopCamera(false);
    cameraState.value = "error";
    statusMessage.value = cameraErrorMessage(error);
  }
}

async function ensureLandmarker() {
  if (landmarker) return;
  const vision = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
  const options = {
    baseOptions: { modelAssetPath: "/mediapipe/models/hand_landmarker.task", delegate: "GPU" as const },
    runningMode: "VIDEO" as const,
    numHands: 2,
    minHandDetectionConfidence: 0.55,
    minHandPresenceConfidence: 0.55,
    minTrackingConfidence: 0.5,
  };
  try {
    landmarker = await HandLandmarker.createFromOptions(vision, options);
  } catch {
    landmarker = await HandLandmarker.createFromOptions(vision, {
      ...options,
      baseOptions: { modelAssetPath: "/mediapipe/models/hand_landmarker.task", delegate: "CPU" },
    });
  }
}

function predictFrame(now: number) {
  if (cameraState.value !== "running") return;
  const video = videoRef.value;
  const canvas = canvasRef.value;
  if (video && canvas && landmarker && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
    if (video.currentTime !== lastVideoTime) {
      lastVideoTime = video.currentTime;
      const result = landmarker.detectForVideo(video, now);
      renderResult(result, canvas, video.videoWidth, video.videoHeight);
      updateFps(now);
    }
  }
  animationFrame = requestAnimationFrame(predictFrame);
}

function renderResult(result: HandLandmarkerResult, canvas: HTMLCanvasElement, width: number, height: number) {
  if (!width || !height) return;
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  if (!context) return;
  context.clearRect(0, 0, width, height);
  readings.value = result.landmarks.map((points, index) => {
    drawHand(context, points, width, height, index);
    const category = result.handedness[index]?.[0];
    return {
      side: category?.categoryName === "Left" ? "左手" : category?.categoryName === "Right" ? "右手" : "手部",
      confidence: category?.score ?? 0,
      fingers: extendedFingers(points).length,
      gesture: classifyGesture(points),
    };
  });
  statusMessage.value = readings.value.length ? `已检测到 ${readings.value.length} 只手` : "未检测到手部，请调整距离和光线";
}

function drawHand(context: CanvasRenderingContext2D, points: NormalizedLandmark[], width: number, height: number, handIndex: number) {
  const color = handIndex === 0 ? "#36d399" : "#ffb84d";
  context.lineWidth = Math.max(3, width / 320);
  context.strokeStyle = color;
  context.lineCap = "round";
  for (const connection of HandLandmarker.HAND_CONNECTIONS) {
    const start = points[connection.start];
    const end = points[connection.end];
    context.beginPath();
    context.moveTo(start.x * width, start.y * height);
    context.lineTo(end.x * width, end.y * height);
    context.stroke();
  }
  for (const [index, point] of points.entries()) {
    context.beginPath();
    context.fillStyle = [4, 8, 12, 16, 20].includes(index) ? "#ffffff" : color;
    context.strokeStyle = "#10232f";
    context.lineWidth = 2;
    context.arc(point.x * width, point.y * height, Math.max(4, width / 210), 0, Math.PI * 2);
    context.fill();
    context.stroke();
  }
}

function extendedFingers(points: NormalizedLandmark[]) {
  const extended: string[] = [];
  const wrist = points[0];
  const fingerJoints = [
    { name: "食指", tip: 8, pip: 6 },
    { name: "中指", tip: 12, pip: 10 },
    { name: "无名指", tip: 16, pip: 14 },
    { name: "小指", tip: 20, pip: 18 },
  ];
  for (const finger of fingerJoints) {
    if (pointDistance(points[finger.tip], wrist) > pointDistance(points[finger.pip], wrist) * 1.16) extended.push(finger.name);
  }
  if (pointDistance(points[4], points[5]) > pointDistance(points[3], points[5]) * 1.15) extended.unshift("拇指");
  return extended;
}

function classifyGesture(points: NormalizedLandmark[]) {
  const fingers = extendedFingers(points);
  const has = (name: string) => fingers.includes(name);
  if (pointDistance(points[4], points[8]) < 0.055 && has("中指") && has("无名指") && has("小指")) return "OK";
  if (fingers.length === 0) return "握拳";
  if (fingers.length >= 4) return "张开手掌";
  if (fingers.length === 1 && has("食指")) return "食指指向";
  if (fingers.length === 1 && has("拇指")) return points[4].y < points[2].y ? "点赞" : "拇指手势";
  if (fingers.length === 2 && has("食指") && has("中指")) return "胜利手势";
  return `${fingers.length} 指伸展`;
}

function pointDistance(a: NormalizedLandmark, b: NormalizedLandmark) {
  return Math.hypot(a.x - b.x, a.y - b.y, (a.z ?? 0) - (b.z ?? 0));
}

function updateFps(now: number) {
  frameCount += 1;
  const elapsed = now - fpsStartedAt;
  if (elapsed >= 1000) {
    fps.value = Math.round((frameCount * 1000) / elapsed);
    frameCount = 0;
    fpsStartedAt = now;
  }
}

function stopCamera(resetState = true) {
  cancelAnimationFrame(animationFrame);
  animationFrame = 0;
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  if (videoRef.value) videoRef.value.srcObject = null;
  const context = canvasRef.value?.getContext("2d");
  if (context && canvasRef.value) context.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height);
  readings.value = [];
  fps.value = 0;
  if (resetState) {
    cameraState.value = "idle";
    statusMessage.value = "摄像头已停止";
  }
}

function cameraErrorMessage(error: unknown) {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError") return "摄像头权限被拒绝，请在浏览器地址栏中允许访问后重试";
  if (name === "NotFoundError") return "未检测到可用摄像头";
  if (name === "NotReadableError") return "摄像头正被其他程序占用";
  return error instanceof Error ? `启动失败：${error.message}` : "摄像头启动失败";
}

onBeforeUnmount(() => {
  stopCamera(false);
  landmarker?.close();
  landmarker = null;
});
</script>

<template>
  <section class="gesture-page">
    <div class="gesture-toolbar">
      <div>
        <h2>实时手势识别</h2>
        <p>{{ statusMessage }}</p>
      </div>
      <div class="gesture-actions">
        <span class="camera-state" :class="`state-${cameraState}`"><i></i>{{ stateText }}</span>
        <button v-if="cameraState !== 'running'" :disabled="cameraState === 'loading'" @click="startCamera">
          <Loader2 v-if="cameraState === 'loading'" class="spin" :size="17" />
          <Camera v-else :size="17" />
          {{ cameraState === "error" ? "重新启动" : "启动摄像头" }}
        </button>
        <button v-else class="ghost-button" @click="stopCamera()"><CameraOff :size="17" />停止</button>
      </div>
    </div>

    <div class="gesture-layout">
      <div class="camera-stage">
        <video ref="videoRef" muted playsinline></video>
        <canvas ref="canvasRef"></canvas>
        <div v-if="cameraState !== 'running'" class="camera-placeholder">
          <Loader2 v-if="cameraState === 'loading'" class="spin" :size="48" />
          <CameraOff v-else :size="48" />
          <strong>{{ stateText }}</strong>
          <span>{{ statusMessage }}</span>
        </div>
        <div v-if="cameraState === 'running'" class="camera-metrics">
          <span>{{ fps }} FPS</span><span>{{ readings.length }} HANDS</span>
        </div>
      </div>

      <aside class="gesture-results">
        <div class="result-panel-heading">
          <span><Hand :size="18" />识别结果</span>
          <small>最多同时识别 2 只手</small>
        </div>
        <div v-if="readings.length === 0" class="gesture-empty">
          <Hand :size="34" />
          <strong>等待手部进入画面</strong>
          <span>保持手掌完整可见，并避免逆光</span>
        </div>
        <article v-for="(reading, index) in readings" :key="index" class="hand-result">
          <header><span>手部 {{ index + 1 }}</span><strong>{{ reading.gesture }}</strong></header>
          <dl>
            <dt>左右手</dt><dd>{{ reading.side }}</dd>
            <dt>置信度</dt><dd>{{ Math.round(reading.confidence * 100) }}%</dd>
            <dt>伸展手指</dt><dd>{{ reading.fingers }} 根</dd>
            <dt>关键点</dt><dd>21 个</dd>
          </dl>
        </article>
        <div class="privacy-note"><ShieldCheck :size="17" /><span>视频仅在当前浏览器中实时处理，不会上传或保存。</span></div>
        <div v-if="!isSecureCameraContext" class="https-warning">
          当前地址不是 HTTPS。公网摄像头识别需要配置 HTTPS 后才能使用。
        </div>
        <button v-if="cameraState === 'error'" class="retry-button" @click="startCamera"><RefreshCw :size="16" />重试</button>
      </aside>
    </div>
  </section>
</template>
