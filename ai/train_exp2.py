#!/usr/bin/env python3
"""
PantryPilot AI - Experiment 2 (combined dataset, YOLO26-small, 150 epochs)

Run from the `ai/` folder:
    source .venv/bin/activate
    caffeinate -i python train_exp2.py

Outputs go to:  runs/pantrypilot/exp2_combined_150/   (never overwrites; a
numeric suffix is added if the folder already exists).
"""

import csv
import random
import shutil
import sys
import time
import traceback
from pathlib import Path

# --------------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------------
DATA_YAML = Path("/Volumes/Personal/Dataset(PantryPilot_AI)/PantryPilot_Combined_Dataset/data.yaml")

# Small pretrained checkpoint. The project already uses yolo26n.pt, so the
# installed Ultralytics (8.4.x) ships YOLO26 -> the matching small model is yolo26s.pt.
# Falls back to yolo11s.pt if yolo26s.pt cannot be obtained.
MODEL_CANDIDATES = ["yolo26s.pt", "yolo11s.pt"]

EPOCHS = 150          # overnight run
PATIENCE = 25         # early stopping: stop if fitness doesn't improve for 25 epochs
IMGSZ = 640
BATCH = 8             # conservative for a 'small' model at 640 on Apple Silicon unified memory
WORKERS = 4           # dataloader workers (kept modest; more can cause MPS/mac stalls)
SEED = 42

# Output location (relative to this script's folder -> ai/runs/pantrypilot/...)
PROJECT_DIR = Path(__file__).resolve().parent / "runs" / "pantrypilot"
RUN_NAME = "exp2_combined_150"

# Real-world images: searched AFTER training only, never used for training.
REAL_WORLD_CANDIDATES = [
    "real_world_test", "real_world", "real_world_images", "realworld", "real_world_samples",
    "data/real_world", "data/real_world_test", "data/real_world_images",
    "runs/pantrypilot/real_world_test", "../real_world_test", "../real_world",
    "../docs/real_world", "../docs/real_world_test",
]
REAL_WORLD_CONFS = [0.25, 0.40, 0.50, 0.60]

# Previous model baseline
BASELINE = {"mAP50": 0.590, "mAP50-95": 0.338, "Precision": 0.551, "Recall": 0.631}

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LEAKAGE_LABEL = "Official test evaluation — video-frame leakage present"

BAR = "=" * 50


