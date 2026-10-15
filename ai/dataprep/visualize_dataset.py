"""STEPS 8-9 — Class-balance charts + visual sanity-check previews.

Reads the WRITTEN dataset (labels on disk), so previews verify the real output,
not the in-memory conversion.

Outputs (in PantryPilot_Combined_Dataset/):
    chart_images_per_class.png, chart_objects_per_class.png, chart_split_distribution.png
    dataset_preview_source_a.jpg   10 Source A examples with the intentional full-image box
    dataset_preview_source_b.jpg   20 Source B examples with converted YOLO boxes
    dataset_preview_contact_sheet.jpg
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import common as C  # noqa: E402

OUT = C.COMBINED_DIR
GREEN, ORANGE, BLUE, GREY = "#5C8D45", "#E6A23C", "#4C78A8", "#9AA09A"


def save_plot(fig, name: str) -> None:
    for dest in (OUT / name, C.REPORT_DIR / name):
        C.assert_writable_target(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(dest, dpi=130, bbox_inches="tight")
    plt.close(fig)


def charts() -> None:
    rows = list(csv.DictReader(open(OUT / "class_distribution.csv")))
    names = [r["class"] for r in rows]
    x = np.arange(len(names))
    g = lambda k: np.array([int(r[k]) for r in rows])  # noqa: E731

    # 1. images per class
    fig, ax = plt.subplots(figsize=(14, 5))
    w = 0.27
    ax.bar(x - w, g("train_images_from_B"), w, color=GREEN, label="train (Source B)")
    ax.bar(x - w, g("train_images_from_A"), w, bottom=g("train_images_from_B"), color=ORANGE, label="train (Source A, supplemental)")
    ax.bar(x, g("val_images"), w, color=BLUE, label="val")
    ax.bar(x + w, g("test_images"), w, color=GREY, label="test")
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=60, ha="right")
    ax.set_ylabel("images containing class"); ax.set_title("Images per class")
    ax.legend(); fig.tight_layout(); save_plot(fig, "chart_images_per_class.png")

    # 2. objects per class
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(x - w, g("train_objects_from_B"), w, color=GREEN, label="train (Source B)")
    ax.bar(x - w, g("train_objects_from_A"), w, bottom=g("train_objects_from_B"), color=ORANGE, label="train (Source A)")
    ax.bar(x, g("val_objects"), w, color=BLUE, label="val")
    ax.bar(x + w, g("test_objects"), w, color=GREY, label="test")
    ax.set_xticks(x); ax.set_xticklabels(names, rotation=60, ha="right")
    ax.set_ylabel("annotated objects"); ax.set_title("Objects per class")
    ax.legend(); fig.tight_layout(); save_plot(fig, "chart_objects_per_class.png")

    # 3. split distribution
    b = json.loads((OUT / "build_stats.json").read_text())["counts"]
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.2))
    sp = ["train", "val", "test"]
    axs[0].bar(sp, [b[s]["images"] for s in sp], color=[GREEN, BLUE, GREY]); axs[0].set_title("Images per split")
    axs[1].bar(sp, [b[s]["objects"] for s in sp], color=[GREEN, BLUE, GREY]); axs[1].set_title("Objects per split")
    axs[2].pie([b["train"]["from_B"], b["train"]["from_A"]],
               labels=[f"Source B\n{b['train']['from_B']}", f"Source A\n{b['train']['from_A']}"],
               colors=[GREEN, ORANGE], autopct="%1.0f%%"); axs[2].set_title("Training images by source")
    for a, s in zip(axs[:2], ("images", "objects")):
        for i, v in enumerate([b[k][s] for k in sp]):
            a.text(i, v, str(v), ha="center", va="bottom")
    fig.tight_layout(); save_plot(fig, "chart_split_distribution.png")


def read_boxes(lbl: Path):
    out = []
    for line in lbl.read_text().splitlines():
        if line.strip():
            c, x, y, w, h = line.split()[:5]
            out.append((int(c), float(x), float(y), float(w), float(h)))
    return out


def tile(img, caption, tw, th, cap_h=26):
    ih, iw = img.shape[:2]
    s = min(tw / iw, (th) / ih)
    img = cv2.resize(img, (int(iw * s), int(ih * s)), interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
    canvas = np.full((th + cap_h, tw, 3), 244, np.uint8)
    canvas[: img.shape[0], : img.shape[1]] = img
    cv2.putText(canvas, caption[:int(tw / 7.2)], (4, th + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (30, 30, 30), 1, cv2.LINE_AA)
    return canvas


def grid(tiles, cols):
    rows = (len(tiles) + cols - 1) // cols
    th, tw = tiles[0].shape[:2]
    sheet = np.full((rows * th + (rows + 1) * 6, cols * tw + (cols + 1) * 6, 3), 255, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        y, x = 6 + r * (th + 6), 6 + c * (tw + 6)
        sheet[y:y + th, x:x + tw] = t
    return sheet


def save_img(name: str, img) -> None:
    for dest in (OUT / name, C.REPORT_DIR / name):
        C.assert_writable_target(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), img, [cv2.IMWRITE_JPEG_QUALITY, 90])


def previews() -> None:
    rng = random.Random(C.SEED)

    # Source A: 10 examples from distinct classes, drawn from the written train labels
    a_lbls = sorted((OUT / "labels" / "train").glob("a_*.txt"))
    by_cls = {}
    for p in a_lbls:
        by_cls.setdefault(int(p.read_text().split()[0]), []).append(p)
    classes = sorted(by_cls)
    rng.shuffle(classes)
    tiles_a = []
    for cid in classes[:10]:
        lp = rng.choice(by_cls[cid])
        img = cv2.imread(str(OUT / "images" / "train" / f"{lp.stem}.jpg"))
        img = cv2.resize(img, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
        boxes = read_boxes(lp)
        assert len(boxes) == 1 and boxes[0][1:] == (0.5, 0.5, 1.0, 1.0), f"unexpected A label {lp}"
        h, w = img.shape[:2]
        cv2.rectangle(img, (3, 3), (w - 4, h - 4), (0, 0, 255), 3)        # full-image box (inset so it is visible)
        cv2.putText(img, f"{C.CLASS_NAMES[boxes[0][0]]}", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
        tiles_a.append(tile(img, "FULL-IMAGE BOX 0.5 0.5 1.0 1.0 (synthetic)", 360, 360))
    sheet_a = grid(tiles_a, 5)
    save_img("dataset_preview_source_a.jpg", sheet_a)

    # Source B: 20 examples across splits (7 train, 7 val, 6 test), from written labels
    tiles_b = []
    palette = [tuple(int(v) for v in np.random.RandomState(i * 7 + 3).randint(40, 230, 3)) for i in range(22)]
    picks = []
    for split, n in (("train", 7), ("val", 7), ("test", 6)):
        ls = sorted((OUT / "labels" / split).glob("b_*.txt"))
        picks += [(split, p) for p in rng.sample(ls, n)]
    for split, lp in picks:
        img_path = next((OUT / "images" / split).glob(f"{lp.stem}.*"))
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        boxes = read_boxes(lp)
        for c, x, y, bw, bh in boxes:
            p1 = (int((x - bw / 2) * w), int((y - bh / 2) * h)); p2 = (int((x + bw / 2) * w), int((y + bh / 2) * h))
            cv2.rectangle(img, p1, p2, palette[c], 2)
            cv2.putText(img, C.CLASS_NAMES[c][:9], (p1[0] + 2, max(p1[1] + 11, 11)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, palette[c], 1, cv2.LINE_AA)
        tiles_b.append(tile(img, f"[{split}] {len(boxes)} boxes  {lp.stem[2:34]}", 420, 250))
    sheet_b = grid(tiles_b, 4)
    save_img("dataset_preview_source_b.jpg", sheet_b)

    # contact sheet: both previews stacked at the same width
    W = 1700
    ra = cv2.resize(sheet_a, (W, int(sheet_a.shape[0] * W / sheet_a.shape[1])))
    rb = cv2.resize(sheet_b, (W, int(sheet_b.shape[0] * W / sheet_b.shape[1])))
    def banner(text):
        b = np.full((46, W, 3), 92 // 2 + 20, np.uint8); b[:] = (69, 141, 92)
        cv2.putText(b, text, (14, 31), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
        return b
    contact = np.vstack([banner("SOURCE A - supplemental single-vegetable images (full-image boxes are intentional)"), ra,
                         banner("SOURCE B - true multi-object detection (converted VOC -> YOLO boxes)"), rb])
    save_img("dataset_preview_contact_sheet.jpg", contact)
    print("previews written")


if __name__ == "__main__":
    charts()
    previews()
    print(f"Saved to {OUT}")
