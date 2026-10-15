"""Shared configuration for the PantryPilot vegetable detector.

All scripts import paths from here so the dataset location is defined once.

Dataset safety
--------------
The cleaned dataset lives on an external SSD and must NOT be modified or copied.
Ultralytics normally writes ``labels/<split>.cache`` files next to the label
folders, which would write into the dataset directory. To prevent that, we build
a tiny *symlink view* of the dataset inside ``ai/data/``:

    ai/data/images/train -> <SSD>/images/train   (symlink, no copy)
    ai/data/labels/train -> <SSD>/labels/train   (symlink, no copy)
    ...

Ultralytics then resolves labels via ``ai/data/labels/...`` and stores its cache
files as ``ai/data/labels/train.cache`` on the internal disk. The SSD is only
ever read.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

# ── Paths ────────────────────────────────────────────────────────────────────
AI_DIR = Path(__file__).resolve().parent

DATASET_DIR = Path(
    "/Volumes/Personal/Dataset(PantryPilot_AI)/"
    "Vegetable Object Detection Dataset from Bangladesh/PantryPilot_Dataset"
)
SOURCE_DATA_YAML = DATASET_DIR / "data.yaml"

# Symlink view + derived yaml (internal disk, tiny)
DATA_VIEW_DIR = AI_DIR / "data"
VIEW_DATA_YAML = DATA_VIEW_DIR / "data.yaml"

RUNS_PROJECT = AI_DIR / "runs"
RUN_NAME = "pantrypilot"
RUN_DIR = RUNS_PROJECT / RUN_NAME
BEST_WEIGHTS = RUN_DIR / "weights" / "best.pt"

SPLITS = ("train", "val", "test")

# Default lightweight checkpoints, in order of preference. The first one that
# the installed Ultralytics version can load is used.
PREFERRED_MODELS = ("yolo26n.pt", "yolo11n.pt", "yolov8n.pt")


def load_source_yaml() -> dict:
    """Read the dataset's own data.yaml (read-only)."""
    if not SOURCE_DATA_YAML.exists():
        raise FileNotFoundError(
            f"data.yaml not found at {SOURCE_DATA_YAML}. Is the external SSD mounted?"
        )
    with open(SOURCE_DATA_YAML) as f:
        return yaml.safe_load(f)


def class_names() -> dict[int, str]:
    names = load_source_yaml()["names"]
    if isinstance(names, list):
        names = dict(enumerate(names))
    return {int(k): v for k, v in names.items()}


def ensure_data_view() -> Path:
    """Create (idempotently) the symlink view and return the derived data.yaml path."""
    src = load_source_yaml()
    for kind in ("images", "labels"):
        (DATA_VIEW_DIR / kind).mkdir(parents=True, exist_ok=True)
        for split in SPLITS:
            target = DATASET_DIR / kind / split
            link = DATA_VIEW_DIR / kind / split
            if not target.is_dir():
                raise FileNotFoundError(f"Missing dataset folder: {target}")
            if link.is_symlink() and Path(os.readlink(link)) == target:
                continue
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(target, target_is_directory=True)

    view = {
        "path": str(DATA_VIEW_DIR),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": src["nc"],
        "names": class_names(),
    }
    with open(VIEW_DATA_YAML, "w") as f:
        yaml.safe_dump(view, f, sort_keys=False)
    return VIEW_DATA_YAML


def pick_device() -> str:
    """Prefer Apple Metal (MPS), fall back to CPU. CUDA is not assumed."""
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def auto_batch_size() -> int:
    """Pick a batch size from total unified memory (Ultralytics AutoBatch is CUDA-only)."""
    try:
        mem_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3
    except (ValueError, OSError):
        mem_gb = 8
    if mem_gb <= 8.5:
        return 8
    if mem_gb <= 16.5:
        return 16
    return 32


def resolve_model(name: str | None = None) -> str:
    """Return a loadable pretrained checkpoint name."""
    from ultralytics import YOLO

    candidates = (name,) if name else PREFERRED_MODELS
    last_err = None
    for cand in candidates:
        try:
            YOLO(cand)  # downloads pretrained weights if needed
            return cand
        except Exception as e:  # noqa: BLE001 - try next candidate
            last_err = e
    raise RuntimeError(f"Could not load any of {candidates}: {last_err}")
