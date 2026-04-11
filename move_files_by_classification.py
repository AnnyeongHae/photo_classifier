# -*- coding: utf-8 -*-
import argparse
import csv
import hashlib
import os
import shutil
from pathlib import Path
from typing import Dict, List


def sha1_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    i = 1
    while True:
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def load_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def build_plan(rows: List[Dict[str, str]], only_success: bool) -> List[Dict[str, str]]:
    plan: List[Dict[str, str]] = []
    for row in rows:
        status = (row.get("sort_status") or "").strip()
        if only_success and status not in ("Success", "Success_Country_Others"):
            continue
        source = Path((row.get("source_path") or "").strip())
        target_folder = (row.get("target_folder") or "").strip()
        file_name = (row.get("file_name") or source.name).strip()
        if not target_folder:
            continue
        destination = Path(target_folder) / file_name
        plan.append(
            {
                "source_path": str(source),
                "destination_path": str(destination),
                "sort_status": status,
                "geo_country": row.get("geo_country", ""),
                "geo_city": row.get("geo_city", ""),
            }
        )
    return plan


def write_plan_csv(plan_csv: Path, plan: List[Dict[str, str]]) -> None:
    plan_csv.parent.mkdir(parents=True, exist_ok=True)
    columns = ["source_path", "destination_path", "sort_status", "geo_country", "geo_city"]
    with plan_csv.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=columns)
        writer.writeheader()
        writer.writerows(plan)


def run_dry(plan: List[Dict[str, str]]) -> Dict[str, int]:
    exists = 0
    missing = 0
    for item in plan:
        if Path(item["source_path"]).exists():
            exists += 1
        else:
            missing += 1
    return {"planned": len(plan), "exists": exists, "missing": missing}


def apply_copy_verify_move(plan: List[Dict[str, str]], duplicate_policy: str) -> Dict[str, int]:
    copied = 0
    verified = 0
    removed = 0
    skipped_missing = 0
    skipped_duplicate = 0
    overwritten = 0
    renamed = 0
    failed_verify = 0
    for item in plan:
        src = Path(item["source_path"])
        if not src.exists() or not src.is_file():
            skipped_missing += 1
            continue
        requested_dest = Path(item["destination_path"])
        dest = requested_dest
        if requested_dest.exists():
            if duplicate_policy == "skip":
                skipped_duplicate += 1
                continue
            if duplicate_policy == "rename":
                dest = unique_destination(requested_dest)
                renamed += 1
        dest.parent.mkdir(parents=True, exist_ok=True)

        temp_dest = dest.with_name(f".tmp_{dest.name}_{os.getpid()}")
        shutil.copy2(src, temp_dest)
        copied += 1

        src_hash = sha1_file(src)
        dst_hash = sha1_file(temp_dest)
        if src_hash != dst_hash:
            temp_dest.unlink(missing_ok=True)
            failed_verify += 1
            continue
        verified += 1

        if requested_dest.exists() and dest == requested_dest and duplicate_policy == "overwrite":
            requested_dest.unlink()
            overwritten += 1
        temp_dest.replace(dest)
        src.unlink()
        removed += 1
    return {
        "planned": len(plan),
        "copied": copied,
        "verified": verified,
        "removed": removed,
        "skipped_missing": skipped_missing,
        "skipped_duplicate": skipped_duplicate,
        "overwritten": overwritten,
        "renamed": renamed,
        "failed_verify": failed_verify,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe file operation pipeline: plan -> dry-run -> apply(copy+verify+remove)."
    )
    parser.add_argument("--input-csv", required=True, help="Classification CSV path")
    parser.add_argument("--plan-csv", default="move_plan.csv", help="Generated move plan CSV path")
    parser.add_argument(
        "--mode",
        default="dry-run",
        choices=["plan", "dry-run", "apply"],
        help="plan: write plan only, dry-run: validate plan, apply: copy+verify+remove",
    )
    parser.add_argument(
        "--only-success",
        action="store_true",
        help="Include only Success/Success_Country_Others rows in plan",
    )
    parser.add_argument(
        "--duplicate-policy",
        choices=["overwrite", "skip", "rename"],
        default="rename",
        help="How to handle destination file conflicts during apply",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_csv = Path(args.input_csv)
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    rows = load_rows(input_csv)
    plan = build_plan(rows, only_success=args.only_success)
    plan_csv = Path(args.plan_csv)
    write_plan_csv(plan_csv, plan)

    if args.mode == "plan":
        print(f"Plan created: {len(plan)} -> {plan_csv}")
        return
    if args.mode == "dry-run":
        result = run_dry(plan)
        print(
            f"DryRun planned={result['planned']} exists={result['exists']} missing={result['missing']} "
            f"plan_csv={plan_csv}"
        )
        return

    result = apply_copy_verify_move(plan, duplicate_policy=args.duplicate_policy)
    print(
        "Apply "
        f"planned={result['planned']} copied={result['copied']} verified={result['verified']} "
        f"removed={result['removed']} failed_verify={result['failed_verify']} "
        f"skipped_missing={result['skipped_missing']} skipped_duplicate={result['skipped_duplicate']} "
        f"overwritten={result['overwritten']} renamed={result['renamed']} "
        f"duplicate_policy={args.duplicate_policy} plan_csv={plan_csv}"
    )


if __name__ == "__main__":
    main()
