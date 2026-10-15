"""Quick sanity check BEFORE spending hours on training.

1. Loads data.yaml and confirms class names / count.
2. Scans every label file: class IDs in range, boxes normalised to [0, 1].
3. Draws ground-truth boxes on a few training images so you can eyeball them.
4. Loads the pretrained YOLO checkpoint and runs inference on those images
   (pretrained = COCO classes, so this only proves the model + device work).

Outputs go to ai/runs/sanity_check/.

Usage:
    python sanity_check.py [--model yolo26n.pt] [--n 3]
"""
from __future__ import annotations

import argparse
import random
from collections import Counter
from pathlib import Path

import cv2

import config

OUT_DIR = config.RUNS_PROJECT / "sanity_check"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def scan_labels(names: dict[int, str]) -> bool:
    ok = True
    nc = len(names)
    total_counts: Counter = Counter()
    for split in config.SPLITS:
        img_dir = config.DATASET_DIR / "images" / split
        lbl_dir = config.DATASET_DIR / "labels" / split
        imgs = [p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXTS]
        n_boxes, empty, bad_cls, bad_box, missing = 0, 0, 0, 0, 0
        for img in imgs:
            lbl = lbl_dir / f"{img.stem}.txt"
            if not lbl.exists():
                missing += 1
                continue
            lines = [l.split() for l in lbl.read_text().splitlines() if l.strip()]
            if not lines:
                empty += 1
            for parts in lines:
                cls = int(float(parts[0]))
                x, y, w, h = map(float, parts[1:5])
                if not 0 <= cls < nc:
                    bad_cls += 1
                if not all(0.0 <= v <= 1.0 for v in (x, y, w, h)) or w <= 0 or h <= 0:
                    bad_box += 1
                total_counts[cls] += 1
                n_boxes += 1
        print(
            f"  {split:<5} images={len(imgs):<5} boxes={n_boxes:<6} empty={empty:<3} "
            f"missing_labels={missing} bad_class_ids={bad_cls} bad_boxes={bad_box}"
        )
        ok &= missing == 0 and bad_cls == 0 and bad_box == 0

    print("\n  Objects per class (all splits):")
    for cid in sorted(names):
        print(f"    {cid:>2} {names[cid]:<14} {total_counts.get(cid, 0):>6}")
    print(f"  Total objects: {sum(total_counts.values())}")
    return ok


def draw_ground_truth(img_path: Path, names: dict[int, str], out_path: Path) -> int:
    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]
    lbl = config.DATASET_DIR / "labels" / "train" / f"{img_path.stem}.txt"
    n = 0
    for line in lbl.read_text().splitlines():
        if not line.strip():
            continue
        cls, x, y, bw, bh = line.split()[:5]
        cls = int(float(cls))
        x, y, bw, bh = float(x) * w, float(y) * h, float(bw) * w, float(bh) * h
        p1 = (int(x - bw / 2), int(y - bh / 2))
        p2 = (int(x + bw / 2), int(y + bh / 2))
        cv2.rectangle(img, p1, p2, (69, 141, 92), 2)
        cv2.putText(img, names[cls], (p1[0], max(p1[1] - 4, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (69, 141, 92), 2)
        n += 1
    cv2.imwrite(str(out_path), img)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--n", type=int, default=3)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("1) data.yaml")
    src = config.load_source_yaml()
    names = config.class_names()
    print(f"  nc={src['nc']}  names={len(names)}  path={src.get('path')}")
    assert src["nc"] == len(names), "nc does not match number of names"
    for cid, name in names.items():
        print(f"    {cid:>2}: {name}")

    print("\n2) Label scan")
    labels_ok = scan_labels(names)

    print("\n3) Symlink data view (prevents cache writes on the SSD)")
    view_yaml = config.ensure_data_view()
    print(f"  {view_yaml}")

    print("\n4) Ground-truth visualisation")
    train_imgs = sorted(
        p for p in (config.DATASET_DIR / "images" / "train").iterdir()
        if p.suffix.lower() in IMG_EXTS
    )
    random.seed(0)
    picks = random.sample(train_imgs, args.n)
    for i, p in enumerate(picks, 1):
        out = OUT_DIR / f"gt_{i:02d}_{p.stem}.jpg"
        n = draw_ground_truth(p, names, out)
        print(f"  {p.name}: {n} boxes -> {out.name}")

    print("\n5) Model + device")
    from ultralytics import YOLO

    device = config.pick_device()
    model_name = config.resolve_model(args.model)
    model = YOLO(model_name)
    print(f"  model={model_name}  device={device}")
    results = model.predict([str(p) for p in picks], device=device, verbose=False)
    for p, r in zip(picks, results):
        r.save(filename=str(OUT_DIR / f"pretrained_{p.stem}.jpg"))
        print(f"  {p.name}: {len(r.boxes)} pretrained (COCO) detections")

    print("\nRESULT:", "PASS" if labels_ok else "FAIL - fix labels before training")
    print(f"Visuals: {OUT_DIR}")


if __name__ == "__main__":
    main()
