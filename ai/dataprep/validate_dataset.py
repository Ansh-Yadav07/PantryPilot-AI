"""STEP 11/12 — Full validation of the combined dataset + final report.

Checks (all must pass):
  1. every image has a label file and vice-versa (combined splits + Source A holdout)
  2. labels well-formed: 5 fields, valid class id, finite coords in [0,1], w/h > 0
  3. manifests point at files that exist; copied files are byte-identical to sources (md5)
  4. no exact or near duplicates (dHash<=4) across train/val/test/holdouts
  5. Source B official split preserved (membership of every val/test/train image)
  6. Source B labels equal an independent re-conversion from the XML
  7. Source A labels are exactly the full-image box with the class of its folder
  8. class IDs / names in data.yaml match the taxonomy; broccoli absent
  9. Ultralytics loads every image+label pair (verify_image_label) and parses data.yaml

Then appends the validation result + final summary to dataset_report.txt and prints the banner.
Usage: python validate_dataset.py
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

import common as C
from audit_source_b import parse_xml
from build_combined import convert_b

OUT = C.COMBINED_DIR
SETS = {  # name -> (images dir, labels dir)
    "train": (OUT / "images" / "train", OUT / "labels" / "train"),
    "val": (OUT / "images" / "val", OUT / "labels" / "val"),
    "test": (OUT / "images" / "test", OUT / "labels" / "test"),
    "A_holdout_val": (OUT / "source_a_holdout" / "images" / "val", OUT / "source_a_holdout" / "labels" / "val"),
    "A_holdout_test": (OUT / "source_a_holdout" / "images" / "test", OUT / "source_a_holdout" / "labels" / "test"),
}


def main() -> None:
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")

    a_rows = list(csv.DictReader(open(OUT / "source_a" / "manifest.csv")))
    b_rows = list(csv.DictReader(open(OUT / "source_b" / "manifest.csv")))
    build = json.loads((OUT / "build_stats.json").read_text())

    # 1+2 pairing and label format ------------------------------------------------
    files: dict[str, list[tuple[Path, Path]]] = {}
    bad_fmt, missing_lbl, missing_img, nan_vals, bad_cls, bad_range, bad_wh = [], [], [], 0, 0, 0, 0
    label_class_counts: dict[str, Counter] = {}
    for sname, (idir, ldir) in SETS.items():
        imgs = {p.stem: p for p in idir.iterdir() if p.suffix.lower() in C.IMG_EXTS}
        lbls = {p.stem: p for p in ldir.glob("*.txt")}
        missing_lbl += [str(imgs[s]) for s in set(imgs) - set(lbls)]
        missing_img += [str(lbls[s]) for s in set(lbls) - set(imgs)]
        files[sname] = [(imgs[s], lbls[s]) for s in sorted(set(imgs) & set(lbls))]
        label_class_counts[sname] = Counter()
        for _, lp in files[sname]:
            for line in lp.read_text().splitlines():
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) != 5:
                    bad_fmt.append(str(lp)); continue
                try:
                    c = int(parts[0]); v = [float(x) for x in parts[1:]]
                except ValueError:
                    bad_fmt.append(str(lp)); continue
                if any(math.isnan(x) or math.isinf(x) for x in v):
                    nan_vals += 1; continue
                if not 0 <= c < 22: bad_cls += 1
                if any(not 0.0 <= x <= 1.0 for x in v): bad_range += 1
                if v[2] <= 0 or v[3] <= 0: bad_wh += 1
                label_class_counts[sname][c] += 1
    n_imgs = {k: len(v) for k, v in files.items()}
    check("every image has a label file", not missing_lbl, f"missing labels: {len(missing_lbl)}")
    check("every label has an image", not missing_img, f"orphan labels: {len(missing_img)}")
    check("labels well-formed (5 fields)", not bad_fmt, f"malformed: {len(bad_fmt)}")
    check("no NaN/inf coordinates", nan_vals == 0, f"nan: {nan_vals}")
    check("class ids within 0..21", bad_cls == 0, f"bad: {bad_cls}")
    check("coordinates within [0,1]", bad_range == 0, f"out of range: {bad_range}")
    check("box width/height > 0", bad_wh == 0, f"degenerate: {bad_wh}")

    # 3 manifests + byte-identical copies -----------------------------------------
    dest_rows = []   # (set, dest_path, src_md5, src_dhash, source, src_path)
    missing_dest = 0
    final_dir_of = {"train": "train", "val": "val", "test": "test"}
    for r in b_rows:
        if r["status"] == "included":
            sp = r["final_split"]
            dest_rows.append((sp, SETS[sp][0] / r["dest_name"], r["md5"], int(r["dhash"], 16), "B", r["src_image"]))
    for r in a_rows:
        st = r["status"]
        if st == "included_train":
            dest_rows.append(("train", SETS["train"][0] / r["dest_name"], r["md5"], int(r["dhash"], 16), "A", r["src_image"]))
        elif st in ("holdout_val", "holdout_test"):
            sp = "A_" + st
            dest_rows.append((sp, SETS[sp][0] / r["dest_name"], r["md5"], int(r["dhash"], 16), "A", r["src_image"]))
    for d in dest_rows:
        if not d[1].exists():
            missing_dest += 1
    check("manifest entries all exist on disk", missing_dest == 0, f"missing: {missing_dest}")
    set_totals = Counter(d[0] for d in dest_rows)
    check("manifest counts == files on disk",
          all(set_totals[k] == n_imgs[k] for k in SETS), f"{dict(set_totals)} vs {n_imgs}")

    def _md5_ok(d):
        return C.md5_file(d[1]) == d[2]
    with ThreadPoolExecutor(max_workers=8) as ex:
        md5_bad = sum(not ok for ok in ex.map(_md5_ok, dest_rows))
    check("copied images byte-identical to sources (md5)", md5_bad == 0, f"mismatches: {md5_bad}")

    # 4 duplicates across splits ----------------------------------------------------
    by_md5 = defaultdict(set)
    for d in dest_rows:
        by_md5[d[2]].add(d[0])
    exact_cross = sum(1 for s in by_md5.values() if len(s) > 1)
    check("no exact duplicates across splits", exact_cross == 0, f"groups crossing splits: {exact_cross}")
    items = [(str(d[1]), d[3]) for d in dest_rows]
    split_of = {str(d[1]): d[0] for d in dest_rows}
    pairs = C.near_duplicate_pairs(items, max_dist=4)
    cross = [(a, b, dist) for a, b, dist in pairs if split_of[a] != split_of[b]]
    within = len(pairs) - len(cross)
    check("no near-duplicates (dHash<=4) across splits", not cross,
          f"crossing: {len(cross)}   (same-split near-dups, harmless: {within})")

    # 5 official split preserved ----------------------------------------------------
    official = {s: {p.stem for p in (C.SOURCE_B_ROOT / s).iterdir() if p.suffix.lower() in C.IMG_EXTS}
                for s in ("train", "valid", "test")}
    wrong = 0
    for r in b_rows:
        if r["status"] == "included":
            stem = Path(r["dest_name"]).stem[2:]
            want = {"train": "train", "valid": "val", "test": "test"}[r["official_split"]]
            if stem not in official[r["official_split"]] or r["final_split"] != want:
                wrong += 1
    check("Source B official split preserved (no reshuffle)", wrong == 0, f"misplaced: {wrong}")
    dropped = Counter((r["official_split"], r["status"]) for r in b_rows if r["status"] != "included")
    check("official TEST split fully intact", n_imgs["test"] == len(official["test"]),
          f"{n_imgs['test']}/{len(official['test'])}")
    check("official VAL: only leakage-flagged images removed",
          n_imgs["val"] + dropped.get(("valid", "dropped_leak_near_dup_of_test"), 0) == len(official["valid"]),
          f"{n_imgs['val']} kept, {dropped.get(('valid','dropped_leak_near_dup_of_test'),0)} removed of {len(official['valid'])}")
    check("official TRAIN: only leakage-flagged images removed",
          sum(1 for r in b_rows if r["official_split"] == "train" and r["status"] == "included")
          + dropped.get(("train", "dropped_leak_near_dup_of_val_or_test"), 0) == len(official["train"]),
          f"{dropped.get(('train','dropped_leak_near_dup_of_val_or_test'),0)} removed of {len(official['train'])}")

    # 6 Source B labels == independent re-conversion --------------------------------
    mism = 0
    for r in b_rows:
        if r["status"] != "included":
            continue
        ann = parse_xml(Path(r["src_xml"]))
        conv = convert_b(ann, int(r["width"]), int(r["height"]))
        lp = SETS[r["final_split"]][1] / (Path(r["dest_name"]).stem + ".txt")
        got = [l for l in lp.read_text().splitlines() if l.strip()]
        if got != conv["lines"]:
            mism += 1
    check("Source B labels match independent XML re-conversion", mism == 0, f"mismatching files: {mism}")

    # 7 Source A labels --------------------------------------------------------------
    a_bad = 0
    for r in a_rows:
        st = r["status"]
        if st in ("included_train", "holdout_val", "holdout_test"):
            sp = "train" if st == "included_train" else "A_" + st
            lp = SETS[sp][1] / (Path(r["dest_name"]).stem + ".txt")
            if lp.read_text().strip() != f"{r['class_id']} 0.5 0.5 1.0 1.0":
                a_bad += 1
    check("Source A labels = full-image box with correct class", a_bad == 0, f"bad: {a_bad}")

    # 8 yaml --------------------------------------------------------------------------
    y = yaml.safe_load((OUT / "data.yaml").read_text())
    names = y["names"] if isinstance(y["names"], list) else [y["names"][i] for i in sorted(y["names"])]
    check("data.yaml: nc=22 and names match taxonomy", y["nc"] == 22 and names == C.CLASS_NAMES, f"nc={y['nc']}")
    check("data.yaml paths exist", all(Path(y[k]).is_dir() for k in ("train", "val", "test")), "")
    check("broccoli not in model classes / labels", "broccoli" not in names and all(
        max(c.keys(), default=0) < 22 for c in label_class_counts.values()), "")

    # 9 Ultralytics ---------------------------------------------------------------------
    from ultralytics.data.utils import check_det_dataset, verify_image_label
    try:
        d = check_det_dataset(str(OUT / "data.yaml"), autodownload=False)
        check("Ultralytics check_det_dataset parses data.yaml", d["nc"] == 22 and len(d["names"]) == 22,
              f"nc={d['nc']}")
    except Exception as e:  # noqa: BLE001
        check("Ultralytics check_det_dataset parses data.yaml", False, str(e)[:120])
    ul = Counter()
    for sname in SETS:
        args = [(str(ip), str(lp), f"{sname}: ", False, 22, 0, 2, False) for ip, lp in files[sname]]
        with ThreadPoolExecutor(max_workers=8) as ex:
            for res in ex.map(verify_image_label, args):
                nm, nf, ne, nc = res[5], res[6], res[7], res[8]
                ul["missing"] += nm; ul["found"] += nf; ul["empty"] += ne; ul["corrupt"] += nc
    check("Ultralytics loads every image+label pair", ul["corrupt"] == 0 and ul["missing"] == 0,
          f"found={ul['found']} empty(background)={ul['empty']} corrupt={ul['corrupt']} missing={ul['missing']}")

    all_pass = all(ok for _, ok, _ in results)

    # ── final report ------------------------------------------------------------------
    a_audit = json.loads((C.REPORT_DIR / "audit_source_a.json").read_text())
    b_audit = json.loads((C.REPORT_DIR / "audit_source_b.json").read_text())
    cnt = build["counts"]
    dist = list(csv.DictReader(open(OUT / "class_distribution.csv")))
    bc = build["b_conversion"]
    near_before = build["near_dup_pair_counts_before_cleaning"]
    gaps = b_audit["nearest_train_frame_gap"]

    L = []
    L.append("=" * 56); L.append("PANTRYPILOT DATASET READY" if all_pass else "PANTRYPILOT DATASET — VALIDATION FAILED"); L.append("=" * 56)
    L.append("\nSource A (single-vegetable classification images, supplemental):")
    L.append(f"  images: {a_audit['total_images']}   classes: 15 folders -> 14 in the 22-class model + broccoli")
    L.append(f"  valid: {a_audit['valid']}   invalid: {a_audit['invalid']}   exact duplicates: {a_audit['exact_duplicate_extra_files']}"
             f"   near-dup pairs: {a_audit['near_duplicate_pairs_hamming<=4']}")
    L.append(f"  broccoli (excluded, kept in manifest): {build['broccoli_images']}")
    L.append(f"  resolution: 224x224 (Source B is 640x360)")
    a_st = build["a_status"]
    L.append(f"  pooled & re-split by near-dup group 80/10/10 -> train pool {a_st.get('included_train',0)+a_st.get('unused_train_pool_over_cap',0)}, "
             f"val {a_st.get('holdout_val',0)}, test {a_st.get('holdout_test',0)}")
    L.append(f"  used in combined train (cap {build['a_per_class_cap']}/class): {a_st.get('included_train',0)}")
    L.append("\nSource B (Bangladesh detection data, primary):")
    L.append(f"  official images  train/val/test: {b_audit['per_split']['train']['images']} / {b_audit['per_split']['valid']['images']} / {b_audit['per_split']['test']['images']}")
    L.append(f"  classes: {b_audit['num_classes_found']}   objects: {sum(b_audit['objects_per_class_total'].values())}"
             f"   avg objects/image: {b_audit['objects_per_image_overall']['mean']}")
    L.append(f"  boxes clipped: train {bc['train']['clipped']}, valid {bc['valid']['clipped']}, test {bc['test']['clipped']}"
             f"   exact-duplicate boxes removed: {sum(bc[s]['dup'] for s in bc)}   invalid boxes rejected: {sum(bc[s]['invalid'] for s in bc)}")
    L.append(f"  empty-annotation images kept as background: {sum(bc[s]['empty'] for s in bc)}")
    L.append(f"  leakage cleaning: removed {build['b_status'].get('dropped_leak_near_dup_of_val_or_test',0)} train and "
             f"{build['b_status'].get('dropped_leak_near_dup_of_test',0)} val images that near-duplicate val/test images")
    L.append("\nCombined:")
    for s in ("train", "val", "test"):
        c = cnt[s]
        L.append(f"  {s:<5}: {c['images']:>5} images ({c['from_B']} from B, {c['from_A']} from A)   {c['objects']:>6} objects")
    for s, v in build["holdout_A"].items():
        L.append(f"  Source-A-only holdout {s}: {v['images']} images (separate; NOT in combined val/test)")
    L.append("\nClass distribution (combined)   images train/val/test | objects train(B+A)/val/test")
    for r in dist:
        L.append(f"  {r['class']:<13} {r['train_images']:>5}/{r['val_images']:>4}/{r['test_images']:>4} | "
                 f"{r['train_objects']:>5} ({r['train_objects_from_B']}+{r['train_objects_from_A']})/{r['val_objects']:>4}/{r['test_objects']:>4}")
    L.append("\nPotential problems:")
    L.append(f"  1. FRAME-LEVEL LEAKAGE IN THE OFFICIAL SPLIT: all {b_audit['video_overlap']['videos_per_split']['train']} train videos are also in val/test;"
             f" {gaps['test']['pct_within_5_frames']}% of test frames are within 5 frames of a train frame (median gap {gaps['test']['median']}).")
    L.append("     Official val/test scores will be OPTIMISTIC versus real phone/fridge photos. Remaining near-duplicate pairs "
             "were only removed at <=4 dHash bits; adjacent video frames still look alike.")
    L.append(f"  2. OLD BASELINE COMPARABILITY: the old model's random split was drawn ONLY from official train; its old test (284 imgs) "
             f"is now part of train. Do NOT compare the new model on the old test set. Compare both models on the new official test.")
    L.append(f"  3. Underrepresented classes (train objects < 25% of median {build['median_train_objects_per_class']}): "
             f"{build['underrepresented_severe'] or 'none'}; moderate (<50%): {build['underrepresented_moderate'] or 'none'}")
    L.append("  4. Source A covers 14/22 classes only; it adds NO images for lemon, turnip, coriander, beetroot, spring_onion, snake_gourd, green_banana.")
    L.append("  5. Source A full-image boxes teach 'one vegetable fills the frame'; kept to ~24% of training images / ~1% of objects to limit large-box false positives.")
    L.append("  6. Source A is 224px, upscaled at imgsz=640 (blurrier than B frames).")
    L.append(f"  7. Cross-source near-duplicates detected: {near_before}")
    L.append(f"\nDataset path : {OUT}")
    L.append(f"data.yaml    : {OUT / 'data.yaml'}")
    L.append("\nValidation checks:")
    for n, ok, d in results:
        L.append(f"  [{'PASS' if ok else 'FAIL'}] {n} {d}")
    L.append("\n" + "=" * 56)
    L.append("DATASET PREPARATION COMPLETE — READY FOR TRAINING" if all_pass else "DATASET PREPARATION INCOMPLETE — FIX FAILURES")
    text = "\n".join(L)

    report_path = OUT / "dataset_report.txt"
    audit_a = (C.REPORT_DIR / "audit_source_a.txt").read_text()
    audit_b = (C.REPORT_DIR / "audit_source_b.txt").read_text()
    C.assert_writable_target(report_path)
    report_path.write_text(text + "\n\n\n" + audit_a + "\n\n" + audit_b)
    (C.REPORT_DIR / "dataset_report.txt").write_text(text)
    print("\n" + text)


if __name__ == "__main__":
    main()
