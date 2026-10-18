<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import DOMPurify from "dompurify";
import { marked } from "marked";
import {
  Boxes,
  Camera,
  Check,
  ClipboardCopy,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  Edit3,
  Film,
  Image as ImageIcon,
  Info,
  LogOut,
  Loader2,
  Maximize2,
  MousePointer2,
  Move,
  Pentagon,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings,
  Sparkles,
  Tags,
  Trash2,
  Upload,
  UserRound,
  MessageSquare,
  Volume2,
  Waypoints,
  ZoomIn,
  ZoomOut,
} from "@lucide/vue";
import ChatPage from "./components/ChatPage.vue";
import LiveGesturePage from "./components/LiveGesturePage.vue";
import {
  ApiRequestError,
  type AuthUser,
  type ImageAsset,
  type ImageReviewStatus,
  type ImageTaskResult,
  type ImageTaskResultVersion,
  type ImageTaskStatus,
  type ImageTaskType,
  type LabelConfig,
  type LocalModelCatalog,
  type VideoTermCandidate,
  type VideoCaptionBatch,
  type VideoCaptionFrame,
  type VideoCaptionVideo,
  type TrainingImage,
  type TrainingMetric,
  type TrainingTask,
  type TrainingTaskType,
  assetUrl,
  createImageTask,
  createLabel,
  copyLabel,
  deleteLabel,
  deleteImage,
  getTaskResult,
  getTaskResultVersion,
  inferImageTask,
  getCurrentUser,
  listImages,
  listLocalModels,
  listLabels,
  listUsers,
  listTaskResultVersions,
  listVideoCaptionBatches,
  listVideoCaptionFrames,
  listVideoCaptionVideos,
  searchLabels,
  listVideoTermCandidates,
  findLabelThumbnail,
  findMissingLabelThumbnails,
  updateVideoCaptionFrameReview,
  translateVideoCaptionFrame,
  login,
  logout,
  register,
  restoreTaskResultVersion,
  reviewTaskResult,
  saveTaskResult,
  submitTaskResult,
  updateAnnotation,
  updateLabel,
  updateUserRole,
  uploadImage,
  listTrainingImages,
  listTrainingTasks,
  getTrainingTask,
  createTrainingTask,
} from "./api";

type PageMode = "workspace" | "videoCaptions" | "chat" | "liveGesture" | "settings" | "training";
type AnnotationTool = "select" | "pan" | "box" | "polygon" | "line" | "brush" | "pose-point";
type ShapeType = "box" | "polygon" | "line" | "brush";
type ResizeSide = "history" | "thumbnail";
type AuthMode = "login" | "register";
type UiLanguage = "zh" | "en";

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
  reviewStatus: ImageReviewStatus;
  reviewComment: string;
  submittedAt: string | null;
  reviewedAt: string | null;
};

type Point = { x: number; y: number };
type PoseKeypoint = Point & { name: string; score: number };
type PoseSkeletonLine = {
  name: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  score: number;
};
type AnnotationShape = {
  id: string;
  type: ShapeType;
  labelId: number | null;
  label: string;
  points: Point[];
  score?: number;
  source: "ai" | "manual" | "edited";
};

const taskConfigs: TaskConfig[] = [
  { type: "detection", title: "目标检测", description: "检测框、类别与置信度", models: [] },
  { type: "segmentation", title: "实例分割", description: "区域掩码、轮廓与类别", models: [] },
  { type: "pose", title: "姿态识别", description: "关键点与骨架连线", models: [] },
  {
    type: "caption",
    title: "图像描述",
    description: "生成图片描述文本",
    models: [],
  },
];

const poseSkeletonPairs = [
  ["left_shoulder", "right_shoulder"],
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
  ["left_shoulder", "left_hip"],
  ["right_shoulder", "right_hip"],
  ["left_hip", "right_hip"],
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
  ["nose", "left_eye"],
  ["nose", "right_eye"],
  ["left_eye", "left_ear"],
  ["right_eye", "right_ear"],
];

const currentPage = ref<PageMode>("workspace");
const currentTaskType = ref<ImageTaskType>("detection");
const selectedModelByTask = reactive<Record<ImageTaskType, string>>({
  detection: "yolo11n",
  segmentation: "yolo11n-seg",
  pose: "yolo11n-pose",
  classification: "yolo11n-cls",
  caption: "deepseek-vl2-tiny",
});

const imageHistoryList = ref<ImageAsset[]>([]);
const imageHistoryPage = ref(1);
const imageHistoryTotal = ref(0);
const imageHistoryPageSize = ref(30);
const imageHistoryPageSizeInput = ref("30");
const imageHistoryQuery = ref("");
const imageHistoryPageInput = ref("1");
const uiLanguage = ref<UiLanguage>("zh");
const localModelCatalog = ref<LocalModelCatalog>({ detection: [], segmentation: [], pose: [], classification: [], caption: [] });
const labels = ref<LabelConfig[]>([]);
const activeRequestCount = ref(0);
const loading = computed(() => activeRequestCount.value > 0);
const processingOverlayText = ref("");
const message = ref("");
const errorDialog = ref("");
const historyCollapsed = ref(false);
const thumbnailCollapsed = ref(false);
const presetPopoverOpen = ref(false);
const workspaceBodyRef = ref<HTMLElement | null>(null);
const panelLayout = reactive({
  historyWidth: 320,
  thumbnailWidth: 300,
  resizing: null as ResizeSide | null,
});
const originalPreview = ref<ImageAsset | null>(null);
const imageInfoDialogTarget = ref<ImageAsset | null>(null);
const videoPreviewUrl = ref("");
const videoPreviewTitle = ref("");
const activeTool = ref<AnnotationTool>("select");
const selectedShapeId = ref<string | null>(null);
const selectedClassificationLabelIds = computed<number[]>({
  get: () => {
    const saved = currentState.value.annotationJson?.classificationLabels as number[] | undefined;
    if (saved) return saved.map(Number);
    const resultNames = resultLabels().map((item) => item.label);
    return labels.value.filter((label) => resultNames.includes(label.englishName) || resultNames.includes(label.chineseName)).map((label) => label.labelId);
  },
  set: (value) => {
    currentState.value.annotationJson = { ...(currentState.value.annotationJson ?? emptyAnnotation()), classificationLabels: value, updatedAt: new Date().toISOString() };
  },
});
const activePresetLabelId = ref<number | null>(null);
const draftShape = ref<AnnotationShape | null>(null);
const polygonDraft = ref<Point[]>([]);
const drawing = reactive({ active: false, mode: "" as "" | "draw" | "move" | "resize", shapeId: "", start: null as Point | null });
const poseDraggingName = ref("");
const selectedPosePointName = ref("");
const poseDrawingPerson = ref<number | null>(null);
const poseDrawingIndex = ref(0);

const labelForm = reactive({
  englishName: "",
  chineseName: "",
  description: "",
});
const workspaceLabelFormOpen = ref(false);
const editingLabelId = ref<number | null>(null);
const editingLabel = reactive({ englishName: "", chineseName: "", description: "" });
const currentUser = ref<AuthUser | null>(null);
const authReady = ref(false);
const authMode = ref<AuthMode>("login");
const authForm = reactive({ username: "", displayName: "", password: "" });
const users = ref<AuthUser[]>([]);
const trainingType = ref<TrainingTaskType>("detection");
const trainingImages = ref<TrainingImage[]>([]);
const trainingValImages = ref<TrainingImage[]>([]);
const trainingImageTotal = ref(0);
const trainingValImageTotal = ref(0);
const trainingImagePage = ref(1);
const trainingValImagePage = ref(1);
const trainingImagePageSize = 30;
const trainingImageQuery = ref("");
const trainingImageShuffle = ref(false);
const trainingValImageShuffle = ref(false);
const trainingImageDetail = ref<TrainingImage | null>(null);
const trainingMetricDetail = ref<{ task: TrainingTask; metrics: TrainingMetric[] } | null>(null);
const trainingMetricHover = ref<number | null>(null);
const trainingTasks = ref<TrainingTask[]>([]);
const selectedTrainIds = ref<string[]>([]);
const selectedValIds = ref<string[]>([]);
const selectedTrainingId = ref("");
const trainingMetrics = ref<TrainingMetric[]>([]);
const trainingForm = reactive({ name: "railway-training", modelName: "yolo11n.pt", epochs: 50, batchSize: 8, imageSize: 640 });
const reviewCommentInput = ref("");
const videoCaptionBatches = ref<VideoCaptionBatch[]>([]);
const videoCaptionVideos = ref<VideoCaptionVideo[]>([]);
const videoCaptionFrames = ref<VideoCaptionFrame[]>([]);
const selectedVideoCaptionBatchId = ref("");
const selectedVideoCaptionVideoId = ref("");
const selectedVideoCaptionFrameId = ref("");
const videoCaptionQuery = ref("");
const videoCaptionTotal = ref(0);
const videoCaptionPage = ref(1);
const videoCaptionPageSize = ref(20);
const lightboxStageEl = ref<HTMLElement | null>(null);
const frameZoomTarget = computed(() => lightboxStageEl.value);
const frameView = reactive({ zoom: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, originX: 0, originY: 0 });
const lightboxFrameId = ref("");
const lightboxTaskType = ref<"detection" | "segmentation" | "pose" | "original">("detection");
const manualFrameDescription = ref("");
const frameSafetyScore = ref<number | null>(null);
const frameReviewBusy = ref(false);
const frameTranslationBusy = ref(false);
const settingsLabelRecords = ref<LabelConfig[]>([]);
const settingsLabelTotal = ref(0);
const settingsLabelPage = ref(1);
const settingsLabelPageSize = 20;
const settingsLabelQuery = ref("");
const termCandidates = ref<VideoTermCandidate[]>([]);
const termCandidateTotal = ref(0);
const termCandidatePage = ref(1);
const termCandidateQuery = ref("");
const labelThumbnailBusyId = ref<number | null>(null);
const allLabelThumbnailsBusy = ref(false);
watch(selectedVideoCaptionFrameId, () => resetFrameView());

const defaultSessionId = "default";
const taskStates = reactive<Record<ImageTaskType, TaskState>>({
  detection: createDefaultTaskState(),
  segmentation: createDefaultTaskState(),
  pose: createDefaultTaskState(),
  classification: createDefaultTaskState(),
  caption: createDefaultTaskState(),
});

const currentState = computed(() => taskStates[currentTaskType.value]);
const currentConfig = computed(() => taskConfigs.find((item) => item.type === currentTaskType.value) ?? taskConfigs[0]);
function taskTitle(task: ImageTaskType) {
  const titles: Record<ImageTaskType, [string, string]> = {
    detection: ["目标检测", "Object Detection"],
    segmentation: ["实例分割", "Instance Segmentation"],
    pose: ["姿态识别", "Pose Estimation"],
    classification: ["图像分类", "Image Classification"],
    caption: ["图像描述", "Image Captioning"],
  };
  return titles[task][uiLanguage.value === "zh" ? 0 : 1];
}
const currentConfigTitle = computed(() => taskTitle(currentTaskType.value));
function taskDescription(task: ImageTaskType) {
  const descriptions: Record<ImageTaskType, string> = {
    detection: "Detection boxes, classes, and confidence scores",
    segmentation: "Instance masks, contours, and classes",
    pose: "Keypoints and skeleton connections",
    classification: "Class labels and probabilities",
    caption: "Generate a natural-language image caption",
  };
  return descriptions[task];
}
function labelDescription(description: string) {
  const parts = description.split(" / ");
  if (parts.length < 2) return description;
  return uiLanguage.value === "zh" ? parts.slice(1).join(" / ") : parts[0];
}
function uiText(chinese: string, english: string) {
  return uiLanguage.value === "zh" ? chinese : english;
}
function uiNotice(value: string) {
  if (uiLanguage.value === "zh" || !value) return value;
  const exact: Record<string, string> = {
    "已退出登录": "Signed out",
    "上传完成，原图已保存": "Upload complete; original image saved",
    "图片及关联标注数据已删除": "Image and linked annotations deleted",
    "任务结果已加载": "Task result loaded",
    "当前图片暂无该任务结果": "No result for this image and task",
    "请先上传或选择图片": "Upload or select an image first",
    "AI 结果已生成并保存，可继续人工校验": "AI result generated and saved; ready for human review",
    "当前任务结果已保存": "Task result saved",
    "标注已保存": "Annotation saved",
    "用户角色已更新": "User role updated",
    "已提交审核": "Submitted for review",
    "审核已通过，结果已锁定": "Review approved; result is locked",
    "已驳回并返回修改": "Rejected and returned for revision",
    "视频解帧批次已加载": "Video frame batches loaded",
    "人工描述和安全评分已保存": "Manual caption and safety score saved",
    "保存失败": "Save failed",
    "英文翻译失败": "English translation failed",
    "缩略图检索失败": "Thumbnail lookup failed",
    "批量缩略图检索失败": "Batch thumbnail lookup failed",
    "标签已新增": "Label added",
    "标签已复制": "Label duplicated",
    "标签已更新": "Label updated",
    "标签已删除": "Label deleted",
    "多边形至少需要 3 个点": "A polygon requires at least 3 points",
    "暂无可播放的图像描述": "No image caption to play",
    "当前浏览器不支持语音播放": "Speech playback is not supported in this browser",
    "语音播放失败": "Speech playback failed",
    "审核员只能查看和审核任务": "Reviewers can only view and review tasks",
    "审核通过的结果已锁定": "Approved results are locked",
  };
  if (exact[value]) return exact[value];
  const added = value.match(/^已添加标签：(.+)$/);
  if (added) return `Label added: ${added[1]}`;
  const copied = value.match(/^已复制标签：(.+)$/);
  if (copied) return `Copied label: ${copied[1]}`;
  const version = value.match(/^正在查看历史版本 v(.+)$/);
  if (version) return `Viewing version ${version[1]}`;
  const restored = value.match(/^已恢复为新版本 v(.+)$/);
  if (restored) return `Restored as new version ${restored[1]}`;
  return value;
}
function persistUiLanguage() {
  window.localStorage.setItem("railway-ui-language", uiLanguage.value);
}
function labelDisplay(label: Pick<LabelConfig, "englishName" | "chineseName">) {
  return uiLanguage.value === "zh" ? label.chineseName : label.englishName;
}
const detectionLabelZh: Record<string, string> = {
  person: "人员", train: "列车", car: "车辆", truck: "卡车", bus: "公交车", traffic: "交通设施",
  "traffic light": "信号灯", refrigerator: "铁路设备", chair: "座椅", bench: "站台座椅", oven: "设备",
  "dining table": "作业台", tv: "显示屏", bottle: "瓶体", backpack: "背包", suitcase: "工具箱",
  "fire hydrant": "消防栓", bicycle: "自行车", motorcycle: "摩托车",
};
function detectionLabelDisplay(value: unknown) {
  const raw = String(value ?? "目标");
  if (uiLanguage.value !== "zh") return raw;
  const configured = labels.value.find((item) => item.englishName === raw || item.chineseName === raw);
  return configured?.chineseName ?? detectionLabelZh[raw.toLowerCase()] ?? raw;
}
function shapeDisplayLabel(shape: AnnotationShape) {
  const label = labels.value.find((item) => item.labelId === shape.labelId)
    ?? labels.value.find((item) => item.englishName === shape.label || item.chineseName === shape.label);
  if (label) return labelDisplay(label);
  return detectionLabelDisplay(uiLanguage.value === "zh" ? shape.label.split(" / ").at(-1) ?? shape.label : shape.label.split(" / ")[0]);
}
const currentImageUrl = computed(() => assetUrl(currentState.value.imageUrl));
const workspaceGridStyle = computed(() => ({
  gridTemplateColumns: `${historyCollapsed.value ? 48 : panelLayout.historyWidth}px 6px minmax(360px, 1fr) 6px ${
    thumbnailCollapsed.value ? 48 : panelLayout.thumbnailWidth
  }px`,
}));
const captionIsTransferring = computed(() => currentTaskType.value === "caption" && (loading.value || currentState.value.status === "processing"));
const view = reactive({ zoom: 1, x: 0, y: 0, dragging: false, startX: 0, startY: 0, originX: 0, originY: 0 });

const annotationShapes = computed(() => readShapes(currentState.value.annotationJson));
const selectedShape = computed(() => annotationShapes.value.find((shape) => shape.id === selectedShapeId.value) ?? null);
const activePresetLabel = computed(() => labels.value.find((label) => label.labelId === activePresetLabelId.value) ?? labels.value[0] ?? null);
const presetLabels = computed(() =>
  labels.value.map((label, index) => ({
    label,
    shortcut: labelShortcut(index),
  })),
);
const selectedLabelId = computed({
  get: () => selectedShape.value?.labelId ?? "",
  set: (value: string | number) => {
    if (!selectedShape.value) return;
    if (value === "") {
      updateShape(selectedShape.value.id, {
        labelId: null,
        label: selectedShape.value.label,
        source: "edited",
      });
      return;
    }
    const label = labels.value.find((item) => item.labelId === Number(value));
    if (label) selectPresetLabel(label);
  },
});
const selectedVideoCaptionBatch = computed(
  () => videoCaptionBatches.value.find((batch) => batch.batchId === selectedVideoCaptionBatchId.value) ?? null,
);
const selectedVideoCaptionVideo = computed(
  () => videoCaptionVideos.value.find((video) => video.videoId === selectedVideoCaptionVideoId.value) ?? null,
);
const selectedVideoCaptionFrame = computed(
  () => videoCaptionFrames.value.find((frame) => frame.frameId === selectedVideoCaptionFrameId.value) ?? null,
);
const canReview = computed(() => currentUser.value?.role === "reviewer" || currentUser.value?.role === "admin");
const isAdmin = computed(() => currentUser.value?.role === "admin");
const resultLocked = computed(() => currentState.value.reviewStatus === "approved");
const editingDisabled = computed(() => resultLocked.value || currentUser.value?.role === "reviewer");

watch(selectedShape, (shape) => {
  if (shape?.labelId !== null && shape?.labelId !== undefined && labels.value.some((label) => label.labelId === shape.labelId)) {
    activePresetLabelId.value = shape.labelId;
  }
});

onMounted(async () => {
  window.addEventListener("keydown", handleGlobalKeydown);
  uiLanguage.value = localStorage.getItem("railway-ui-language") === "en" ? "en" : "zh";
  await restoreLoginState();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
  stopPanelResize();
});

