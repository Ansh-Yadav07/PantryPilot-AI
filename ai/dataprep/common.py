"""Shared helpers for the PantryPilot dataset-preparation pipeline.

Safety rules enforced here:
  * Source datasets are READ-ONLY. Nothing in this package opens a source path
    for writing.
  * The only SSD directory ever written to is COMBINED_DIR (a brand-new folder).
    ``assert_writable_target`` refuses to write anywhere else on the SSD.
"""
from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageFile

# ── Paths ────────────────────────────────────────────────────────────────────
SSD_ROOT = Path("/Volumes/Personal/Dataset(PantryPilot_AI)")
SOURCE_A_ROOT = SSD_ROOT / "Vegetable Images 2"            # classification images
SOURCE_B_ROOT = SSD_ROOT / "Vegetable Object Detection Dataset from Bangladesh" / "Original Dataset"
OLD_CLEAN_DATASET = SSD_ROOT / "Vegetable Object Detection Dataset from Bangladesh" / "PantryPilot_Dataset"
COMBINED_DIR = SSD_ROOT / "PantryPilot_Combined_Dataset"

PREP_DIR = Path(__file__).resolve().parent                  # ai/dataprep
REPORT_DIR = PREP_DIR / "reports"                           # internal disk
CACHE_DIR = PREP_DIR / "cache"                              # internal disk

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SEED = 42

# ── Taxonomy ─────────────────────────────────────────────────────────────────
CLASS_NAMES = [
    "cucumber", "tomato", "green_beans", "lemon", "eggplant", "green_chilli",
    "turnip", "coriander", "pumpkin", "potato", "cauliflower", "green_papaya",
    "bitter_gourd", "carrot", "bottle_gourd", "capsicum", "beetroot", "cabbage",
    "spring_onion", "snake_gourd", "radish", "green_banana",
]
CLASS_ID = {n: i for i, n in enumerate(CLASS_NAMES)}

# Source B XML <name> -> PantryPilot class (exact strings from the brief)
B_NAME_MAP = {
    "Cucumber": "cucumber", "Tomato": "tomato", "Green Beans": "green_beans",
    "Lemon": "lemon", "Eggplant": "eggplant", "Green Chilli": "green_chilli",
    "Turnip": "turnip", "Coriander leaves": "coriander", "Pumpkin": "pumpkin",
    "Potato": "potato", "Cauliflower": "cauliflower", "Green Papaya": "green_papaya",
    "Bitter Gourd": "bitter_gourd", "Carrots": "carrot", "Bottle gourd": "bottle_gourd",
    "Capsicum": "capsicum", "Beetroot": "beetroot", "Cabbage": "cabbage",
    "Spring Onion": "spring_onion", "Snake gourd": "snake_gourd", "Radish": "radish",
    "Green Banana": "green_banana",
}

# Source A folder -> class. "broccoli" is deliberately NOT in CLASS_NAMES.
A_FOLDER_MAP = {
    "Bean": "green_beans", "Bitter_Gourd": "bitter_gourd", "Bottle_Gourd": "bottle_gourd",
    "Brinjal": "eggplant", "Broccoli": "broccoli", "Cabbage": "cabbage",
    "Capsicum": "capsicum", "Carrot": "carrot", "Cauliflower": "cauliflower",
    "Cucumber": "cucumber", "Papaya": "green_papaya", "Potato": "potato",
    "Pumpkin": "pumpkin", "Radish": "radish", "Tomato": "tomato",
}
A_EXCLUDED_CLASSES = {"broccoli"}   # reported separately, not in the 22-class model

ImageFile.LOAD_TRUNCATED_IMAGES = False  # truncated files must count as corrupted


# ── Safety ───────────────────────────────────────────────────────────────────
def assert_writable_target(path: Path) -> None:
    """Refuse to write anywhere on the SSD except inside COMBINED_DIR."""
    p = Path(os.path.abspath(path))
    if str(p).startswith(str(SSD_ROOT)):
        if not (p == COMBINED_DIR or COMBINED_DIR in p.parents):
            raise PermissionError(f"Refusing to write outside {COMBINED_DIR}: {p}")


# ── Hashing ──────────────────────────────────────────────────────────────────
def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dhash64(img: Image.Image) -> int:
    """64-bit difference hash (robust to resize / mild re-compression)."""
    g = img.convert("L").resize((9, 8), Image.LANCZOS)
    a = np.asarray(g, dtype=np.int16)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def inspect_image(path_str: str) -> dict:
    """Decode one image fully. Returns validity, size, md5 and dHash."""
    p = Path(path_str)
    rec = {"path": path_str, "size_bytes": 0, "valid": False, "error": "",
           "width": 0, "height": 0, "mode": "", "format": "", "md5": "", "dhash": 0}
    try:
        rec["size_bytes"] = p.stat().st_size
        rec["md5"] = md5_file(p)
        with Image.open(p) as im:
            rec["format"] = im.format or ""
            im.load()                      # force full decode -> detects truncation
            rec["width"], rec["height"] = im.size
            rec["mode"] = im.mode
            if rec["width"] < 2 or rec["height"] < 2:
                raise ValueError("degenerate image size")
            rec["dhash"] = dhash64(im)
        rec["valid"] = True
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"[:200]
    return rec


def inspect_many(paths: list[Path], cache_name: str, workers: int = 6) -> dict[str, dict]:
    """Inspect many images in parallel, with an on-disk cache keyed by path+size+mtime."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_name}.json"
    cache: dict = json.loads(cache_file.read_text()) if cache_file.exists() else {}

    todo, out = [], {}
    for p in paths:
        st = p.stat()
        key = f"{p}|{st.st_size}|{int(st.st_mtime)}"
        if key in cache:
            out[str(p)] = cache[key]
        else:
            todo.append((p, key))

    if todo:
        print(f"  hashing/validating {len(todo)} images ({len(out)} cached) ...", flush=True)
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = ex.map(inspect_image, [str(p) for p, _ in todo], chunksize=64)
            for i, ((p, key), rec) in enumerate(zip(todo, results), 1):
                cache[key] = rec
                out[str(p)] = rec
                if i % 2000 == 0:
                    print(f"    {i}/{len(todo)}", flush=True)
        cache_file.write_text(json.dumps(cache))
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def near_duplicate_pairs(items: list[tuple[str, int]], max_dist: int = 4) -> list[tuple[str, str, int]]:
    """All pairs with Hamming distance <= max_dist, via multi-index hashing.

    Pigeonhole: splitting 64 bits into (max_dist+1) chunks guarantees that any
    pair within max_dist differs in at most max_dist chunks, so at least one
    chunk matches exactly.
    """
    n_chunks = max_dist + 1
    bounds = np.linspace(0, 64, n_chunks + 1, dtype=int)
    buckets: list[dict[int, list[int]]] = [dict() for _ in range(n_chunks)]
    for idx, (_, h) in enumerate(items):
        for c in range(n_chunks):
            lo, hi = int(bounds[c]), int(bounds[c + 1])
            key = (h >> lo) & ((1 << (hi - lo)) - 1)
            buckets[c].setdefault(key, []).append(idx)

    seen: set[tuple[int, int]] = set()
    pairs = []
    for c in range(n_chunks):
        for members in buckets[c].values():
            if len(members) < 2 or len(members) > 400:   # skip degenerate flat-image buckets
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    if (a, b) in seen:
                        continue
                    seen.add((a, b))
                    d = hamming(items[a][1], items[b][1])
                    if d <= max_dist:
                        pairs.append((items[a][0], items[b][0], d))
    return pairs


def list_images(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() in IMG_EXTS and not p.name.startswith("._"))
