"""STEPS 3-8 — Build the derived PantryPilot_Combined_Dataset.

Reads Source A + Source B (read-only), writes ONLY to COMBINED_DIR.

Policy summary
--------------
Source B (primary, true detection data)
  * Official split preserved: train->train, valid->val, test->test (no reshuffle).
  * VOC -> YOLO with clipping; exact-duplicate box lines removed; only boxes with
    xmax<=xmin or ymax<=ymin are rejected. Empty-annotation images kept as backgrounds.
  * Leakage protection (perceptual dHash <= 4 bits, plus exact md5):
      - val images that near-duplicate a TEST image are dropped from val
      - train images that near-duplicate a (remaining) val or any test image are
        dropped from train
    -> val/test are otherwise untouched.
Source A (supplemental, full-image boxes "c 0.5 0.5 1.0 1.0")
  * Broccoli is excluded from the 22-class model (counted, reported, kept in manifest).
  * Exact md5 duplicates collapsed; any image near-duplicating a Source B image is dropped.
  * Pool is re-split 80/10/10 per class BY NEAR-DUPLICATE GROUP (union-find), seed fixed.
  * Only a capped, class-balanced subset of the A *train* split goes into the combined
    training set (--a-per-class) so A cannot overwhelm B.
  * A's val/test splits are written to a SEPARATE holdout (source_a_holdout/) and are NOT
    mixed into combined val/test: full-image boxes would inflate detection metrics and
    break comparability with the baseline.

Usage:  python build_combined.py [--a-per-class 60] [--force]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

import common as C
from audit_source_b import SPLITS as B_SPLITS, parse_xml

B2FINAL = {"train": "train", "valid": "val", "test": "test"}


# ── small helpers ────────────────────────────────────────────────────────────
class UnionFind:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def convert_b(ann: dict, W: int, H: int) -> dict:
    """Pascal VOC objects -> YOLO lines with clipping + exact duplicate-box removal."""
    lines, seen = [], set()
    clipped = dup = invalid = 0
    for o in ann["objects"]:
        cid = C.CLASS_ID[C.B_NAME_MAP[o["name"]]]
        x0, y0, x1, y1 = o["xmin"], o["ymin"], o["xmax"], o["ymax"]
        cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if (cx0, cy0, cx1, cy1) != (x0, y0, x1, y1):
            clipped += 1
        if cx1 <= cx0 or cy1 <= cy0:
            invalid += 1
            continue
        xc, yc = (cx0 + cx1) / 2 / W, (cy0 + cy1) / 2 / H
        w, h = (cx1 - cx0) / W, (cy1 - cy0) / H
        line = f"{cid} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}"
        if line in seen:
            dup += 1
            continue
        seen.add(line)
        lines.append(line)
    return {"lines": lines, "clipped": clipped, "dup": dup, "invalid": invalid}


def safe_copy(src: Path, dst: Path) -> None:
    C.assert_writable_target(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)          # data only; source opened read-only


def write_text(path: Path, text: str) -> None:
    C.assert_writable_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def write_csv(path: Path, rows: list[dict]) -> None:
    C.assert_writable_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-per-class", type=int, default=60,
                    help="Max Source A train images per class added to combined train")
    ap.add_argument("--near-dist", type=int, default=4, help="dHash Hamming threshold for near-duplicates")
    ap.add_argument("--force", action="store_true", help="Rebuild: delete and recreate COMBINED_DIR only")
    args = ap.parse_args()

    out = C.COMBINED_DIR
    if out.exists() and any(out.iterdir()):
        if not args.force:
            raise SystemExit(f"{out} already exists. Re-run with --force to rebuild it (only this folder is deleted).")
        assert out == C.COMBINED_DIR
        C.assert_writable_target(out)
        shutil.rmtree(out)
    rng = random.Random(C.SEED)

    # ── load + hash everything ──────────────────────────────────────────────
    print("Loading images / hashes (cached) ...")
    a_paths = C.list_images(C.SOURCE_A_ROOT)
    a_info = C.inspect_many(a_paths, "source_a")
    b_items = []     # (split, stem, img_path, xml_path)
    for s in B_SPLITS:
        d = C.SOURCE_B_ROOT / s
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in C.IMG_EXTS and not p.name.startswith("._"):
                b_items.append((s, p.stem, p, d / f"{p.stem}.xml"))
    b_info = C.inspect_many([p for _, _, p, _ in b_items], "source_b")

    # ── near-duplicate graph over A+B ──────────────────────────────────────
    all_hash = [(str(p), a_info[str(p)]["dhash"]) for p in a_paths if a_info[str(p)]["valid"]]
    all_hash += [(str(p), b_info[str(p)]["dhash"]) for _, _, p, _ in b_items if b_info[str(p)]["valid"]]
    print(f"Searching near-duplicates among {len(all_hash)} images (<= {args.near_dist} bits) ...")
    pairs = C.near_duplicate_pairs(all_hash, max_dist=args.near_dist)
    src_of = {str(p): "A" for p in a_paths}
    split_of_b = {str(p): s for s, _, p, _ in b_items}
    nb: dict[str, set[str]] = defaultdict(set)
    for a, b, _ in pairs:
        nb[a].add(b)
        nb[b].add(a)

    # ── SOURCE B: official split + leakage protection ───────────────────────
    b_status = {}                                           # img path -> status
    drop_val = set()
    for p, split in split_of_b.items():
        if split == "valid" and any(split_of_b.get(q) == "test" for q in nb.get(p, ())):
            drop_val.add(p)
    drop_train = set()
    for p, split in split_of_b.items():
        if split == "train":
            for q in nb.get(p, ()):
                qs = split_of_b.get(q)
                if qs == "test" or (qs == "valid" and q not in drop_val):
                    drop_train.add(p)
                    break
    for p, split in split_of_b.items():
        if not b_info[p]["valid"]:
            b_status[p] = "dropped_corrupt"
        elif p in drop_val:
            b_status[p] = "dropped_leak_near_dup_of_test"
        elif p in drop_train:
            b_status[p] = "dropped_leak_near_dup_of_val_or_test"
        else:
            b_status[p] = "included"

    b_rows, b_final = [], defaultdict(list)                 # final split -> [(dest_stem, img, lines)]
    conv_totals = defaultdict(Counter)
    for split, stem, img, xml in b_items:
        info = b_info[str(img)]
        row = {"src_image": str(img), "src_xml": str(xml), "official_split": split,
               "status": b_status[str(img)], "final_split": "", "dest_name": "",
               "width": info["width"], "height": info["height"], "md5": info["md5"],
               "dhash": f"{info['dhash']:016x}", "n_objects": 0, "n_boxes_clipped": 0,
               "n_duplicate_boxes_removed": 0, "empty_label": ""}
        if b_status[str(img)] == "included":
            ann = parse_xml(xml)
            conv = convert_b(ann, info["width"], info["height"])
            dest = f"b_{stem}"
            row.update(final_split=B2FINAL[split], dest_name=dest + img.suffix.lower(),
                       n_objects=len(conv["lines"]), n_boxes_clipped=conv["clipped"],
                       n_duplicate_boxes_removed=conv["dup"], empty_label=int(not conv["lines"]))
            b_final[B2FINAL[split]].append((dest, img, conv["lines"]))
            for k in ("clipped", "dup", "invalid"):
                conv_totals[split][k] += conv[k]
            conv_totals[split]["objects"] += len(conv["lines"])
            conv_totals[split]["images"] += 1
            conv_totals[split]["empty"] += int(not conv["lines"])
        b_rows.append(row)

    # ── SOURCE A: dedupe, drop B-dups, group, split, cap ────────────────────
    a_rows = []
    a_recs = []
    for p in a_paths:
        info = a_info[str(p)]
        rel = p.relative_to(C.SOURCE_A_ROOT).parts
        a_recs.append({"path": str(p), "name": p.name, "folder": rel[1], "orig_split": rel[0],
                       "cls": C.A_FOLDER_MAP[rel[1]], "info": info})

    a_status = {}
    seen_md5 = {}
    for r in sorted(a_recs, key=lambda r: r["path"]):
        i = r["info"]
        if not i["valid"]:
            a_status[r["path"]] = "dropped_corrupt"
        elif r["cls"] in C.A_EXCLUDED_CLASSES:
            a_status[r["path"]] = "excluded_broccoli_not_in_22_class_taxonomy"
        elif i["md5"] in seen_md5:
            a_status[r["path"]] = "dropped_exact_duplicate"
        elif any(src_of.get(q) is None for q in nb.get(r["path"], ())):
            a_status[r["path"]] = "dropped_near_dup_of_source_b"
        else:
            a_status[r["path"]] = "candidate"
            seen_md5[i["md5"]] = r["path"]

    cand = [r for r in a_recs if a_status[r["path"]] == "candidate"]
    uf = UnionFind([r["path"] for r in cand])
    cand_set = {r["path"] for r in cand}
    for r in cand:
        for q in nb.get(r["path"], ()):
            if q in cand_set:
                uf.union(r["path"], q)
    group_of = {r["path"]: uf.find(r["path"]) for r in cand}

    a_split = {}
    group_stats = {}
    for cls in sorted({r["cls"] for r in cand}):
        members = [r for r in cand if r["cls"] == cls]
        groups = defaultdict(list)
        for r in members:
            groups[group_of[r["path"]]].append(r["path"])
        n = len(members)
        t_val, t_test = round(0.10 * n), round(0.10 * n)
        gl = sorted(groups.items())
        giants = [g for g in gl if len(g[1]) > 0.10 * n]        # too large to place in a 10% split
        rest = [g for g in gl if len(g[1]) <= 0.10 * n]
        rng.shuffle(rest)
        n_test = n_val = 0
        for _, ps in giants:
            for p in ps:
                a_split[p] = "train"
        for _, ps in rest:
            if n_test < t_test:
                tag = "test"; n_test += len(ps)
            elif n_val < t_val:
                tag = "val"; n_val += len(ps)
            else:
                tag = "train"
            for p in ps:
                a_split[p] = tag
        group_stats[cls] = {"images": n, "groups": len(groups),
                            "largest_group": max(len(v) for v in groups.values())}

    # cap supplemental A training images (class-balanced, prefer one-per-group first)
    a_train_sel = set()
    for cls in sorted({r["cls"] for r in cand}):
        pool = [r["path"] for r in cand if r["cls"] == cls and a_split[r["path"]] == "train"]
        rng.shuffle(pool)
        picked, used_groups, rest = [], set(), []
        for p in pool:
            if len(picked) < args.a_per_class and group_of[p] not in used_groups:
                picked.append(p); used_groups.add(group_of[p])
            else:
                rest.append(p)
        for p in rest:
            if len(picked) >= args.a_per_class:
                break
            picked.append(p)
        a_train_sel.update(picked)

    a_dest = {}
    for r in cand:
        p, cls = r["path"], r["cls"]
        sp = a_split[p]
        base = Path(r["name"]).stem
        stem = f"a_{cls}_{r['orig_split'][:2]}_{base}"
        if sp == "train":
            a_dest[p] = ("train" if p in a_train_sel else None, stem)
        else:
            a_dest[p] = (f"holdout_{sp}", stem)

    for r in a_recs:
        p = r["path"]; i = r["info"]
        st = a_status[p]
        if st == "candidate":
            sp = a_split[p]
            dest_split, stem = a_dest[p]
            if sp == "train":
                st = "included_train" if dest_split else "unused_train_pool_over_cap"
            else:
                st = f"holdout_{sp}"
        a_rows.append({
            "src_image": p, "source_folder": r["folder"], "class": r["cls"],
            "class_id": C.CLASS_ID.get(r["cls"], ""), "orig_split": r["orig_split"],
            "status": st, "assigned_split": a_split.get(p, ""),
            "group_id": group_of.get(p, "").split("/")[-1] if p in group_of else "",
            "dest_name": (a_dest[p][1] + ".jpg") if p in a_dest and a_dest[p][0] else "",
            "width": i["width"], "height": i["height"], "md5": i["md5"], "dhash": f"{i['dhash']:016x}",
            "label": "full-image box (synthetic): 0.5 0.5 1.0 1.0",
        })

    # ── WRITE dataset ───────────────────────────────────────────────────────
    print("Writing dataset ...")
    jobs = []   # (src, dst_img, dst_lbl, label_text)
    for split, items in b_final.items():
        for stem, img, lines in items:
            jobs.append((img, out / "images" / split / f"{stem}{img.suffix.lower()}",
                         out / "labels" / split / f"{stem}.txt", "\n".join(lines) + ("\n" if lines else "")))
    n_a_train = 0
    for r in cand:
        p = r["path"]
        dest_split, stem = a_dest[p]
        if dest_split is None:
            continue
        cid = C.CLASS_ID[r["cls"]]
        txt = f"{cid} 0.5 0.5 1.0 1.0\n"
        if dest_split == "train":
            n_a_train += 1
            jobs.append((Path(p), out / "images" / "train" / f"{stem}.jpg", out / "labels" / "train" / f"{stem}.txt", txt))
        else:
            sp = dest_split.replace("holdout_", "")
            jobs.append((Path(p), out / "source_a_holdout" / "images" / sp / f"{stem}.jpg",
                         out / "source_a_holdout" / "labels" / sp / f"{stem}.txt", txt))

    def _do(job):
        src, di, dl, txt = job
        safe_copy(src, di)
        write_text(dl, txt)

    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, _ in enumerate(ex.map(_do, jobs), 1):
            if i % 1000 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)

    # data.yaml (exact paths from the brief) + holdout yaml
    yml = {"train": str(out / "images" / "train"), "val": str(out / "images" / "val"),
           "test": str(out / "images" / "test"), "nc": 22, "names": list(C.CLASS_NAMES)}
    write_text(out / "data.yaml", yaml.safe_dump(yml, sort_keys=False, width=200))
    hold = {"path": str(out / "source_a_holdout"), "train": "images/val", "val": "images/val",
            "test": "images/test", "nc": 22, "names": list(C.CLASS_NAMES)}
    write_text(out / "data_source_a_holdout.yaml", yaml.safe_dump(hold, sort_keys=False, width=200))

    write_csv(out / "source_a" / "manifest.csv", a_rows)
    write_csv(out / "source_b" / "manifest.csv", b_rows)

    # ── stats from the files actually written ───────────────────────────────
    def count_split(img_dir: Path, lbl_dir: Path):
        imgs, objs, by_src_img, by_src_obj = Counter(), Counter(), {"a": Counter(), "b": Counter()}, {"a": Counter(), "b": Counter()}
        n_imgs = {"a": 0, "b": 0}
        for lp in sorted(lbl_dir.glob("*.txt")):
            src = "a" if lp.name.startswith("a_") else "b"
            n_imgs[src] += 1
            seen = set()
            for line in lp.read_text().splitlines():
                if line.strip():
                    c = int(line.split()[0])
                    objs[c] += 1; by_src_obj[src][c] += 1
                    seen.add(c)
            for c in seen:
                imgs[c] += 1; by_src_img[src][c] += 1
        return {"images": imgs, "objects": objs, "src_images": by_src_img, "src_objects": by_src_obj, "n": n_imgs}

    stats = {s: count_split(out / "images" / s, out / "labels" / s) for s in ("train", "val", "test")}
    hold_stats = {s: count_split(out / "source_a_holdout" / "images" / s, out / "source_a_holdout" / "labels" / s)
                  for s in ("val", "test") if (out / "source_a_holdout" / "labels" / s).exists()}

    # class_distribution.csv
    dist_rows = []
    for cid, name in enumerate(C.CLASS_NAMES):
        row = {"class_id": cid, "class": name}
        for s in ("train", "val", "test"):
            row[f"{s}_images"] = stats[s]["images"][cid]
            row[f"{s}_objects"] = stats[s]["objects"][cid]
        row["train_images_from_B"] = stats["train"]["src_images"]["b"][cid]
        row["train_images_from_A"] = stats["train"]["src_images"]["a"][cid]
        row["train_objects_from_B"] = stats["train"]["src_objects"]["b"][cid]
        row["train_objects_from_A"] = stats["train"]["src_objects"]["a"][cid]
        row["total_objects"] = sum(stats[s]["objects"][cid] for s in ("train", "val", "test"))
        row["holdoutA_val_images"] = hold_stats.get("val", {"images": Counter()})["images"][cid]
        row["holdoutA_test_images"] = hold_stats.get("test", {"images": Counter()})["images"][cid]
        dist_rows.append(row)
    write_csv(out / "class_distribution.csv", dist_rows)

    # underrepresentation (on combined TRAIN objects)
    tr_obj = [stats["train"]["objects"][c] for c in range(22)]
    med = sorted(tr_obj)[len(tr_obj) // 2]
    severe = [C.CLASS_NAMES[c] for c in range(22) if tr_obj[c] < 0.25 * med]
    moderate = [C.CLASS_NAMES[c] for c in range(22) if 0.25 * med <= tr_obj[c] < 0.5 * med]

    # ── reports ─────────────────────────────────────────────────────────────
    a_status_counts = Counter(r["status"] for r in a_rows)
    b_status_counts = Counter(r["status"] for r in b_rows)
    cross_pairs = Counter()
    for a, b, _ in pairs:
        sa = "A" if a in src_of else f"B-{split_of_b[a]}"
        sb = "A" if b in src_of else f"B-{split_of_b[b]}"
        cross_pairs["|".join(sorted((sa, sb)))] += 1
    build = {
        "a_per_class_cap": args.a_per_class, "near_dist": args.near_dist, "seed": C.SEED,
        "b_status": dict(b_status_counts), "a_status": dict(a_status_counts),
        "b_conversion": {s: dict(v) for s, v in conv_totals.items()},
        "near_dup_pair_counts_before_cleaning": dict(cross_pairs),
        "a_group_stats": group_stats,
        "counts": {s: {"images": sum(stats[s]["n"].values()), "from_A": stats[s]["n"]["a"],
                       "from_B": stats[s]["n"]["b"], "objects": sum(stats[s]["objects"].values())}
                   for s in stats},
        "holdout_A": {s: {"images": sum(v["n"].values()), "objects": sum(v["objects"].values())}
                      for s, v in hold_stats.items()},
        "underrepresented_severe": severe, "underrepresented_moderate": moderate,
        "median_train_objects_per_class": med,
        "broccoli_images": sum(1 for r in a_rows if r["status"].startswith("excluded_broccoli")),
    }
    write_text(out / "build_stats.json", json.dumps(build, indent=2))
    (C.REPORT_DIR / "build_stats.json").write_text(json.dumps(build, indent=2))
    print("\nBuild summary")
    print(json.dumps({k: build[k] for k in ("counts", "holdout_A", "b_status", "a_status",
                                            "underrepresented_severe", "underrepresented_moderate")}, indent=2))
    print(f"\nDataset written to {out}")


if __name__ == "__main__":
    main()