def fail(msg):
    print(f"\n[ERROR] {msg}\n", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------
# Imports with useful errors
# --------------------------------------------------------------------------
try:
    import torch
    import ultralytics
    import yaml
    from ultralytics import YOLO
except ImportError as e:
    fail(f"Missing package: {e}. Activate the venv (`source .venv/bin/activate`) or run "
         f"`pip install -U ultralytics`.")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def pick_device():
    if torch.backends.mps.is_available():
        return "mps", "MPS"
    if torch.cuda.is_available():
        return "0", "CUDA"
    return "cpu", "CPU"


def unique_run_dir(project: Path, name: str) -> Path:
    """Never overwrite an old experiment: add _2, _3, ... if the folder exists."""
    d = project / name
    i = 2
    while d.exists():
        d = project / f"{name}_{i}"
        i += 1
    return d


def split_images(cfg, split):
    """Resolve the image folder(s) of a split from data.yaml (read-only)."""
    root = Path(cfg.get("path", DATA_YAML.parent))
    if not root.is_absolute():
        root = (DATA_YAML.parent / root).resolve()
    entry = cfg.get(split)
    if entry is None:
        return []
    entries = entry if isinstance(entry, list) else [entry]
    out = []
    for e in entries:
        p = Path(e)
        out.append(p if p.is_absolute() else root / p)
    return out


def list_images(paths):
    files = []
    for p in paths:
        if p.is_file() and p.suffix.lower() == ".txt":
            files += [Path(l.strip()) for l in p.read_text().splitlines() if l.strip()]
        elif p.is_dir():
            files += [f for f in sorted(p.rglob("*")) if f.suffix.lower() in IMG_EXT]
    return files


def fmt(v, w=9):
    return f"{v:{w}.4f}" if isinstance(v, (int, float)) else f"{'-':>{w}}"


# --------------------------------------------------------------------------
# Live epoch table + best tracker (Ultralytics callback)
# --------------------------------------------------------------------------
class LiveReporter:
    HEADER = (f"{'Epoch':<9}{'GPU/MPS':<9}{'BoxLoss':>9}{'ClsLoss':>9}{'DFLoss':>9}"
              f"{'Precision':>11}{'Recall':>9}{'mAP50':>9}{'mAP50-95':>10}")

    def __init__(self, run_dir, device_label):
        self.run_dir = run_dir
        self.dev = device_label
        self.best = -1.0
        self.best_epoch = 0
        self.rows = 0
        self.t0 = time.time()
        self.progress_file = run_dir / "training_progress.txt"
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(self.progress_file, "w") as f:
            f.write(self.HEADER + "\n")

    def on_train_start(self, trainer):
        print("\n" + self.HEADER)
        print("-" * len(self.HEADER))

    def on_fit_epoch_end(self, trainer):
        try:
            m = trainer.metrics or {}
            P = m.get("metrics/precision(B)")
            R = m.get("metrics/recall(B)")
            m50 = m.get("metrics/mAP50(B)")
            m5095 = m.get("metrics/mAP50-95(B)")

            losses = {}
            try:
                losses = trainer.label_loss_items(trainer.tloss, prefix="")
            except Exception:
                pass
            box = losses.get("box_loss", losses.get("box"))
            cls = losses.get("cls_loss", losses.get("cls"))
            dfl = losses.get("dfl_loss", losses.get("dfl"))

            ep = f"{trainer.epoch + 1}/{trainer.epochs}"
            row = (f"{ep:<9}{self.dev:<9}{fmt(box)}{fmt(cls)}{fmt(dfl)}"
                   f"{fmt(P, 11)}{fmt(R)}{fmt(m50)}{fmt(m5095, 10)}")
            if self.rows and self.rows % 25 == 0:
                print(self.HEADER)
            print(row, flush=True)
            self.rows += 1

            elapsed = (time.time() - self.t0) / 60
            with open(self.progress_file, "a") as f:
                f.write(row + f"   [{elapsed:.1f} min elapsed]\n")

            if isinstance(m5095, (int, float)) and m5095 > self.best:
                self.best, self.best_epoch = m5095, trainer.epoch + 1
                msg = (f"\n★ NEW BEST MODEL\n"
                       f"  mAP50:     {fmt(m50, 0)}\n"
                       f"  mAP50-95:  {fmt(m5095, 0)}\n"
                       f"  Precision: {fmt(P, 0)}\n"
                       f"  Recall:    {fmt(R, 0)}\n"
                       f"  Epoch:     {ep}\n")
                print(msg, flush=True)
                with open(self.progress_file, "a") as f:
                    f.write(msg)
        except Exception as e:  # never let reporting kill training
            print(f"[reporter warning] {e}")


# --------------------------------------------------------------------------
# Post-training steps
# --------------------------------------------------------------------------
def final_test_eval(best_pt, data_yaml, run_dir, device, names):
    print(f"\n{BAR}\nFINAL EVALUATION (best.pt on test split)\n{LEAKAGE_LABEL}\n{BAR}")
    model = YOLO(str(best_pt))
    res = model.val(
        data=str(data_yaml), split="test", imgsz=IMGSZ, batch=BATCH, device=device,
        plots=True,                       # confusion matrix, PR curve, F1 curve, val prediction batches
        project=str(run_dir), name="test_eval", exist_ok=False, verbose=False, workers=WORKERS,
    )
    b = res.box
    final = {"mAP50": float(b.map50), "mAP50-95": float(b.map),
             "Precision": float(b.mp), "Recall": float(b.mr)}
    print(f"  {LEAKAGE_LABEL}")
    for k, v in final.items():
        print(f"  {k:<10}: {v:.4f}")

    # per-class metrics
    csv_path = run_dir / "per_class_metrics.csv"
    print("\nPer-class metrics (test):")
    print(f"  {'Class':<24}{'Precision':>10}{'Recall':>9}{'mAP50':>9}{'mAP50-95':>10}")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["class", "precision", "recall", "mAP50", "mAP50-95"])
        for i, ci in enumerate(b.ap_class_index):
            p, r, a50, a = b.class_result(i)
            name = names.get(int(ci), str(ci)) if isinstance(names, dict) else names[int(ci)]
            w.writerow([name, f"{p:.4f}", f"{r:.4f}", f"{a50:.4f}", f"{a:.4f}"])
            print(f"  {name:<24}{p:>10.4f}{r:>9.4f}{a50:>9.4f}{a:>10.4f}")
    print(f"\n  Saved: {csv_path}")
    return model, final, Path(res.save_dir)


