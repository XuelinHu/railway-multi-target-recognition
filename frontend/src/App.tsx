import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { Download, Play, RefreshCw, Save, Upload } from "lucide-react";
import {
  AnnotationsDocument,
  Asset,
  DetectTask,
  createDetectionTask,
  exportAnnotations,
  getAnnotations,
  getTask,
  listAssets,
  saveAnnotations,
  uploadAsset,
} from "./api";

function App() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [task, setTask] = useState<DetectTask | null>(null);
  const [annotationText, setAnnotationText] = useState("");
  const [exportText, setExportText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.id === selectedAssetId) ?? null,
    [assets, selectedAssetId],
  );

  useEffect(() => {
    refreshAssets();
  }, []);

  async function refreshAssets() {
    setBusy(true);
    setMessage("");
    try {
      const data = await listAssets();
      setAssets(data);
      if (!selectedAssetId && data.length > 0) {
        setSelectedAssetId(data[0].id);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "资源加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setMessage("");
    try {
      const asset = await uploadAsset(file);
      setAssets((items) => [asset, ...items.filter((item) => item.id !== asset.id)]);
      setSelectedAssetId(asset.id);
      setAnnotationText("");
      setExportText("");
      setMessage("上传完成");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function startDetection() {
    if (!selectedAssetId) return;
    setBusy(true);
    setMessage("");
    try {
      const nextTask = await createDetectionTask(selectedAssetId);
      setTask(nextTask);
      const latestTask = await getTask(nextTask.id);
      setTask(latestTask);
      if (latestTask.status === "completed") {
        await loadAnnotations(selectedAssetId);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "识别任务创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function pollTask() {
    if (!task) return;
    setBusy(true);
    setMessage("");
    try {
      const latestTask = await getTask(task.id);
      setTask(latestTask);
      if (latestTask.status === "completed") {
        await loadAnnotations(latestTask.asset_id);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "任务刷新失败");
    } finally {
      setBusy(false);
    }
  }

  async function loadAnnotations(assetId = selectedAssetId) {
    if (!assetId) return;
    setBusy(true);
    setMessage("");
    try {
      const annotations = await getAnnotations(assetId);
      setAnnotationText(JSON.stringify(annotations, null, 2));
      setExportText("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "标注加载失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveEditedAnnotations() {
    if (!selectedAssetId) return;
    setBusy(true);
    setMessage("");
    try {
      const parsed = JSON.parse(annotationText) as AnnotationsDocument;
      const saved = await saveAnnotations(selectedAssetId, parsed);
      setAnnotationText(JSON.stringify(saved, null, 2));
      setMessage("保存完成");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function runExport(format: "json" | "coco" | "yolo") {
    if (!selectedAssetId) return;
    setBusy(true);
    setMessage("");
    try {
      const data = await exportAnnotations(selectedAssetId, format);
      setExportText(data);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "导出失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>铁路多目标识别</h1>
          <span>{busy ? "处理中" : "就绪"}</span>
        </div>
        <div className="toolbar">
          <label className="icon-button file-button" title="上传">
            <Upload size={18} />
            <input type="file" accept="image/*,video/*" onChange={onFileChange} />
          </label>
          <button className="icon-button" title="刷新" onClick={refreshAssets} disabled={busy}>
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      <section className="workspace">
        <aside className="asset-pane">
          <div className="pane-title">资源</div>
          <div className="asset-list">
            {assets.map((asset) => (
              <button
                key={asset.id}
                className={asset.id === selectedAssetId ? "asset-row active" : "asset-row"}
                onClick={() => {
                  setSelectedAssetId(asset.id);
                  setTask(null);
                  setAnnotationText("");
                  setExportText("");
                }}
              >
                <strong>{asset.filename}</strong>
                <span>
                  {asset.type}
                  {asset.width && asset.height ? ` · ${asset.width}x${asset.height}` : ""}
                </span>
              </button>
            ))}
          </div>
        </aside>

        <section className="review-pane">
          <div className="action-strip">
            <select
              value={selectedAssetId}
              onChange={(event) => {
                setSelectedAssetId(event.target.value);
                setAnnotationText("");
                setExportText("");
              }}
            >
              <option value="">选择资源</option>
              {assets.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.filename}
                </option>
              ))}
            </select>
            <button onClick={startDetection} disabled={!selectedAssetId || busy}>
              <Play size={17} />
              识别
            </button>
            <button onClick={pollTask} disabled={!task || busy}>
              <RefreshCw size={17} />
              任务
            </button>
            <button onClick={() => loadAnnotations()} disabled={!selectedAssetId || busy}>
              <RefreshCw size={17} />
              标注
            </button>
            <button onClick={saveEditedAnnotations} disabled={!annotationText || busy}>
              <Save size={17} />
              保存
            </button>
          </div>

          <div className="status-line">
            <span>{selectedAsset ? selectedAsset.filename : "未选择资源"}</span>
            <span>{task ? `${task.status} · ${Math.round(task.progress * 100)}% · ${task.model_name}` : "无任务"}</span>
            <span>{message}</span>
          </div>

          <textarea
            className="annotation-editor"
            value={annotationText}
            onChange={(event) => setAnnotationText(event.target.value)}
            spellCheck={false}
          />

          <div className="export-strip">
            <button onClick={() => runExport("json")} disabled={!selectedAssetId || busy}>
              <Download size={17} />
              JSON
            </button>
            <button onClick={() => runExport("coco")} disabled={!selectedAssetId || busy}>
              <Download size={17} />
              COCO
            </button>
            <button onClick={() => runExport("yolo")} disabled={!selectedAssetId || busy}>
              <Download size={17} />
              YOLO
            </button>
          </div>

          <pre className="export-view">{exportText}</pre>
        </section>
      </section>
    </main>
  );
}

export default App;