async function restoreLoginState() {
  try {
    currentUser.value = await getCurrentUser();
  } catch (error) {
    currentUser.value = null;
    const detail = error instanceof Error && error.message ? error.message : "登录状态检查失败";
    message.value = detail;
  } finally {
    // The auth gate must not wait for optional workspace data to finish loading.
    authReady.value = true;
  }
  if (currentUser.value) {
    await runBusy(() => initializeAuthenticatedWorkspace(), "工作区数据加载失败");
  }
}

async function initializeAuthenticatedWorkspace() {
  await Promise.all([loadLabels(), loadImageHistory(), loadLocalModelCatalog()]);
  const first = imageHistoryList.value[0];
  if (first) await selectImage(first);
}

async function submitAuth() {
  const username = authForm.username.trim();
  const password = authForm.password;
  if (!username || !password) {
    const detail = "请输入账号和密码";
    message.value = detail;
    errorDialog.value = detail;
    return;
  }
  if (authMode.value === "register" && !authForm.displayName.trim()) {
    const detail = "请输入姓名";
    message.value = detail;
    errorDialog.value = detail;
    return;
  }
  await runBusy(async () => {
    currentUser.value =
      authMode.value === "login"
        ? await login({ username, password })
        : await register({
            username,
            displayName: authForm.displayName.trim(),
            password,
          });
    authForm.password = "";
    currentPage.value = "workspace";
    await initializeAuthenticatedWorkspace();
    message.value = `欢迎，${currentUser.value.displayName}`;
  }, authMode.value === "login" ? "登录失败" : "注册失败");
}

function switchAuthMode(mode: AuthMode) {
  authMode.value = mode;
  errorDialog.value = "";
  message.value = "";
}

async function signOut() {
  await runBusy(async () => {
    await logout();
    currentUser.value = null;
    imageHistoryList.value = [];
    labels.value = [];
    for (const state of Object.values(taskStates)) Object.assign(state, createDefaultTaskState());
    authForm.password = "";
    message.value = "已退出登录";
  }, "退出登录失败");
}

async function setTaskType(taskType: ImageTaskType) {
  currentTaskType.value = taskType;
  imageHistoryPage.value = 1;
  activeTool.value = "select";
  selectedShapeId.value = null;
  message.value = "";
  await loadImageHistory();
  const state = currentState.value;
  if (!state.currentImageId && imageHistoryList.value[0]) await selectImage(imageHistoryList.value[0]);
}

async function setPage(page: PageMode) {
  currentPage.value = page;
  message.value = "";
  if (page === "videoCaptions" && videoCaptionBatches.value.length === 0) {
    await loadVideoCaptionBatches();
  }
  if (page === "settings") {
    await Promise.all([loadSettingsLabelPage(), loadTermCandidates()]);
    if (isAdmin.value) await loadUsers();
  }
  if (page === "training") await loadTrainingWorkspace();
}

async function loadTrainingWorkspace() {
  await runBusy(async () => {
    const [images, validationImages, tasks] = await Promise.all([
      listTrainingImages(trainingType.value, trainingImagePage.value, trainingImagePageSize, trainingImageQuery.value, trainingImageShuffle.value),
      listTrainingImages(trainingType.value, trainingValImagePage.value, trainingImagePageSize, trainingImageQuery.value, trainingValImageShuffle.value),
      listTrainingTasks(),
    ]);
    trainingImages.value = images.records;
    trainingValImages.value = validationImages.records;
    trainingImageTotal.value = images.total;
    trainingValImageTotal.value = validationImages.total;
    trainingTasks.value = tasks;
  }, "训练数据加载失败");
}

async function changeTrainingType() {
  selectedTrainIds.value = [];
  selectedValIds.value = [];
  trainingImagePage.value = 1;
  trainingValImagePage.value = 1;
  await loadTrainingWorkspace();
}

async function searchTrainingImages() {
  trainingImagePage.value = 1;
  trainingValImagePage.value = 1;
  await loadTrainingWorkspace();
}

async function changeTrainingImagePage(page: number) {
  trainingImagePage.value = Math.max(1, Math.min(Math.max(1, Math.ceil(trainingImageTotal.value / trainingImagePageSize)), page));
  await loadTrainingWorkspace();
}

async function changeTrainingValPage(page: number) {
  trainingValImagePage.value = Math.max(1, Math.min(Math.max(1, Math.ceil(trainingValImageTotal.value / trainingImagePageSize)), page));
  await loadTrainingWorkspace();
}

async function randomizeTrainingSet(target: "train" | "val") {
  if (target === "train") { trainingImageShuffle.value = true; trainingImagePage.value = 1; }
  else { trainingValImageShuffle.value = true; trainingValImagePage.value = 1; }
  await loadTrainingWorkspace();
}

function removeUnannotatedFromCurrentPage(target: "train" | "val") {
  const items = target === "train" ? trainingImages.value : trainingValImages.value;
  const ids = items.filter((item) => !item.resultJson || Object.keys(item.resultJson).length === 0).map((item) => item.imageId);
  if (target === "train") selectedTrainIds.value = selectedTrainIds.value.filter((id) => !ids.includes(id));
  else selectedValIds.value = selectedValIds.value.filter((id) => !ids.includes(id));
  message.value = uiText(`已排除本页 ${ids.length} 张无标注图片`, `Excluded ${ids.length} unannotated images on this page`);
}

async function openTrainingMetricDetail(trainingId: string) {
  trainingMetricDetail.value = await getTrainingTask(trainingId);
  trainingMetricHover.value = null;
}

function metricChartPoints(field: "trainLoss" | "precision" | "recall" | "map50") {
  const values = (trainingMetricDetail.value?.metrics ?? []).map((metric) => Number(metric[field] ?? 0));
  if (!values.length) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values.map((value, index) => `${(index / Math.max(1, values.length - 1)) * 100},${96 - ((value - min) / span) * 88}`).join(" ");
}

function toggleTrainingId(target: "train" | "val", imageId: string) {
  const ref = target === "train" ? selectedTrainIds : selectedValIds;
  const other = target === "train" ? selectedValIds : selectedTrainIds;
  if (ref.value.includes(imageId)) ref.value = ref.value.filter((id) => id !== imageId);
  else { other.value = other.value.filter((id) => id !== imageId); ref.value = [...ref.value, imageId]; }
}

async function startTraining() {
  if (!trainingForm.name.trim() || selectedTrainIds.value.length === 0 || selectedValIds.value.length === 0) {
    message.value = uiText("请填写名称并至少选择训练集和验证集各一张图片", "Enter a name and select at least one train and validation image");
    return;
  }
  await runBusy(async () => {
    const task = await createTrainingTask({ name: trainingForm.name.trim(), taskType: trainingType.value, modelName: trainingForm.modelName, trainImageIds: selectedTrainIds.value, valImageIds: selectedValIds.value, epochs: trainingForm.epochs, batchSize: trainingForm.batchSize, imageSize: trainingForm.imageSize });
    trainingTasks.value = [task, ...trainingTasks.value];
    selectedTrainingId.value = task.trainingId;
    message.value = uiText("训练任务已启动", "Training task started");
    await pollTrainingTask(task.trainingId);
  }, "训练任务启动失败");
}

function runTrainingSmokeTest() {
  const problems: string[] = [];
  if (!trainingForm.name.trim()) problems.push(uiText("任务名称为空", "run name is empty"));
  if (!trainingForm.modelName) problems.push(uiText("未选择基础模型", "no base model selected"));
  if (!selectedTrainIds.value.length) problems.push(uiText("训练集为空", "training set is empty"));
  if (!selectedValIds.value.length) problems.push(uiText("验证集为空", "validation set is empty"));
  message.value = problems.length ? `${uiText("冒烟测试失败", "Smoke test failed")}: ${problems.join("、")}` : uiText("冒烟测试通过：配置、训练集和验证集均可用", "Smoke test passed: configuration and datasets are ready");
}

async function pollTrainingTask(trainingId: string) {
  const refresh = async () => { const detail = await getTrainingTask(trainingId); trainingMetrics.value = detail.metrics; trainingTasks.value = trainingTasks.value.map((task) => task.trainingId === trainingId ? detail.task : task); return detail.task.status; };
  let status = await refresh();
  while (status === "queued" || status === "running") { await new Promise((resolve) => window.setTimeout(resolve, 2000)); status = await refresh(); }
}

async function refreshSettingsData() {
  await runBusy(async () => {
    await Promise.all([loadLabels(), loadSettingsLabelPage(), loadTermCandidates()]);
  }, "标签配置刷新失败");
}

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  const error = validateImage(file);
  if (error) {
    message.value = error;
    errorDialog.value = error;
    return;
  }
  await runBusy(async () => {
    const image = await uploadImage(file, currentTaskType.value, defaultSessionId);
    await bindImageToCurrentTask(image);
    imageHistoryPage.value = 1;
    await loadImageHistory();
    message.value = "上传完成，原图已保存";
  }, "图片上传失败，请稍后重试");
}

async function loadImageHistory() {
  await runBusy(async () => {
    const data = await listImages({ taskType: currentTaskType.value, page: imageHistoryPage.value, pageSize: imageHistoryPageSize.value, query: imageHistoryQuery.value });
    imageHistoryList.value = data.records;
    imageHistoryTotal.value = data.total;
  }, "历史图片加载失败");
}

async function searchImageHistory() {
  imageHistoryPage.value = 1;
  await loadImageHistory();
}

async function changeImageHistoryPageSize(event: Event) {
  const size = Number((event.target as HTMLInputElement).value);
  if (!Number.isInteger(size) || size < 1 || size > 200) {
    imageHistoryPageSizeInput.value = String(imageHistoryPageSize.value);
    return;
  }
  if (size === imageHistoryPageSize.value) return;
  imageHistoryPageSize.value = size;
  imageHistoryPageSizeInput.value = String(size);
  imageHistoryPage.value = 1;
  await loadImageHistory();
}

async function loadLocalModelCatalog() {
  localModelCatalog.value = await listLocalModels();
  for (const config of taskConfigs) config.models = localModelCatalog.value[config.type];
  for (const config of taskConfigs) {
    if (!config.models.includes(selectedModelByTask[config.type])) {
      selectedModelByTask[config.type] = config.models[0] ?? "";
    }
  }
}

async function changeImageHistoryPage(page: number) {
  const lastPage = Math.max(1, Math.ceil(imageHistoryTotal.value / imageHistoryPageSize.value));
  imageHistoryPage.value = Math.min(lastPage, Math.max(1, page));
  imageHistoryPageInput.value = String(imageHistoryPage.value);
  await loadImageHistory();
}

async function jumpImageHistoryPage() {
  const page = Number(imageHistoryPageInput.value);
  if (!Number.isInteger(page) || page < 1) {
    imageHistoryPageInput.value = String(imageHistoryPage.value);
    return;
  }
  await changeImageHistoryPage(page);
}

async function removeHistoryImage(image: ImageAsset) {
  if (!window.confirm(`删除“${image.originalName}”及其识别结果、标注版本和文件？此操作不可撤销。`)) return;
  await runBusy(async () => {
    await deleteImage(image.imageId);
    if (currentState.value.currentImageId === image.imageId) {
      for (const state of Object.values(taskStates)) Object.assign(state, createDefaultTaskState());
    }
    if (imageHistoryList.value.length === 1 && imageHistoryPage.value > 1) imageHistoryPage.value -= 1;
    await loadImageHistory();
    message.value = "图片及关联标注数据已删除";
  }, "删除图片失败");
}

async function selectImage(image: ImageAsset) {
  await runBusy(async () => {
    await bindImageToCurrentTask(image);
    const sessionId = image.sessionId || defaultSessionId;
    const result = await getTaskResult({
      imageId: image.imageId,
      taskType: currentTaskType.value,
      sessionId,
    });
    applyTaskResult(result);
    await loadCurrentVersions(sessionId);
    message.value = result ? "任务结果已加载" : "当前图片暂无该任务结果";
    resetView();
  }, "图片或任务结果加载失败");
}

async function runCurrentTask() {
  if (!currentState.value.currentImageId) {
    message.value = "请先上传或选择图片";
    return;
  }
  const taskTitle = currentConfig.value.title;
  const modelName = selectedModelByTask[currentTaskType.value];
  await runBusy(async () => {
    processingOverlayText.value = `${taskTitle}正在处理中，请稍候`;
    currentState.value.status = "processing";
    const result = await inferImageTask({
      imageId: currentState.value.currentImageId,
      taskType: currentTaskType.value,
      sessionId: currentImageSessionId(),
      modelName,
    });
    applyTaskResult(result);
    await loadCurrentVersions();
    await loadImageHistory();
    message.value = "AI 结果已生成并保存，可继续人工校验";
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
      : await createImageTask({
          imageId: state.currentImageId!,
          taskType: currentTaskType.value,
          sessionId: currentImageSessionId(),
        });
    state.taskId = task.taskId;
    ensureAnnotationJson();
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
    state.reviewStatus = "draft";
    state.reviewComment = "";
    state.reviewedAt = null;
    message.value = "当前任务结果已保存";
  }, "保存当前结果失败");
}

