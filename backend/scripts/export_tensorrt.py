import argparse
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an Ultralytics YOLO model to TensorRT.")
    parser.add_argument("model", type=Path, help="Path to the source .pt model")
    parser.add_argument("--device", default="0", help="CUDA device, for example 0")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    parser.add_argument("--workspace", type=float, default=4.0, help="TensorRT workspace size in GiB")
    parser.add_argument("--batch", type=int, default=1, help="Maximum engine batch size")
    parser.add_argument("--fp32", action="store_true", help="Disable FP16 export")
    args = parser.parse_args()

    if args.model.suffix != ".pt":
        raise SystemExit("The source model must be an Ultralytics .pt file")
    if not args.model.exists():
        raise SystemExit(f"Model not found: {args.model}")

    model = YOLO(str(args.model))
    output = model.export(
        format="engine",
        device=args.device,
        imgsz=args.imgsz,
        workspace=args.workspace,
        batch=args.batch,
        half=not args.fp32,
    )
    print(output)


if __name__ == "__main__":
    main()
