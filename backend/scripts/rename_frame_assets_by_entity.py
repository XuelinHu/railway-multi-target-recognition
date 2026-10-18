from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.dependencies import get_store


ENTITY_WORDS = (
    ("人员", ("工作人员", "作业人员", "施工人员", "工人", "人员")),
    ("轨道", ("钢轨", "铁轨", "轨道", "铁路轨道", "道岔", "道床", "轨枕")),
    ("接触网", ("接触网", "接触线", "承力索", "电线杆", "支柱")),
    ("信号设备", ("信号设备", "信号机", "信号灯", "铁路信号")),
    ("铁路设备", ("铁路设备", "控制柜", "控制室", "设备箱", "控制面板", "电力设备")),
    ("列车", ("列车", "火车", "机车", "动车", "车厢")),
    ("铁路车辆", ("铁路车辆", "工程车", "车辆")),
    ("站台", ("站台", "车站", "站场")),
    ("桥梁", ("桥梁", "高架桥", "桥")),
    ("隧道", ("隧道",)),
    ("施工现场", ("施工", "检修", "维护", "作业")),
    ("道床", ("道砟", "碎石", "道床")),
)


def main() -> None:
    store = get_store()
    renamed = 0
    for batch in store.list_video_caption_batches():
        for video in store.list_video_caption_videos(batch.batch_id):
            frames, _ = store.list_video_caption_frames(video.video_id, page=1, page_size=100000)
            for frame in frames:
                path = Path(frame.image_path)
                if not path.is_file():
                    continue
                result = store.get_image_task_result(frame.frame_id, "detection", f"video-import:{video.video_id}", None)
                labels = [str(item.get("label", "")) for item in ((result.result_json or {}).get("boxes", []) if result else [])]
                entity = _entity_name(frame.description_text, labels, video.filename)
                target = path.with_name(f"{entity}_{frame.frame_id}.jpg")
                if target != path:
                    if target.exists():
                        target = path.with_name(f"{entity}_{frame.frame_id}_{frame.frame_index:06d}.jpg")
                    path.replace(target)
                frame.image_path = str(target)
                store.update_image_asset_file(frame.frame_id, target.name, target.name, str(target))
                store.save_video_caption_frame(frame)
                renamed += 1
    print(f"renamed={renamed}")


def _entity_name(description: str, labels: list[str], video_name: str) -> str:
    matches = [english for english, words in ENTITY_WORDS if any(word in description for word in words)]
    if not matches:
        label_map = {"person": "人员", "train": "列车", "car": "铁路车辆", "truck": "铁路车辆", "traffic light": "信号设备"}
        matches = [label_map.get(label, "铁路目标") for label in labels if label]
    unique = list(dict.fromkeys(item for item in matches if item))
    return "_".join(unique[:3]) or "铁路目标"


if __name__ == "__main__":
    main()
