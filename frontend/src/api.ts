export type ImageTaskType = "detection" | "segmentation" | "pose" | "classification" | "caption";
export type ImageTaskStatus = "idle" | "pending" | "processing" | "success" | "failed";
export type ImageReviewStatus = "draft" | "pending_review" | "approved" | "rejected";

export type ImageAsset = {
  imageId: string;
  imageUrl: string;
  originalName: string;
  fileName: string;
  fileUrl: string;
  filePath?: string;
  mimeType?: string | null;
  fileSize: number;
  width?: number | null;
  height?: number | null;
  sessionId?: string;
  createdAt: string;
  updatedAt?: string;
  reviewStatus: ImageReviewStatus;
  submittedBy?: string | null;
  submittedAt?: string | null;
  reviewedBy?: string | null;
  reviewedAt?: string | null;
  reviewComment?: string;
  hasCurrentTaskResult: boolean;
  taskStatus: ImageTaskStatus;
};

export type ImageHistoryData = {
  records: ImageAsset[];
  total: number;
};

export type ImageTask = {
  taskId: string;
  imageId: string;
  taskType: ImageTaskType;
  status: ImageTaskStatus;
  createdAt?: string;
  updatedAt?: string;
};

export type ImageTaskResult = {
  resultId?: string;
  taskId: string;
  imageId: string;
  taskType: ImageTaskType;
  status: ImageTaskStatus;
  resultImageUrl?: string;
  resultImagePath?: string;
  resultJson?: Record<string, unknown> | null;
  annotationJson?: Record<string, unknown> | null;
  descriptionText?: string;
  source?: "ai" | "manual" | "edited";
  modelId?: string;
  latestVersionId?: string | null;
  latestVersionNo?: number | null;
  createdAt?: string;
  updatedAt?: string;
};

export type ImageTaskResultVersion = {
  versionId: string;
  resultId: string;
  taskId: string;
  imageId: string;
  taskType: ImageTaskType;
  versionNo: number;
  source: "ai" | "manual" | "edited";
  modelId?: string;
  resultImageUrl?: string;
  resultImagePath?: string;
  resultJson?: Record<string, unknown> | null;
  annotationJson?: Record<string, unknown> | null;
  descriptionText?: string;
  createdAt: string;
};

export type LabelConfig = {
  labelId: number;
  englishName: string;
  chineseName: string;
  description: string;
  createdAt: string;
  updatedAt: string;
};

export type VideoCaptionBatch = {
  batchId: string;
  name: string;
  sourceDir: string;
  outputDir: string;
  modelId: string;
  prompt: string;
  frameIntervalSeconds: number;
  status: "pending" | "processing" | "success" | "failed";
  totalVideos: number;
  totalFrames: number;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type VideoCaptionVideo = {
  videoId: string;
  batchId: string;
  filename: string;
  displayName: string;
  keywords: string[];
  sourcePath: string;
  frameDir: string;
  fps?: number | null;
  width?: number | null;
  height?: number | null;
  frameCount?: number | null;
  durationMs?: number | null;
  status: "pending" | "processing" | "success" | "failed";
  error: string;
  createdAt: string;
  updatedAt: string;
};

export type VideoCaptionFrame = {
  frameId: string;
  batchId: string;
  videoId: string;
  frameIndex: number;
  timestampMs: number;
  imagePath: string;
  imageUrl: string;
  width?: number | null;
  height?: number | null;
  descriptionText: string;
  descriptionEn: string;
  modelId: string;
  status: "pending" | "processing" | "success" | "failed";
  error: string;
  resultJson: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
};

export type VideoCaptionFrameData = {
  records: VideoCaptionFrame[];
  total: number;
};

export type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

export type AuthUser = {
  userId: string;
  username: string;
  displayName: string;
  role: string;
};

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  let response: Response;
  try {
    response = await fetch(url, { credentials: "include", ...options });
  } catch (error) {
    console.error("[API] Network error", {
      url,
      method: options?.method ?? "GET",
      error,
    });
    throw new Error("网络异常，请检查后端服务或网络连接");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      const rawDetail = payload.detail ?? payload.message ?? payload;
      detail = typeof rawDetail === "string" ? rawDetail : JSON.stringify(rawDetail);
    } catch {
      detail = await response.text();
    }
    console.error("[API] Request failed", {
      url,
      method: options?.method ?? "GET",
      status: response.status,
      detail,
    });
    throw new ApiRequestError(detail || `HTTP ${response.status}`, response.status);
  }
  return response.json() as Promise<T>;
}