async function saveAnnotationSnapshot() {
  const state = currentState.value;
  if (!state.currentImageId) {
    message.value = "请先上传或选择图片";
    return;
  }
  await runBusy(async () => {
    if (!state.taskId) {
      const task = await createImageTask({
        imageId: state.currentImageId!,
        taskType: currentTaskType.value,
        sessionId: currentImageSessionId(),
      });
      state.taskId = task.taskId;
    }
    ensureAnnotationJson();
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
    state.annotationJson = emptyAnnotation();
    state.descriptionText = "";
    state.status = "idle";
    state.activeVersionId = null;
    state.latestVersionNo = null;
    state.isViewingHistory = false;
    state.reviewStatus = "draft";
    state.reviewComment = "";
    state.submittedAt = null;
    state.reviewedAt = null;
    return;
  }
  state.taskId = result.taskId;
  state.resultImageUrl = result.resultImageUrl || "";
  state.resultJson = (result.resultJson as Record<string, unknown> | null) ?? null;
  state.annotationJson = normalizeAnnotation(result.annotationJson as Record<string, unknown> | null, state.resultJson);
  state.descriptionText = result.descriptionText || "";
  state.status = result.status || "success";
  state.activeVersionId = result.latestVersionId || null;
  state.latestVersionNo = result.latestVersionNo || null;
  state.isViewingHistory = false;
  state.reviewStatus = result.reviewStatus || "draft";
  state.reviewComment = result.reviewComment || "";
  state.submittedAt = result.submittedAt || null;
  state.reviewedAt = result.reviewedAt || null;
  reviewCommentInput.value = result.reviewComment || "";
  selectedShapeId.value = null;
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
    sessionId: currentImageSessionId(),
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
    state.annotationJson = normalizeAnnotation(version.annotationJson as Record<string, unknown> | null, state.resultJson);
    state.descriptionText = version.descriptionText || "";
    state.status = "success";
    state.activeVersionId = version.versionId;
    state.isViewingHistory = state.latestVersionNo !== version.versionNo;
    selectedShapeId.value = null;
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
  state.annotationJson = emptyAnnotation();
  state.descriptionText = "";
  state.status = "idle";
  state.versions = [];
  state.activeVersionId = null;
  state.latestVersionNo = null;
  state.isViewingHistory = false;
  selectedShapeId.value = null;
}

async function loadLabels() {
  await runBusy(async () => {
    labels.value = await listLabels();
    if (!labels.value.some((label) => label.labelId === activePresetLabelId.value)) {
      activePresetLabelId.value = labels.value[0]?.labelId ?? null;
    }
  }, "标签加载失败");
}

async function loadUsers() {
  if (!isAdmin.value) return;
  await runBusy(async () => {
    users.value = await listUsers();
  }, "用户列表加载失败");
}

async function changeUserRole(userId: string, role: "student" | "reviewer" | "admin") {
  await runBusy(async () => {
    await updateUserRole(userId, role);
    await loadUsers();
    message.value = "用户角色已更新";
  }, "用户角色更新失败");
}

function handleRoleChange(userId: string, event: Event) {
  const role = (event.target as HTMLSelectElement).value;
  if (role === "student" || role === "reviewer" || role === "admin") void changeUserRole(userId, role);
}

async function submitForReview() {
  if (!currentState.value.taskId) return;
  await runBusy(async () => {
    applyTaskResult(await submitTaskResult(currentState.value.taskId!));
    message.value = "已提交审核";
  }, "提交审核失败");
}

async function reviewCurrentResult(status: "approved" | "rejected") {
  if (!currentState.value.taskId) return;
  await runBusy(async () => {
    applyTaskResult(await reviewTaskResult(currentState.value.taskId!, status, reviewCommentInput.value));
    message.value = status === "approved" ? "审核已通过，结果已锁定" : "已驳回并返回修改";
  }, "审核操作失败");
}

async function loadVideoCaptionBatches() {
  await runBusy(async () => {
    videoCaptionBatches.value = await listVideoCaptionBatches();
    if (!selectedVideoCaptionBatchId.value && videoCaptionBatches.value[0]) {
      selectedVideoCaptionBatchId.value = videoCaptionBatches.value[0].batchId;
    }
    if (selectedVideoCaptionBatchId.value) await loadVideoCaptionVideos();
    message.value = "视频解帧批次已加载";
  }, "视频解帧批次加载失败");
}

async function loadVideoCaptionVideos() {
  if (!selectedVideoCaptionBatchId.value) {
    videoCaptionVideos.value = [];
    videoCaptionFrames.value = [];
    selectedVideoCaptionVideoId.value = "";
    selectedVideoCaptionFrameId.value = "";
    return;
  }
  videoCaptionVideos.value = await listVideoCaptionVideos(selectedVideoCaptionBatchId.value);
  if (!videoCaptionVideos.value.some((video) => video.videoId === selectedVideoCaptionVideoId.value)) {
    selectedVideoCaptionVideoId.value = videoCaptionVideos.value[0]?.videoId ?? "";
  }
  await loadVideoCaptionFrames();
}

async function selectVideoCaptionBatch(batchId: string) {
  selectedVideoCaptionBatchId.value = batchId;
  selectedVideoCaptionVideoId.value = "";
  selectedVideoCaptionFrameId.value = "";
  await runBusy(loadVideoCaptionVideos, "视频列表加载失败");
}

async function selectVideoCaptionVideo(videoId: string) {
  selectedVideoCaptionVideoId.value = videoId;
  selectedVideoCaptionFrameId.value = "";
  videoCaptionPage.value = 1;
  await runBusy(loadVideoCaptionFrames, "视频帧加载失败");
}

async function loadVideoCaptionFrames() {
  if (!selectedVideoCaptionVideoId.value) {
    videoCaptionFrames.value = [];
    selectedVideoCaptionFrameId.value = "";
    videoCaptionTotal.value = 0;
    return;
  }
  const data = await listVideoCaptionFrames({
    videoId: selectedVideoCaptionVideoId.value,
    page: videoCaptionPage.value,
    pageSize: videoCaptionPageSize.value,
    query: videoCaptionQuery.value.trim(),
  });
  videoCaptionFrames.value = data.records;
  videoCaptionTotal.value = data.total;
  if (!videoCaptionFrames.value.some((frame) => frame.frameId === selectedVideoCaptionFrameId.value)) {
    selectedVideoCaptionFrameId.value = videoCaptionFrames.value[0]?.frameId ?? "";
  }
}

async function searchVideoCaptionFrames() {
  videoCaptionPage.value = 1;
  await runBusy(loadVideoCaptionFrames, "帧描述检索失败");
}

async function changeVideoCaptionPage(page: number) {
  const lastPage = Math.max(1, Math.ceil(videoCaptionTotal.value / videoCaptionPageSize.value));
  videoCaptionPage.value = Math.min(lastPage, Math.max(1, page));
  await runBusy(loadVideoCaptionFrames, "视频帧分页加载失败");
}

async function changeVideoCaptionPageSize(event: Event) {
  const pageSize = Number((event.target as HTMLSelectElement).value);
  if (![10, 20, 30, 50].includes(pageSize) || pageSize === videoCaptionPageSize.value) return;
  videoCaptionPageSize.value = pageSize;
  videoCaptionPage.value = 1;
  await runBusy(loadVideoCaptionFrames, "视频帧分页加载失败");
}

function selectVideoCaptionFrame(frameId: string) {
  selectedVideoCaptionFrameId.value = frameId;
  const frame = videoCaptionFrames.value.find((item) => item.frameId === frameId);
  if (frame) openFrameLightbox(frame);
}

function setFrameSafetyScore(event: Event) {
  const input = event.target as HTMLInputElement;
  if (input.value === "") {
    frameSafetyScore.value = null;
    return;
  }
  frameSafetyScore.value = Math.max(0, Math.min(10, Math.trunc(Number(input.value))));
}

function frameVisionSummary(task: "detection" | "segmentation" | "pose", listKey: string) {
  const result = selectedVideoCaptionFrame.value?.resultJson[task] as Record<string, unknown> | undefined;
  const items = result?.[listKey];
  if (!Array.isArray(items)) return result?.error ? "推理失败" : "0";
  if (task === "pose") return `${items.length} 人体姿态`;
  const labels = items.map((item) => String((item as Record<string, unknown>).label ?? "目标"));
  return `${items.length} 个：${labels.slice(0, 5).join("、")}${labels.length > 5 ? "…" : ""}`;
}

const FRAME_MIN_ZOOM = 1;
const FRAME_MAX_ZOOM = 5;
const lightboxFrame = computed(
  () => videoCaptionFrames.value.find((frame) => frame.frameId === lightboxFrameId.value) ?? null,
);
const lightboxAnalysis = computed(
  () => (lightboxFrame.value?.resultJson?.[lightboxTaskType.value] as Record<string, any> | undefined) ?? {},
);
const lightboxImageSize = computed(() => {
  const dimensions = lightboxAnalysis.value.image as { width?: number; height?: number } | undefined;
  return { width: dimensions?.width ?? lightboxFrame.value?.width ?? 1920, height: dimensions?.height ?? lightboxFrame.value?.height ?? 1080 };
});
const detectionOverlayBoxes = computed(() => (lightboxAnalysis.value.objects as Array<Record<string, any>> | undefined) ?? []);
const segmentationOverlayPolygons = computed(() => (lightboxAnalysis.value.segments as Array<Record<string, any>> | undefined) ?? []);
const poseOverlayPoints = computed(() => {
  const poses = (lightboxAnalysis.value.poses as Array<Record<string, any>> | undefined) ?? [];
  return poses.flatMap((pose, poseIndex) => ((pose.keypoints as number[][] | undefined) ?? []).map((point, index) => ({
    key: `${poseIndex}-${index}`,
    name: poseKeypointNames[index] ?? `point_${index}`,
    poseIndex,
    x: Number(point[0]),
    y: Number(point[1]),
    score: Number((pose.confidence as number[] | undefined)?.[index] ?? 1),
  })));
});
const poseKeypointNames = ["nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"];
const poseOverlayBones = computed(() => {
  const pointsByName = new Map(poseOverlayPoints.value.map((point) => [`${point.poseIndex}:${point.name}`, point]));
  const poseIndexes = new Set(poseOverlayPoints.value.map((point) => point.poseIndex));
  return poseSkeletonPairs.flatMap(([start, end], index) => {
    return [...poseIndexes].flatMap((poseIndex) => {
      const a = pointsByName.get(`${poseIndex}:${start}`);
      const b = pointsByName.get(`${poseIndex}:${end}`);
      return a && b && a.score > 0.05 && b.score > 0.05 && (a.x > 0 || a.y > 0) && (b.x > 0 || b.y > 0)
        ? [{ key: `${poseIndex}-${index}`, x1: a.x, y1: a.y, x2: b.x, y2: b.y, score: Math.min(a.score, b.score) }]
        : [];
    });
  });
});
watch(selectedVideoCaptionFrame, (frame) => {
  manualFrameDescription.value = frame?.descriptionManual ?? "";
  frameSafetyScore.value = frame?.safetyScore ?? null;
});

function resetFrameView() {
  frameView.zoom = 1;
  frameView.x = 0;
  frameView.y = 0;
}

function applyFrameZoom(target: number, anchorX: number, anchorY: number) {
  const next = Math.min(FRAME_MAX_ZOOM, Math.max(FRAME_MIN_ZOOM, Number(target.toFixed(3))));
  if (next === frameView.zoom) return;
  const scale = next / frameView.zoom;
  if (next === FRAME_MIN_ZOOM) {
    frameView.zoom = next;
    frameView.x = 0;
    frameView.y = 0;
    return;
  }
  frameView.x = anchorX - scale * (anchorX - frameView.x);
  frameView.y = anchorY - scale * (anchorY - frameView.y);
  frameView.zoom = next;
}

function zoomFrameAtCenter(factor: number, container: HTMLElement | null) {
  const rect = container?.getBoundingClientRect();
  applyFrameZoom(frameView.zoom * factor, (rect?.width ?? 0) / 2, (rect?.height ?? 0) / 2);
}

function onFrameWheel(event: WheelEvent) {
  if (!selectedVideoCaptionFrame.value) return;
  event.preventDefault();
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  applyFrameZoom(
    frameView.zoom * (event.deltaY > 0 ? 1 / 1.15 : 1.15),
    event.clientX - rect.left,
    event.clientY - rect.top,
  );
}

function onFramePointerDown(event: PointerEvent) {
  if (frameView.zoom <= FRAME_MIN_ZOOM) return;
  frameView.dragging = true;
  frameView.startX = event.clientX;
  frameView.startY = event.clientY;
  frameView.originX = frameView.x;
  frameView.originY = frameView.y;
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function onFramePointerMove(event: PointerEvent) {
  if (!frameView.dragging) return;
  frameView.x = frameView.originX + event.clientX - frameView.startX;
  frameView.y = frameView.originY + event.clientY - frameView.startY;
}

function stopFrameDrag() {
  frameView.dragging = false;
}

function openFrameLightbox(frame: VideoCaptionFrame) {
  lightboxFrameId.value = frame.frameId;
  selectedVideoCaptionFrameId.value = frame.frameId;
  lightboxTaskType.value = "detection";
  manualFrameDescription.value = frame.descriptionManual ?? "";
  frameSafetyScore.value = frame.safetyScore ?? null;
  resetFrameView();
}

function openFrameOriginal(frame: VideoCaptionFrame) {
  originalPreview.value = { imageId: frame.frameId, imageUrl: frame.imageUrl, originalName: `${selectedVideoCaptionVideo.value?.displayName || "video"}_frame_${frame.frameIndex}.jpg`, fileName: "", fileUrl: frame.imageUrl, fileSize: 0, reviewStatus: "draft", taskStatus: "success", createdAt: frame.createdAt, updatedAt: frame.updatedAt };
}

function playSelectedVideo(video: VideoCaptionVideo) {
  if (video.sourceUrl) {
    videoPreviewTitle.value = uiText("原始视频", "Original video");
    videoPreviewUrl.value = assetUrl(video.sourceUrl);
  }
}

function playPoseVideo(video: VideoCaptionVideo) {
  if (video.poseUrl) {
    videoPreviewTitle.value = uiText("姿态识别视频", "Pose recognition video");
    videoPreviewUrl.value = assetUrl(video.poseUrl);
  }
}

function closeFrameLightbox() {
  lightboxFrameId.value = "";
  resetFrameView();
}

function stepLightbox(delta: number) {
  const index = videoCaptionFrames.value.findIndex((frame) => frame.frameId === lightboxFrameId.value);
  const next = index < 0 ? null : videoCaptionFrames.value[index + delta];
  if (!next) return;
  lightboxFrameId.value = next.frameId;
  selectVideoCaptionFrame(next.frameId);
  resetFrameView();
}

function handleVideoCaptionKeydown(event: KeyboardEvent) {
  if (!lightboxFrameId.value) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeFrameLightbox();
    return;
  }
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    stepLightbox(event.key === "ArrowLeft" ? -1 : 1);
    return;
  }
  if (event.key === "+" || event.key === "=") {
    event.preventDefault();
    zoomFrameAtCenter(1.15, frameZoomTarget.value);
    return;
  }
  if (event.key === "-" || event.key === "_") {
    event.preventDefault();
    zoomFrameAtCenter(1 / 1.15, frameZoomTarget.value);
  }
}

function renderMarkdown(text: string) {
  return DOMPurify.sanitize(marked.parse(text || "暂无描述", { async: false }) as string);
}

async function saveCaptionReview() {
  if (!lightboxFrame.value) return;
  frameReviewBusy.value = true;
  try {
    const updated = await updateVideoCaptionFrameReview(lightboxFrame.value.frameId, {
      descriptionManual: manualFrameDescription.value,
      safetyScore: frameSafetyScore.value,
    });
    videoCaptionFrames.value = videoCaptionFrames.value.map((frame) => frame.frameId === updated.frameId ? updated : frame);
    message.value = "人工描述和安全评分已保存";
  } catch (error) {
    errorDialog.value = error instanceof Error ? error.message : "保存失败";
  } finally {
    frameReviewBusy.value = false;
  }
}

async function generateCaptionEnglish() {
  if (!lightboxFrame.value) return;
  frameTranslationBusy.value = true;
  try {
    const updated = await translateVideoCaptionFrame(lightboxFrame.value.frameId);
    videoCaptionFrames.value = videoCaptionFrames.value.map((frame) => frame.frameId === updated.frameId ? updated : frame);
  } catch (error) {
    errorDialog.value = error instanceof Error ? error.message : "英文翻译失败";
  } finally {
    frameTranslationBusy.value = false;
  }
}

async function loadSettingsLabelPage() {
  const result = await searchLabels({ page: settingsLabelPage.value, pageSize: settingsLabelPageSize, query: settingsLabelQuery.value.trim() });
  settingsLabelRecords.value = result.records;
  settingsLabelTotal.value = result.total;
}

async function searchSettingsLabels() {
  settingsLabelPage.value = 1;
  await loadSettingsLabelPage();
}

async function changeSettingsLabelPage(page: number) {
  const maxPage = Math.max(1, Math.ceil(settingsLabelTotal.value / settingsLabelPageSize));
  settingsLabelPage.value = Math.max(1, Math.min(maxPage, page));
  await loadSettingsLabelPage();
}

async function loadTermCandidates() {
  const result = await listVideoTermCandidates({ page: termCandidatePage.value, pageSize: 20, query: termCandidateQuery.value.trim() });
  termCandidates.value = result.records;
  termCandidateTotal.value = result.total;
}

async function searchTermCandidates() {
  termCandidatePage.value = 1;
  await loadTermCandidates();
}

async function addTermCandidate(candidate: VideoTermCandidate) {
  await runBusy(async () => {
    const created = await createLabel({ englishName: candidate.englishName, chineseName: candidate.chineseName, description: `Extracted from Chinese video captions (${candidate.occurrences} occurrences) / 从视频帧中文描述提取（${candidate.occurrences} 次）` });
    try {
      await findLabelThumbnail(created.labelId);
    } catch {
      // The label remains usable without a matching public thumbnail.
    }
    await Promise.all([loadLabels(), loadSettingsLabelPage(), loadTermCandidates()]);
    message.value = `已添加标签：${candidate.chineseName}`;
  }, "添加描述词标签失败");
}

async function lookupLabelThumbnail(labelId: number) {
  labelThumbnailBusyId.value = labelId;
  try {
    const updated = await findLabelThumbnail(labelId);
    settingsLabelRecords.value = settingsLabelRecords.value.map((label) => label.labelId === labelId ? updated : label);
    labels.value = labels.value.map((label) => label.labelId === labelId ? updated : label);
  } catch (error) {
    errorDialog.value = error instanceof Error ? error.message : "缩略图检索失败";
  } finally {
    labelThumbnailBusyId.value = null;
  }
}

async function lookupMissingLabelThumbnails() {
  allLabelThumbnailsBusy.value = true;
  try {
    const result = await findMissingLabelThumbnails();
    const byId = new Map(result.updated.map((label) => [label.labelId, label]));
    settingsLabelRecords.value = settingsLabelRecords.value.map((label) => byId.get(label.labelId) ?? label);
    labels.value = labels.value.map((label) => byId.get(label.labelId) ?? label);
    message.value = `在线搜索 ${result.searched} 个标签，找到 ${result.found} 张缩略图`;
  } catch (error) {
    errorDialog.value = error instanceof Error ? error.message : "批量缩略图检索失败";
  } finally {
    allLabelThumbnailsBusy.value = false;
  }
}

async function copyLabelText(label: LabelConfig) {
  const text = `${label.englishName}\t${label.chineseName}\t${label.description}`;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const input = document.createElement("textarea");
    input.value = text;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }
  message.value = `已复制标签：${label.chineseName}`;
}

async function copyCurrentImageInfo() {
  const image = imageInfoDialogTarget.value;
  if (!image) return;
  const text = [
    `${uiText("文件名", "File name")}: ${image.originalName}`,
    `${uiText("存储位置", "Storage path")}: ${image.filePath || image.fileUrl}`,
    `${uiText("大小", "Size")}: ${formatBytes(image.fileSize)}`,
    `${uiText("数据库", "Database")}: image_asset → image_task → image_task_result → image_task_result_version`,
    `${uiText("图片 ID", "Image ID")}: ${image.imageId}`,
  ].join("\n");
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const input = document.createElement("textarea");
    input.value = text;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }
  message.value = uiText("图片信息已复制", "Image information copied");
}

async function submitLabel() {
  await runBusy(async () => {
    await createLabel({
      englishName: labelForm.englishName.trim(),
      chineseName: labelForm.chineseName.trim(),
      description: labelForm.description.trim(),
    });
    labelForm.englishName = "";
    labelForm.chineseName = "";
    labelForm.description = "";
    await loadLabels();
    await loadSettingsLabelPage();
    message.value = "标签已新增";
  }, "新增标签失败");
}

async function submitWorkspaceLabel() {
  await runBusy(async () => {
    const created = await createLabel({ englishName: labelForm.englishName.trim(), chineseName: labelForm.chineseName.trim(), description: labelForm.description.trim() });
    labelForm.englishName = "";
    labelForm.chineseName = "";
    labelForm.description = "";
    workspaceLabelFormOpen.value = false;
    await loadLabels();
    activePresetLabelId.value = created.labelId;
    message.value = uiText("标签已添加并设为当前标签", "Label added and selected");
  }, "添加标签失败");
}

function startEditLabel(label: LabelConfig) {
  editingLabelId.value = label.labelId;
  editingLabel.englishName = label.englishName;
  editingLabel.chineseName = label.chineseName;
  editingLabel.description = label.description;
}

async function duplicateLabel(labelId: number) {
  await runBusy(async () => {
    await copyLabel(labelId);
    await loadLabels();
    await loadSettingsLabelPage();
    message.value = "标签已复制";
  }, "复制标签失败");
}

async function submitEditLabel(labelId: number) {
  await runBusy(async () => {
    await updateLabel(labelId, {
      englishName: editingLabel.englishName.trim(),
      chineseName: editingLabel.chineseName.trim(),
      description: editingLabel.description.trim(),
    });
    editingLabelId.value = null;
    await loadLabels();
    await loadSettingsLabelPage();
    message.value = "标签已更新";
  }, "更新标签失败");
}

async function removeLabel(labelId: number) {
  await runBusy(async () => {
    await deleteLabel(labelId);
    if (selectedShape.value?.labelId === labelId) selectedShapeId.value = null;
    await loadLabels();
    await loadSettingsLabelPage();
    message.value = "标签已删除";
  }, "删除标签失败");
}

function setTool(tool: AnnotationTool) {
  if (currentTaskType.value === "pose" && !["select", "pan", "pose-point"].includes(tool)) {
    activeTool.value = "select";
    return;
  }
  if (editingDisabled.value && ["box", "polygon", "line", "brush", "pose-point"].includes(tool)) {
    message.value = resultLocked.value ? "审核通过的结果已锁定" : "审核员只能查看和审核任务";
    return;
  }
  activeTool.value = tool;
  draftShape.value = null;
  polygonDraft.value = [];
  drawing.active = false;
}

function startPoseDrawing() {
  if (editingDisabled.value || currentTaskType.value !== "pose") return;
  const points = resultKeypoints();
  const personIndexes = points.map((point) => Number(point.name.match(/^person_(\d+)_/)?.[1] ?? -1)).filter((index) => index >= 0);
  poseDrawingPerson.value = personIndexes.length ? Math.max(...personIndexes) + 1 : 0;
  poseDrawingIndex.value = 0;
  selectedPosePointName.value = "";
  setTool("pose-point");
}

