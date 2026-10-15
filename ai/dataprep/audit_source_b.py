"""STEP 2 — Audit Source B (Bangladesh Pascal-VOC detection dataset). Read-only.

Also analyses leakage between the OFFICIAL splits (exact + near-duplicate images,
and adjacent video frames), and where the old baseline's random split came from.

Usage:  python audit_source_b.py
Output: reports/audit_source_b.txt, reports/audit_source_b.json
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import common as C

SPLITS = ("train", "valid", "test")
FRAME_RE = re.compile(r"^(?P<video>.+?)_mp4-(?P<frame>\d+)_jpg")


def parse_xml(path: Path) -> dict:
    """Parse one VOC file. Never raises; returns {'error': ...} on malformed XML."""
    try:
        root = ET.parse(path).getroot()
        size = root.find("size")
        w = int(float(size.findtext("width"))) if size is not None else 0
        h = int(float(size.findtext("height"))) if size is not None else 0
        objs = []
        for o in root.findall("object"):
            bb = o.find("bndbox")
            objs.append({
                "name": (o.findtext("name") or "").strip(),
                "xmin": float(bb.findtext("xmin")), "ymin": float(bb.findtext("ymin")),
                "xmax": float(bb.findtext("xmax")), "ymax": float(bb.findtext("ymax")),
            })
        return {"w": w, "h": h, "filename": (root.findtext("filename") or "").strip(), "objects": objs}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"[:160]}


def main() -> None:
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    root = C.SOURCE_B_ROOT
    print(f"Source B root: {root}")

    per_split: dict[str, dict] = {}
    all_img_paths: list[Path] = []
    records: list[dict] = []          # one per (image or xml stem)

    for s in SPLITS:
        d = root / s
        imgs = {p.stem: p for p in d.iterdir() if p.suffix.lower() in C.IMG_EXTS and not p.name.startswith("._")}
        xmls = {p.stem: p for p in d.iterdir() if p.suffix.lower() == ".xml" and not p.name.startswith("._")}
        stems = sorted(set(imgs) | set(xmls))
        per_split[s] = {"images": len(imgs), "xml": len(xmls),
                        "missing_xml": sorted(set(imgs) - set(xmls)),
                        "missing_image": sorted(set(xmls) - set(imgs))}
        all_img_paths += list(imgs.values())
        for st in stems:
            records.append({"split": s, "stem": st, "img": imgs.get(st), "xml": xmls.get(st)})

    print(f"  validating {len(all_img_paths)} images ...")
    img_info = C.inspect_many(all_img_paths, "source_b")

    # parse annotations ---------------------------------------------------------
    stats = {s: defaultdict(int) for s in SPLITS}
    obj_per_class = {s: Counter() for s in SPLITS}
    obj_counts = {s: [] for s in SPLITS}
    unknown_names = Counter()
    malformed, size_mismatch, bad_boxes, clipped_examples = [], [], [], []

    for r in records:
        s = r["split"]
        if r["xml"] is None:
            continue
        ann = parse_xml(r["xml"])
        r["ann"] = ann
        if "error" in ann:
            stats[s]["malformed_xml"] += 1
            malformed.append((str(r["xml"]), ann["error"]))
            continue
        info = img_info.get(str(r["img"])) if r["img"] else None
        W, H = (info["width"], info["height"]) if info and info["valid"] else (ann["w"], ann["h"])
        if info and info["valid"] and (ann["w"], ann["h"]) != (W, H):
            stats[s]["xml_size_mismatch"] += 1
            size_mismatch.append((r["stem"], (ann["w"], ann["h"]), (W, H)))
        n_valid = 0
        for o in ann["objects"]:
            cls = C.B_NAME_MAP.get(o["name"])
            if cls is None:
                unknown_names[o["name"]] += 1
                stats[s]["unknown_class_objects"] += 1
                continue
            xmin, ymin, xmax, ymax = o["xmin"], o["ymin"], o["xmax"], o["ymax"]
            outside = xmin < 0 or ymin < 0 or xmax > W or ymax > H
            cx0, cy0, cx1, cy1 = max(0, xmin), max(0, ymin), min(W, xmax), min(H, ymax)
            if cx1 <= cx0 or cy1 <= cy0:
                stats[s]["invalid_boxes"] += 1
                bad_boxes.append((r["stem"], o["name"], (xmin, ymin, xmax, ymax), (W, H)))
                continue
            if outside:
                stats[s]["boxes_outside_image"] += 1
            obj_per_class[s][cls] += 1
            n_valid += 1
        stats[s]["objects_valid"] += n_valid
        obj_counts[s].append(n_valid)
        if n_valid == 0:
            stats[s]["empty_annotations"] += 1
        if n_valid > 1:
            stats[s]["multi_object_images"] += 1

    # frame-level leakage between official splits -------------------------------
    frames = {s: defaultdict(list) for s in SPLITS}
    for r in records:
        m = FRAME_RE.match(r["stem"])
        if m and r["img"]:
            frames[r["split"]][m["video"]].append(int(m["frame"]))
    videos = {s: set(frames[s]) for s in SPLITS}
    shared_videos = {
        "train&valid": len(videos["train"] & videos["valid"]),
        "train&test": len(videos["train"] & videos["test"]),
        "valid&test": len(videos["valid"] & videos["test"]),
        "videos_per_split": {s: len(videos[s]) for s in SPLITS},
    }
    gaps = {}
    for s in ("valid", "test"):
        g = []
        for v, fl in frames[s].items():
            tr = np.array(sorted(frames["train"].get(v, [])))
            for f in fl:
                if len(tr):
                    g.append(int(np.min(np.abs(tr - f))))
        gaps[s] = g

    # exact + near duplicates across official splits ----------------------------
    valid_imgs = [(str(p), img_info[str(p)]) for p in all_img_paths if img_info[str(p)]["valid"]]
    split_of = {str(r["img"]): r["split"] for r in records if r["img"]}
    by_md5 = defaultdict(list)
    for p, i in valid_imgs:
        by_md5[i["md5"]].append(p)
    exact_groups = [v for v in by_md5.values() if len(v) > 1]
    exact_cross = [g for g in exact_groups if len({split_of[p] for p in g}) > 1]

    print("  searching near-duplicates (dHash<=4) ...")
    near = C.near_duplicate_pairs([(p, i["dhash"]) for p, i in valid_imgs], max_dist=4)
    near_cross = Counter()
    for a, b, d in near:
        near_cross[tuple(sorted((split_of[a], split_of[b])))] += 1

    # old baseline split provenance ----------------------------------------------
    old = {}
    if C.OLD_CLEAN_DATASET.exists():
        name_to_split = {Path(p).name: split_of[p] for p in split_of}
        for s in ("train", "val", "test"):
            d = C.OLD_CLEAN_DATASET / "images" / s
            names = [p.name for p in d.iterdir() if p.suffix.lower() in C.IMG_EXTS]
            old[s] = {"n": len(names),
                      "from_official": dict(Counter(name_to_split.get(n, "NOT FOUND") for n in names))}

    # summary ---------------------------------------------------------------------
    total_obj = Counter()
    for s in SPLITS:
        total_obj += obj_per_class[s]
    all_counts = [c for s in SPLITS for c in obj_counts[s]]
    summary = {
        "root": str(root),
        "per_split": {s: {
            "images": per_split[s]["images"], "xml": per_split[s]["xml"],
            "missing_xml": len(per_split[s]["missing_xml"]),
            "missing_image": len(per_split[s]["missing_image"]),
            "corrupt_images": sum(1 for p in all_img_paths if split_of.get(str(p)) == s and not img_info[str(p)]["valid"]),
            "malformed_xml": stats[s]["malformed_xml"],
            "valid_objects": stats[s]["objects_valid"],
            "images_with_multiple_objects": stats[s]["multi_object_images"],
            "empty_annotations": stats[s]["empty_annotations"],
            "invalid_boxes": stats[s]["invalid_boxes"],
            "boxes_outside_image": stats[s]["boxes_outside_image"],
            "xml_size_mismatch": stats[s]["xml_size_mismatch"],
            "unknown_class_objects": stats[s]["unknown_class_objects"],
            "objects_per_image": {"min": int(min(obj_counts[s])) if obj_counts[s] else 0,
                                  "max": int(max(obj_counts[s])) if obj_counts[s] else 0,
                                  "mean": round(float(np.mean(obj_counts[s])), 2) if obj_counts[s] else 0},
        } for s in SPLITS},
        "num_classes_found": len(total_obj),
        "unknown_class_names": dict(unknown_names),
        "objects_per_class": {s: dict(obj_per_class[s]) for s in SPLITS},
        "objects_per_class_total": dict(total_obj),
        "objects_per_image_overall": {"min": int(min(all_counts)), "max": int(max(all_counts)),
                                      "mean": round(float(np.mean(all_counts)), 2)},
        "exact_duplicate_groups": len(exact_groups),
        "exact_duplicate_groups_across_splits": len(exact_cross),
        "near_duplicate_pairs": len(near),
        "near_duplicate_pairs_by_split_pair": {f"{a}|{b}": n for (a, b), n in near_cross.items()},
        "video_overlap": shared_videos,
        "nearest_train_frame_gap": {s: {"n": len(g), "median": float(np.median(g)) if g else None,
                                        "pct_within_5_frames": round(100 * float(np.mean(np.array(g) <= 5)), 1) if g else None}
                                    for s, g in gaps.items()},
        "old_baseline_split_provenance": old,
        "malformed_examples": malformed[:10], "invalid_box_examples": bad_boxes[:10],
        "size_mismatch_examples": size_mismatch[:10],
    }
    (C.REPORT_DIR / "audit_source_b.json").write_text(json.dumps(summary, indent=2, default=str))

    L = []
    L.append("=" * 72); L.append("SOURCE B AUDIT — Bangladesh multi-object detection dataset"); L.append("=" * 72)
    L.append(f"Root: {root}\n")
    hdr = f"{'':<30}" + "".join(f"{s:>10}" for s in SPLITS)
    L.append(hdr)
    def row(label, key):
        L.append(f"{label:<30}" + "".join(f"{summary['per_split'][s][key]:>10}" for s in SPLITS))
    for lab, key in [("images", "images"), ("xml files", "xml"), ("missing xml", "missing_xml"),
                     ("missing image", "missing_image"), ("corrupt images", "corrupt_images"),
                     ("malformed xml", "malformed_xml"), ("valid objects", "valid_objects"),
                     ("images w/ multiple objects", "images_with_multiple_objects"),
                     ("empty annotations", "empty_annotations"), ("invalid boxes (xmax<=xmin..)", "invalid_boxes"),
                     ("boxes outside image (clip)", "boxes_outside_image"),
                     ("xml size != image size", "xml_size_mismatch"), ("unknown class objects", "unknown_class_objects")]:
        row(lab, key)
    for lab, k in [("objects/image min", "min"), ("objects/image max", "max"), ("objects/image mean", "mean")]:
        L.append(f"{lab:<30}" + "".join(f"{summary['per_split'][s]['objects_per_image'][k]:>10}" for s in SPLITS))
    L.append(f"\nClasses found: {summary['num_classes_found']}   unknown XML names: {dict(unknown_names) or 'none'}")
    L.append(f"Overall objects/image: {summary['objects_per_image_overall']}")
    L.append("\nObjects per class")
    L.append(f"{'class':<15}" + "".join(f"{s:>9}" for s in SPLITS) + f"{'total':>9}")
    for c in C.CLASS_NAMES:
        L.append(f"{c:<15}" + "".join(f"{obj_per_class[s][c]:>9}" for s in SPLITS) + f"{total_obj[c]:>9}")
    L.append(f"{'TOTAL':<15}" + "".join(f"{sum(obj_per_class[s].values()):>9}" for s in SPLITS) + f"{sum(total_obj.values()):>9}")

    L.append("\nLEAKAGE BETWEEN OFFICIAL SPLITS")
    L.append(f"  exact duplicate groups            : {len(exact_groups)} (crossing splits: {len(exact_cross)})")
    L.append(f"  near-duplicate pairs (dHash<=4)   : {len(near)}  by split pair: {dict(near_cross)}")
    L.append(f"  videos per split                  : {shared_videos['videos_per_split']}")
    L.append(f"  videos shared train&valid/test    : {shared_videos['train&valid']} / {shared_videos['train&test']}")
    for s in ("valid", "test"):
        g = summary["nearest_train_frame_gap"][s]
        L.append(f"  {s}: median gap to nearest TRAIN frame of same video = {g['median']} frames; "
                 f"{g['pct_within_5_frames']}% within 5 frames")
    if old:
        L.append("\nOLD BASELINE SPLIT PROVENANCE (PantryPilot_Dataset -> official split of each image)")
        for s, v in old.items():
            L.append(f"  old {s:<5} ({v['n']} imgs) came from official: {v['from_official']}")
    text = "\n".join(L)
    (C.REPORT_DIR / "audit_source_b.txt").write_text(text)
    print("\n" + text)


if __name__ == "__main__":
    main()
