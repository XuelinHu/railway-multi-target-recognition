import tempfile
from pathlib import Path
from typing import Any, Literal

from fastapi import UploadFile
from PIL import Image

from app.core.config import Settings

VisionFeature = Literal["detection", "pose", "segmentation", "classification", "caption"]

DEFAULT_MODELS: dict[VisionFeature, str] = {
    "detection": "yolo11n.pt",
    "pose": "yolo11n-pose.pt",
    "segmentation": "yolo11n-seg.pt",
    "classification": "yolo11n-cls.pt",
    "caption": "Salesforce/blip-image-captioning-base",
}

MODEL_ALIASES: dict[str, str] = {
    "railway-yolo-default": "yolo11n.pt",
    "custom-railway-detector": "yolo11n.pt",
    "yolov8n": "yolov8n.pt",
    "yolo11n": "yolo11n.pt",
    "yolo11n-seg": "yolo11n-seg.pt",
    "railway-seg-light": "yolo11n-seg.pt",
    "custom-segmentation": "yolo11n-seg.pt",
    "yolo11n-pose": "yolo11n-pose.pt",
    "railway-worker-pose": "yolo11n-pose.pt",
    "custom-pose": "yolo11n-pose.pt",
    "yolo11n-cls": "yolo11n-cls.pt",
    "railway-scene-cls": "yolo11n-cls.pt",
    "resnet50": "yolo11n-cls.pt",
    "efficientnet-b0": "yolo11n-cls.pt",
    "deepseek-vl2-tiny": "deepseek-ai/deepseek-vl2-tiny",
    "deepseek-ai/deepseek-vl2-tiny": "deepseek-ai/deepseek-vl2-tiny",
    "blip-image-captioning-base": "Salesforce/blip-image-captioning-base",
    "yolo-cls-fallback": "yolo11n-cls.pt",
    "custom-caption": "Salesforce/blip-image-captioning-base",
}


class VisionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._yolo_models: dict[str, Any] = {}
        self._caption_model: Any | None = None
        self._caption_processor: Any | None = None
        self._deepseek_vl2_model: Any | None = None
        self._deepseek_vl2_processor: Any | None = None
        self._deepseek_vl2_tokenizer: Any | None = None

    def analyze_upload(
        self,
        file: UploadFile,
        feature: VisionFeature,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "image.jpg").suffix or ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as target:
            target.write(file.file.read())
            image_path = Path(target.name)
        try:
            return self.analyze_path(image_path, feature, model_name)
        finally:
            image_path.unlink(missing_ok=True)

    def analyze_path(
        self,
        image_path: Path,
        feature: VisionFeature,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        if not image_path.exists():
            raise RuntimeError(f"图片文件不存在: {image_path}")
        if feature == "caption":
            return self._caption(image_path, model_name)
        return self._yolo(feature, image_path, model_name)

    def _yolo(
        self,
        feature: VisionFeature,
        image_path: Path,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        resolved_model = self._resolve_model(feature, model_name)
        model = self._load_yolo(resolved_model)
        results = model(str(image_path), device=self._device(), verbose=False)
        result = results[0]
        height, width = result.orig_shape[:2]

        if feature == "classification":
            items: list[dict[str, Any]] = []
            probs = result.probs
            names = result.names
            if probs is not None:
                for index in probs.top5:
                    score = float(probs.data[index].item())
                    items.append({"label": str(names.get(int(index), index)), "confidence": score})
            return {
                "feature": feature,
                "model": model_name or resolved_model,
                "image": {"width": int(width), "height": int(height)},
                "results": items,
            }

        boxes: list[dict[str, Any]] = []
        names = result.names
        for box in result.boxes or []:
            xyxy = box.xyxy[0].tolist()
            class_id = int(box.cls[0].item()) if box.cls is not None else -1
            boxes.append(
                {
                    "label": str(names.get(class_id, class_id)),
                    "confidence": float(box.conf[0].item()) if box.conf is not None else 0.0,
                    "bbox": {
                        "x": max(float(xyxy[0]), 0.0),
                        "y": max(float(xyxy[1]), 0.0),
                        "width": max(float(xyxy[2] - xyxy[0]), 1.0),
                        "height": max(float(xyxy[3] - xyxy[1]), 1.0),
                    },
                }
            )

        payload: dict[str, Any] = {
            "feature": feature,
            "model": model_name or resolved_model,
            "image": {"width": int(width), "height": int(height)},
            "objects": boxes,
        }

        if feature == "pose" and result.keypoints is not None:
            payload["poses"] = [
                {
                    "keypoints": keypoints.xy[0].tolist(),
                    "confidence": keypoints.conf[0].tolist() if keypoints.conf is not None else [],
                }
                for keypoints in result.keypoints
            ]

        if feature == "segmentation" and result.masks is not None:
            segments = []
            for index, polygon in enumerate(result.masks.xy):
                box = boxes[index] if index < len(boxes) else {}
                segments.append(
                    {
                        "label": box.get("label", "object"),
                        "confidence": box.get("confidence", 0.0),
                        "polygon": polygon.tolist(),
                    }
                )
            payload["segments"] = segments

        return payload

    def _caption(self, image_path: Path, model_name: str | None = None) -> dict[str, Any]:
        with Image.open(image_path) as image:
            rgb_image = image.convert("RGB")
            width, height = rgb_image.size
            try:
                resolved_model = MODEL_ALIASES.get(model_name or "", model_name or DEFAULT_MODELS["caption"])
                if resolved_model == "deepseek-ai/deepseek-vl2-tiny":
                    text = self._deepseek_vl2_caption(image_path)
                    used_model = "deepseek-ai/deepseek-vl2-tiny"
                else:
                    model, processor = self._load_caption_model()
                    inputs = processor(rgb_image, return_tensors="pt").to(model.device)
                    outputs = model.generate(**inputs, max_new_tokens=40)
                    text = processor.decode(outputs[0], skip_special_tokens=True)
                    used_model = model_name or DEFAULT_MODELS["caption"]
            except Exception:
                classified = self._yolo("classification", image_path, "yolo11n-cls").get("results", [])[:3]
                labels = [item["label"] for item in classified]
                text = (
                    "This image contains " + ", ".join(labels) + "."
                    if labels
                    else "No obvious visual category identified."
                )
                used_model = model_name or "yolo11n-cls fallback description"
        return {
            "feature": "caption",
            "model": used_model,
            "image": {"width": width, "height": height},
            "caption": text,
        }

    def _load_yolo(self, model_name: str) -> Any:
        if model_name in self._yolo_models:
            return self._yolo_models[model_name]
        try:
            from ultralytics import YOLO
        except Exception as exc:
            raise RuntimeError("当前 Python 环境未安装 ultralytics，无法执行 YOLO 视觉功能") from exc

        resolved = model_name
        if resolved.startswith("/") and not Path(resolved).exists():
            resolved = "yolo11n.pt"
        self._yolo_models[model_name] = YOLO(resolved)
        return self._yolo_models[model_name]

    def _load_caption_model(self) -> tuple[Any, Any]:
        if self._caption_model is not None and self._caption_processor is not None:
            return self._caption_model, self._caption_processor
        try:
            from transformers import BlipForConditionalGeneration, BlipProcessor
        except Exception as exc:
            raise RuntimeError("当前 Python 环境未安装 transformers，无法执行图文描述功能") from exc

        model_name = DEFAULT_MODELS["caption"]
        self._caption_processor = BlipProcessor.from_pretrained(model_name)
        self._caption_model = BlipForConditionalGeneration.from_pretrained(model_name)
        return self._caption_model, self._caption_processor

    def _deepseek_vl2_caption(self, image_path: Path) -> str:
        model, processor, tokenizer = self._load_deepseek_vl2_model()
        conversation = [
            {
                "role": "<|User|>",
                "content": f"<image>\n{self.settings.deepseek_vl2_prompt}",
                "images": [str(image_path)],
            },
            {"role": "<|Assistant|>", "content": ""},
        ]
        try:
            import torch
            from deepseek_vl2.utils.io import load_pil_images
        except Exception as exc:
            raise RuntimeError("当前 Python 环境未安装 DeepSeek-VL2 代码包，无法执行 deepseek-vl2-tiny 图片理解") from exc

        self._patch_xformers_attention()
        pil_images = load_pil_images(conversation)
        prepare_inputs = processor(
            conversations=conversation,
            images=pil_images,
            force_batchify=True,
            system_prompt="",
        ).to(model.device)
        with torch.inference_mode():
            inputs_embeds = model.prepare_inputs_embeds(**prepare_inputs)
            language_model = getattr(model, "language_model", None) or getattr(model, "language")
            outputs = language_model.generate(
                inputs_embeds=inputs_embeds,
                attention_mask=prepare_inputs.attention_mask,
                pad_token_id=tokenizer.eos_token_id,
                bos_token_id=tokenizer.bos_token_id,
                eos_token_id=tokenizer.eos_token_id,
                max_new_tokens=256,
                do_sample=False,
                use_cache=True,
            )
        return tokenizer.decode(outputs[0].detach().cpu().tolist(), skip_special_tokens=True).strip()

    def _patch_xformers_attention(self) -> None:
        try:
            import torch
            import xformers.ops as xformers_ops
        except Exception as exc:
            raise RuntimeError("当前 Python 环境缺少 xformers，无法执行 deepseek-vl2-tiny 视觉注意力") from exc

        if getattr(xformers_ops.memory_efficient_attention, "_railway_torch_fallback", False):
            return

        def torch_attention(
            query: Any,
            key: Any,
            value: Any,
            attn_bias: Any = None,
            p: float = 0.0,
            scale: float | None = None,
            **_: Any,
        ) -> Any:
            if attn_bias is not None:
                raise RuntimeError("deepseek-vl2-tiny 当前仅支持无 attn_bias 的 PyTorch 注意力回退")
            query_t = query.transpose(1, 2)
            key_t = key.transpose(1, 2)
            value_t = value.transpose(1, 2)
            output = torch.nn.functional.scaled_dot_product_attention(
                query_t,
                key_t,
                value_t,
                dropout_p=p,
                scale=scale,
            )
            return output.transpose(1, 2).contiguous()

        torch_attention._railway_torch_fallback = True  # type: ignore[attr-defined]
        xformers_ops.memory_efficient_attention = torch_attention

    def _load_deepseek_vl2_model(self) -> tuple[Any, Any, Any]:
        if (
            self._deepseek_vl2_model is not None
            and self._deepseek_vl2_processor is not None
            and self._deepseek_vl2_tokenizer is not None
        ):
            return self._deepseek_vl2_model, self._deepseek_vl2_processor, self._deepseek_vl2_tokenizer
        try:
            import torch
            from transformers import AutoModelForCausalLM
            from deepseek_vl2.models import DeepseekVLV2Processor
        except Exception as exc:
            raise RuntimeError("当前 Python 环境缺少 transformers 或 DeepSeek-VL2 依赖，无法加载 deepseek-vl2-tiny") from exc

        model_path = self._deepseek_vl2_model_path()
        processor = DeepseekVLV2Processor.from_pretrained(model_path)
        model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True)
        if torch.cuda.is_available() and self._device() is not None:
            device = f"cuda:{self._device()}" if self._device().isdigit() else self._device()
            model = model.to(torch.bfloat16).to(device)
        else:
            model = model.to(torch.float32)
        model = model.eval()
        self._deepseek_vl2_processor = processor
        self._deepseek_vl2_tokenizer = processor.tokenizer
        self._deepseek_vl2_model = model
        return self._deepseek_vl2_model, self._deepseek_vl2_processor, self._deepseek_vl2_tokenizer

    def _deepseek_vl2_model_path(self) -> str:
        configured = Path(self.settings.deepseek_vl2_model_path)
        if configured.exists():
            return str(configured)
        return "deepseek-ai/deepseek-vl2-tiny"

    def _resolve_model(self, feature: VisionFeature, model_name: str | None) -> str:
        if model_name and model_name in MODEL_ALIASES:
            return MODEL_ALIASES[model_name]
        if model_name and (model_name.endswith(".pt") or model_name.startswith("/")):
            return model_name
        if feature == "detection" and self.settings.model_path:
            return self.settings.model_path
        return DEFAULT_MODELS[feature]

    def _device(self) -> str | None:
        return self.settings.device or None