function addPosePoint(point: Point) {
  if (poseDrawingPerson.value === null || poseDrawingIndex.value >= poseKeypointNames.length) return;
  const name = `person_${poseDrawingPerson.value}_${poseKeypointNames[poseDrawingIndex.value]}`;
  const points = resultKeypoints().filter((item) => item.name !== name);
  points.push({ name, x: point.x, y: point.y, score: 1 });
  currentState.value.annotationJson = { ...(currentState.value.annotationJson ?? emptyAnnotation()), poseKeypoints: points, updatedAt: new Date().toISOString() };
  selectedPosePointName.value = name;
  poseDrawingIndex.value += 1;
  if (poseDrawingIndex.value >= poseKeypointNames.length) {
    poseDrawingPerson.value = null;
    activeTool.value = "select";
    message.value = uiText("17 个关键点已添加，骨架线已自动生成", "17 keypoints added; skeleton lines generated automatically");
  }
}

function onStagePointerDown(event: PointerEvent) {
  if (activeTool.value !== "pan" || !currentState.value.imageUrl) return;
  view.dragging = true;
  view.startX = event.clientX;
  view.startY = event.clientY;
  view.originX = view.x;
  view.originY = view.y;
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function onStagePointerMove(event: PointerEvent) {
  if (!view.dragging) return;
  view.x = view.originX + event.clientX - view.startX;
  view.y = view.originY + event.clientY - view.startY;
}

function stopStageDrag() {
  view.dragging = false;
}

function startPanelResize(event: PointerEvent, side: ResizeSide) {
  if ((side === "history" && historyCollapsed.value) || (side === "thumbnail" && thumbnailCollapsed.value)) return;
  event.preventDefault();
  panelLayout.resizing = side;
  window.addEventListener("pointermove", onPanelResize);
  window.addEventListener("pointerup", stopPanelResize);
}

function onPanelResize(event: PointerEvent) {
  const workspace = workspaceBodyRef.value;
  if (!workspace || !panelLayout.resizing) return;
  const rect = workspace.getBoundingClientRect();
  if (panelLayout.resizing === "history") {
    panelLayout.historyWidth = clampPanelWidth(event.clientX - rect.left - 12);
    return;
  }
  panelLayout.thumbnailWidth = clampPanelWidth(rect.right - event.clientX - 12);
}

function stopPanelResize() {
  panelLayout.resizing = null;
  window.removeEventListener("pointermove", onPanelResize);
  window.removeEventListener("pointerup", stopPanelResize);
}

function clampPanelWidth(value: number) {
  return Math.min(520, Math.max(180, Math.round(value)));
}

function onOverlayPointerDown(event: PointerEvent) {
  if (!currentState.value.imageInfo || activeTool.value === "pan") return;
  const point = svgPoint(event);
  if (!point) return;
  if (activeTool.value === "pose-point" && currentTaskType.value === "pose") {
    addPosePoint(point);
    return;
  }
  if (activeTool.value === "select") {
    selectedShapeId.value = null;
    return;
  }
  if (activeTool.value === "polygon") {
    polygonDraft.value = [...polygonDraft.value, point];
    return;
  }
  if (activeTool.value === "brush") {
    draftShape.value = makeShape("brush", [point]);
    drawing.active = true;
    drawing.mode = "draw";
    drawing.start = point;
    return;
  }
  draftShape.value = makeShape(activeTool.value === "line" ? "line" : "box", [point, point]);
  drawing.active = true;
  drawing.mode = "draw";
  drawing.start = point;
}

function onOverlayPointerMove(event: PointerEvent) {
  const point = svgPoint(event);
  if (!point) return;
  if (poseDraggingName.value) {
    const next = resultKeypoints().map((item) => item.name === poseDraggingName.value ? { ...item, x: point.x, y: point.y, score: 1 } : item);
    currentState.value.annotationJson = { ...(currentState.value.annotationJson ?? emptyAnnotation()), poseKeypoints: next, updatedAt: new Date().toISOString() };
    return;
  }
  if (draftShape.value && drawing.mode === "draw") {
    draftShape.value = { ...draftShape.value, points: activeTool.value === "brush" ? [...draftShape.value.points, point] : [draftShape.value.points[0], point] };
    return;
  }
  if (drawing.mode === "move" && drawing.start) moveSelectedShape(point);
  if (drawing.mode === "resize" && drawing.start) resizeSelectedBox(point);
}

function onOverlayPointerUp() {
  poseDraggingName.value = "";
  if (draftShape.value && drawing.mode === "draw") {
    const shape = draftShape.value.type === "brush"
      ? { ...draftShape.value, points: [...draftShape.value.points, draftShape.value.points[0]] }
      : normalizeShapePoints(draftShape.value);
    if (shape.points.length >= 2 && (shape.type === "brush" || shapeSize(shape) > 6)) addShape(shape);
    draftShape.value = null;
  }
  drawing.active = false;
  drawing.mode = "";
  drawing.start = null;
}

function finishPolygon() {
  if (polygonDraft.value.length < 3) {
    message.value = "多边形至少需要 3 个点";
    return;
  }
  addShape(makeShape("polygon", polygonDraft.value));
  polygonDraft.value = [];
  activeTool.value = "select";
}

function cancelPolygon() {
  polygonDraft.value = [];
}

function startMoveShape(event: PointerEvent, shapeId: string) {
  if (activeTool.value !== "select") return;
  const point = svgPoint(event);
  if (!point) return;
  selectedShapeId.value = shapeId;
  drawing.active = true;
  drawing.mode = "move";
  drawing.shapeId = shapeId;
  drawing.start = point;
}

function startResizeBox(event: PointerEvent, shapeId: string) {
  const point = svgPoint(event);
  if (!point) return;
  selectedShapeId.value = shapeId;
  drawing.active = true;
  drawing.mode = "resize";
  drawing.shapeId = shapeId;
  drawing.start = point;
}

function startPosePoint(event: PointerEvent, name: string) {
  if (editingDisabled.value || currentTaskType.value !== "pose") return;
  event.stopPropagation();
  selectedPosePointName.value = name;
  poseDraggingName.value = name;
  (event.currentTarget as Element).setPointerCapture?.(event.pointerId);
}

function moveSelectedShape(point: Point) {
  const shape = annotationShapes.value.find((item) => item.id === drawing.shapeId);
  if (!shape || !drawing.start) return;
  const dx = point.x - drawing.start.x;
  const dy = point.y - drawing.start.y;
  drawing.start = point;
  updateShape(shape.id, {
    points: shape.points.map((item) => clampPoint({ x: item.x + dx, y: item.y + dy })),
    source: "edited",
  });
}

function resizeSelectedBox(point: Point) {
  const shape = annotationShapes.value.find((item) => item.id === drawing.shapeId);
  if (!shape || shape.type !== "box") return;
  updateShape(shape.id, { points: [shape.points[0], clampPoint(point)], source: "edited" });
}

function addShape(shape: AnnotationShape) {
  if (editingDisabled.value) return;
  setShapes([...annotationShapes.value, shape]);
  selectedShapeId.value = shape.id;
  if (shape.type !== "brush") activeTool.value = "select";
}

function updateShape(shapeId: string, patch: Partial<AnnotationShape>) {
  if (editingDisabled.value) return;
  setShapes(annotationShapes.value.map((shape) => (shape.id === shapeId ? { ...shape, ...patch } : shape)));
}

function removeSelectedShape() {
  if (editingDisabled.value) return;
  if (!selectedShapeId.value) return;
  setShapes(annotationShapes.value.filter((shape) => shape.id !== selectedShapeId.value));
  selectedShapeId.value = null;
}

function selectShape(shapeId: string) {
  selectedShapeId.value = shapeId;
  activeTool.value = "select";
}

function selectPresetLabel(label: LabelConfig) {
  activePresetLabelId.value = label.labelId;
  if (selectedShape.value) {
    updateShape(selectedShape.value.id, {
      labelId: label.labelId,
      label: `${label.englishName} / ${label.chineseName}`,
      source: "edited",
    });
  }
}

function labelShortcut(index: number) {
  if (index < 0 || index >= 20) return "";
  const slot = index % 10;
  const key = slot === 9 ? "0" : String(slot + 1);
  return index >= 10 ? `Shift+${key}` : key;
}

function shortcutLabel(event: KeyboardEvent) {
  const match = event.code.match(/^Digit([0-9])$/);
  if (!match || event.altKey || event.ctrlKey || event.metaKey) return null;
  const digit = Number(match[1]);
  const slot = digit === 0 ? 9 : digit - 1;
  return labels.value[(event.shiftKey ? 10 : 0) + slot] ?? null;
}

function handleGlobalKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null;
  if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
  if (currentPage.value === "videoCaptions") {
    handleVideoCaptionKeydown(event);
    return;
  }
  if (currentPage.value !== "workspace") return;
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    if (!editingDisabled.value) void saveAnnotationSnapshot();
    return;
  }
  const presetLabel = shortcutLabel(event);
  if (presetLabel) {
    event.preventDefault();
    selectPresetLabel(presetLabel);
    return;
  }
  const toolByKey: Partial<Record<string, AnnotationTool>> = { v: "select", h: "pan", b: "box", p: "polygon", l: "line" };
  const tool = toolByKey[event.key.toLowerCase()];
  if (tool) {
    event.preventDefault();
    setTool(tool);
    return;
  }
  if (event.key === "Enter" && polygonDraft.value.length >= 3) {
    event.preventDefault();
    finishPolygon();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    cancelPolygon();
    selectedShapeId.value = null;
    setTool("select");
    return;
  }
  if (event.key.toLowerCase() === "f") {
    event.preventDefault();
    fitView();
    return;
  }
  if (event.key.toLowerCase() === "a" || event.key.toLowerCase() === "d") {
    event.preventDefault();
    void selectAdjacentImage(event.key.toLowerCase() === "a" ? -1 : 1);
    return;
  }
  if (event.key === "+" || event.key === "=") view.zoom = Math.min(5, view.zoom + 0.1);
  if (event.key === "-" || event.key === "_") view.zoom = Math.max(0.2, view.zoom - 0.1);
  if ((event.key === "Delete" || event.key === "Backspace") && selectedShapeId.value) {
    event.preventDefault();
    removeSelectedShape();
  }
}

async function selectAdjacentImage(direction: -1 | 1) {
  const currentIndex = imageHistoryList.value.findIndex((image) => image.imageId === currentState.value.currentImageId);
  const nextIndex = Math.min(imageHistoryList.value.length - 1, Math.max(0, currentIndex + direction));
  const image = imageHistoryList.value[nextIndex];
  if (image && nextIndex !== currentIndex) await selectImage(image);
}

function setShapes(shapes: AnnotationShape[]) {
  currentState.value.annotationJson = {
    ...(currentState.value.annotationJson ?? emptyAnnotation()),
    shapes: shapes.map((shape) => serializeShape(shape)),
    updatedAt: new Date().toISOString(),
  };
}

function ensureAnnotationJson() {
  currentState.value.annotationJson = normalizeAnnotation(currentState.value.annotationJson, currentState.value.resultJson);
}

function emptyAnnotation() {
  return { shapes: [], updatedAt: new Date().toISOString() };
}

function normalizeAnnotation(annotation: Record<string, unknown> | null, result: Record<string, unknown> | null) {
  const shapes = readShapes(annotation);
  if (shapes.length > 0) return { ...(annotation ?? {}), shapes: shapes.map((shape) => serializeShape(shape)) };
  return { ...(annotation ?? {}), shapes: resultToShapes(result).map((shape) => serializeShape(shape)), updatedAt: new Date().toISOString() };
}

function resultToShapes(result: Record<string, unknown> | null): AnnotationShape[] {
  const boxes = ((result?.boxes as Array<Record<string, unknown>> | undefined) ?? []).map((box) => {
    const label = String(box.label ?? "object");
    return makeShape(
      "box",
      [
        { x: Number(box.x ?? 0), y: Number(box.y ?? 0) },
        { x: Number(box.x ?? 0) + Number(box.width ?? 0), y: Number(box.y ?? 0) + Number(box.height ?? 0) },
      ],
      label,
      Number(box.score ?? 0),
      "ai",
    );
  });
  const segments = ((result?.segments as Array<Record<string, unknown>> | undefined) ?? []).map((segment) => {
    const points = ((segment.polygon as number[][] | undefined) ?? []).map(([x, y]) => ({ x: Number(x), y: Number(y) }));
    return makeShape("polygon", points, String(segment.label ?? "segment"), Number(segment.score ?? 0), "ai");
  });
  return [...boxes, ...segments].filter((shape) => shape.points.length >= 2);
}

function readShapes(annotation: Record<string, unknown> | null): AnnotationShape[] {
  const raw = ((annotation?.shapes as Array<Record<string, unknown>> | undefined) ?? []) as Array<Record<string, unknown>>;
  return raw
    .map((shape) => ({
      id: String(shape.id ?? newId("shape")),
      type: (shape.type === "polygon" || shape.type === "line" || shape.type === "brush" ? shape.type : "box") as ShapeType,
      labelId: shape.labelId === null || shape.labelId === undefined ? null : Number(shape.labelId),
      label: String(shape.label ?? "object"),
      points: ((shape.points as Array<Record<string, number>> | undefined) ?? []).map((point) => ({ x: Number(point.x), y: Number(point.y) })),
      score: shape.score === undefined ? undefined : Number(shape.score),
      source: shape.source === "ai" ? "ai" : shape.source === "manual" ? "manual" : "edited",
    }))
    .filter((shape) => shape.points.length >= 2 || shape.type === "polygon");
}

function serializeShape(shape: AnnotationShape) {
  return {
    id: shape.id,
    type: shape.type,
    labelId: shape.labelId,
    label: shape.label,
    points: shape.points.map((point) => ({ x: round(point.x), y: round(point.y) })),
    score: shape.score,
    source: shape.source,
  };
}

function makeShape(type: ShapeType, points: Point[], label = defaultLabelText(), score?: number, source: AnnotationShape["source"] = "manual") {
  const labelConfig = source === "ai" ? labels.value.find((item) => item.englishName === label) : activePresetLabel.value;
  return {
    id: newId("shape"),
    type,
    labelId: labelConfig?.labelId ?? null,
    label: labelConfig ? `${labelConfig.englishName} / ${labelConfig.chineseName}` : label,
    points: points.map(clampPoint),
    score,
    source,
  };
}

function normalizeShapePoints(shape: AnnotationShape) {
  if (shape.type !== "box") return { ...shape, points: shape.points.map(clampPoint) };
  const [a, b] = shape.points;
  return { ...shape, points: [clampPoint({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y) }), clampPoint({ x: Math.max(a.x, b.x), y: Math.max(a.y, b.y) })] };
}

function shapeSize(shape: AnnotationShape) {
  if (shape.type === "line") return distance(shape.points[0], shape.points[1]);
  const box = shapeBounds(shape);
  return Math.max(box.width, box.height);
}

function shapeBounds(shape: AnnotationShape) {
  const xs = shape.points.map((point) => point.x);
  const ys = shape.points.map((point) => point.y);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y };
}

function svgPoint(event: PointerEvent): Point | null {
  const svg = event.currentTarget instanceof SVGSVGElement ? event.currentTarget : (event.currentTarget as Element).closest("svg");
  if (!svg || !currentState.value.imageInfo?.width || !currentState.value.imageInfo?.height) return null;
  const rect = svg.getBoundingClientRect();
  return clampPoint({
    x: ((event.clientX - rect.left) / rect.width) * currentState.value.imageInfo.width,
    y: ((event.clientY - rect.top) / rect.height) * currentState.value.imageInfo.height,
  });
}

function clampPoint(point: Point) {
  const width = currentState.value.imageInfo?.width ?? Number.MAX_SAFE_INTEGER;
  const height = currentState.value.imageInfo?.height ?? Number.MAX_SAFE_INTEGER;
  return { x: Math.min(width, Math.max(0, point.x)), y: Math.min(height, Math.max(0, point.y)) };
}

function boxRect(shape: AnnotationShape) {
  const box = shapeBounds(shape);
  return { ...box, labelY: Math.max(box.y - 8, 16), handleX: box.x + box.width, handleY: box.y + box.height };
}

function polygonPoints(points: Point[]) {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}

function annotationPointsText(points: Point[]) {
  return points.map((point, index) => `P${index + 1}(${Math.round(point.x)}, ${Math.round(point.y)})`).join(" · ");
}

function coordinatePairsToPoints(points: number[][]) {
  return points.map(([x, y]) => `${x},${y}`).join(" ");
}

function linePoints(points: Point[]) {
  return points.length >= 2 ? { x1: points[0].x, y1: points[0].y, x2: points[1].x, y2: points[1].y } : { x1: 0, y1: 0, x2: 0, y2: 0 };
}

function shapeTypeText(type: ShapeType) {
  const text = { box: ["矩形框", "Box"], polygon: ["多边形", "Polygon"], line: ["线段", "Line"], brush: ["画笔掩码", "Brush mask"] };
  return text[type][uiLanguage.value === "zh" ? 0 : 1];
}

function resultKeypoints(): PoseKeypoint[] {
  const saved = currentState.value.annotationJson?.poseKeypoints as Array<Record<string, number | string>> | undefined;
  const direct = currentState.value.resultJson?.keypoints as Array<Record<string, number | string>> | undefined;
  const poses = currentState.value.resultJson?.poses as Array<Record<string, unknown>> | undefined;
  const flattened = poses?.flatMap((pose, poseIndex) => {
    const points = (pose.keypoints as number[][] | undefined) ?? [];
    const scores = (pose.confidence as number[] | undefined) ?? [];
    return points.map((point, index) => ({ name: `person_${poseIndex}_${poseKeypointNames[index] ?? `point_${index}`}`, x: point[0], y: point[1], score: scores[index] ?? 1 }));
  });
  const keypoints = saved ?? direct ?? flattened ?? [];
  return keypoints.map((point) => ({
    name: String(point.name),
    x: Number(point.x),
    y: Number(point.y),
    score: Number(point.score ?? 1),
  }));
}

function resultSkeleton(): PoseSkeletonLine[] {
  if (currentState.value.annotationJson?.poseKeypoints) return fallbackSkeletonFromKeypoints(resultKeypoints());
  const skeleton = (currentState.value.resultJson?.skeleton as Array<Record<string, number | string>> | undefined) ?? [];
  if (skeleton.length > 0) {
    return skeleton.map((line, index) => ({
      name: String(line.name ?? `skeleton_${index}`),
      x1: Number(line.x1),
      y1: Number(line.y1),
      x2: Number(line.x2),
      y2: Number(line.y2),
      score: Number(line.score ?? 1),
    }));
  }
  return fallbackSkeletonFromKeypoints(resultKeypoints());
}

