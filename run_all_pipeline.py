import argparse
import shutil
import subprocess
import sys
from pathlib import Path


# Edit only these two if you don't want to pass CLI args.
DEFAULT_INPUT_FOLDER = r"d:\2026.04.09_photo classification\other\test_imges"
DEFAULT_OUTPUT_FOLDER = r"d:\2026.04.09_photo classification\other\output"

DEFAULT_EXIFTOOL_CANDIDATES = [
    r"c:\Users\user\Downloads\exiftool-13.55_64\exiftool-13.55_64\exiftool.exe",
    "exiftool",
]


def resolve_exiftool_path() -> str:
    for candidate in DEFAULT_EXIFTOOL_CANDIDATES:
        if candidate.lower() == "exiftool":
            if shutil.which("exiftool"):
                return "exiftool"
            continue
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "ExifTool executable not found. Add it to PATH or edit DEFAULT_EXIFTOOL_CANDIDATES in run_all_pipeline.py."
    )


def run_cmd(cmd: list[str], workdir: Path) -> None:
    print("[RUN]", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(workdir), text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout.strip())
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr.strip())
        raise RuntimeError(f"Command failed with exit code {completed.returncode}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full pipeline: extract -> classify -> plan -> dry-run -> apply"
    )
    parser.add_argument("--input-folder", default=DEFAULT_INPUT_FOLDER, help="Root folder with media files")
    parser.add_argument("--output-folder", default=DEFAULT_OUTPUT_FOLDER, help="Final organized output root")
    parser.add_argument("--max-city-distance-km", type=float, default=30.0, help="City cutoff distance")
    parser.add_argument("--fallback-city", default="Unknown_City", help="Fallback city label")
    parser.add_argument(
        "--duplicate-policy",
        choices=["overwrite", "skip", "rename"],
        default="rename",
        help="Destination conflict policy during apply",
    )
    parser.add_argument("--workdir", default=".", help="Project working directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    workdir = Path(args.workdir).resolve()
    input_folder = Path(args.input_folder).resolve()
    output_folder = Path(args.output_folder).resolve()
    exiftool_path = resolve_exiftool_path()

    if not input_folder.exists() or not input_folder.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_folder}")

    metadata_csv = workdir / "pipeline_metadata_input.csv"
    classified_csv = workdir / "pipeline_classified.csv"
    classified_db = workdir / "pipeline_classified.db"
    plan_csv = workdir / "pipeline_move_plan.csv"

    run_cmd(
        [
            sys.executable,
            "exiftool_batch_to_mvp_csv.py",
            "--scan-folder",
            str(input_folder),
            "--output-csv",
            str(metadata_csv),
            "--exiftool-path",
            str(exiftool_path),
        ],
        workdir=workdir,
    )

    run_cmd(
        [
            sys.executable,
            "country_classification_mvp.py",
            "--input-csv",
            str(metadata_csv),
            "--cities-csv",
            "my_cities.csv",
            "--max-city-distance-km",
            str(args.max_city_distance_km),
            "--fallback-city",
            args.fallback_city,
            "--target-root",
            str(output_folder),
            "--output-csv",
            str(classified_csv),
            "--output-db",
            str(classified_db),
        ],
        workdir=workdir,
    )

    run_cmd(
        [
            sys.executable,
            "move_files_by_classification.py",
            "--input-csv",
            str(classified_csv),
            "--plan-csv",
            str(plan_csv),
            "--mode",
            "plan",
        ],
        workdir=workdir,
    )

    run_cmd(
        [
            sys.executable,
            "move_files_by_classification.py",
            "--input-csv",
            str(classified_csv),
            "--plan-csv",
            str(plan_csv),
            "--mode",
            "dry-run",
        ],
        workdir=workdir,
    )

    run_cmd(
        [
            sys.executable,
            "move_files_by_classification.py",
            "--input-csv",
            str(classified_csv),
            "--plan-csv",
            str(plan_csv),
            "--mode",
            "apply",
            "--duplicate-policy",
            args.duplicate_policy,
        ],
        workdir=workdir,
    )

    print("Pipeline complete.")
    print(f"Input: {input_folder}")
    print(f"Output: {output_folder}")
    print(f"Metadata CSV: {metadata_csv}")
    print(f"Classified CSV: {classified_csv}")
    print(f"Move Plan CSV: {plan_csv}")


if __name__ == "__main__":
    main()
