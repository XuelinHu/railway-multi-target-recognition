<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import {
  Boxes,
  Camera,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  Edit3,
  Film,
  Image as ImageIcon,
  LogOut,
  Loader2,
  Maximize2,
  MousePointer2,
  Move,
  Pentagon,
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
  Volume2,
  Waypoints,
  ZoomIn,
} from "@lucide/vue";
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
  type VideoCaptionBatch,
  type VideoCaptionFrame,
  type VideoCaptionVideo,
  assetUrl,
  createImageTask,
  createLabel,
  copyLabel,
  deleteLabel,
  getTaskResult,
  getTaskResultVersion,
  inferImageTask,
  getCurrentUser,
  listImages,
  listLabels,
  listUsers,
  listTaskResultVersions,
  listVideoCaptionBatches,
  listVideoCaptionFrames,
  listVideoCaptionVideos,
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
} from "./api";

type PageMode = "workspace" | "videoCaptions" | "liveGesture" | "settings";
type AnnotationTool = "select" | "pan" | "box" | "polygon" | "line";
type ShapeType = "box" | "polygon" | "line";
type ResizeSide = "history" | "thumbnail";
type AuthMode = "login" | "register";

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
  { type: "detection", title: "目标检测", description: "检测框、类别与置信度", models: ["yolo11n", "yolov8n"] },
  { type: "segmentation", title: "实例分割", description: "区域 mask、轮廓与类别", models: ["yolo11n-seg"] },
  { type: "pose", title: "姿态识别", description: "关键点与骨架连线", models: ["yolo11n-pose"] },
  { type: "classification", title: "图像分类", description: "分类标签与概率", models: ["yolo11n-cls"] },
  {
    type: "caption",
    title: "图像描述",
    description: "生成图片描述文本",
    models: ["deepseek-vl2-tiny", "blip-image-captioning-base", "yolo-cls-fallback"],
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
const labels = ref<LabelConfig[]>([]);
const activeRequestCount = ref(0);
const loading = computed(() => activeRequestCount.value > 0);
const processingOverlayText = ref("");
const message = ref("");
const errorDialog = ref("");
const historyCollapsed = ref(false);
const thumbnailCollapsed = ref(false);
const workspaceBodyRef = ref<HTMLElement | null>(null);
const panelLayout = reactive({
  historyWidth: 280,
  thumbnailWidth: 300,
  resizing: null as ResizeSide | null,
});
const originalPreview = ref<ImageAsset | null>(null);
const activeTool = ref<AnnotationTool>("select");
const selectedShapeId = ref<string | null>(null);
const activePresetLabelId = ref<number | null>(null);
const draftShape = ref<AnnotationShape | null>(null);
const polygonDraft = ref<Point[]>([]);
const drawing = reactive({ active: false, mode: "" as "" | "draw" | "move" | "resize", shapeId: "", start: null as Point | null });

const labelForm = reactive({
  englishName: "",
  chineseName: "",
  description: "",
});
const editingLabelId = ref<number | null>(null);
const editingLabel = reactive({ englishName: "", chineseName: "", description: "" });
const currentUser = ref<AuthUser | null>(null);
const authReady = ref(false);
const authMode = ref<AuthMode>("login");
const authForm = reactive({ username: "", displayName: "", password: "" });
const users = ref<AuthUser[]>([]);
const reviewCommentInput = ref("");
const videoCaptionBatches = ref<VideoCaptionBatch[]>([]);
const videoCaptionVideos = ref<VideoCaptionVideo[]>([]);
const videoCaptionFrames = ref<VideoCaptionFrame[]>([]);
const selectedVideoCaptionBatchId = ref("");
const selectedVideoCaptionVideoId = ref("");
const selectedVideoCaptionFrameId = ref("");
const videoCaptionQuery = ref("");
const videoCaptionTotal = ref(0);

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
  await restoreLoginState();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
  stopPanelResize();
});

async function restoreLoginState() {
  await runBusy(async () => {
    currentUser.value = await getCurrentUser();
    if (currentUser.value) await initializeAuthenticatedWorkspace();
  }, "登录状态检查失败");
  authReady.value = true;
}

