export type Asset = {
  id: string;
  filename: string;
  content_type: string;
  type: "image" | "video" | "unknown";
  path: string;
  size_bytes: number;
  width?: number | null;
  height?: number | null;
  duration_ms?: number | null;
  fps?: number | null;
  created_at: string;
};

export type DetectTask = {
  id: string;
  asset_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  model_name: string;
  error?: string | null;
};

export type AnnotationsDocument = {
  asset_id: string;
  type: "image" | "video" | "unknown";
  model: string;
  frames: Array<{
    frame_index: number;
    timestamp_ms: number;
    width?: number | null;
    height?: number | null;
    objects: Array<{
      id: string;
      label: string;
      confidence: number;
      bbox: { x: number; y: number; width: number; height: number };
      track_id?: number | null;
      source: "auto" | "manual";
      status: "auto" | "confirmed" | "edited" | "rejected";
    }>;
  }>;
  updated_at: string;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function uploadAsset(file: File): Promise<Asset> {
  const body = new FormData();
  body.append("file", file);
  return request<Asset>("/api/assets/upload", {
    method: "POST",
    body,
  });
}

export function listAssets(): Promise<Asset[]> {
  return request<Asset[]>("/api/assets");
}

export function createDetectionTask(assetId: string): Promise<DetectTask> {
  return request<DetectTask>("/api/tasks/detect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asset_id: assetId, confidence: 0.25, iou: 0.7, frame_stride: 1 }),
  });
}

export function getTask(taskId: string): Promise<DetectTask> {
  return request<DetectTask>(`/api/tasks/${taskId}`);
}

export function getAnnotations(assetId: string): Promise<AnnotationsDocument> {
  return request<AnnotationsDocument>(`/api/assets/${assetId}/annotations`);
}

export function saveAnnotations(assetId: string, annotations: AnnotationsDocument): Promise<AnnotationsDocument> {
  return request<AnnotationsDocument>(`/api/assets/${assetId}/annotations`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(annotations),
  });
}

export async function exportAnnotations(assetId: string, format: "json" | "coco" | "yolo"): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/assets/${assetId}/export?format=${format}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.text();
}
