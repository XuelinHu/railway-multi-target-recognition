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

const props = defineProps<{ language: "zh" | "en" }>();
const isEnglish = computed(() => props.language === "en");
const text = (zh: string, en: string) => isEnglish.value ? en : zh;

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
  if (cameraState.value === "loading") return text("模型与摄像头初始化中", "Initializing model and camera");
  if (cameraState.value === "running") return text("实时识别中", "Recognizing in real time");
  if (cameraState.value === "error") return text("摄像头不可用", "Camera unavailable");
  return text("未启动", "Not started");
});

const displayStatusMessage = computed(() => {
  if (!isEnglish.value) return statusMessage.value;
  const messages: Record<string, string> = {
    摄像头尚未启动: "Camera has not started",
    "正在加载手部关键点模型": "Loading hand landmark model",
    "正在请求摄像头权限": "Requesting camera permission",
    "请将手掌置于画面中央": "Place your palm in the center of the frame",
    "请将手掌完整置于画面内": "Keep your full palm in the frame",
    "摄像头已停止": "Camera stopped",
  };
  return messages[statusMessage.value] ?? statusMessage.value;
});

function displayGesture(gesture: string) {
  if (!isEnglish.value) return gesture;
  const translations: Record<string, string> = { 握拳: "Fist", 张开手掌: "Open palm", 食指指向: "Pointing", 点赞: "Thumbs up", 拇指手势: "Thumb gesture", 胜利手势: "Victory", 拇指: "thumb", 食指: "index", 中指: "middle", 无名指: "ring", 小指: "little" };
  return translations[gesture] ?? gesture;
}

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
        <h2>{{ text("实时手势识别", "Live Gesture Recognition") }}</h2>
        <p>{{ displayStatusMessage }}</p>
      </div>
      <div class="gesture-actions">
        <span class="camera-state" :class="`state-${cameraState}`"><i></i>{{ stateText }}</span>
        <button v-if="cameraState !== 'running'" :disabled="cameraState === 'loading'" @click="startCamera">
          <Loader2 v-if="cameraState === 'loading'" class="spin" :size="17" />
          <Camera v-else :size="17" />
          {{ cameraState === "error" ? text("重新启动", "Restart") : text("启动摄像头", "Start Camera") }}
        </button>
        <button v-else class="ghost-button" @click="stopCamera()"><CameraOff :size="17" />{{ text("停止", "Stop") }}</button>
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
          <span><Hand :size="18" />{{ text("识别结果", "Recognition Results") }}</span>
          <small>{{ text("最多同时识别 2 只手", "Up to 2 hands at once") }}</small>
        </div>
        <div v-if="readings.length === 0" class="gesture-empty">
          <Hand :size="34" />
          <strong>{{ text("等待手部进入画面", "Waiting for a hand") }}</strong>
          <span>{{ text("保持手掌完整可见，并避免逆光", "Keep the whole palm visible and avoid backlighting") }}</span>
        </div>
        <article v-for="(reading, index) in readings" :key="index" class="hand-result">
          <header><span>{{ text("手部", "Hand") }} {{ index + 1 }}</span><strong>{{ displayGesture(reading.gesture) }}</strong></header>
          <dl>
            <dt>{{ text("左右手", "Side") }}</dt><dd>{{ isEnglish ? (reading.side === "左手" ? "Left" : "Right") : reading.side }}</dd>
            <dt>{{ text("置信度", "Confidence") }}</dt><dd>{{ Math.round(reading.confidence * 100) }}%</dd>
            <dt>{{ text("伸展手指", "Extended fingers") }}</dt><dd>{{ reading.fingers }} {{ text("根", "") }}</dd>
            <dt>{{ text("关键点", "Landmarks") }}</dt><dd>21</dd>
          </dl>
        </article>
        <div class="privacy-note"><ShieldCheck :size="17" /><span>{{ text("视频仅在当前浏览器中实时处理，不会上传或保存。", "Video is processed in this browser only and is not uploaded or saved.") }}</span></div>
        <div v-if="!isSecureCameraContext" class="https-warning">
          {{ text("当前地址不是 HTTPS。公网摄像头识别需要配置 HTTPS 后才能使用。", "This page is not using HTTPS. Public camera access requires HTTPS.") }}
        </div>
        <button v-if="cameraState === 'error'" class="retry-button" @click="startCamera"><RefreshCw :size="16" />{{ text("重试", "Retry") }}</button>
      </aside>
    </div>
  </section>
</template>