async function initializeAuthenticatedWorkspace() {
  await Promise.all([loadLabels(), loadImageHistory()]);
  const first = imageHistoryList.value[0];
  if (first) await selectImage(first);
}

async function submitAuth() {
  await runBusy(async () => {
    currentUser.value =
      authMode.value === "login"
        ? await login({ username: authForm.username.trim(), password: authForm.password })
        : await register({
            username: authForm.username.trim(),
            displayName: authForm.displayName.trim(),
            password: authForm.password,
          });
    authForm.password = "";
    await initializeAuthenticatedWorkspace();
    message.value = `欢迎，${currentUser.value.displayName}`;
  }, authMode.value === "login" ? "登录失败" : "注册失败");
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
  if (page === "settings" && isAdmin.value) await loadUsers();
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
    await loadImageHistory();
    message.value = "上传完成，原图已保存";
  }, "图片上传失败，请稍后重试");
}

async function loadImageHistory() {
  await runBusy(async () => {
    const records: ImageAsset[] = [];
    let page = 1;
    let total = 0;
    do {
      const data = await listImages({ taskType: currentTaskType.value, page, pageSize: 200 });
      records.push(...data.records);
      total = data.total;
      page += 1;
    } while (records.length < total);
    imageHistoryList.value = records;
  }, "历史图片加载失败");
}

async function selectImage(image: ImageAsset) {
  await runBusy(async () => {
    await bindImageToCurrentTask(image);
    const result = await getTaskResult({
      imageId: image.imageId,
      taskType: currentTaskType.value,
      sessionId: image.sessionId || defaultSessionId,
    });
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
    page: 1,
    pageSize: 500,
    query: videoCaptionQuery.value.trim(),
  });
  videoCaptionFrames.value = data.records;
  videoCaptionTotal.value = data.total;
  if (!videoCaptionFrames.value.some((frame) => frame.frameId === selectedVideoCaptionFrameId.value)) {
    selectedVideoCaptionFrameId.value = videoCaptionFrames.value[0]?.frameId ?? "";
  }
}

async function searchVideoCaptionFrames() {
  await runBusy(loadVideoCaptionFrames, "帧描述检索失败");
}

function selectVideoCaptionFrame(frameId: string) {
  selectedVideoCaptionFrameId.value = frameId;
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
    message.value = "标签已新增";
  }, "新增标签失败");
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
    message.value = "标签已更新";
  }, "更新标签失败");
}

async function removeLabel(labelId: number) {
  await runBusy(async () => {
    await deleteLabel(labelId);
    if (selectedShape.value?.labelId === labelId) selectedShapeId.value = null;
    await loadLabels();
    message.value = "标签已删除";
  }, "删除标签失败");
}

