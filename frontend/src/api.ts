export type ImageTaskType = "detection" | "segmentation" | "pose" | "classification" | "caption";
export type ImageTaskStatus = "idle" | "pending" | "processing" | "success" | "failed";

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

export type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8010";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      const rawDetail = payload.detail ?? payload.message ?? payload;
      detail = typeof rawDetail === "string" ? rawDetail : JSON.stringify(rawDetail);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function apiData<T>(path: string, options?: RequestInit): Promise<T> {
  const payload = await request<ApiEnvelope<T>>(path, options);
  return payload.data;
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
  sessionId: string;
}): Promise<ImageHistoryData> {
  const query = new URLSearchParams();
  if (params.taskType) query.set("taskType", params.taskType);
  query.set("page", String(params.page ?? 1));
  query.set("pageSize", String(params.pageSize ?? 50));
  query.set("sessionId", params.sessionId);
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

export function deleteLabel(labelId: number): Promise<{ deleted: boolean }> {
  return apiData<{ deleted: boolean }>(`/api/labels/${labelId}`, { method: "DELETE" });
}

export function assetUrl(path?: string | null): string {
  if (!path) return "";
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE_URL}${path}`;
}