async function apiData<T>(path: string, options?: RequestInit): Promise<T> {
  const payload = await request<ApiEnvelope<T>>(path, options);
  return payload.data;
}

export function getCurrentUser(): Promise<AuthUser | null> {
  return apiData<AuthUser | null>("/api/auth/me");
}

export function login(data: { username: string; password: string }): Promise<AuthUser> {
  return apiData<AuthUser>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function register(data: { username: string; displayName: string; password: string }): Promise<AuthUser> {
  return apiData<AuthUser>("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function logout(): Promise<{ loggedOut: boolean }> {
  return apiData<{ loggedOut: boolean }>("/api/auth/logout", { method: "POST" });
}

export function listUsers(): Promise<AuthUser[]> {
  return apiData<AuthUser[]>("/api/auth/users");
}

export function updateUserRole(userId: string, role: "student" | "reviewer" | "admin"): Promise<AuthUser> {
  return apiData<AuthUser>(`/api/auth/users/${userId}/role`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
}

export function uploadImage(file: File, taskType: ImageTaskType, sessionId: string): Promise<ImageAsset> {
  const form = new FormData();
  form.append("file", file);
  form.append("taskType", taskType);
  form.append("sessionId", sessionId);
  return apiData<ImageAsset>("/api/images/upload", { method: "POST", body: form });
}

export function listImages(params: {
  taskType?: ImageTaskType;
  page?: number;
  pageSize?: number;
  sessionId?: string;
}): Promise<ImageHistoryData> {
  const query = new URLSearchParams();
  if (params.taskType) query.set("taskType", params.taskType);
  query.set("page", String(params.page ?? 1));
  query.set("pageSize", String(params.pageSize ?? 50));
  if (params.sessionId) query.set("sessionId", params.sessionId);
  return apiData<ImageHistoryData>(`/api/images/list?${query.toString()}`);
}

export function createImageTask(data: {
  imageId: string;
  taskType: ImageTaskType;
  sessionId: string;
}): Promise<ImageTask> {
  return apiData<ImageTask>("/api/image-tasks/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function saveTaskResult(data: {
  taskId: string;
  imageId: string;
  taskType: ImageTaskType;
  resultImageUrl?: string;
  resultJson?: Record<string, unknown> | null;
  annotationJson?: Record<string, unknown> | null;
  descriptionText?: string;
  source?: "ai" | "manual" | "edited";
  modelId?: string;
}): Promise<{ resultId: string; versionId: string; versionNo: number }> {
  return apiData<{ resultId: string; versionId: string; versionNo: number }>("/api/image-tasks/result/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function getTaskResult(params: {
  imageId: string;
  taskType: ImageTaskType;
  sessionId: string;
}): Promise<ImageTaskResult | null> {
  const query = new URLSearchParams({
    imageId: params.imageId,
    taskType: params.taskType,
    sessionId: params.sessionId,
  });
  return apiData<ImageTaskResult | null>(`/api/image-tasks/result?${query.toString()}`);
}

export function listTaskResultVersions(params: {
  imageId: string;
  taskType: ImageTaskType;
  sessionId: string;
}): Promise<ImageTaskResultVersion[]> {
  const query = new URLSearchParams({
    imageId: params.imageId,
    taskType: params.taskType,
    sessionId: params.sessionId,
  });
  return apiData<ImageTaskResultVersion[]>(`/api/image-tasks/result/versions?${query.toString()}`);
}

export function getTaskResultVersion(versionId: string): Promise<ImageTaskResultVersion> {
  return apiData<ImageTaskResultVersion>(`/api/image-tasks/result/version/${versionId}`);
}

export function restoreTaskResultVersion(versionId: string): Promise<ImageTaskResult> {
  return apiData<ImageTaskResult>(`/api/image-tasks/result/version/${versionId}/restore`, {
    method: "POST",
  });
}

export function updateAnnotation(data: {
  taskId: string;
  imageId: string;
  taskType: ImageTaskType;
  annotationJson: Record<string, unknown>;
}): Promise<ImageTaskResult> {
  return apiData<ImageTaskResult>("/api/image-tasks/annotation", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function submitTaskResult(taskId: string): Promise<ImageTaskResult> {
  return apiData<ImageTaskResult>(`/api/image-tasks/result/${taskId}/submit`, { method: "POST" });
}

export function reviewTaskResult(taskId: string, status: "approved" | "rejected", comment: string): Promise<ImageTaskResult> {
  return apiData<ImageTaskResult>(`/api/image-tasks/result/${taskId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, comment }),
  });
}

export function inferImageTask(data: {
  imageId: string;
  taskType: ImageTaskType;
  sessionId: string;
  modelName?: string;
}): Promise<ImageTaskResult> {
  return apiData<ImageTaskResult>("/api/ai/infer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function listLabels(): Promise<LabelConfig[]> {
  return apiData<LabelConfig[]>("/api/labels");
}

export function createLabel(data: {
  englishName: string;
  chineseName: string;
  description: string;
  copyFromLabelId?: number | null;
}): Promise<LabelConfig> {
  return apiData<LabelConfig>("/api/labels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updateLabel(
  labelId: number,
  data: {
    englishName: string;
    chineseName: string;
    description: string;
  },
): Promise<LabelConfig> {
  return apiData<LabelConfig>(`/api/labels/${labelId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function copyLabel(labelId: number): Promise<LabelConfig> {
  return apiData<LabelConfig>(`/api/labels/${labelId}/copy`, { method: "POST" });
}

export function deleteLabel(labelId: number): Promise<{ deleted: boolean }> {
  return apiData<{ deleted: boolean }>(`/api/labels/${labelId}`, { method: "DELETE" });
}

export function listVideoCaptionBatches(): Promise<VideoCaptionBatch[]> {
  return apiData<VideoCaptionBatch[]>("/api/video-captions/batches");
}

export function listVideoCaptionVideos(batchId: string): Promise<VideoCaptionVideo[]> {
  return apiData<VideoCaptionVideo[]>(`/api/video-captions/batches/${batchId}/videos`);
}

export function listVideoCaptionFrames(params: {
  videoId: string;
  page?: number;
  pageSize?: number;
  query?: string;
}): Promise<VideoCaptionFrameData> {
  const query = new URLSearchParams({
    page: String(params.page ?? 1),
    pageSize: String(params.pageSize ?? 200),
  });
  if (params.query) query.set("query", params.query);
  return apiData<VideoCaptionFrameData>(`/api/video-captions/videos/${params.videoId}/frames?${query.toString()}`);
}

export function assetUrl(path?: string | null): string {
  if (!path) return "";
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE_URL}${path}`;
}

export type ChatRole = "system" | "user" | "assistant";
export type ChatMessage = { role: ChatRole; content: string };
export type ChatModelInfo = { name: string; size: number };
export type ChatLanguage = "zh" | "en";

export function listChatModels(): Promise<{ models: ChatModelInfo[]; defaultModel: string }> {
  return apiData<{ models: ChatModelInfo[]; defaultModel: string }>("/api/chat/models");
}

export async function streamChatCompletion(
  body: { messages: ChatMessage[]; model?: string; lang: ChatLanguage },
  handlers: {
    onDelta: (text: string) => void;
    onDone: (reason: string) => void;
    onError: (detail: string) => void;
  },
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    let detail = response.statusText || `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      /* keep the status text */
    }
    throw new ApiRequestError(detail, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // stream:true keeps multi-byte CJK characters intact across chunk boundaries
      buffer += decoder.decode(value, { stream: true });
      let separator = buffer.indexOf("\n\n");
      while (separator >= 0) {
        const rawEvent = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        dispatchChatEvent(rawEvent, handlers);
        separator = buffer.indexOf("\n\n");
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) dispatchChatEvent(buffer, handlers);
  } finally {
    reader.releaseLock();
  }
}

function dispatchChatEvent(
  rawEvent: string,
  handlers: { onDelta: (text: string) => void; onDone: (reason: string) => void; onError: (detail: string) => void },
): void {
  let eventName = "message";
  let dataLine = "";
  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("event: ")) eventName = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataLine = line.slice(6);
  }
  if (!dataLine) return;
  let payload: { content?: string; doneReason?: string; detail?: string };
  try {
    payload = JSON.parse(dataLine);
  } catch {
    return;
  }
  if (eventName === "delta") handlers.onDelta(payload.content ?? "");
  else if (eventName === "done") handlers.onDone(payload.doneReason ?? "stop");
  else if (eventName === "error") handlers.onError(payload.detail ?? "对话失败");
}

export async function fetchSpeech(text: string, lang: ChatLanguage): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/chat/tts`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang }),
  });
  if (!response.ok) {
    let detail = response.statusText || `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      /* keep the status text */
    }
    throw new ApiRequestError(detail, response.status);
  }
  return response.blob();
}
