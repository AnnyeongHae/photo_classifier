"""
File move/copy with verification.
Wraps move_files_by_classification.py functions with a progress callback interface.
"""
# -*- coding: utf-8 -*-
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from move_files_by_classification import (
    build_plan,
    sha1_file,
    unique_destination,
)


@dataclass
class MoveStats:
    planned: int = 0
    copied: int = 0
    verified: int = 0
    removed: int = 0
    skipped_missing: int = 0
    skipped_duplicate: int = 0
    overwritten: int = 0
    renamed: int = 0
    failed_verify: int = 0

    @property
    def success(self) -> int:
        return self.verified

    @property
    def failed(self) -> int:
        return self.failed_verify + self.skipped_missing


def move_files(
    rows: List[dict],
    duplicate_policy: str = "rename",
    only_success: bool = False,
    cancel_flag: Optional[threading.Event] = None,
    progress_cb: Optional[Callable[[int, int, "MoveStats"], None]] = None,
) -> MoveStats:
    """Build move plan and execute copy+verify+remove for each file."""
    plan = build_plan(rows, only_success=only_success)
    total = len(plan)
    stats = MoveStats(planned=total)

    if progress_cb:
        progress_cb(0, total, stats)

    for idx, item in enumerate(plan):
        if cancel_flag and cancel_flag.is_set():
            raise RuntimeError("Pipeline cancelled by user")

        src = Path(item["source_path"])
        if not src.exists() or not src.is_file():
            stats.skipped_missing += 1
        else:
            requested_dest = Path(item["destination_path"])
            dest = requested_dest

            if requested_dest.exists():
                if duplicate_policy == "skip":
                    stats.skipped_duplicate += 1
                    if progress_cb:
                        progress_cb(idx + 1, total, stats)
                    continue
                if duplicate_policy == "rename":
                    dest = unique_destination(requested_dest)
                    stats.renamed += 1

            import os
            import shutil

            dest.parent.mkdir(parents=True, exist_ok=True)
            temp_dest = dest.with_name(f".tmp_{dest.name}_{os.getpid()}")
            shutil.copy2(src, temp_dest)
            stats.copied += 1

            src_hash = sha1_file(src)
            dst_hash = sha1_file(temp_dest)
            if src_hash != dst_hash:
                temp_dest.unlink(missing_ok=True)
                stats.failed_verify += 1
            else:
                stats.verified += 1
                if requested_dest.exists() and dest == requested_dest and duplicate_policy == "overwrite":
                    requested_dest.unlink()
                    stats.overwritten += 1
                temp_dest.replace(dest)
                src.unlink()
                stats.removed += 1

        if progress_cb:
            progress_cb(idx + 1, total, stats)

    return stats