def contact_sheet(model, test_imgs, run_dir, device, n=25, cols=5, tile=360):
    import cv2
    import numpy as np
    if not test_imgs:
        print("[contact sheet] no test images found, skipping")
        return
    rnd = random.Random(SEED)
    picks = rnd.sample(test_imgs, min(n, len(test_imgs)))
    tiles = []
    for img in picks:
        r = model.predict(str(img), imgsz=IMGSZ, conf=0.25, device=device, verbose=False)[0]
        im = r.plot()
        h, w = im.shape[:2]
        s = tile / max(h, w)
        im = cv2.resize(im, (int(w * s), int(h * s)))
        canvas = np.full((tile, tile, 3), 30, dtype=np.uint8)
        y, x = (tile - im.shape[0]) // 2, (tile - im.shape[1]) // 2
        canvas[y:y + im.shape[0], x:x + im.shape[1]] = im
        tiles.append(canvas)
    while len(tiles) % cols:
        tiles.append(np.full((tile, tile, 3), 30, dtype=np.uint8))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    out = run_dir / "prediction_contact_sheet.jpg"
    cv2.imwrite(str(out), np.vstack(rows))
    print(f"  Contact sheet ({len(picks)} test images): {out}")


def real_world_inference(model, run_dir, device):
    base = Path(__file__).resolve().parent
    folder = None
    for c in REAL_WORLD_CANDIDATES:
        p = (base / c).resolve()
        if p.is_dir() and list_images([p]):
            folder = p
            break
    if folder is None:
        print("\n[real-world] No previous real-world image folder found "
              f"(looked in: {', '.join(REAL_WORLD_CANDIDATES)}). Skipping.\n"
              "  To run later: set REAL_WORLD_CANDIDATES in this script to your folder.")
        return
    imgs = list_images([folder])
    print(f"\n[real-world] {len(imgs)} images from {folder}")
    out_root = run_dir / "real_world_predictions"
    for conf in REAL_WORLD_CONFS:
        res = model.predict(source=str(folder), imgsz=IMGSZ, conf=conf, device=device, save=True,
                            project=str(out_root), name=f"conf_{conf:.2f}", exist_ok=True,
                            verbose=False, stream=False)
        dets = sum(len(r.boxes) for r in res)
        print(f"  conf={conf:.2f}: {dets} detections over {len(res)} images "
              f"-> {out_root / f'conf_{conf:.2f}'}")


