# PantryPilot AI — Vegetable Detector

Stage 1 of the PantryPilot AI pipeline: **photo → multiple vegetable detections**.
(Recipe recommendation is intentionally out of scope here.)

## Dataset

Read directly from the external SSD — never copied, never modified:

```
/Volumes/Personal/Dataset(PantryPilot_AI)/Vegetable Object Detection Dataset from Bangladesh/PantryPilot_Dataset
```

22 classes · 2,828 images (2,262 train / 282 val / 284 test) · YOLO format.

> Ultralytics normally writes `labels/*.cache` next to the labels. To keep the SSD
> read-only, `config.ensure_data_view()` builds `ai/data/` containing **symlinks**
> to the SSD split folders plus a derived `data.yaml`. Caches land in `ai/data/`.

## Setup

```bash
cd ai
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import torch; print(torch.backends.mps.is_available())"
```

## Workflow

| Step | Command | Output |
|---|---|---|
| 1. Sanity check | `.venv/bin/python sanity_check.py` | `runs/sanity_check/` (GT boxes, label scan) |
| 2. Train | `.venv/bin/python train_vegetable_detector.py` | `runs/pantrypilot/` (weights, curves, confusion matrix) |
| 3. Test evaluation | `.venv/bin/python evaluate.py` | `runs/pantrypilot/test_eval/` (metrics.json, per-class CSV) |
| 4. Visual check | `.venv/bin/python visualize_predictions.py` | `runs/pantrypilot/test_predictions/` (+ contact sheet) |
| 5. Any photo | `.venv/bin/python predict.py --image photo.jpg` | prints detections, saves `photo_detected.jpg` |

Resume an interrupted training run: `train_vegetable_detector.py --resume`.

## Files

| File | Purpose |
|---|---|
| `config.py` | Dataset path, run dirs, device/batch/model selection, symlink view |
| `sanity_check.py` | Validates yaml + every label file, draws GT, test-runs the model |
| `train_vegetable_detector.py` | Training (pretrained nano YOLO, MPS, early stopping, plots) |
| `evaluate.py` | Test-split P/R/mAP, per-class AP, confusion matrix, confidence histogram |
| `visualize_predictions.py` | 20 annotated test predictions + contact sheet + GT-vs-pred sheet |
| `predict.py` | CLI + importable `detect()` for the future FastAPI endpoint |

Production candidate: `runs/pantrypilot/weights/best.pt` (PyTorch; no TFLite/CoreML export yet).

## Dataset preparation (combined Source A + Source B)

Scripts live in `dataprep/` (run from `ai/`, SSD must be mounted). Sources are read-only; output goes to
`/Volumes/Personal/Dataset(PantryPilot_AI)/PantryPilot_Combined_Dataset/` only.

```bash
.venv/bin/python dataprep/audit_source_a.py      # step 1
.venv/bin/python dataprep/audit_source_b.py      # step 2
.venv/bin/python dataprep/build_combined.py [--a-per-class 60] [--force]   # steps 3-8
.venv/bin/python dataprep/visualize_dataset.py   # step 9 charts + previews
.venv/bin/python dataprep/validate_dataset.py    # step 11 + final report
```

Reports are mirrored to `dataprep/reports/`. The baseline model in `runs/pantrypilot/` is untouched;
train the new model under a different run name.
