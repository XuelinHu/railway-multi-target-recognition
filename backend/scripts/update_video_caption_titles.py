import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.dependencies import get_store


KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("接触网", ("接触网", "供电线路", "电力线路", "架空线路", "电线", "电线杆", "支柱", "横梁")),
    ("人员", ("人员", "行人", "工人", "工作人员", "作业人员", "人体")),
    ("轨道", ("轨道", "铁轨", "钢轨", "铁路轨道", "道岔", "枕木", "碎石")),
    ("标识牌", ("标识牌", "标志牌", "警示牌", "牌", "文字", "标有")),
    ("设备", ("设备", "箱体", "控制箱", "信号设备", "仪器", "探伤")),
    ("车辆", ("车辆", "列车", "火车", "车厢", "汽车", "工程车")),
    ("桥梁", ("桥梁", "桥", "高架", "涵洞")),
    ("站场", ("站台", "站场", "车站", "建筑物", "站房")),
    ("植被", ("树木", "绿树", "植被", "草地", "灌木")),
    ("雨天地面", ("湿滑", "积水", "雨", "水洼", "潮湿")),
    ("施工", ("施工", "作业", "实训", "检修", "维护")),
    ("安全风险", ("风险", "危险", "警示", "安全", "障碍", "侵限")),
]


def main() -> None:
    store = get_store()
    updated = 0
    for batch in store.list_video_caption_batches():
        for video in store.list_video_caption_videos(batch.batch_id):
            frames, _ = store.list_video_caption_frames(video.video_id, page=1, page_size=5000)
            keywords = _extract_keywords(" ".join(frame.description_text for frame in frames))
            display_name = _display_name(video.filename, keywords)
            store.update_video_caption_video_summary(video.video_id, display_name, keywords)
            updated += 1
            print(f"{video.filename} -> {display_name}")
    print(f"updated {updated} video title(s)")


def _extract_keywords(text: str) -> list[str]:
    counts: Counter[str] = Counter()
    for keyword, aliases in KEYWORD_RULES:
        counts[keyword] = sum(text.count(alias) for alias in aliases)
    selected = [keyword for keyword, count in counts.most_common() if count > 0]
    return selected[:4] or ["铁路场景"]


def _display_name(filename: str, keywords: list[str]) -> str:
    timestamp = _timestamp_label(filename)
    stem = Path(filename).stem
    suffix = " · ".join(keywords[:3])
    return f"{timestamp} · {suffix}" if timestamp else f"{stem} · {suffix}"


def _timestamp_label(filename: str) -> str:
    match = re.search(r"DJI_(\d{8})(\d{6})_(\d+)_", filename)
    if not match:
        return ""
    date, time, index = match.groups()
    return f"{date[:4]}-{date[4:6]}-{date[6:8]} {time[:2]}:{time[2:4]}:{time[4:6]} #{index}"


if __name__ == "__main__":
    main()
