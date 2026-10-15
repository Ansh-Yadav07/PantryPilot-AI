"""Train the PantryPilot multi-vegetable object detector (Ultralytics YOLO).

- Pretrained lightweight checkpoint (never trains from scratch)
- Apple Metal (MPS) if available, else CPU
- Train split for training, val split for model selection / early stopping
- Test split is NOT touched here; use evaluate.py for the final test evaluation
- Ultralytics plots (loss curves, P/R/mAP, confusion matrix, PR curves, batch
  previews) are saved into ai/runs/pantrypilot/

Usage:
    python train_vegetable_detector.py                 # defaults: 50 epochs, 640px
    python train_vegetable_detector.py --epochs 100 --batch 8
    python train_vegetable_detector.py --resume        # continue an interrupted run
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

import config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="Pretrained checkpoint (default: newest nano available)")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=None, help="Default: chosen from system memory")
    ap.add_argument("--patience", type=int, default=15, help="Early-stopping patience (epochs)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--resume", action="store_true", help="Resume from runs/pantrypilot/weights/last.pt")
    args = ap.parse_args()

    from ultralytics import YOLO

    device = config.pick_device()
    data_yaml = config.ensure_data_view()

    if args.resume:
        last = config.RUN_DIR / "weights" / "last.pt"
        print(f"Resuming from {last} on {device}")
        start = time.time()
        YOLO(str(last)).train(resume=True, device=device)
        _write_summary({"resumed": True}, time.time() - start)
        return

    model_name = config.resolve_model(args.model)
    batch = args.batch or config.auto_batch_size()

    print("=" * 60)
    print(f" model   : {model_name} (pretrained)")
    print(f" device  : {device}")
    print(f" data    : {data_yaml}")
    print(f" epochs  : {args.epochs}  (patience {args.patience})")
    print(f" imgsz   : {args.imgsz}   batch: {batch}")
    print(f" output  : {config.RUN_DIR}")
    print("=" * 60)

    model = YOLO(model_name)
    start = time.time()
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=batch,
        device=device,
        workers=args.workers,
        patience=args.patience,
        pretrained=True,
        project=str(config.RUNS_PROJECT),
        name=config.RUN_NAME,
        exist_ok=True,
        plots=True,          # loss/metric curves, confusion matrix, PR/F1/P/R curves, batch previews
        save=True,           # weights/best.pt + weights/last.pt
        save_period=10,      # extra checkpoint every 10 epochs
        cache=False,         # 8 GB unified memory: don't cache images in RAM
        seed=0,
        deterministic=False,
        verbose=True,
    )
    elapsed = time.time() - start

    _write_summary(
        {
            "model": model_name,
            "device": device,
            "epochs_requested": args.epochs,
            "imgsz": args.imgsz,
            "batch": batch,
            "patience": args.patience,
        },
        elapsed,
    )


def _write_summary(meta: dict, elapsed_s: float) -> None:
    """Persist training metadata + best epoch (from results.csv) to training_summary.json."""
    import csv

    summary = dict(meta)
    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    summary["training_time_s"] = round(elapsed_s, 1)
    summary["training_time_h"] = round(elapsed_s / 3600, 2)

    results_csv = config.RUN_DIR / "results.csv"
    if results_csv.exists():
        with open(results_csv) as f:
            rows = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(f)]
        key = "metrics/mAP50-95(B)"
        best = max(rows, key=lambda r: float(r[key]))
        summary["epochs_completed"] = max(int(float(r["epoch"])) for r in rows)
        summary["best_epoch"] = int(float(best["epoch"]))
        summary["best_val"] = {
            "precision": round(float(best["metrics/precision(B)"]), 4),
            "recall": round(float(best["metrics/recall(B)"]), 4),
            "mAP50": round(float(best["metrics/mAP50(B)"]), 4),
            "mAP50-95": round(float(best[key]), 4),
        }

    out = config.RUN_DIR / "training_summary.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nTraining summary -> {out}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
