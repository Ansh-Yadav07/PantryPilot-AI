"""Detect vegetables in a single photograph.

Prints each detected ingredient with confidence and bounding box, and saves an
annotated copy of the image. The ``detect()`` function is importable so the
FastAPI backend can reuse it later.

Usage:
    python predict.py --image /path/to/photo.jpg
    python predict.py --image photo.jpg --conf 0.4 --out annotated.jpg
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import config

_MODEL_CACHE: dict = {}


def _load(weights: str):
    from ultralytics import YOLO
    if weights not in _MODEL_CACHE:
        _MODEL_CACHE[weights] = YOLO(weights)
    return _MODEL_CACHE[weights]


def detect(image, weights: str | Path = config.BEST_WEIGHTS, conf: float = 0.25,
           iou: float = 0.5, imgsz: int = 640, device: str | None = None):
    """Run detection. ``image`` may be a path, URL, numpy array or PIL image.

    Returns (detections, ultralytics_result) where detections is a list of
    ``{"name", "class_id", "confidence", "box": [x1, y1, x2, y2]}`` sorted by confidence.
    """
    model = _load(str(weights))
    result = model.predict(source=image, conf=conf, iou=iou, imgsz=imgsz,
                           device=device or config.pick_device(), verbose=False)[0]
    dets = []
    for b in result.boxes:
        cid = int(b.cls)
        dets.append({
            "name": result.names[cid],
            "class_id": cid,
            "confidence": round(float(b.conf), 4),
            "box": [round(float(v), 1) for v in b.xyxy[0].tolist()],
        })
    dets.sort(key=lambda d: d["confidence"], reverse=True)
    return dets, result


def pretty(name: str) -> str:
    return name.replace("_", " ").title()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--weights", default=str(config.BEST_WEIGHTS))
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", default=None, help="Annotated output path (default: <image>_detected.jpg)")
    ap.add_argument("--json", action="store_true", help="Also print raw JSON")
    args = ap.parse_args()

    img = Path(args.image).expanduser()
    if not img.exists():
        raise SystemExit(f"Image not found: {img}")
    if not Path(args.weights).exists():
        raise SystemExit(f"Weights not found: {args.weights} (train first)")

    dets, result = detect(str(img), args.weights, conf=args.conf)

    out = Path(args.out) if args.out else img.with_name(f"{img.stem}_detected.jpg")
    result.save(filename=str(out))

    print(f"\n{len(dets)} detections in {img.name} (conf >= {args.conf})\n")
    print(f"{'Ingredient':<16}{'Conf':>6}   Box [x1, y1, x2, y2]")
    print("-" * 52)
    for d in dets:
        x1, y1, x2, y2 = d["box"]
        print(f"{pretty(d['name']):<16}{d['confidence']:>6.2f}   [{x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f}]")

    counts = Counter(d["name"] for d in dets)
    if counts:
        print("\nSummary: " + ", ".join(f"{pretty(n)} x{c}" for n, c in counts.most_common()))
    print(f"\nAnnotated image: {out}")
    if args.json:
        print(json.dumps(dets, indent=2))


if __name__ == "__main__":
    main()