function setTool(tool: AnnotationTool) {
  if (editingDisabled.value && ["box", "polygon", "line"].includes(tool)) {
    message.value = resultLocked.value ? "审核通过的结果已锁定" : "审核员只能查看和审核任务";
    return;
  }
  activeTool.value = tool;
  draftShape.value = null;
  polygonDraft.value = [];
  drawing.active = false;
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
  if (activeTool.value === "select") {
    selectedShapeId.value = null;
    return;
  }
  if (activeTool.value === "polygon") {
    polygonDraft.value = [...polygonDraft.value, point];
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
  if (draftShape.value && drawing.mode === "draw") {
    draftShape.value = { ...draftShape.value, points: [draftShape.value.points[0], point] };
    return;
  }
  if (drawing.mode === "move" && drawing.start) moveSelectedShape(point);
  if (drawing.mode === "resize" && drawing.start) resizeSelectedBox(point);
}

function onOverlayPointerUp() {
  if (draftShape.value && drawing.mode === "draw") {
    const shape = normalizeShapePoints(draftShape.value);
    if (shapeSize(shape) > 6) addShape(shape);
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
  activeTool.value = "select";
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
      type: (shape.type === "polygon" || shape.type === "line" ? shape.type : "box") as ShapeType,
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

function linePoints(points: Point[]) {
  return points.length >= 2 ? { x1: points[0].x, y1: points[0].y, x2: points[1].x, y2: points[1].y } : { x1: 0, y1: 0, x2: 0, y2: 0 };
}

function shapeTypeText(type: ShapeType) {
  return { box: "矩形框", polygon: "多边形", line: "线段" }[type];
}

function resultKeypoints(): PoseKeypoint[] {
  const keypoints = (currentState.value.resultJson?.keypoints as Array<Record<string, number | string>> | undefined) ?? [];
  return keypoints.map((point) => ({
    name: String(point.name),
    x: Number(point.x),
    y: Number(point.y),
    score: Number(point.score ?? 1),
  }));
}

function resultSkeleton(): PoseSkeletonLine[] {
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
  return "object / 对象";
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
  return { idle: "未处理", pending: "待处理", processing: "处理中", success: "已完成", failed: "失败" }[status];
}

function reviewStatusText(status: ImageReviewStatus) {
  return { draft: "草稿", pending_review: "待审核", approved: "已通过", rejected: "已驳回" }[status];
}
</script>

<template>
  <main v-if="currentUser" class="app-shell image-task-workspace">
    <header class="topbar">
      <div class="brand">
        <img :src="'/favicon.svg'" alt="" />
        <div>
          <h1>铁路多目标识别平台</h1>
          <span>{{ loading ? "处理中" : "就绪" }}<template v-if="message"> · {{ message }}</template></span>
        </div>
      </div>
      <div class="topbar-actions">
        <nav class="task-tabs" aria-label="工作区">
          <button :class="{ active: currentPage === 'workspace' }" @click="setPage('workspace')"><Boxes :size="16" />标注工作台</button>
          <button :class="{ active: currentPage === 'videoCaptions' }" @click="setPage('videoCaptions')"><Film :size="16" />视频解帧</button>
          <button :class="{ active: currentPage === 'liveGesture' }" @click="setPage('liveGesture')"><Camera :size="16" />实时手势</button>
          <button :class="{ active: currentPage === 'settings' }" @click="setPage('settings')"><Settings :size="16" />系统配置</button>
        </nav>
        <div class="user-session">
          <UserRound :size="17" />
          <span><strong>{{ currentUser.displayName }}</strong><small>{{ currentUser.username }}</small></span>
          <button title="退出登录" aria-label="退出登录" @click="signOut"><LogOut :size="16" /></button>
        </div>
      </div>
    </header>

    <nav v-if="currentPage === 'workspace'" class="task-strip" aria-label="功能页面">
      <button v-for="task in taskConfigs" :key="task.type" :class="{ active: currentTaskType === task.type }" @click="setTaskType(task.type)">
        {{ task.title }}
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
          <button class="ghost-button" :disabled="loading" @click="loadImageHistory"><RefreshCw :size="16" /> 刷新历史</button>
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

      <button
        class="panel-resizer history-resizer"
        :disabled="historyCollapsed"
        title="拖动调整历史图片宽度"
        aria-label="拖动调整历史图片宽度"
        @pointerdown="startPanelResize($event, 'history')"
      ></button>

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
                <option v-for="model in currentConfig.models" :key="model" :value="model">{{ model }}</option>
              </select>
            </label>
            <button :disabled="!currentState.currentImageId || loading || editingDisabled" @click="runCurrentTask">
              <Loader2 v-if="loading" class="spin" :size="16" />
              <Sparkles v-else :size="16" />
              开始处理
            </button>
            <button :disabled="!currentState.currentImageId || loading || editingDisabled" @click="saveCurrentResult"><Save :size="16" />保存结果</button>
            <button :disabled="!currentState.currentImageId || loading || editingDisabled" @click="saveAnnotationSnapshot"><Download :size="16" />保存标注</button>
          </div>
        </div>

        <div class="annotation-toolbar">
          <button :class="{ active: activeTool === 'select' }" title="选择" @click="setTool('select')"><MousePointer2 :size="16" />（选择）</button>
          <button :class="{ active: activeTool === 'pan' }" title="移动画布" @click="setTool('pan')"><Move :size="16" />（移动）</button>
          <button :disabled="editingDisabled" :class="{ active: activeTool === 'box' }" title="矩形框（B）" @click="setTool('box')"><Boxes :size="16" />（矩形框）</button>
          <button :disabled="editingDisabled" :class="{ active: activeTool === 'polygon' }" title="多边形（P）" @click="setTool('polygon')"><Pentagon :size="16" />（多边形）</button>
          <button :disabled="editingDisabled" :class="{ active: activeTool === 'line' }" title="线段（L）" @click="setTool('line')"><Waypoints :size="16" />（线段）</button>
          <button :disabled="polygonDraft.length < 3" @click="finishPolygon"><Check :size="16" />（完成）</button>
          <button :disabled="polygonDraft.length === 0" @click="cancelPolygon"><RotateCcw :size="16" />（取消）</button>
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
              <span>选择图片开始</span>
              <input type="file" accept="image/jpeg,image/png,image/webp,image/bmp" @change="handleUpload" />
            </label>
          </div>

          <div v-else class="canvas-content" :style="{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})` }">
            <img class="base-image" :src="currentImageUrl" alt="原始图片" />
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
                  <text class="box-label" :x="boxRect(shape).x + 4" :y="boxRect(shape).labelY">{{ shape.label }}</text>
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
                  <text class="box-label" :x="shapeBounds(shape).x + 4" :y="Math.max(shapeBounds(shape).y - 8, 16)">{{ shape.label }}</text>
                </g>
                <g v-else class="shape-group" :class="{ selected: shape.id === selectedShapeId }" @pointerdown.stop="startMoveShape($event, shape.id)">
                  <line class="line-shape" v-bind="linePoints(shape.points)" />
                  <text class="box-label" :x="shape.points[0].x + 4" :y="Math.max(shape.points[0].y - 8, 16)">{{ shape.label }}</text>
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
              <polyline v-if="polygonDraft.length > 0" class="draft-shape" :points="polygonPoints(polygonDraft)" />
              <circle v-for="(point, index) in polygonDraft" :key="index" class="draft-point" :cx="point.x" :cy="point.y" r="6" />
              <line v-for="line in resultSkeleton()" :key="line.name" class="pose-bone" :x1="line.x1" :y1="line.y1" :x2="line.x2" :y2="line.y2" />
              <circle v-for="point in resultKeypoints()" :key="point.name" class="keypoint" :cx="point.x" :cy="point.y" r="7" />
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
          <button @click="fitView"><Maximize2 :size="15" />适应窗口</button>
          <button @click="originalView"><ZoomIn :size="15" />原始比例</button>
          <button @click="resetView"><RotateCcw :size="15" />重置视图</button>
          <span>缩放 {{ Math.round(view.zoom * 100) }}%</span>
        </div>
      </section>

      <button
        class="panel-resizer thumbnail-resizer"
        :disabled="thumbnailCollapsed"
        title="拖动调整标签与属性宽度"
        aria-label="拖动调整标签与属性宽度"
        @pointerdown="startPanelResize($event, 'thumbnail')"
      ></button>

      <aside class="thumbnail-panel" :class="{ collapsed: thumbnailCollapsed }">
        <div class="panel-head">
          <strong v-if="!thumbnailCollapsed">标签与属性</strong>
          <button :title="thumbnailCollapsed ? '展开属性' : '收起属性'" @click="thumbnailCollapsed = !thumbnailCollapsed">
            <ChevronLeft v-if="thumbnailCollapsed" :size="16" />
            <ChevronRight v-else :size="16" />
          </button>
        </div>
        <template v-if="!thumbnailCollapsed">
          <button v-if="currentState.imageInfo" class="thumbnail-card" @click="originalPreview = currentState.imageInfo">
            <img :src="currentImageUrl" alt="原图缩略图" />
          </button>
          <dl v-if="currentState.imageInfo" class="image-info">
            <dt>文件名</dt>
            <dd>{{ currentState.imageInfo.originalName }}</dd>
            <dt>分辨率</dt>
            <dd>{{ currentState.imageInfo.width || "-" }} x {{ currentState.imageInfo.height || "-" }}</dd>
            <dt>大小</dt>
            <dd>{{ formatBytes(currentState.imageInfo.fileSize) }}</dd>
          </dl>

          <section class="result-summary label-preset-summary">
            <div class="preset-heading">
              <h2>标签预设</h2>
              <span>{{ labels.length }} 类</span>
            </div>
            <div v-if="labels.length === 0" class="empty-state">请先在系统配置中添加标签</div>
            <div v-else class="label-preset-grid">
              <button
                v-for="entry in presetLabels"
                :key="entry.label.labelId"
                class="preset-label-button"
                :class="{ active: entry.label.labelId === activePresetLabel?.labelId }"
                :title="entry.shortcut ? `快捷键 ${entry.shortcut}` : `标签 #${entry.label.labelId}`"
                @click="selectPresetLabel(entry.label)"
              >
                <kbd v-if="entry.shortcut">{{ entry.shortcut.replace('Shift+', '⇧') }}</kbd>
                <kbd v-else>--</kbd>
                <span>
                  <strong>#{{ entry.label.labelId }} {{ entry.label.chineseName }}</strong>
                  <small>{{ entry.label.englishName }}</small>
                </span>
              </button>
            </div>
          </section>

          <section class="result-summary">
            <h2>选中对象</h2>
            <div v-if="!selectedShape" class="empty-state">
              下一个标注：{{ activePresetLabel ? `#${activePresetLabel.labelId} ${activePresetLabel.chineseName}` : "未配置" }}
            </div>
            <template v-else>
              <label class="field-label">
                <span>标签</span>
                <select v-model="selectedLabelId">
                  <option value="">未配置</option>
                  <option v-for="label in labels" :key="label.labelId" :value="label.labelId">
                    #{{ label.labelId }} {{ label.englishName }} / {{ label.chineseName }}
                  </option>
                </select>
              </label>
              <div class="result-row"><strong>类型</strong><span>{{ shapeTypeText(selectedShape.type) }}</span></div>
              <div class="result-row"><strong>来源</strong><span>{{ selectedShape.source }}</span></div>
              <button class="danger-button" @click="removeSelectedShape"><Trash2 :size="16" />删除标注</button>
            </template>
          </section>

          <section class="result-summary annotated-summary">
            <h2>已标注对象</h2>
            <div v-if="annotationShapes.length === 0" class="empty-state">暂无标注对象</div>
            <button
              v-for="(shape, index) in annotationShapes"
              :key="shape.id"
              class="annotation-row"
              :class="{ selected: shape.id === selectedShapeId }"
              @click="selectShape(shape.id)"
            >
              <strong>{{ index + 1 }}. {{ shape.label }}</strong>
              <span>{{ shapeTypeText(shape.type) }}</span>
            </button>
          </section>

          <section class="result-summary">
            <h2>任务结果</h2>
            <div v-if="currentState.isViewingHistory" class="history-viewing">正在查看历史版本，恢复后会生成一个新版本。</div>
            <div v-if="currentState.status === 'idle'" class="empty-state">当前图片暂无该任务结果</div>
            <template v-else-if="currentTaskType === 'classification'">
              <div v-for="item in resultLabels()" :key="item.label" class="result-row">
                <strong>{{ item.label }}</strong><span>{{ Math.round(item.score * 100) }}%</span>
              </div>
            </template>
            <template v-else-if="currentTaskType === 'caption'">
              <div class="caption-actions">
                <button :disabled="captionIsTransferring || !currentState.descriptionText" @click="playCaption">
                  <Loader2 v-if="captionIsTransferring" class="spin" :size="15" />
                  <Volume2 v-else :size="15" />
                  {{ captionIsTransferring ? "处理中" : "播放中文简体" }}
                </button>
              </div>
              <p class="caption-text">{{ currentState.descriptionText || "暂无描述" }}</p>
            </template>
            <div v-else class="result-row"><strong>标注对象</strong><span>{{ annotationShapes.length }} 个</span></div>
          </section>

          <section class="result-summary review-summary">
            <div class="review-heading">
              <h2>审核状态</h2>
              <span class="review-status" :class="`status-${currentState.reviewStatus}`">{{ reviewStatusText(currentState.reviewStatus) }}</span>
            </div>
            <p v-if="currentState.reviewComment" class="review-comment">{{ currentState.reviewComment }}</p>
            <small v-if="currentState.reviewedAt">审核时间：{{ formatTime(currentState.reviewedAt) }}</small>
            <button
              v-if="!canReview"
              :disabled="!currentState.taskId || currentState.status === 'idle' || currentState.reviewStatus === 'pending_review' || resultLocked || loading"
              @click="submitForReview"
            >
              <Check :size="16" />提交审核
            </button>
            <template v-else-if="currentState.reviewStatus === 'pending_review'">
              <textarea v-model="reviewCommentInput" rows="3" placeholder="填写审核意见，驳回时建议说明修改位置"></textarea>
              <div class="review-actions">
                <button @click="reviewCurrentResult('approved')"><Check :size="16" />通过</button>
                <button class="danger-button" @click="reviewCurrentResult('rejected')"><RotateCcw :size="16" />驳回</button>
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
                <span><strong>v{{ version.versionNo }}</strong><small>{{ version.source }} · {{ version.modelId || "-" }}</small></span>
                <small>{{ formatTime(version.createdAt) }}</small>
              </button>
            </div>
            <button class="ghost-button restore-button" :disabled="!currentState.activeVersionId || !currentState.isViewingHistory || loading" @click="restoreVersion(currentState.activeVersionId!)">
              恢复此版本
            </button>
          </section>
        </template>
      </aside>
    </section>

    <section v-else-if="currentPage === 'videoCaptions'" class="video-caption-page">
      <aside class="video-list-panel">
        <div class="panel-head">
          <strong>视频批次</strong>
          <button :disabled="loading" title="刷新" @click="loadVideoCaptionBatches"><RefreshCw :size="16" /></button>
        </div>
        <div class="batch-summary" v-if="selectedVideoCaptionBatch">
          <strong>{{ selectedVideoCaptionBatch.name }}</strong>
          <span>{{ selectedVideoCaptionBatch.totalVideos }} 个视频 · {{ selectedVideoCaptionBatch.totalFrames }} 帧 · {{ selectedVideoCaptionBatch.status }}</span>
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
            <span>{{ batch.totalVideos }} 视频 · {{ batch.totalFrames }} 帧</span>
          </button>
          <div v-if="videoCaptionBatches.length === 0" class="empty-state">暂无解帧批次</div>
        </div>

        <div class="panel-head sub-head">
          <strong>视频列表</strong>
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
            <span>{{ formatDuration(video.durationMs) }} · {{ video.status }}</span>
            <span class="keyword-list">
              <small v-for="keyword in video.keywords" :key="keyword">{{ keyword }}</small>
            </span>
          </button>
          <div v-if="videoCaptionVideos.length === 0" class="empty-state">暂无视频记录</div>
        </div>
      </aside>

      <section class="frame-browser">
        <div class="frame-toolbar">
          <div>
            <strong>{{ selectedVideoCaptionVideo?.displayName || selectedVideoCaptionVideo?.filename || "请选择视频" }}</strong>
            <span>{{ videoCaptionTotal }} 帧记录</span>
          </div>
          <form class="frame-search" @submit.prevent="searchVideoCaptionFrames">
            <Search :size="16" />
            <input v-model="videoCaptionQuery" placeholder="搜索人员、轨道、车辆、安全风险" />
            <button :disabled="loading">搜索</button>
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
          <div v-if="videoCaptionFrames.length === 0" class="empty-state">暂无匹配帧</div>
        </div>
      </section>

      <aside class="frame-detail-panel">
        <template v-if="selectedVideoCaptionFrame">
          <div class="frame-preview">
            <img :src="assetUrl(selectedVideoCaptionFrame.imageUrl)" alt="视频帧" />
          </div>
          <dl class="image-info">
            <dt>时间</dt>
            <dd>{{ formatTimestamp(selectedVideoCaptionFrame.timestampMs) }}</dd>
            <dt>帧号</dt>
            <dd>{{ selectedVideoCaptionFrame.frameIndex }}</dd>
            <dt>模型</dt>
            <dd>{{ selectedVideoCaptionFrame.modelId }}</dd>
            <dt>状态</dt>
            <dd>{{ selectedVideoCaptionFrame.status }}</dd>
          </dl>
          <section class="result-summary">
            <h2>DeepSeek 描述</h2>
            <p class="caption-text">{{ selectedVideoCaptionFrame.descriptionText || selectedVideoCaptionFrame.error || "暂无描述" }}</p>
          </section>
        </template>
        <div v-else class="empty-state detail-empty">请选择一个视频帧</div>
      </aside>
    </section>

    <LiveGesturePage v-else-if="currentPage === 'liveGesture'" />

    <section v-else class="settings-page">
      <div class="settings-header">
        <div>
          <h2><Tags :size="22" />标签配置</h2>
          <p>标签 ID 由系统从 0 开始生成，英文名用于模型和导出，中文名用于人工校验界面。</p>
        </div>
        <button :disabled="loading" @click="loadLabels"><RefreshCw :size="16" />刷新</button>
      </div>

      <form v-if="isAdmin" class="label-form" @submit.prevent="submitLabel">
        <label class="field-label"><span>英文名称</span><input v-model="labelForm.englishName" required placeholder="person" /></label>
        <label class="field-label"><span>中文名称</span><input v-model="labelForm.chineseName" required placeholder="行人" /></label>
        <label class="field-label wide"><span>描述信息</span><textarea v-model="labelForm.description" rows="2" placeholder="标签使用范围、边界说明或审核标准"></textarea></label>
        <button :disabled="loading"><Plus :size="16" />新增标签</button>
      </form>

      <div class="label-table">
        <div class="label-table-head">
          <span>ID</span><span>英文</span><span>中文</span><span>描述</span><span>生成日期</span><span>修改日期</span><span>操作</span>
        </div>
        <div v-if="labels.length === 0" class="empty-state table-empty">暂无标签配置</div>
        <div v-for="label in labels" :key="label.labelId" class="label-row">
          <span>#{{ label.labelId }}</span>
          <template v-if="editingLabelId === label.labelId">
            <input v-model="editingLabel.englishName" />
            <input v-model="editingLabel.chineseName" />
            <textarea v-model="editingLabel.description" rows="2"></textarea>
            <span>{{ formatTime(label.createdAt) }}</span>
            <span>{{ formatTime(label.updatedAt) }}</span>
            <span v-if="isAdmin" class="row-actions">
              <button @click="submitEditLabel(label.labelId)"><Save :size="15" /></button>
              <button @click="editingLabelId = null"><RotateCcw :size="15" /></button>
            </span>
          </template>
          <template v-else>
            <span>{{ label.englishName }}</span>
            <span>{{ label.chineseName }}</span>
            <span>{{ label.description || "-" }}</span>
            <span>{{ formatTime(label.createdAt) }}</span>
            <span>{{ formatTime(label.updatedAt) }}</span>
            <span v-if="isAdmin" class="row-actions">
              <button title="编辑" @click="startEditLabel(label)"><Edit3 :size="15" /></button>
              <button title="复制标签" @click="duplicateLabel(label.labelId)"><Copy :size="15" /></button>
              <button title="删除" @click="removeLabel(label.labelId)"><Trash2 :size="15" /></button>
            </span>
          </template>
        </div>
      </div>

      <template v-if="isAdmin">
        <div class="settings-header user-admin-header">
          <div>
            <h2><UserRound :size="22" />账号与角色</h2>
            <p>学生负责标注，审核员负责通过或驳回，管理员可维护标签和账号角色。</p>
          </div>
          <button :disabled="loading" @click="loadUsers"><RefreshCw :size="16" />刷新</button>
        </div>
        <div class="user-admin-list">
          <div v-for="user in users" :key="user.userId" class="user-admin-row">
            <span><strong>{{ user.displayName }}</strong><small>{{ user.username }}</small></span>
            <select :value="user.role" :disabled="user.userId === currentUser?.userId" @change="handleRoleChange(user.userId, $event)">
              <option value="student">学生</option>
              <option value="reviewer">审核员</option>
              <option value="admin">管理员</option>
            </select>
          </div>
        </div>
      </template>
    </section>

    <div v-if="loading" class="system-loading-backdrop" role="status" aria-live="polite" aria-label="正在加载后台数据">
      <div class="system-loading-dialog">
        <Loader2 class="spin" :size="28" />
        <strong>{{ processingOverlayText || "正在加载后台数据" }}</strong>
        <span>请稍候，数据将从后台服务读取</span>
      </div>
    </div>

    <div v-if="errorDialog" class="system-error-backdrop" role="alertdialog" aria-modal="true" aria-labelledby="system-error-title">
      <div class="system-error-dialog">
        <div>
          <strong id="system-error-title">操作失败</strong>
          <span>{{ errorDialog }}</span>
        </div>
        <button autofocus @click="errorDialog = ''">关闭</button>
      </div>
    </div>

    <div v-if="originalPreview" class="modal-backdrop" @click="originalPreview = null">
      <div class="original-modal" @click.stop>
        <img :src="assetUrl(originalPreview.imageUrl)" alt="原图预览" />
        <button @click="originalPreview = null">关闭</button>
      </div>
    </div>
  </main>

  <main v-else class="auth-shell">
    <section class="auth-panel" aria-labelledby="auth-title">
      <div class="auth-brand">
        <img :src="'/favicon.svg'" alt="" />
        <div>
          <h1 id="auth-title">铁路多目标识别平台</h1>
          <span>学生标注与智能识别工作台</span>
        </div>
      </div>

      <div class="auth-mode" role="tablist" aria-label="账号操作">
        <button :class="{ active: authMode === 'login' }" type="button" @click="authMode = 'login'">登录</button>
        <button :class="{ active: authMode === 'register' }" type="button" @click="authMode = 'register'">注册</button>
      </div>

      <form class="auth-form" @submit.prevent="submitAuth">
        <label>
          <span>学号或账号</span>
          <input v-model="authForm.username" required minlength="3" maxlength="50" autocomplete="username" placeholder="请输入学号或账号" />
        </label>
        <label v-if="authMode === 'register'">
          <span>学生姓名</span>
          <input v-model="authForm.displayName" required maxlength="80" autocomplete="name" placeholder="请输入姓名" />
        </label>
        <label>
          <span>密码</span>
          <input
            v-model="authForm.password"
            required
            :minlength="authMode === 'register' ? 6 : 1"
            maxlength="128"
            type="password"
            :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'"
            placeholder="请输入密码"
          />
        </label>
        <button class="auth-submit" :disabled="loading || !authReady">
          <Loader2 v-if="loading" class="spin" :size="17" />
          <UserRound v-else :size="17" />
          {{ authMode === "login" ? "登录系统" : "创建学生账号" }}
        </button>
      </form>
    </section>

    <div v-if="loading" class="system-loading-backdrop" role="status" aria-live="polite">
      <div class="system-loading-dialog">
        <Loader2 class="spin" :size="28" />
        <strong>{{ authReady ? "正在验证账号" : "正在恢复登录状态" }}</strong>
        <span>登录状态由后台数据库持久化保存</span>
      </div>
    </div>

    <div v-if="errorDialog" class="system-error-backdrop" role="alertdialog" aria-modal="true">
      <div class="system-error-dialog">
        <div><strong>操作失败</strong><span>{{ errorDialog }}</span></div>
        <button autofocus @click="errorDialog = ''">关闭</button>
      </div>
    </div>
  </main>
</template>