def comparison_table(final, run_dir):
    lines = ["", BAR, "OLD BASELINE vs EXPERIMENT 2", BAR,
             f"({LEAKAGE_LABEL})",
             f"{'Metric':<12}{'Old':>10}{'Exp2':>10}{'Delta':>10}",
             "-" * 42]
    for k in ["mAP50", "mAP50-95", "Precision", "Recall"]:
        lines.append(f"{k:<12}{BASELINE[k]:>10.3f}{final[k]:>10.3f}{final[k] - BASELINE[k]:>+10.3f}")
    lines += ["",
              "NOTE: The Source B test split contains video-frame leakage, so these numbers",
              "are optimistic and do NOT represent fully unseen real-world performance."]
    text = "\n".join(lines)
    print(text)
    (run_dir / "comparison_vs_baseline.txt").write_text(text + "\n")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    if not DATA_YAML.exists():
        fail(f"Dataset yaml not found: {DATA_YAML}\nIs the external drive '/Volumes/Personal' mounted?")
    cfg = yaml.safe_load(DATA_YAML.read_text())
    names = cfg.get("names", {})
    if isinstance(names, list):
        names = {i: n for i, n in enumerate(names)}
    train_imgs = list_images(split_images(cfg, "train"))
    val_imgs = list_images(split_images(cfg, "val"))
    test_imgs = list_images(split_images(cfg, "test"))
    if not train_imgs:
        fail("No training images found - check data.yaml paths.")

    device, dev_label = pick_device()

    # Load pretrained weights (NOT from scratch)
    model, model_name, last_err = None, None, None
    for cand in MODEL_CANDIDATES:
        try:
            model = YOLO(cand)
            model_name = cand
            break
        except Exception as e:
            last_err = e
            print(f"[warn] could not load {cand}: {e}")
    if model is None:
        fail(f"Could not load any pretrained model ({MODEL_CANDIDATES}). Need internet for the "
             f"first download. Last error: {last_err}")

    run_dir = unique_run_dir(PROJECT_DIR, RUN_NAME)
    if run_dir.name != RUN_NAME:
        print(f"[note] '{RUN_NAME}' already exists - using '{run_dir.name}' instead (no overwrite).")

    print(f"\n{BAR}\nPANTRYPILOT EXPERIMENT 2\n{BAR}\n")
    print(f"Device:            {dev_label} ({device})")
    print(f"PyTorch version:   {torch.__version__}")
    print(f"Ultralytics version: {ultralytics.__version__}")
    print(f"Model:             {model_name} (pretrained)")
    print(f"Dataset:           {DATA_YAML}")
    print(f"Classes:           {len(names)}")
    print(f"Train images:      {len(train_imgs)}")
    print(f"Validation images: {len(val_imgs)}")
    print(f"Test images:       {len(test_imgs)}")
    print(f"Image size:        {IMGSZ}")
    print(f"Batch size:        {BATCH}")
    print(f"Epochs:            {EPOCHS}")
    print(f"Output dir:        {run_dir}")
    print(f"\n{BAR}")

    reporter = LiveReporter(run_dir, dev_label)
    model.add_callback("on_train_start", reporter.on_train_start)
    model.add_callback("on_fit_epoch_end", reporter.on_fit_epoch_end)

    interrupted = False
    t_start = time.time()
    try:
        model.train(
            data=str(DATA_YAML),
            epochs=EPOCHS,
            patience=PATIENCE,
            imgsz=IMGSZ,
            batch=BATCH,
            device=device,
            workers=WORKERS,
            seed=SEED,
            project=str(PROJECT_DIR),
            name=run_dir.name,
            exist_ok=False,       # never overwrite
            pretrained=True,
            val=True,             # validate every epoch
            plots=True,           # results.png, labels, PR/F1 curves, confusion matrix, batches
            save=True,            # best.pt + last.pt
            save_period=-1,       # only best/last (no per-epoch checkpoints)
            cache=False,          # don't hold dataset in RAM (safe for overnight)
            close_mosaic=10,      # turn off mosaic for last 10 epochs (standard)
            # Default/normal augmentation (hsv, fliplr=0.5, mosaic=1.0, scale=0.5, ...) - nothing extreme.
            verbose=False,        # keep terminal compact; the epoch table is printed by our callback
        )
    except KeyboardInterrupt:
        interrupted = True
        print("\n[!] Interrupted by user. Saving state and evaluating best checkpoint so far...")
    except Exception as e:
        print(f"\n[ERROR] Training crashed: {e}")
        traceback.print_exc()
        interrupted = True
        print("Will attempt to evaluate any saved checkpoint.")

    train_min = (time.time() - t_start) / 60
    print(f"\nTraining time: {train_min:.1f} min ({'interrupted/failed' if interrupted else 'finished'})")

    weights = run_dir / "weights"
    best_pt, last_pt = weights / "best.pt", weights / "last.pt"
    for p in (best_pt, last_pt):
        if p.exists():
            shutil.copy2(p, run_dir / p.name)   # convenience copy of best.pt / last.pt at run root
    if not best_pt.exists():
        fail(f"best.pt not found in {weights}. Nothing to evaluate.")
    if interrupted:
        print(f"Resume later with: yolo train resume model={last_pt}")

    try:
        eval_model, final, _ = final_test_eval(best_pt, DATA_YAML, run_dir, device, names)
    except Exception as e:
        print(f"[ERROR] Final evaluation failed: {e}")
        traceback.print_exc()
        return

    try:
        print("\nPrediction examples:")
        contact_sheet(eval_model, test_imgs, run_dir, device)
    except Exception as e:
        print(f"[warn] contact sheet failed: {e}")

    try:
        real_world_inference(eval_model, run_dir, device)
    except Exception as e:
        print(f"[warn] real-world inference failed: {e}")

    comparison_table(final, run_dir)

    print(f"\n{BAR}\nDONE. Everything is in: {run_dir}")
    print("  weights/best.pt, weights/last.pt, results.csv, results.png, training_progress.txt,")
    print("  test_eval/ (confusion matrix, PR/F1 curves, val batches), per_class_metrics.csv,")
    print("  prediction_contact_sheet.jpg, real_world_predictions/ (if images found)")
    print(BAR)


if __name__ == "__main__":
    main()