function fallbackSkeletonFromKeypoints(keypoints: PoseKeypoint[]): PoseSkeletonLine[] {
  const grouped = new Map<string, Map<string, PoseKeypoint>>();
  for (const point of keypoints) {
    const match = point.name.match(/^person_(\d+)_(.+)$/);
    if (!match || point.score <= 0.05 || (point.x <= 0 && point.y <= 0)) continue;
    const [, personIndex, keypointName] = match;
    const group = grouped.get(personIndex) ?? new Map<string, PoseKeypoint>();
    group.set(keypointName, point);
    grouped.set(personIndex, group);
  }

  const lines: PoseSkeletonLine[] = [];
  for (const [personIndex, points] of grouped) {
    for (const [fromName, toName] of poseSkeletonPairs) {
      const from = points.get(fromName);
      const to = points.get(toName);
      if (!from || !to) continue;
      lines.push({
        name: `person_${personIndex}_${fromName}_to_${toName}`,
        x1: from.x,
        y1: from.y,
        x2: to.x,
        y2: to.y,
        score: Math.min(from.score, to.score),
      });
    }
  }
  return lines;
}

function resultLabels() {
  return ((currentState.value.resultJson?.labels as Array<Record<string, number | string>> | undefined) ?? []) as Array<{
    label: string;
    score: number;
  }>;
}

function toggleClassificationLabel(labelId: number) {
  const ids = new Set(selectedClassificationLabelIds.value);
  if (ids.has(labelId)) ids.delete(labelId); else ids.add(labelId);
  selectedClassificationLabelIds.value = [...ids];
}

function onWheel(event: WheelEvent) {
  if (!currentState.value.imageUrl) return;
  event.preventDefault();
  const direction = event.deltaY > 0 ? -0.12 : 0.12;
  view.zoom = Math.min(5, Math.max(0.2, Number((view.zoom + direction).toFixed(2))));
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
  resetView();
}

async function runBusy(action: () => Promise<void>, fallback: string) {
  activeRequestCount.value += 1;
  message.value = "";
  try {
    await action();
  } catch (error) {
    const detail = error instanceof Error && error.message ? error.message : fallback;
    if (error instanceof ApiRequestError && error.status === 401) {
      currentUser.value = null;
    }
    message.value = detail;
    errorDialog.value = detail;
  } finally {
    activeRequestCount.value = Math.max(0, activeRequestCount.value - 1);
    processingOverlayText.value = "";
  }
}

function currentImageSessionId() {
  return currentState.value.imageInfo?.sessionId || defaultSessionId;
}

function currentImageUserId() {
  return currentState.value.imageInfo?.sessionId?.startsWith("video-import:") ? null : currentUser.value?.userId;
}

function playCaption() {
  const text = currentState.value.descriptionText?.trim();
  if (!text) {
    message.value = "暂无可播放的图像描述";
    return;
  }
  if (!("speechSynthesis" in window)) {
    message.value = "当前浏览器不支持语音播放";
    console.error("[Speech] speechSynthesis is not supported");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  utterance.rate = 0.95;
  utterance.onerror = (event) => {
    console.error("[Speech] Caption playback failed", event);
    message.value = "语音播放失败";
  };
  window.speechSynthesis.speak(utterance);
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
    annotationJson: emptyAnnotation(),
    descriptionText: "",
    status: "idle",
    versions: [],
    activeVersionId: null,
    latestVersionNo: null,
    isViewingHistory: false,
    reviewStatus: "draft",
    reviewComment: "",
    submittedAt: null,
    reviewedAt: null,
  };
}

function defaultLabelText() {
  return uiText("对象", "object");
}

