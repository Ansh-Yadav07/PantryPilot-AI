"""Final evaluation of the trained detector on the held-out TEST split.

Reports overall Precision / Recall / mAP50 / mAP50-95, per-class metrics,
a confusion matrix, PR/F1 curves, and the confidence distribution of detections.

Outputs (ai/runs/pantrypilot/test_eval/):
    confusion_matrix.png, confusion_matrix_normalized.png, *_curve.png
    metrics.json            overall + per-class numbers
    per_class_metrics.csv   per-class table (sorted worst -> best)
    confidence_hist.png     histogram of detection confidences on the test set

Usage:
    python evaluate.py [--weights runs/pantrypilot/weights/best.pt] [--split test]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(config.BEST_WEIGHTS))
    ap.add_argument("--split", default="test", choices=["val", "test"])
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--conf", type=float, default=0.25, help="Confidence used for the detection-count/histogram stats")
    args = ap.parse_args()

    from ultralytics import YOLO

    device = config.pick_device()
    data_yaml = config.ensure_data_view()
    out_name = f"{args.split}_eval"
    out_dir = config.RUN_DIR / out_name

    model = YOLO(args.weights)
    metrics = model.val(
        data=str(data_yaml),
        split=args.split,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        plots=True,
        project=str(config.RUN_DIR),
        name=out_name,
        exist_ok=True,
        verbose=True,
    )

    box = metrics.box
    names = metrics.names
    overall = {
        "split": args.split,
        "weights": args.weights,
        "device": device,
        "precision": round(float(box.mp), 4),
        "recall": round(float(box.mr), 4),
        "mAP50": round(float(box.map50), 4),
        "mAP50-95": round(float(box.map), 4),
    }

    # Per-class metrics
    nt = getattr(metrics, "nt_per_class", None)
    rows = []
    for i, cid in enumerate(box.ap_class_index):
        cid = int(cid)
        rows.append({
            "class_id": cid,
            "class": names[cid],
            "instances": int(nt[cid]) if nt is not None else None,
            "precision": round(float(box.p[i]), 4),
            "recall": round(float(box.r[i]), 4),
            "AP50": round(float(box.ap50[i]), 4),
            "AP50-95": round(float(box.ap[i]), 4),
        })
    rows.sort(key=lambda r: r["AP50-95"])

    # Confidence distribution + detection counts on the split
    conf_stats = _confidence_stats(model, args.split, args.conf, device, args.imgsz, out_dir)

    report = {"overall": overall, "per_class": rows, "detections": conf_stats}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(report, indent=2))
    _write_csv(rows, out_dir / "per_class_metrics.csv")

    print("\n" + "=" * 64)
    print(f" {args.split.upper()} SET RESULTS")
    print("=" * 64)
    for k in ("precision", "recall", "mAP50", "mAP50-95"):
        print(f"  {k:<10} {overall[k]:.4f}")
    print("\n  Per-class (worst -> best by AP50-95):")
    print(f"  {'class':<14}{'inst':>6}{'P':>8}{'R':>8}{'AP50':>8}{'AP50-95':>9}")
    for r in rows:
        print(f"  {r['class']:<14}{(r['instances'] or 0):>6}{r['precision']:>8.3f}"
              f"{r['recall']:>8.3f}{r['AP50']:>8.3f}{r['AP50-95']:>9.3f}")
    print(f"\n  Detections @conf>={args.conf}: {conf_stats['total_detections']} "
          f"({conf_stats['mean_per_image']:.1f}/image), median conf {conf_stats['median_conf']:.3f}")
    print(f"\n  Saved to {out_dir}")


def _confidence_stats(model, split: str, conf: float, device: str, imgsz: int, out_dir: Path) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    img_dir = config.DATA_VIEW_DIR / "images" / split
    confs, per_image = [], []
    for r in model.predict(source=str(img_dir), conf=conf, device=device, imgsz=imgsz,
                           stream=True, verbose=False):
        c = r.boxes.conf.cpu().numpy() if r.boxes is not None else np.array([])
        confs.extend(c.tolist())
        per_image.append(len(c))

    confs_arr = np.array(confs) if confs else np.array([0.0])
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(7, 4))
    plt.hist(confs_arr, bins=30, range=(conf, 1.0), color="#5C8D45", edgecolor="white")
    plt.title(f"Detection confidence distribution ({split}, conf>={conf})")
    plt.xlabel("confidence"); plt.ylabel("detections")
    plt.tight_layout(); plt.savefig(out_dir / "confidence_hist.png", dpi=120); plt.close()

    bins = [conf, 0.5, 0.7, 0.9, 1.0001]
    hist, _ = np.histogram(confs_arr, bins=bins)
    return {
        "conf_threshold": conf,
        "images": len(per_image),
        "total_detections": int(len(confs)),
        "mean_per_image": float(np.mean(per_image)) if per_image else 0.0,
        "max_per_image": int(max(per_image)) if per_image else 0,
        "median_conf": float(np.median(confs_arr)),
        "buckets": {f"{bins[i]:.2f}-{min(bins[i+1],1):.2f}": int(hist[i]) for i in range(len(hist))},
    }


def _write_csv(rows: list[dict], path: Path) -> None:
    import csv
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
