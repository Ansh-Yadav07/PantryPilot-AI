"""Visual inspection of the detector on TEST images.

Runs inference on N random test images and saves:
    runs/pantrypilot/test_predictions/prediction_001.jpg ...  (boxes + confidence)
    runs/pantrypilot/test_predictions/contact_sheet.jpg       (grid of all predictions,
                                                              each captioned with its
                                                              top detected classes)
    runs/pantrypilot/test_predictions/gt_vs_pred_sheet.jpg    (ground truth | prediction
                                                              pairs, to spot misses)

Usage:
    python visualize_predictions.py [--n 20] [--cols 4] [--conf 0.25]
"""
from __future__ import annotations

import argparse
import random
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

import config
from predict import detect, pretty

OUT_DIR = config.RUN_DIR / "test_predictions"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
TILE_W, TILE_H, CAPTION_H = 480, 360, 56
BG = (236, 242, 244)  # warm off-white (BGR of #F4F2EC)


def _fit(img: np.ndarray, w: int, h: int) -> np.ndarray:
    ih, iw = img.shape[:2]
    s = min(w / iw, h / ih)
    resized = cv2.resize(img, (int(iw * s), int(ih * s)), interpolation=cv2.INTER_AREA)
    canvas = np.full((h, w, 3), BG, dtype=np.uint8)
    y, x = (h - resized.shape[0]) // 2, (w - resized.shape[1]) // 2
    canvas[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
    return canvas


def _tile(img: np.ndarray, title: str, caption: str) -> np.ndarray:
    tile = np.full((TILE_H + CAPTION_H, TILE_W, 3), BG, dtype=np.uint8)
    tile[:TILE_H] = _fit(img, TILE_W, TILE_H)
    cv2.putText(tile, title, (8, TILE_H + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (31, 34, 32), 1, cv2.LINE_AA)
    cv2.putText(tile, caption[:62], (8, TILE_H + 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (69, 141, 92), 1, cv2.LINE_AA)
    cv2.rectangle(tile, (0, 0), (TILE_W - 1, TILE_H + CAPTION_H - 1), (255, 255, 255), 2)
    return tile


def _grid(tiles: list[np.ndarray], cols: int) -> np.ndarray:
    rows = (len(tiles) + cols - 1) // cols
    th, tw = tiles[0].shape[:2]
    pad = 8
    sheet = np.full((rows * (th + pad) + pad, cols * (tw + pad) + pad, 3), BG, dtype=np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        y, x = pad + r * (th + pad), pad + c * (tw + pad)
        sheet[y:y + th, x:x + tw] = t
    return sheet


def _draw_gt(img_path: Path, names: dict[int, str]) -> tuple[np.ndarray, int]:
    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]
    lbl = config.DATASET_DIR / "labels" / "test" / f"{img_path.stem}.txt"
    n = 0
    if lbl.exists():
        for line in lbl.read_text().splitlines():
            if not line.strip():
                continue
            c, x, y, bw, bh = line.split()[:5]
            x, y, bw, bh = float(x) * w, float(y) * h, float(bw) * w, float(bh) * h
            cv2.rectangle(img, (int(x - bw / 2), int(y - bh / 2)), (int(x + bw / 2), int(y + bh / 2)), (60, 160, 60), 2)
            n += 1
    return img, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(config.BEST_WEIGHTS))
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    names = config.class_names()
    test_dir = config.DATASET_DIR / "images" / "test"
    imgs = sorted(p for p in test_dir.iterdir() if p.suffix.lower() in IMG_EXTS)
    random.seed(args.seed)
    picks = random.sample(imgs, min(args.n, len(imgs)))

    tiles, pair_tiles = [], []
    for i, p in enumerate(picks, 1):
        dets, result = detect(str(p), args.weights, conf=args.conf)
        out = OUT_DIR / f"prediction_{i:03d}.jpg"
        result.save(filename=str(out))
        annotated = result.plot()

        counts = Counter(d["name"] for d in dets)
        top = sorted({d["name"]: d["confidence"] for d in reversed(dets)}.items(), key=lambda kv: -kv[1])[:3]
        caption = "  ".join(f"{pretty(n)} {c:.2f}" for n, c in top) or "no detections"
        title = f"#{i:02d} {p.name[:30]}  |  {len(dets)} boxes, {len(counts)} classes"
        tiles.append(_tile(annotated, title, caption))

        gt_img, n_gt = _draw_gt(p, names)
        pair_tiles.append(_tile(gt_img, f"#{i:02d} GROUND TRUTH", f"{n_gt} labelled objects"))
        pair_tiles.append(_tile(annotated, f"#{i:02d} PREDICTION", f"{len(dets)} detections"))
        print(f"  {out.name}: {len(dets):>3} detections  {caption}")

    cv2.imwrite(str(OUT_DIR / "contact_sheet.jpg"), _grid(tiles, args.cols), [cv2.IMWRITE_JPEG_QUALITY, 88])
    cv2.imwrite(str(OUT_DIR / "gt_vs_pred_sheet.jpg"), _grid(pair_tiles, 4), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"\nContact sheet : {OUT_DIR / 'contact_sheet.jpg'}")
    print(f"GT vs pred    : {OUT_DIR / 'gt_vs_pred_sheet.jpg'}")


if __name__ == "__main__":
    main()