function newId(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function round(value: number) {
  return Math.round(value * 100) / 100;
}

function distance(a: Point, b: Point) {
  return Math.hypot(a.x - b.x, a.y - b.y);
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

function formatDuration(value?: number | null) {
  if (!value) return "-";
  return formatTimestamp(value);
}

function formatTimestamp(value?: number | null) {
  if (!value) return "00:00";
  const totalSeconds = Math.floor(value / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const base = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours > 0 ? `${String(hours).padStart(2, "0")}:${base}` : base;
}

function statusText(status: ImageTaskStatus) {
  const text = { idle: ["未处理", "Not processed"], pending: ["待处理", "Pending"], processing: ["处理中", "Processing"], success: ["已完成", "Complete"], failed: ["失败", "Failed"] };
  return text[status][uiLanguage.value === "zh" ? 0 : 1];
}

function reviewStatusText(status: ImageReviewStatus) {
  const text = { draft: ["草稿", "Draft"], pending_review: ["待审核", "Pending review"], approved: ["已通过", "Approved"], rejected: ["已驳回", "Rejected"] };
  return text[status][uiLanguage.value === "zh" ? 0 : 1];
}
</script>

<template>
  <main v-if="currentUser" class="app-shell image-task-workspace">
    <header class="topbar">
      <div class="brand">
        <img :src="'/favicon.svg'" alt="" />
        <div>
          <h1>{{ uiText("铁路多目标识别平台", "Railway Multi-Target Recognition") }}</h1>
          <span>{{ loading ? uiText("处理中", "Processing") : uiText("就绪", "Ready") }}<template v-if="message"> · {{ uiNotice(message) }}</template></span>
        </div>
      </div>
      <div class="topbar-actions">
        <nav class="task-tabs" :aria-label="uiText('工作区', 'Workspace')">
          <button :class="{ active: currentPage === 'workspace' }" @click="setPage('workspace')"><Boxes :size="16" />{{ uiText("标注工作台", "Annotation Workspace") }}</button>
          <button :class="{ active: currentPage === 'videoCaptions' }" @click="setPage('videoCaptions')"><Film :size="16" />{{ uiText("视频解帧", "Video Frames") }}</button>
          <button :class="{ active: currentPage === 'settings' }" @click="setPage('settings')"><Settings :size="16" />{{ uiText("系统配置", "Settings") }}</button>
          <button :class="{ active: currentPage === 'training' }" @click="setPage('training')"><Sparkles :size="16" />{{ uiText("模型训练", "Training") }}</button>
        </nav>
        <div class="user-session">
          <UserRound :size="17" />
          <span><strong>{{ currentUser.displayName }}</strong><small>{{ currentUser.username }}</small></span>
          <label class="language-picker" :aria-label="uiText('界面语言', 'Interface language')">
            <select v-model="uiLanguage" @change="persistUiLanguage">
              <option value="zh">中文</option><option value="en">English</option>
            </select>
          </label>
          <button :title="uiText('退出登录', 'Sign out')" :aria-label="uiText('退出登录', 'Sign out')" @click="signOut"><LogOut :size="16" /></button>
        </div>
      </div>
    </header>

    <nav v-if="currentPage === 'workspace'" class="task-strip" aria-label="功能页面">
      <button v-for="task in taskConfigs" :key="task.type" :class="{ active: currentTaskType === task.type }" @click="setTaskType(task.type)">
        {{ taskTitle(task.type) }}
      </button>
    </nav>

    <section
      v-if="currentPage === 'workspace'"
      ref="workspaceBodyRef"
      class="workspace-body"
      :class="{ 'is-resizing': panelLayout.resizing }"
      :style="workspaceGridStyle"
    >
      <aside class="history-panel" :class="{ collapsed: historyCollapsed }">
        <div class="panel-head">
          <strong v-if="!historyCollapsed">{{ uiText("图片", "Images") }}</strong>
          <button :title="historyCollapsed ? uiText('展开历史列表', 'Expand image list') : uiText('收起历史列表', 'Collapse image list')" @click="historyCollapsed = !historyCollapsed">
            <ChevronRight v-if="historyCollapsed" :size="16" />
            <ChevronLeft v-else :size="16" />
          </button>
        </div>
        <template v-if="!historyCollapsed">
          <div class="history-actions">
          <label class="icon-button upload-zone compact" :title="uiText('上传图片', 'Upload image')" :aria-label="uiText('上传图片', 'Upload image')">
            <Upload :size="17" />
            <input type="file" accept="image/jpeg,image/png,image/webp,image/bmp" @change="handleUpload" />
          </label>
          <button class="icon-button" :disabled="loading" :title="uiText('刷新', 'Refresh')" @click="loadImageHistory"><RefreshCw :size="17" /></button>
          <form class="history-search" @submit.prevent="searchImageHistory">
            <Search :size="15" />
            <input v-model="imageHistoryQuery" :aria-label="uiText('按图片名称搜索', 'Search image names')" :placeholder="uiText('搜索图片名称', 'Search image names')" />
            <button :title="uiText('搜索', 'Search')" :disabled="loading"><Search :size="14" /></button>
          </form>
          </div>
          <div class="history-list">
            <div
              v-for="image in imageHistoryList"
              :key="image.imageId"
              class="history-item"
              :class="{ selected: image.imageId === currentState.currentImageId }"
            >
              <button class="history-select" @click="selectImage(image)">
                <strong>{{ image.originalName }}</strong>
                <small>{{ formatTime(image.createdAt) }}</small>
                <small>{{ statusText(image.taskStatus) }} · {{ image.hasCurrentTaskResult ? "已有结果" : "暂无结果" }}</small>
              </button>
              <span class="history-item-actions">
                <button class="history-info" :title="uiText('查看图片详细信息', 'View image details')" @click.stop="imageInfoDialogTarget = image"><Info :size="15" /></button>
                <button class="history-delete" :title="uiText('删除图片及标注', 'Delete image and annotations')" :disabled="loading" @click.stop="removeHistoryImage(image)"><Trash2 :size="15" /></button>
              </span>
            </div>
            <div v-if="imageHistoryList.length === 0" class="empty-state">{{ uiText("暂无图片", "No images") }}</div>
          </div>
          <div class="pagination-controls history-pagination">
            <label class="page-size-control"><span>{{ uiText("每页", "Per page") }}</span><input v-model="imageHistoryPageSizeInput" type="number" min="1" max="200" :disabled="loading" @change="changeImageHistoryPageSize" @keydown.enter="changeImageHistoryPageSize" /></label>
            <button :disabled="loading || imageHistoryPage <= 1" @click="changeImageHistoryPage(imageHistoryPage - 1)">{{ uiText("上一页", "Previous") }}</button>
            <label class="page-jump"><span>{{ uiText("页", "Page") }}</span><input v-model="imageHistoryPageInput" type="number" min="1" :max="Math.max(1, Math.ceil(imageHistoryTotal / imageHistoryPageSize))" :disabled="loading" @keydown.enter="jumpImageHistoryPage" /><button :disabled="loading" @click="jumpImageHistoryPage">{{ uiText("跳转", "Go") }}</button></label>
            <span>/ {{ Math.max(1, Math.ceil(imageHistoryTotal / imageHistoryPageSize)) }}</span>
            <button :disabled="loading || imageHistoryPage * imageHistoryPageSize >= imageHistoryTotal" @click="changeImageHistoryPage(imageHistoryPage + 1)">{{ uiText("下一页", "Next") }}</button>
          </div>
        </template>
      </aside>

      <button
        class="panel-resizer history-resizer"
        :disabled="historyCollapsed"
        :title="uiText('拖动调整图片列表宽度', 'Drag to resize image list')"
        :aria-label="uiText('拖动调整图片列表宽度', 'Drag to resize image list')"
        @pointerdown="startPanelResize($event, 'history')"
      ></button>

      <section class="editor-panel">
        <div class="editor-toolbar">
          <div>
            <strong>{{ currentConfigTitle }}</strong>
            <span>{{ uiLanguage === "zh" ? currentConfig.description : taskDescription(currentTaskType) }}</span>
          </div>
          <div class="toolbar-actions">
            <label class="model-select">
              <span>{{ uiText("模型", "Model") }}</span>
              <select v-model="selectedModelByTask[currentTaskType]" :disabled="loading">
                <option v-for="model in currentConfig.models" :key="model" :value="model">{{ model }}</option>
              </select>
            </label>
            <button :disabled="!currentState.currentImageId || loading || editingDisabled" @click="runCurrentTask">
              <Loader2 v-if="loading" class="spin" :size="16" />
              <Sparkles v-else :size="16" />
              {{ uiText("开始处理", "Run Inference") }}
            </button>
            <button :disabled="!currentState.currentImageId || loading || editingDisabled" @click="saveCurrentResult"><Save :size="16" />{{ uiText("保存结果", "Save Result") }}</button>
            <button :disabled="!currentState.currentImageId || loading || editingDisabled" @click="saveAnnotationSnapshot"><Download :size="16" />{{ uiText("保存标注", "Save Annotation") }}</button>
          </div>
        </div>

        <div class="annotation-toolbar">
          <button :class="{ active: activeTool === 'select' }" :title="uiText('选择', 'Select')" @click="setTool('select')"><MousePointer2 :size="16" />{{ uiText("选择", "Select") }}</button>
          <button :class="{ active: activeTool === 'pan' }" :title="uiText('移动画布', 'Pan canvas')" @click="setTool('pan')"><Move :size="16" />{{ uiText("移动", "Pan") }}</button>
          <button v-if="currentTaskType !== 'segmentation' && currentTaskType !== 'pose' && currentTaskType !== 'caption'" :disabled="editingDisabled" :class="{ active: activeTool === 'box' }" :title="uiText('矩形框（B）', 'Bounding box (B)')" @click="setTool('box')"><Boxes :size="16" />{{ uiText("矩形框", "Box") }}</button>
          <button v-if="currentTaskType !== 'pose' && currentTaskType !== 'caption'" :disabled="editingDisabled" :class="{ active: activeTool === 'polygon' }" :title="uiText('多边形（P）', 'Polygon (P)')" @click="setTool('polygon')"><Pentagon :size="16" />{{ uiText("多边形", "Polygon") }}</button>
          <button v-if="currentTaskType !== 'segmentation' && currentTaskType !== 'pose' && currentTaskType !== 'caption'" :disabled="editingDisabled" :class="{ active: activeTool === 'line' }" :title="uiText('线段（L）', 'Line (L)')" @click="setTool('line')"><Waypoints :size="16" />{{ uiText("线段", "Line") }}</button>
          <button v-if="currentTaskType === 'segmentation'" :disabled="editingDisabled" :class="{ active: activeTool === 'brush' }" :title="uiText('画笔掩码', 'Brush mask')" @click="setTool('brush')"><Edit3 :size="16" />{{ uiText("画笔", "Brush") }}</button>
          <template v-if="currentTaskType === 'pose'">
            <button :disabled="editingDisabled" :class="{ active: activeTool === 'pose-point' }" :title="uiText('按 COCO 17 点顺序添加新人体', 'Add a person using the COCO 17-keypoint order')" @click="startPoseDrawing"><Waypoints :size="16" />{{ uiText("新增人体", "Add person") }}</button>
            <span v-if="poseDrawingPerson !== null" class="pose-drawing-hint">{{ uiText(`请点击第 ${poseDrawingIndex + 1} 个关键点：${poseKeypointNames[poseDrawingIndex]}`, `Click keypoint ${poseDrawingIndex + 1}: ${poseKeypointNames[poseDrawingIndex]}`) }}</span>
          </template>
          <button :disabled="polygonDraft.length < 3" @click="finishPolygon"><Check :size="16" />{{ uiText("完成", "Finish") }}</button>
          <button :disabled="polygonDraft.length === 0" @click="cancelPolygon"><RotateCcw :size="16" />{{ uiText("取消", "Cancel") }}</button>
        </div>

        <div
          class="canvas-stage"
          :class="`tool-${activeTool}`"
          @wheel="onWheel"
          @pointerdown="onStagePointerDown"
          @pointermove="onStagePointerMove"
          @pointerup="stopStageDrag"
          @pointerleave="stopStageDrag"
        >
          <div v-if="!currentState.imageUrl" class="empty-canvas">
            <ImageIcon :size="40" />
            <label class="upload-zone">
              <Upload :size="20" />
              <span>{{ uiText("选择图片开始", "Select an image to begin") }}</span>
              <input type="file" accept="image/jpeg,image/png,image/webp,image/bmp" @change="handleUpload" />
            </label>
          </div>

          <div v-else class="canvas-content" :style="{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})` }">
            <img class="base-image" :src="currentImageUrl" :alt="uiText('原始图片', 'Original image')" />
            <svg
              v-if="currentState.imageInfo?.width && currentState.imageInfo?.height"
              class="overlay-layer interactive"
              :viewBox="`0 0 ${currentState.imageInfo.width} ${currentState.imageInfo.height}`"
              @pointerdown.stop="onOverlayPointerDown"
              @pointermove.stop="onOverlayPointerMove"
              @pointerup.stop="onOverlayPointerUp"
              @pointerleave.stop="onOverlayPointerUp"
              @dblclick.stop="finishPolygon"
            >
              <template v-for="shape in annotationShapes" :key="shape.id">
                <g
                  v-if="shape.type === 'box'"
                  class="shape-group"
                  :class="{ selected: shape.id === selectedShapeId }"
                  @pointerdown.stop="startMoveShape($event, shape.id)"
                >
                  <rect class="box-shape" :x="boxRect(shape).x" :y="boxRect(shape).y" :width="boxRect(shape).width" :height="boxRect(shape).height" />
                  <text class="box-label" :x="boxRect(shape).x + 4" :y="boxRect(shape).labelY">{{ shapeDisplayLabel(shape) }}</text>
                  <circle
                    v-if="shape.id === selectedShapeId"
                    class="resize-handle"
                    :cx="boxRect(shape).handleX"
                    :cy="boxRect(shape).handleY"
                    r="9"
                    @pointerdown.stop="startResizeBox($event, shape.id)"
                  />
                </g>
                <g
                  v-else-if="shape.type === 'polygon'"
                  class="shape-group"
                  :class="{ selected: shape.id === selectedShapeId }"
                  @pointerdown.stop="startMoveShape($event, shape.id)"
                >
                  <polygon class="segment-shape" :points="polygonPoints(shape.points)" />
                  <text class="box-label" :x="shapeBounds(shape).x + 4" :y="Math.max(shapeBounds(shape).y - 8, 16)">{{ shapeDisplayLabel(shape) }}</text>
                </g>
                <g v-else-if="shape.type === 'line'" class="shape-group" :class="{ selected: shape.id === selectedShapeId }" @pointerdown.stop="startMoveShape($event, shape.id)">
                  <line class="line-shape" v-bind="linePoints(shape.points)" />
                  <text class="box-label" :x="shape.points[0].x + 4" :y="Math.max(shape.points[0].y - 8, 16)">{{ shapeDisplayLabel(shape) }}</text>
                </g>
                <g v-else class="shape-group" :class="{ selected: shape.id === selectedShapeId }" @pointerdown.stop="startMoveShape($event, shape.id)">
                  <polyline class="brush-shape" :points="polygonPoints(shape.points)" />
                  <text class="box-label" :x="shape.points[0].x + 4" :y="Math.max(shape.points[0].y - 8, 16)">{{ shapeDisplayLabel(shape) }}</text>
                </g>
              </template>
              <rect
                v-if="draftShape?.type === 'box'"
                class="draft-shape"
                :x="boxRect(normalizeShapePoints(draftShape)).x"
                :y="boxRect(normalizeShapePoints(draftShape)).y"
                :width="boxRect(normalizeShapePoints(draftShape)).width"
                :height="boxRect(normalizeShapePoints(draftShape)).height"
              />
              <line v-if="draftShape?.type === 'line'" class="draft-shape" v-bind="linePoints(draftShape.points)" />
              <polygon v-if="draftShape?.type === 'brush' && draftShape.points.length >= 3" class="brush-draft" :points="polygonPoints([...draftShape.points, draftShape.points[0]])" />
              <polyline v-if="polygonDraft.length > 0" class="draft-shape" :points="polygonPoints(polygonDraft)" />
              <circle v-for="(point, index) in polygonDraft" :key="index" class="draft-point" :cx="point.x" :cy="point.y" r="6" />
              <line v-for="line in resultSkeleton()" :key="line.name" class="pose-bone" :x1="line.x1" :y1="line.y1" :x2="line.x2" :y2="line.y2" />
              <circle v-for="point in resultKeypoints()" :key="point.name" class="keypoint" :cx="point.x" :cy="point.y" r="5" @pointerdown.stop="startPosePoint($event, point.name)" />
            </svg>
          </div>

            <div v-if="processingOverlayText" class="processing-mask" role="status" aria-live="polite">
            <div class="processing-card">
              <Loader2 class="processing-spinner" :size="44" />
              <strong>{{ processingOverlayText }}</strong>
              <span>{{ selectedModelByTask[currentTaskType] }} · 请勿关闭页面</span>
            </div>
          </div>
        </div>

        <div class="view-controls">
          <button @click="fitView"><Maximize2 :size="15" />{{ uiText("适应窗口", "Fit View") }}</button>
          <button @click="originalView"><ZoomIn :size="15" />{{ uiText("原始比例", "Original Size") }}</button>
          <button @click="resetView"><RotateCcw :size="15" />{{ uiText("重置视图", "Reset View") }}</button>
          <span>{{ uiText("缩放", "Zoom") }} {{ Math.round(view.zoom * 100) }}%</span>
        </div>
      </section>

      <button
        class="panel-resizer thumbnail-resizer"
        :disabled="thumbnailCollapsed"
        :title="uiText('拖动调整标签与属性宽度', 'Drag to resize labels and properties')"
        :aria-label="uiText('拖动调整标签与属性宽度', 'Drag to resize labels and properties')"
        @pointerdown="startPanelResize($event, 'thumbnail')"
      ></button>

      <aside class="thumbnail-panel" :class="{ collapsed: thumbnailCollapsed }">
        <div class="panel-head">
          <strong v-if="!thumbnailCollapsed">{{ uiText("标签与属性", "Labels & Properties") }}</strong>
          <button :title="thumbnailCollapsed ? uiText('展开属性', 'Expand properties') : uiText('收起属性', 'Collapse properties')" @click="thumbnailCollapsed = !thumbnailCollapsed">
            <ChevronLeft v-if="thumbnailCollapsed" :size="16" />
            <ChevronRight v-else :size="16" />
          </button>
        </div>
        <template v-if="!thumbnailCollapsed">
          <section v-if="currentTaskType !== 'pose' && currentTaskType !== 'caption'" class="result-summary workspace-labels">
            <div class="workspace-labels-head"><h2>{{ uiText("标签预设", "Label presets") }}</h2><button class="icon-button" :title="uiText('添加标签', 'Add label')" @click="workspaceLabelFormOpen = !workspaceLabelFormOpen"><Plus :size="15" /></button></div>
            <form v-if="workspaceLabelFormOpen" class="workspace-label-form" @submit.prevent="submitWorkspaceLabel">
              <input v-model="labelForm.englishName" required :placeholder="uiText('英文名称', 'English name')" />
              <input v-model="labelForm.chineseName" required :placeholder="uiText('中文名称', 'Chinese name')" />
              <input v-model="labelForm.description" :placeholder="uiText('描述（可选）', 'Description (optional)')" />
              <button type="submit" :disabled="loading">{{ uiText("添加", "Add") }}</button>
            </form>
            <div class="workspace-label-list"><button v-for="label in labels" :key="label.labelId" :class="{ selected: activePresetLabelId === label.labelId }" @click="selectPresetLabel(label)">#{{ label.labelId }} {{ labelDisplay(label) }}</button></div>
          </section>
          <section v-if="currentTaskType !== 'pose' && currentTaskType !== 'caption'" class="result-summary">
            <h2>{{ uiText("选中对象", "Selected Object") }}</h2>
            <div v-if="!selectedShape" class="empty-state">
              {{ uiText("下一个标注", "Next annotation") }}：{{ activePresetLabel ? `#${activePresetLabel.labelId} ${labelDisplay(activePresetLabel)}` : uiText("未配置", "Not configured") }}
            </div>
            <div v-if="currentTaskType === 'pose' && selectedPosePointName" class="pose-point-details">
              <strong>{{ uiText("关键点", "Keypoint") }} {{ selectedPosePointName }}</strong>
              <span v-for="point in resultKeypoints().filter((item) => item.name === selectedPosePointName)" :key="point.name">({{ Math.round(point.x) }}, {{ Math.round(point.y) }}) · {{ uiText("置信度", "Score") }} {{ point.score.toFixed(2) }}</span>
            </div>
            <template v-if="selectedShape">
              <label class="field-label">
                <span>{{ uiText("标签", "Label") }}</span>
                <select v-model="selectedLabelId">
                  <option value="">{{ uiText("未配置", "Not configured") }}</option>
                  <option v-for="label in labels" :key="label.labelId" :value="label.labelId">
                    #{{ label.labelId }} {{ labelDisplay(label) }}
                  </option>
                </select>
              </label>
              <div class="result-row"><strong>{{ uiText("类型", "Type") }}</strong><span>{{ shapeTypeText(selectedShape.type) }}</span></div>
              <div class="result-row"><strong>{{ uiText("来源", "Source") }}</strong><span>{{ selectedShape.source }}</span></div>
              <template v-if="selectedShape.type === 'box'">
                <div class="result-row"><strong>{{ uiText("左上角", "Top-left") }}</strong><span>({{ Math.round(shapeBounds(selectedShape).x) }}, {{ Math.round(shapeBounds(selectedShape).y) }})</span></div>
                <div class="result-row"><strong>{{ uiText("宽 × 高", "Width × height") }}</strong><span>{{ Math.round(shapeBounds(selectedShape).width) }} × {{ Math.round(shapeBounds(selectedShape).height) }}</span></div>
              </template>
              <template v-else-if="selectedShape.type === 'line'">
                <div class="result-row"><strong>{{ uiText("起点", "Start") }}</strong><span>({{ Math.round(selectedShape.points[0].x) }}, {{ Math.round(selectedShape.points[0].y) }})</span></div>
                <div class="result-row"><strong>{{ uiText("终点", "End") }}</strong><span>({{ Math.round(selectedShape.points[1].x) }}, {{ Math.round(selectedShape.points[1].y) }})</span></div>
              </template>
              <template v-else>
                <div class="result-row"><strong>{{ uiText("闭合点数", "Closed points") }}</strong><span>{{ selectedShape.points.length }}</span></div>
                <div class="annotation-coordinate-list">{{ annotationPointsText(selectedShape.points) }}</div>
              </template>
              <div v-if="currentTaskType === 'pose' && selectedPosePointName" class="pose-point-details">
                <strong>{{ uiText("关键点", "Keypoint") }} {{ selectedPosePointName }}</strong>
                <span v-for="point in resultKeypoints().filter((item) => item.name === selectedPosePointName)" :key="point.name">({{ Math.round(point.x) }}, {{ Math.round(point.y) }}) · {{ uiText("置信度", "Score") }} {{ point.score.toFixed(2) }}</span>
              </div>
            </template>
          </section>

          <section v-if="currentTaskType !== 'pose' && currentTaskType !== 'caption'" class="result-summary annotated-summary">
            <h2>{{ uiText("已标注对象", "Annotated Objects") }}</h2>
            <div v-if="annotationShapes.length === 0" class="empty-state">{{ uiText("暂无标注对象", "No annotated objects") }}</div>
            <button
              v-for="(shape, index) in annotationShapes"
              :key="shape.id"
              class="annotation-row"
              :class="{ selected: shape.id === selectedShapeId }"
              @click="selectShape(shape.id)"
            >
              <strong>{{ index + 1 }}. {{ shapeDisplayLabel(shape) }}</strong>
              <span>{{ shapeTypeText(shape.type) }}</span>
              <button class="annotation-remove" :title="uiText('删除标注', 'Delete annotation')" @click.stop="selectedShapeId = shape.id; removeSelectedShape()">×</button>
            </button>
          </section>

          <section v-else-if="currentTaskType === 'pose'" class="result-summary pose-annotation-summary">
            <h2>{{ uiText("人体姿态", "Human Pose") }}</h2>
            <p class="pose-mode-note">{{ uiText("姿态标注独立于矩形框、多边形和普通标签。点击“新增人体”后按提示依次点击 17 个关键点。", "Pose annotation is independent from boxes, polygons, and regular labels. Click Add person, then click the 17 keypoints in order.") }}</p>
            <div v-if="resultKeypoints().length === 0" class="empty-state">{{ uiText("暂无人体关键点", "No pose keypoints") }}</div>
            <div v-for="personIndex in [...new Set(resultKeypoints().map((point) => Number(point.name.match(/^person_(\\d+)_/)?.[1] ?? 0)))]" :key="personIndex" class="pose-person-card">
              <strong>{{ uiText("人体", "Person") }} {{ personIndex + 1 }}</strong>
              <div class="pose-point-list">
                <button v-for="point in resultKeypoints().filter((item) => item.name.startsWith(`person_${personIndex}_`))" :key="point.name" :class="{ selected: selectedPosePointName === point.name }" @click="selectedPosePointName = point.name"><span>{{ point.name.split("_").slice(2).join(" ") }}</span><small>{{ Math.round(point.x) }}, {{ Math.round(point.y) }} · {{ point.score.toFixed(2) }}</small></button>
              </div>
            </div>
          </section>

          <section class="result-summary">
            <h2>{{ uiText("任务结果", "Task Results") }}</h2>
            <div v-if="currentState.isViewingHistory" class="history-viewing">{{ uiText("正在查看历史版本，恢复后会生成一个新版本。", "Viewing a previous version. Restoring it creates a new version.") }}</div>
            <div v-if="currentState.status === 'idle'" class="empty-state">{{ uiText("当前图片暂无该任务结果", "No result for this task") }}</div>
            <template v-else-if="currentTaskType === 'classification'">
              <div class="classification-label-picker">
                <label v-for="label in labels" :key="label.labelId" class="classification-label-option">
                  <input type="checkbox" :checked="selectedClassificationLabelIds.includes(label.labelId)" @change="toggleClassificationLabel(label.labelId)" />
                  <span>{{ labelDisplay(label) }}</span>
                </label>
              </div>
              <div v-for="item in resultLabels()" :key="item.label" class="result-row">
                <strong>{{ item.label }}</strong><span>{{ Math.round(item.score * 100) }}%</span>
              </div>
            </template>
            <template v-else-if="currentTaskType === 'caption'">
              <div class="caption-actions">
                <button :disabled="captionIsTransferring || !currentState.descriptionText" @click="playCaption">
                  <Loader2 v-if="captionIsTransferring" class="spin" :size="15" />
                  <Volume2 v-else :size="15" />
                  {{ captionIsTransferring ? uiText("处理中", "Processing") : uiText("播放中文简体", "Play Chinese caption") }}
                </button>
              </div>
              <div class="markdown-content" v-html="renderMarkdown(currentState.descriptionText)" />
            </template>
              <div v-else class="result-row"><strong>{{ uiText("标注对象", "Annotations") }}</strong><span>{{ annotationShapes.length }}</span></div>
          </section>

          <section class="result-summary review-summary">
            <div class="review-heading">
              <h2>{{ uiText("审核状态", "Review Status") }}</h2>
              <span class="review-status" :class="`status-${currentState.reviewStatus}`">{{ reviewStatusText(currentState.reviewStatus) }}</span>
            </div>
            <p v-if="currentState.reviewComment" class="review-comment">{{ currentState.reviewComment }}</p>
            <small v-if="currentState.reviewedAt">{{ uiText("审核时间", "Reviewed") }}: {{ formatTime(currentState.reviewedAt) }}</small>
            <button
              v-if="!canReview"
              :disabled="!currentState.taskId || currentState.status === 'idle' || currentState.reviewStatus === 'pending_review' || resultLocked || loading"
              @click="submitForReview"
            >
              <Check :size="16" />{{ uiText("提交审核", "Submit for Review") }}
            </button>
            <template v-else-if="currentState.reviewStatus === 'pending_review'">
              <textarea v-model="reviewCommentInput" rows="3" :placeholder="uiText('填写审核意见；驳回时建议说明修改位置', 'Enter review notes; specify requested changes when rejecting')"></textarea>
              <div class="review-actions">
                <button @click="reviewCurrentResult('approved')"><Check :size="16" />{{ uiText("通过", "Approve") }}</button>
                <button class="danger-button" @click="reviewCurrentResult('rejected')"><RotateCcw :size="16" />{{ uiText("驳回", "Reject") }}</button>
              </div>
            </template>
          </section>

          <section class="result-summary version-summary">
            <h2>{{ uiText("历史版本", "Version History") }}</h2>
            <div v-if="currentState.versions.length === 0" class="empty-state">{{ uiText("暂无保存版本", "No saved versions") }}</div>
            <div v-else class="version-list">
              <button
                v-for="version in currentState.versions"
                :key="version.versionId"
                class="version-row"
                :class="{ selected: version.versionId === currentState.activeVersionId }"
                @click="viewVersion(version.versionId)"
              >
                <span><strong>v{{ version.versionNo }}</strong><small>{{ version.source }} · {{ version.modelId || "-" }}</small></span>
                <small>{{ formatTime(version.createdAt) }}</small>
              </button>
            </div>
            <button class="ghost-button restore-button" :disabled="!currentState.activeVersionId || !currentState.isViewingHistory || loading" @click="restoreVersion(currentState.activeVersionId!)">
              {{ uiText("恢复此版本", "Restore this version") }}
            </button>
          </section>
        </template>
      </aside>
    </section>

    <section v-else-if="currentPage === 'videoCaptions'" class="video-caption-page">
      <aside class="video-list-panel">
        <div class="panel-head">
          <strong>{{ uiText("视频批次", "Video Batches") }}</strong>
          <button :disabled="loading" :title="uiText('刷新', 'Refresh')" @click="loadVideoCaptionBatches"><RefreshCw :size="16" /></button>
        </div>
        <div class="batch-summary" v-if="selectedVideoCaptionBatch">
          <strong>{{ selectedVideoCaptionBatch.name }}</strong>
          <span>{{ selectedVideoCaptionBatch.totalVideos }} {{ uiText("个视频", "videos") }} · {{ selectedVideoCaptionBatch.totalFrames }} {{ uiText("帧", "frames") }} · {{ selectedVideoCaptionBatch.status }}</span>
        </div>
        <div class="video-list">
          <button
            v-for="batch in videoCaptionBatches"
            :key="batch.batchId"
            class="video-row batch-row"
            :class="{ selected: batch.batchId === selectedVideoCaptionBatchId }"
            @click="selectVideoCaptionBatch(batch.batchId)"
          >
            <strong>{{ batch.name }}</strong>
            <span>{{ batch.totalVideos }} {{ uiText("视频", "videos") }} · {{ batch.totalFrames }} {{ uiText("帧", "frames") }}</span>
          </button>
          <div v-if="videoCaptionBatches.length === 0" class="empty-state">{{ uiText("暂无解帧批次", "No frame batches") }}</div>
        </div>

        <div class="panel-head sub-head">
          <strong>{{ uiText("视频列表", "Videos") }}</strong>
        </div>
        <div class="video-list">
            <button
            v-for="video in videoCaptionVideos"
            :key="video.videoId"
            class="video-row"
            :class="{ selected: video.videoId === selectedVideoCaptionVideoId }"
            @click="selectVideoCaptionVideo(video.videoId)"
          >
            <strong>{{ video.displayName || video.filename }}</strong>
            <span class="video-row-actions">
              <button v-if="video.sourceUrl" class="icon-button" :title="uiText('播放原始视频', 'Play original video')" @click.stop="playSelectedVideo(video)"><Play :size="14" /></button>
              <button v-if="video.poseUrl" class="icon-button" :title="uiText('播放姿态识别视频', 'Play pose recognition video')" @click.stop="playPoseVideo(video)"><Waypoints :size="14" /></button>
            </span>
            <span>{{ formatDuration(video.durationMs) }} · {{ video.status }}</span>
            <span v-if="video.similarFramesSkipped">{{ uiText("跳过相似帧", "Similar frames skipped") }} {{ video.similarFramesSkipped }}</span>
            <span class="keyword-list">
              <small v-for="keyword in video.keywords" :key="keyword">{{ keyword }}</small>
            </span>
          </button>
          <div v-if="videoCaptionVideos.length === 0" class="empty-state">{{ uiText("暂无视频记录", "No video records") }}</div>
        </div>
      </aside>

      <section class="frame-browser">
        <div class="frame-toolbar">
          <div>
            <strong>{{ selectedVideoCaptionVideo?.displayName || selectedVideoCaptionVideo?.filename || uiText("请选择视频", "Select a video") }}</strong>
            <span>{{ videoCaptionTotal }} {{ uiText("帧记录", "frames") }}</span>
          </div>
          <form class="frame-search" @submit.prevent="searchVideoCaptionFrames">
            <Search :size="16" />
            <input v-model="videoCaptionQuery" :placeholder="uiText('搜索人员、轨道、车辆或安全风险', 'Search people, tracks, vehicles, or safety risks')" />
            <button :disabled="loading">{{ uiText("搜索", "Search") }}</button>
          </form>
        </div>
        <div class="frame-grid">
          <button
            v-for="frame in videoCaptionFrames"
            :key="frame.frameId"
            class="frame-card"
            :class="{ selected: frame.frameId === selectedVideoCaptionFrameId }"
            @click="selectVideoCaptionFrame(frame.frameId)"
          >
            <img :src="assetUrl(frame.imageUrl)" alt="" />
            <span>{{ formatTimestamp(frame.timestampMs) }}</span>
          </button>
          <div v-if="videoCaptionFrames.length === 0" class="empty-state">{{ uiText("暂无匹配帧", "No matching frames") }}</div>
        </div>
        <div class="pagination-controls frame-pagination">
          <label class="page-size-control">
            <span>{{ uiText("每页", "Per page") }}</span>
            <select :value="videoCaptionPageSize" :disabled="loading" @change="changeVideoCaptionPageSize">
              <option :value="10">10 {{ uiText("帧", "frames") }}</option>
              <option :value="20">20 {{ uiText("帧", "frames") }}</option>
              <option :value="30">30 {{ uiText("帧", "frames") }}</option>
              <option :value="50">50 {{ uiText("帧", "frames") }}</option>
            </select>
          </label>
          <button :disabled="loading || videoCaptionPage <= 1" @click="changeVideoCaptionPage(videoCaptionPage - 1)">{{ uiText("上一页", "Previous") }}</button>
          <span>{{ uiText("第", "Page") }} {{ videoCaptionPage }} / {{ Math.max(1, Math.ceil(videoCaptionTotal / videoCaptionPageSize)) }} · {{ videoCaptionTotal }} {{ uiText("帧", "frames") }}</span>
          <button :disabled="loading || videoCaptionPage * videoCaptionPageSize >= videoCaptionTotal" @click="changeVideoCaptionPage(videoCaptionPage + 1)">{{ uiText("下一页", "Next") }}</button>
        </div>
      </section>

      <aside class="frame-detail-panel">
        <template v-if="selectedVideoCaptionFrame">
          <dl class="image-info">
            <dt>{{ uiText("时间", "Time") }}</dt>
            <dd>{{ formatTimestamp(selectedVideoCaptionFrame.timestampMs) }}</dd>
            <dt>{{ uiText("帧号", "Frame") }}</dt>
            <dd>{{ selectedVideoCaptionFrame.frameIndex }}</dd>
            <dt>{{ uiText("模型", "Model") }}</dt>
            <dd>{{ selectedVideoCaptionFrame.modelId }}</dd>
            <dt>{{ uiText("状态", "Status") }}</dt>
            <dd>{{ selectedVideoCaptionFrame.status }}</dd>
            <dt>{{ uiText("安全评分", "Safety Score") }}</dt>
            <dd>{{ selectedVideoCaptionFrame.safetyScore ?? uiText("未评分", "Unrated") }} / 10</dd>
          </dl>
          <section class="result-summary frame-vision-summary">
            <h2>{{ uiText("视觉识别结果", "Vision Results") }}</h2>
            <dl class="image-info">
              <dt>{{ uiText("目标检测", "Object Detection") }}</dt>
              <dd>{{ frameVisionSummary("detection", "objects") }}</dd>
              <dt>{{ uiText("实例分割", "Instance Segmentation") }}</dt>
              <dd>{{ frameVisionSummary("segmentation", "segments") }}</dd>
              <dt>{{ uiText("姿态识别", "Pose Estimation") }}</dt>
              <dd>{{ frameVisionSummary("pose", "poses") }}</dd>
            </dl>
          </section>
          <section class="result-summary frame-descriptions">
            <h2>{{ uiText("画面描述", "Frame Caption") }}</h2>
            <template v-if="uiLanguage === 'zh'"><div class="markdown-content" v-html="renderMarkdown(selectedVideoCaptionFrame.descriptionText || '暂无中文描述')" /></template>
            <template v-else>
              <div v-if="!selectedVideoCaptionFrame.descriptionEn" class="frame-description-en-heading"><span>{{ uiText("未生成英文描述", "No English caption") }}</span><button :disabled="frameTranslationBusy" @click="generateFrameEnglish"><Sparkles :size="14" />{{ uiText("本地生成", "Generate locally") }}</button></div>
              <div class="markdown-content" v-html="renderMarkdown(selectedVideoCaptionFrame.descriptionEn || 'No English caption available')" />
            </template>
          </section>
        </template>
        <div v-else class="empty-state detail-empty">{{ uiText("请选择一个视频帧", "Select a video frame") }}</div>
      </aside>
    </section>

    <ChatPage v-else-if="currentPage === 'chat'" :username="currentUser.username" :language="uiLanguage" />

    <LiveGesturePage v-else-if="currentPage === 'liveGesture'" :language="uiLanguage" />

    <section v-else-if="currentPage === 'training'" class="settings-page training-page">
      <div class="settings-header">
        <div><h2><Sparkles :size="22" />{{ uiText("模型训练", "Model Training") }}</h2><p>{{ uiText("使用已有标注结果生成训练集和验证集，实时查看损失与精度指标。", "Build train/validation sets from annotations and monitor loss and accuracy in real time.") }}</p></div>
        <button :disabled="loading" @click="loadTrainingWorkspace"><RefreshCw :size="16" />{{ uiText("刷新", "Refresh") }}</button>
      </div>
      <section class="training-config result-summary">
        <div class="training-config-grid">
          <label class="field-label"><span>{{ uiText("任务类型", "Task type") }}</span><select v-model="trainingType" @change="changeTrainingType"><option value="detection">{{ taskTitle("detection") }}</option><option value="segmentation">{{ taskTitle("segmentation") }}</option><option value="pose">{{ taskTitle("pose") }}</option></select></label>
          <label class="field-label"><span>{{ uiText("基础模型", "Base model") }}</span><select v-model="trainingForm.modelName"><option v-for="model in localModelCatalog[trainingType]" :key="model" :value="model">{{ model }}</option></select></label>
          <label class="field-label"><span>{{ uiText("任务名称", "Run name") }}</span><input v-model="trainingForm.name" /></label>
          <label class="field-label"><span>{{ uiText("训练轮数", "Epochs") }}</span><input v-model.number="trainingForm.epochs" type="number" min="1" max="1000" /></label>
          <label class="field-label"><span>{{ uiText("批大小", "Batch size") }}</span><input v-model.number="trainingForm.batchSize" type="number" min="1" max="256" /></label>
          <label class="field-label"><span>{{ uiText("输入尺寸", "Image size") }}</span><input v-model.number="trainingForm.imageSize" type="number" min="128" max="2048" step="32" /></label>
        </div>
        <div class="training-config-actions"><button :disabled="loading || selectedTrainIds.length === 0 || selectedValIds.length === 0" @click="startTraining"><Sparkles :size="16" />{{ uiText("开始训练", "Start training") }}</button><button :disabled="loading" @click="runTrainingSmokeTest"><Check :size="16" />{{ uiText("冒烟测试", "Smoke test") }}</button></div>
      </section>
      <form class="training-image-search" @submit.prevent="searchTrainingImages"><Search :size="16" /><input v-model="trainingImageQuery" :placeholder="uiText('搜索图片文件名', 'Search image filename')" /><button>{{ uiText("查询", "Search") }}</button></form>
      <section class="training-data-grid">
        <div class="result-summary"><h2>{{ uiText("训练集", "Training set") }} · {{ selectedTrainIds.length }}</h2><div class="training-data-actions"><button @click="randomizeTrainingSet('train')">{{ uiText("随机打乱", "Shuffle") }}</button><button @click="removeUnannotatedFromCurrentPage('train')">{{ uiText("剔除无标注", "Remove empty") }}</button><button @click="trainingImages.forEach((image) => toggleTrainingId('train', image.imageId))">{{ uiText("全选本页", "Select page") }}</button></div><div class="training-image-list training-thumbnail-grid"><div v-for="image in trainingImages" :key="`train-${image.imageId}`" class="training-image-card"><input type="checkbox" :checked="selectedTrainIds.includes(image.imageId)" @change="toggleTrainingId('train', image.imageId)" /><button class="training-image-thumb-button" @click="trainingImageDetail = image"><img :src="assetUrl(image.imageUrl)" :alt="image.name" /><span>{{ image.name }}</span></button></div></div></div>
        <div class="result-summary"><h2>{{ uiText("验证集", "Validation set") }} · {{ selectedValIds.length }}</h2><div class="training-data-actions"><button @click="randomizeTrainingSet('val')">{{ uiText("随机打乱", "Shuffle") }}</button><button @click="removeUnannotatedFromCurrentPage('val')">{{ uiText("剔除无标注", "Remove empty") }}</button><button @click="trainingValImages.forEach((image) => toggleTrainingId('val', image.imageId))">{{ uiText("全选本页", "Select page") }}</button></div><div class="training-image-list training-thumbnail-grid"><div v-for="image in trainingValImages" :key="`val-${image.imageId}`" class="training-image-card"><input type="checkbox" :checked="selectedValIds.includes(image.imageId)" @change="toggleTrainingId('val', image.imageId)" /><button class="training-image-thumb-button" @click="trainingImageDetail = image"><img :src="assetUrl(image.imageUrl)" :alt="image.name" /><span>{{ image.name }}</span></button></div></div></div>
      </section>
      <div class="training-pagination"><div><button :disabled="trainingImagePage <= 1" @click="changeTrainingImagePage(trainingImagePage - 1)">{{ uiText("训练集上一页", "Train previous") }}</button><span>{{ trainingImagePage }} / {{ Math.max(1, Math.ceil(trainingImageTotal / trainingImagePageSize)) }} · {{ trainingImageTotal }}</span><button :disabled="trainingImagePage * trainingImagePageSize >= trainingImageTotal" @click="changeTrainingImagePage(trainingImagePage + 1)">{{ uiText("训练集下一页", "Train next") }}</button></div><div><button :disabled="trainingValImagePage <= 1" @click="changeTrainingValPage(trainingValImagePage - 1)">{{ uiText("验证集上一页", "Val previous") }}</button><span>{{ trainingValImagePage }} / {{ Math.max(1, Math.ceil(trainingValImageTotal / trainingImagePageSize)) }} · {{ trainingValImageTotal }}</span><button :disabled="trainingValImagePage * trainingImagePageSize >= trainingValImageTotal" @click="changeTrainingValPage(trainingValImagePage + 1)">{{ uiText("验证集下一页", "Val next") }}</button></div></div>
      <section class="result-summary training-metrics"><h2>{{ uiText("实时训练指标", "Live metrics") }}</h2><div v-if="trainingMetrics.length === 0" class="empty-state">{{ uiText("训练启动后显示指标", "Metrics appear after training starts") }}</div><div v-else class="metric-grid"><div v-for="metric in trainingMetrics.slice(-1)" :key="metric.metricId"><strong>Epoch {{ metric.epoch }} / {{ metric.totalEpochs }}</strong><span>Loss {{ metric.trainLoss?.toFixed(4) ?? "-" }} · mAP50 {{ metric.map50?.toFixed(4) ?? "-" }} · Precision {{ metric.precision?.toFixed(4) ?? "-" }} · Recall {{ metric.recall?.toFixed(4) ?? "-" }}</span></div></div><div v-if="trainingMetrics.length > 1" class="metric-chart"><div v-for="metric in trainingMetrics" :key="`loss-${metric.metricId}`" class="metric-bar" :style="{ height: `${Math.max(4, Math.min(100, (metric.trainLoss ?? 0) * 100))}%` }" :title="`epoch ${metric.epoch}: ${metric.trainLoss ?? '-'}`"></div></div></section>
      <section class="result-summary"><h2>{{ uiText("训练记录", "Training runs") }}</h2><div v-if="trainingTasks.length === 0" class="empty-state">{{ uiText("暂无训练记录", "No training runs") }}</div><button v-for="task in trainingTasks" :key="task.trainingId" class="version-row" :class="{ selected: selectedTrainingId === task.trainingId }" @click="selectedTrainingId = task.trainingId; openTrainingMetricDetail(task.trainingId); pollTrainingTask(task.trainingId)"><strong>{{ task.name }}</strong><span>{{ task.status }} · {{ task.modelName }} · {{ task.trainImageIds.length }} / {{ task.valImageIds.length }}<small v-if="task.error">{{ task.error }}</small></span></button></section>
    </section>
    <section v-else class="settings-page">
      <div class="settings-header">
        <div>
          <h2><Tags :size="22" />{{ uiText("标签配置", "Label Configuration") }}</h2>
          <p>{{ uiText("标签 ID 从 0 开始。英文名用于模型和导出，中文名用于人工校验。", "Label IDs start at 0. English names are used by models and exports; Chinese names support human review.") }}</p>
        </div>
        <button :disabled="loading" @click="refreshSettingsData"><RefreshCw :size="16" />{{ uiText("刷新", "Refresh") }}</button>
      </div>

      <form v-if="isAdmin" class="label-form" @submit.prevent="submitLabel">
        <label class="field-label"><span>{{ uiText("英文名称", "English Name") }}</span><input v-model="labelForm.englishName" required placeholder="rail_worker" /></label>
        <label class="field-label"><span>{{ uiText("中文名称", "Chinese Name") }}</span><input v-model="labelForm.chineseName" required placeholder="铁路工作人员" /></label>
        <label class="field-label wide"><span>{{ uiText("描述（英文在前，中文在后）", "Description (English first, then Chinese)") }}</span><textarea v-model="labelForm.description" rows="2" placeholder="English description / 中文描述"></textarea></label>
        <button :disabled="loading"><Plus :size="16" />{{ uiText("新增标签", "Add Label") }}</button>
      </form>

      <div class="settings-tools-row">
      <form class="settings-label-search" @submit.prevent="searchSettingsLabels">
          <Search :size="16" />
          <input v-model="settingsLabelQuery" :placeholder="uiText('搜索中英文标签或描述', 'Search English/Chinese labels or descriptions')" />
          <button :disabled="loading">{{ uiText("查询", "Search") }}</button>
      </form>
      <button v-if="isAdmin" :disabled="allLabelThumbnailsBusy" @click="lookupMissingLabelThumbnails">
        <Loader2 v-if="allLabelThumbnailsBusy" class="spin" :size="15" /><ImageIcon v-else :size="15" />{{ uiText("查找缺失缩略图", "Find Missing Thumbnails") }}
      </button>
      </div>
      <div class="label-config-grid">
        <div v-if="settingsLabelRecords.length === 0" class="empty-state table-empty">{{ uiText("暂无标签配置", "No label configurations") }}</div>
        <div v-for="label in settingsLabelRecords" :key="label.labelId" class="label-row">
          <div class="label-card-head">
            <strong>#{{ label.labelId }}</strong>
            <span class="label-thumbnail-cell">
            <img v-if="label.thumbnailUrl" :src="label.thumbnailUrl" :alt="label.chineseName" loading="lazy" />
            <button v-else :title="uiText('在线查找缩略图', 'Find thumbnail online')" :disabled="labelThumbnailBusyId === label.labelId" @click="lookupLabelThumbnail(label.labelId)">
              <Loader2 v-if="labelThumbnailBusyId === label.labelId" class="spin" :size="14" /><ImageIcon v-else :size="15" />
            </button>
            </span>
            <div class="label-card-names">
              <template v-if="editingLabelId === label.labelId">
                <input v-model="editingLabel.englishName" aria-label="English name / 英文名称" />
                <input v-model="editingLabel.chineseName" aria-label="Chinese name / 中文名称" />
              </template>
              <template v-else>
                <strong :title="label.chineseName">{{ labelDisplay(label) }}</strong>
                <span :title="label.englishName">{{ uiLanguage === "zh" ? label.englishName : label.chineseName }}</span>
              </template>
            </div>
          </div>
          <div class="label-card-description">
            <textarea v-if="editingLabelId === label.labelId" v-model="editingLabel.description" rows="2" aria-label="Description / 标签描述" />
            <span v-else :title="label.description || '-'">{{ labelDescription(label.description) || "-" }}</span>
          </div>
          <div class="label-card-footer">
            <small>{{ uiText("创建", "Created") }} {{ formatTime(label.createdAt) }} · {{ uiText("更新", "Updated") }} {{ formatTime(label.updatedAt) }}</small>
            <span v-if="isAdmin" class="row-actions">
              <template v-if="editingLabelId === label.labelId">
                <button :title="uiText('保存', 'Save')" @click="submitEditLabel(label.labelId)"><Save :size="15" /></button>
                <button :title="uiText('取消', 'Cancel')" @click="editingLabelId = null"><RotateCcw :size="15" /></button>
              </template>
              <template v-else>
              <button :title="uiText('编辑', 'Edit')" @click="startEditLabel(label)"><Edit3 :size="15" /></button>
              <button :title="uiText('复制标签', 'Duplicate label')" @click="duplicateLabel(label.labelId)"><Copy :size="15" /></button>
              <button :title="uiText('复制标签文本', 'Copy label text')" @click="copyLabelText(label)"><ClipboardCopy :size="15" /></button>
              <button :title="uiText('删除', 'Delete')" @click="removeLabel(label.labelId)"><Trash2 :size="15" /></button>
              </template>
            </span>
          </div>
        </div>
      </div>

      <div class="pagination-controls label-pagination">
          <span>{{ settingsLabelTotal }} {{ uiText("个标签", "labels") }}</span>
        <button :disabled="settingsLabelPage <= 1" @click="changeSettingsLabelPage(settingsLabelPage - 1)">{{ uiText("上一页", "Previous") }}</button>
        <span>{{ settingsLabelPage }} / {{ Math.max(1, Math.ceil(settingsLabelTotal / settingsLabelPageSize)) }}</span>
        <button :disabled="settingsLabelPage * settingsLabelPageSize >= settingsLabelTotal" @click="changeSettingsLabelPage(settingsLabelPage + 1)">{{ uiText("下一页", "Next") }}</button>
      </div>

      <section class="term-candidates">
        <div class="settings-header">
          <div><h2><Tags :size="20" />{{ uiText("描述词候选", "Caption Term Candidates") }}</h2><p>{{ uiText("从视频帧中文描述中提取的高频名词", "Frequent nouns extracted from Chinese video-frame captions") }}</p></div>
          <form class="settings-label-search" @submit.prevent="searchTermCandidates"><Search :size="16" /><input v-model="termCandidateQuery" :placeholder="uiText('筛选候选词', 'Filter candidate terms')" /><button>{{ uiText("查询", "Search") }}</button></form>
        </div>
        <div class="term-candidate-list">
          <div v-for="term in termCandidates" :key="term.englishName" class="term-candidate-row">
            <span class="term-thumb" :title="term.chineseName">{{ term.chineseName.slice(0, 2) }}</span>
            <strong>{{ uiLanguage === "zh" ? term.chineseName : term.englishName }}</strong><small>{{ term.occurrences }} {{ uiText("次", "occurrences") }}</small>
            <button v-if="isAdmin" :title="uiText('加入标签', 'Add label')" @click="addTermCandidate(term)"><Plus :size="15" /></button>
          </div>
          <div v-if="termCandidates.length === 0" class="empty-state">{{ uiText("暂无待添加的高频名词", "No frequent terms to add") }}</div>
        </div>
        <div class="pagination-controls">
          <span>{{ termCandidateTotal }} {{ uiText("个候选", "candidates") }}</span>
          <button :disabled="termCandidatePage <= 1" @click="termCandidatePage--; loadTermCandidates()">{{ uiText("上一页", "Previous") }}</button>
          <span>{{ termCandidatePage }} / {{ Math.max(1, Math.ceil(termCandidateTotal / 20)) }}</span>
          <button :disabled="termCandidatePage * 20 >= termCandidateTotal" @click="termCandidatePage++; loadTermCandidates()">{{ uiText("下一页", "Next") }}</button>
        </div>
      </section>

      <template v-if="isAdmin">
        <div class="settings-header user-admin-header">
          <div>
            <h2><UserRound :size="22" />{{ uiText("账号与角色", "Accounts & Roles") }}</h2>
            <p>{{ uiText("学生负责标注，审核员负责通过或驳回，管理员可维护标签和账号角色。", "Students annotate, reviewers approve or reject, and admins manage labels and roles.") }}</p>
          </div>
          <button :disabled="loading" @click="loadUsers"><RefreshCw :size="16" />{{ uiText("刷新", "Refresh") }}</button>
        </div>
        <div class="user-admin-list">
          <div v-for="user in users" :key="user.userId" class="user-admin-row">
            <span><strong>{{ user.displayName }}</strong><small>{{ user.username }}</small></span>
            <select :value="user.role" :disabled="user.userId === currentUser?.userId" @change="handleRoleChange(user.userId, $event)">
              <option value="student">{{ uiText("学生", "Student") }}</option>
              <option value="reviewer">{{ uiText("审核员", "Reviewer") }}</option>
              <option value="admin">{{ uiText("管理员", "Administrator") }}</option>
            </select>
          </div>
        </div>
      </template>
    </section>

    <div v-if="loading" class="system-loading-backdrop" role="status" aria-live="polite" aria-label="正在加载后台数据">
      <div class="system-loading-dialog">
        <Loader2 class="spin" :size="28" />
        <strong>{{ processingOverlayText || uiText("正在加载后台数据", "Loading data") }}</strong>
        <span>{{ uiText("请稍候，数据将从后台服务读取", "Please wait while data is loaded from the server") }}</span>
      </div>
    </div>

    <div v-if="errorDialog" class="system-error-backdrop" role="alertdialog" aria-modal="true" aria-labelledby="system-error-title">
      <div class="system-error-dialog">
        <div>
            <strong id="system-error-title">{{ uiText("操作失败", "Operation failed") }}</strong>
          <span>{{ uiNotice(errorDialog) }}</span>
        </div>
        <button autofocus @click="errorDialog = ''">{{ uiText("关闭", "Close") }}</button>
      </div>
    </div>

    <div v-if="originalPreview" class="modal-backdrop" @click="originalPreview = null">
      <div class="original-modal" @click.stop>
        <img :src="assetUrl(originalPreview.imageUrl)" alt="原图预览" />
        <button @click="originalPreview = null">{{ uiText("关闭", "Close") }}</button>
      </div>
    </div>

    <div v-if="trainingImageDetail" class="modal-backdrop" @click.self="trainingImageDetail = null">
      <section class="training-image-detail" role="dialog" aria-modal="true" @click.stop>
        <header><h2>{{ trainingImageDetail.name }}</h2><button @click="trainingImageDetail = null">{{ uiText("关闭", "Close") }}</button></header>
        <div class="training-image-detail-body"><img :src="assetUrl(trainingImageDetail.imageUrl)" :alt="trainingImageDetail.name" /><div><h3>{{ uiText("标注数值", "Annotation values") }}</h3><pre>{{ JSON.stringify(trainingImageDetail.resultJson || trainingImageDetail.annotationJson || {}, null, 2) }}</pre></div></div>
      </section>
    </div>

    <div v-if="trainingMetricDetail" class="modal-backdrop" @click.self="trainingMetricDetail = null">
      <section class="training-metric-detail" role="dialog" aria-modal="true" @click.stop>
        <header><h2>{{ trainingMetricDetail.task.name }}</h2><button @click="trainingMetricDetail = null">{{ uiText("关闭", "Close") }}</button></header>
        <p>{{ trainingMetricDetail.task.status }} · {{ trainingMetricDetail.task.modelName }} · {{ trainingMetricDetail.task.createdAt }}</p>
        <div v-if="trainingMetricDetail.metrics.length" class="metric-chart-panel">
          <div class="metric-chart-legend"><span><i class="legend-loss"></i>Loss</span><span><i class="legend-precision"></i>Precision</span><span><i class="legend-recall"></i>Recall</span><span><i class="legend-map"></i>mAP50</span></div>
          <div class="metric-chart-wrap">
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" class="metric-line-chart">
              <line x1="0" y1="96" x2="100" y2="96" class="chart-axis" /><line x1="0" y1="8" x2="0" y2="96" class="chart-axis" />
              <polyline :points="metricChartPoints('trainLoss')" class="chart-line chart-loss" /><polyline :points="metricChartPoints('precision')" class="chart-line chart-precision" /><polyline :points="metricChartPoints('recall')" class="chart-line chart-recall" /><polyline :points="metricChartPoints('map50')" class="chart-line chart-map" />
              <circle v-for="metric in trainingMetricDetail.metrics" :key="`hover-${metric.metricId}`" :cx="((metric.epoch - 1) / Math.max(1, trainingMetricDetail.metrics.length - 1)) * 100" cy="50" r="1.8" class="chart-hover-target" @mouseenter="trainingMetricHover = metric.epoch" />
            </svg>
            <div v-if="trainingMetricHover" class="metric-tooltip"><strong>Epoch {{ trainingMetricHover }}</strong><template v-for="metric in trainingMetricDetail.metrics.filter((item) => item.epoch === trainingMetricHover)" :key="metric.metricId"><span>Loss: {{ metric.trainLoss?.toFixed(4) ?? "-" }}</span><span>Precision: {{ metric.precision?.toFixed(4) ?? "-" }}</span><span>Recall: {{ metric.recall?.toFixed(4) ?? "-" }}</span><span>mAP50: {{ metric.map50?.toFixed(4) ?? "-" }}</span></template></div>
          </div>
          <div class="metric-chart-axis-labels"><span>Epoch 0</span><span>Epoch 100</span></div>
        </div>
        <div class="metric-detail-grid"><div v-for="metric in trainingMetricDetail.metrics.slice(-1)" :key="metric.metricId"><strong>Epoch {{ metric.epoch }} / 100</strong><span>Loss {{ metric.trainLoss?.toFixed(4) ?? "-" }}</span><span>Precision {{ metric.precision?.toFixed(4) ?? "-" }}</span><span>Recall {{ metric.recall?.toFixed(4) ?? "-" }}</span><span>mAP50 {{ metric.map50?.toFixed(4) ?? "-" }}</span></div></div>
        <div v-if="trainingMetricDetail.metrics.length === 0" class="empty-state">{{ uiText("暂无逐轮指标", "No epoch metrics") }}</div>
      </section>
    </div>

    <div v-if="imageInfoDialogTarget" class="modal-backdrop" @click.self="imageInfoDialogTarget = null">
      <section class="image-info-dialog" role="dialog" aria-modal="true" :aria-label="uiText('图片信息', 'Image information')" @click.stop>
        <header class="image-info-dialog-head">
          <h2>{{ uiText("图片信息", "Image information") }}</h2>
          <button class="icon-button" :title="uiText('关闭', 'Close')" @click="imageInfoDialogTarget = null">×</button>
        </header>
        <dl class="image-info image-info-dialog-list">
          <dt>{{ uiText("文件名", "File name") }}</dt>
          <dd>{{ imageInfoDialogTarget.originalName }}</dd>
          <dt>{{ uiText("存储位置", "Storage path") }}</dt>
          <dd>{{ imageInfoDialogTarget.filePath || imageInfoDialogTarget.fileUrl }}</dd>
          <dt>{{ uiText("大小", "Size") }}</dt>
          <dd>{{ formatBytes(imageInfoDialogTarget.fileSize) }}</dd>
          <dt>{{ uiText("数据库", "Database") }}</dt>
          <dd>image_asset → image_task → image_task_result → image_task_result_version</dd>
          <dt>{{ uiText("图片 ID", "Image ID") }}</dt>
          <dd>{{ imageInfoDialogTarget.imageId }}</dd>
        </dl>
        <button class="image-info-copy" @click="copyCurrentImageInfo"><ClipboardCopy :size="15" />{{ uiText("一键复制", "Copy all") }}</button>
      </section>
    </div>

    <div v-if="videoPreviewUrl" class="modal-backdrop" @click.self="videoPreviewUrl = ''">
      <div class="video-preview-modal" @click.stop>
        <strong>{{ videoPreviewTitle }}</strong>
        <video :src="videoPreviewUrl" controls autoplay playsinline></video>
        <button @click="videoPreviewUrl = ''; videoPreviewTitle = ''">{{ uiText("关闭", "Close") }}</button>
      </div>
    </div>

    <div v-if="lightboxFrame" class="lightbox-backdrop" @click.self="closeFrameLightbox">
      <div class="lightbox-modal" role="dialog" aria-modal="true" :aria-label="uiText('视频帧全屏查看', 'Video frame viewer')">
        <header class="lightbox-head">
          <div>
            <strong>{{ selectedVideoCaptionVideo?.displayName || selectedVideoCaptionVideo?.filename || uiText("视频帧", "Video frame") }}</strong>
            <span>{{ formatTimestamp(lightboxFrame.timestampMs) }} · {{ uiText("帧号", "Frame") }} {{ lightboxFrame.frameIndex }}</span>
          </div>
          <div class="lightbox-actions">
            <button :title="uiText('上一帧', 'Previous frame')" @click="stepLightbox(-1)"><ChevronLeft :size="16" /></button>
            <button :title="uiText('下一帧', 'Next frame')" @click="stepLightbox(1)"><ChevronRight :size="16" /></button>
            <button :title="uiText('放大', 'Zoom in')" @click="zoomFrameAtCenter(1.15, lightboxStageEl)"><ZoomIn :size="16" /></button>
            <button :title="uiText('缩小', 'Zoom out')" @click="zoomFrameAtCenter(1 / 1.15, lightboxStageEl)"><ZoomOut :size="16" /></button>
            <button :title="uiText('重置', 'Reset')" @click="resetFrameView"><RotateCcw :size="16" /></button>
            <button :title="uiText('查看原图', 'View original frame')" @click="openFrameOriginal(lightboxFrame)"><ImageIcon :size="16" /></button>
            <span>{{ Math.round(frameView.zoom * 100) }}%</span>
            <button :title="uiText('关闭', 'Close')" @click="closeFrameLightbox">{{ uiText("关闭", "Close") }}</button>
          </div>
        </header>
        <nav class="lightbox-analysis-tabs" :aria-label="uiText('识别结果', 'Recognition results')">
          <button :class="{ active: lightboxTaskType === 'detection' }" @click="lightboxTaskType = 'detection'">{{ taskTitle("detection") }}</button>
          <button :class="{ active: lightboxTaskType === 'segmentation' }" @click="lightboxTaskType = 'segmentation'">{{ taskTitle("segmentation") }}</button>
          <button :class="{ active: lightboxTaskType === 'pose' }" @click="lightboxTaskType = 'pose'">{{ taskTitle("pose") }}</button>
          <button :class="{ active: lightboxTaskType === 'original' }" @click="lightboxTaskType = 'original'">{{ uiText("原图", "Original") }}</button>
        </nav>
        <div
          ref="lightboxStageEl"
          class="lightbox-stage"
          :class="{ 'is-zoomed': frameView.zoom > 1 }"
          @wheel="onFrameWheel"
          @pointerdown="onFramePointerDown"
          @pointermove="onFramePointerMove"
          @pointerup="stopFrameDrag"
          @pointercancel="stopFrameDrag"
        >
          <div class="lightbox-media" :style="{ aspectRatio: `${lightboxImageSize.width} / ${lightboxImageSize.height}`, transform: `translate(${frameView.x}px, ${frameView.y}px) scale(${frameView.zoom})` }">
            <img :src="assetUrl(lightboxFrame.imageUrl)" alt="视频帧" />
            <svg class="lightbox-overlay" :viewBox="`0 0 ${lightboxImageSize.width} ${lightboxImageSize.height}`" preserveAspectRatio="none">
              <template v-if="lightboxTaskType === 'detection'">
                <g v-for="(item, index) in detectionOverlayBoxes" :key="`box-${index}`" class="lightbox-detection">
                  <rect :x="item.bbox?.x" :y="item.bbox?.y" :width="item.bbox?.width" :height="item.bbox?.height" />
                  <text :x="item.bbox?.x" :y="Math.max(16, Number(item.bbox?.y ?? 0) - 5)">{{ detectionLabelDisplay(item.label) }} {{ Math.round(Number(item.confidence ?? 0) * 100) }}%</text>
                </g>
              </template>
              <polygon v-else-if="lightboxTaskType === 'segmentation'" v-for="(item, index) in segmentationOverlayPolygons" :key="`segment-${index}`" class="lightbox-segment" :points="coordinatePairsToPoints(item.polygon ?? [])" />
              <template v-else-if="lightboxTaskType === 'pose'">
                <line v-for="bone in poseOverlayBones" :key="bone.key" class="lightbox-pose-bone" :x1="bone.x1" :y1="bone.y1" :x2="bone.x2" :y2="bone.y2" :opacity="Math.max(.45, bone.score)" />
                <circle v-for="point in poseOverlayPoints" :key="point.key" class="lightbox-pose-point" :cx="point.x" :cy="point.y" :r="Math.max(3.5, lightboxImageSize.width / 180 * .7)" :opacity="Math.max(.45, point.score)" />
              </template>
            </svg>
          </div>
        </div>
        <footer class="lightbox-caption">
          <section>
            <h3>{{ uiText("画面描述", "Frame Caption") }}</h3>
            <div v-if="uiLanguage === 'zh'" class="markdown-content" v-html="renderMarkdown(lightboxFrame.descriptionText || '暂无中文描述')" />
            <template v-else>
              <div v-if="!lightboxFrame.descriptionEn" class="frame-description-en-heading"><span>{{ uiText("未生成英文描述", "No English caption") }}</span><button :disabled="frameTranslationBusy" @click="generateCaptionEnglish">{{ uiText("本地生成", "Generate locally") }}</button></div>
              <div class="markdown-content" v-html="renderMarkdown(lightboxFrame.descriptionEn || 'No English caption available')" />
            </template>
          </section>
          <section class="manual-caption-editor">
            <label><span>{{ uiText("人工编辑描述", "Manual Caption") }}</span><textarea v-model="manualFrameDescription" rows="4" maxlength="10000" /></label>
            <label class="safety-score-control"><span>{{ uiText("安全程度", "Safety Score") }}</span><input :value="frameSafetyScore ?? ''" @input="setFrameSafetyScore" type="number" min="0" max="10" step="1" :placeholder="uiText('未评分', 'Unrated')" /><output>/ 10</output></label>
            <button :disabled="frameReviewBusy" @click="saveCaptionReview"><Save :size="15" />{{ uiText("保存人工复核", "Save Review") }}</button>
          </section>
        </footer>
      </div>
    </div>
  </main>

  <main v-else class="auth-shell">
    <section class="auth-panel" aria-labelledby="auth-title">
      <div class="auth-brand">
        <img :src="'/favicon.svg'" alt="" />
        <div>
          <h1 id="auth-title">{{ uiText("铁路多目标识别平台", "Railway Multi-Target Recognition") }}</h1>
          <span>{{ uiText("学生标注与智能识别工作台", "Intelligent Annotation Workspace") }}</span>
        </div>
      </div>

      <label class="auth-language-picker"><span>{{ uiText("界面语言", "Interface language") }}</span><select v-model="uiLanguage" @change="persistUiLanguage"><option value="zh">中文</option><option value="en">English</option></select></label>
      <div class="auth-mode" role="tablist" :aria-label="uiText('账号操作', 'Account actions')">
        <button :class="{ active: authMode === 'login' }" type="button" @click="switchAuthMode('login')">{{ uiText("登录", "Log in") }}</button>
        <button :class="{ active: authMode === 'register' }" type="button" @click="switchAuthMode('register')">{{ uiText("注册", "Register") }}</button>
      </div>

      <form class="auth-form" @submit.prevent="submitAuth">
        <label>
          <span>{{ uiText("学号或账号", "Student ID or username") }}</span>
          <input v-model="authForm.username" required minlength="3" maxlength="50" autocomplete="username" :placeholder="uiText('请输入学号或账号', 'Enter student ID or username')" />
        </label>
        <label v-if="authMode === 'register'">
          <span>{{ uiText("学生姓名", "Display name") }}</span>
          <input v-model="authForm.displayName" required maxlength="80" autocomplete="name" :placeholder="uiText('请输入姓名', 'Enter your name')" />
        </label>
        <label>
          <span>{{ uiText("密码", "Password") }}</span>
          <input
            v-model="authForm.password"
            required
            :minlength="authMode === 'register' ? 6 : 1"
            maxlength="128"
            type="password"
            :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'"
            :placeholder="uiText('请输入密码', 'Enter password')"
          />
        </label>
        <button class="auth-submit" type="submit" :disabled="loading">
          <Loader2 v-if="loading" class="spin" :size="17" />
          <UserRound v-else :size="17" />
          {{ authMode === "login" ? uiText("登录系统", "Log in") : uiText("创建学生账号", "Create student account") }}
        </button>
        <div v-if="errorDialog" class="auth-inline-error" role="alert">{{ uiNotice(errorDialog) }}</div>
      </form>
    </section>

    <div v-if="loading" class="system-loading-backdrop" role="status" aria-live="polite">
      <div class="system-loading-dialog">
        <Loader2 class="spin" :size="28" />
        <strong>{{ authReady ? uiText("正在验证账号", "Verifying account") : uiText("正在恢复登录状态", "Restoring session") }}</strong>
        <span>{{ uiText("登录状态由后台数据库持久化保存", "Your session is persisted in the application database") }}</span>
      </div>
    </div>

  </main>
</template>
