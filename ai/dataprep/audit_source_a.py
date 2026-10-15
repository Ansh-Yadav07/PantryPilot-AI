"""STEP 1 — Audit Source A (single-vegetable classification images). Read-only.

Usage:  python audit_source_a.py
Output: reports/audit_source_a.txt, reports/audit_source_a.json
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

import numpy as np

import common as C


def main() -> None:
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    root = C.SOURCE_A_ROOT
    print(f"Source A root: {root}")
    paths = C.list_images(root)
    print(f"  found {len(paths)} image files")
    recs = C.inspect_many(paths, "source_a")

    rows = []
    for p in paths:
        r = recs[str(p)]
        rel = p.relative_to(root).parts            # (orig_split, class_folder, file)
        r = dict(r, orig_split=rel[0], folder=rel[1],
                 cls=C.A_FOLDER_MAP.get(rel[1], f"UNMAPPED:{rel[1]}"))
        rows.append(r)

    # duplicates ---------------------------------------------------------------
    by_md5 = defaultdict(list)
    for r in rows:
        if r["valid"]:
            by_md5[r["md5"]].append(r)
    dup_groups = {k: v for k, v in by_md5.items() if len(v) > 1}
    exact_dup_extra = {id(r) for v in dup_groups.values() for r in v[1:]}      # extras beyond the first

    by_dh = defaultdict(list)
    for r in rows:
        if r["valid"]:
            by_dh[r["dhash"]].append(r)
    dh_groups = {k: v for k, v in by_dh.items() if len(v) > 1}

    print("  searching near-duplicates (dHash Hamming <= 4) ...", flush=True)
    items = [(r["path"], r["dhash"]) for r in rows if r["valid"]]
    near_pairs = C.near_duplicate_pairs(items, max_dist=4)
    path2row = {r["path"]: r for r in rows}
    cross_class = [(a, b, d) for a, b, d in near_pairs if path2row[a]["folder"] != path2row[b]["folder"]]
    cross_split = [(a, b, d) for a, b, d in near_pairs if path2row[a]["orig_split"] != path2row[b]["orig_split"]]

    # per class table ----------------------------------------------------------
    folders = sorted({r["folder"] for r in rows})
    table = []
    for f in folders:
        rs = [r for r in rows if r["folder"] == f]
        table.append({
            "folder": f, "class": C.A_FOLDER_MAP.get(f, "?"), "count": len(rs),
            "valid": sum(r["valid"] for r in rs),
            "invalid": sum(not r["valid"] for r in rs),
            "duplicate": sum(id(r) in exact_dup_extra for r in rs),
            "in_22_class_model": C.A_FOLDER_MAP.get(f) in C.CLASS_ID,
        })

    valid = [r for r in rows if r["valid"]]
    w = np.array([r["width"] for r in valid]); h = np.array([r["height"] for r in valid])
    dims = Counter(f"{r['width']}x{r['height']}" for r in valid)
    fmts = Counter(r["format"] for r in valid)
    exts = Counter(__import__("pathlib").Path(r["path"]).suffix.lower() for r in rows)
    modes = Counter(r["mode"] for r in valid)
    split_counts = Counter(r["orig_split"] for r in rows)

    summary = {
        "root": str(root),
        "total_images": len(rows), "valid": len(valid), "invalid": len(rows) - len(valid),
        "formats": dict(fmts), "extensions": dict(exts), "color_modes": dict(modes),
        "original_splits": dict(split_counts),
        "exact_duplicate_groups": len(dup_groups),
        "exact_duplicate_extra_files": len(exact_dup_extra),
        "identical_dhash_groups": len(dh_groups),
        "near_duplicate_pairs_hamming<=4": len(near_pairs),
        "near_duplicate_pairs_across_different_classes": len(cross_class),
        "near_duplicate_pairs_across_original_splits": len(cross_split),
        "width": {"min": int(w.min()), "max": int(w.max()), "mean": round(float(w.mean()), 1)} if len(w) else {},
        "height": {"min": int(h.min()), "max": int(h.max()), "mean": round(float(h.mean()), 1)} if len(h) else {},
        "top_dimensions": dims.most_common(8),
        "broccoli_images": sum(r["folder"] == "Broccoli" for r in rows),
        "invalid_examples": [{"path": r["path"], "error": r["error"]} for r in rows if not r["valid"]][:20],
        "per_class": table,
    }
    (C.REPORT_DIR / "audit_source_a.json").write_text(json.dumps(summary, indent=2))
    (C.REPORT_DIR / "source_a_near_dup_pairs.json").write_text(json.dumps(near_pairs[:5000]))

    L = []
    L.append("=" * 70); L.append("SOURCE A AUDIT — single-vegetable classification images"); L.append("=" * 70)
    L.append(f"Root                 : {root}")
    L.append(f"Total image files    : {len(rows)}")
    L.append(f"Valid / Invalid      : {len(valid)} / {len(rows) - len(valid)}  (corrupted or unreadable)")
    L.append(f"Extensions           : {dict(exts)}")
    L.append(f"Decoded formats      : {dict(fmts)}   color modes: {dict(modes)}")
    L.append(f"Original splits      : {dict(split_counts)}   (will be re-split by hash group)")
    L.append("")
    L.append("Dimensions")
    L.append(f"  width  min/max/mean: {summary['width']}")
    L.append(f"  height min/max/mean: {summary['height']}")
    L.append(f"  most common sizes  : {dims.most_common(5)}")
    L.append("")
    L.append("Duplicates")
    L.append(f"  exact (identical md5) groups      : {len(dup_groups)}  -> {len(exact_dup_extra)} redundant files")
    L.append(f"  identical perceptual-hash groups  : {len(dh_groups)}")
    L.append(f"  near-duplicate pairs (dHash<=4)   : {len(near_pairs)}")
    L.append(f"     of which across different classes : {len(cross_class)}  (label-noise risk)")
    L.append(f"     of which across original splits   : {len(cross_split)}  (leakage in the source's own split)")
    L.append("")
    L.append(f"{'Class folder':<14}{'-> class':<15}{'Image Count':>12}{'Valid':>8}{'Invalid':>9}{'Duplicate':>10}")
    L.append("-" * 70)
    for t in table:
        tag = "" if t["in_22_class_model"] else "   <-- NOT in 22-class taxonomy"
        L.append(f"{t['folder']:<14}{t['class']:<15}{t['count']:>12}{t['valid']:>8}{t['invalid']:>9}{t['duplicate']:>10}{tag}")
    L.append("-" * 70)
    L.append(f"{'TOTAL':<29}{len(rows):>12}{len(valid):>8}{len(rows)-len(valid):>9}{len(exact_dup_extra):>10}")
    L.append("")
    L.append(f"BROCCOLI images (reported separately, excluded from 22-class model): {summary['broccoli_images']}")
    if summary["invalid_examples"]:
        L.append("\nInvalid examples:")
        for e in summary["invalid_examples"]:
            L.append(f"  {e['path']}: {e['error']}")
    text = "\n".join(L)
    (C.REPORT_DIR / "audit_source_a.txt").write_text(text)
    print("\n" + text)


if __name__ == "__main__":
    main()
