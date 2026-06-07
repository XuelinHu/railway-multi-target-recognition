from app.models.schemas import AnnotationsDocument
from app.repositories.json_store import JsonStore


class ExportService:
    def __init__(self, store: JsonStore) -> None:
        self.store = store

    def get_annotations(self, asset_id: str) -> AnnotationsDocument | None:
        return self.store.get_annotations(asset_id)

    def to_coco(self, annotations: AnnotationsDocument) -> dict:
        categories: dict[str, int] = {}
        images = []
        coco_annotations = []
        annotation_id = 1

        for frame in annotations.frames:
            image_id = frame.frame_index + 1
            images.append(
                {
                    "id": image_id,
                    "file_name": f"{annotations.asset_id}_{frame.frame_index:06d}.jpg",
                    "width": frame.width,
                    "height": frame.height,
                }
            )
            for obj in frame.objects:
                if obj.label not in categories:
                    categories[obj.label] = len(categories) + 1
                category_id = categories[obj.label]
                coco_annotations.append(
                    {
                        "id": annotation_id,
                        "image_id": image_id,
                        "category_id": category_id,
                        "bbox": [obj.bbox.x, obj.bbox.y, obj.bbox.width, obj.bbox.height],
                        "area": obj.bbox.width * obj.bbox.height,
                        "iscrowd": 0,
                        "score": obj.confidence,
                    }
                )
                annotation_id += 1

        return {
            "images": images,
            "annotations": coco_annotations,
            "categories": [{"id": idx, "name": label} for label, idx in categories.items()],
        }

    def to_yolo_text(self, annotations: AnnotationsDocument) -> str:
        labels = sorted({obj.label for frame in annotations.frames for obj in frame.objects})
        label_to_id = {label: idx for idx, label in enumerate(labels)}
        lines = ["# frame_index label_id cx cy w h label confidence"]
        for frame in annotations.frames:
            width = frame.width or 1
            height = frame.height or 1
            for obj in frame.objects:
                cx = (obj.bbox.x + obj.bbox.width / 2) / width
                cy = (obj.bbox.y + obj.bbox.height / 2) / height
                bw = obj.bbox.width / width
                bh = obj.bbox.height / height
                lines.append(
                    f"{frame.frame_index} {label_to_id[obj.label]} "
                    f"{cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f} {obj.label} {obj.confidence:.4f}"
                )
        return "\n".join(lines) + "\n"
