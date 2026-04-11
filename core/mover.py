"""
File move/copy with verification.
Wraps core.file_moving functions with a progress callback interface.
"""
# -*- coding: utf-8 -*-
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from core.logging_config import get_logger
from core.file_moving import (
    build_plan,
    sha1_file,
    unique_destination,
)

logger = get_logger(__name__)


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
    try:
        logger.info(f"Building move plan ({len(rows)} rows, policy={duplicate_policy})")
        plan = build_plan(rows, only_success=only_success)
        total = len(plan)
        stats = MoveStats(planned=total)
        logger.info(f"Plan contains {total} files to move")

        if progress_cb:
            progress_cb(0, total, stats)

        for idx, item in enumerate(plan):
            if cancel_flag and cancel_flag.is_set():
                logger.warning("Move operation cancelled by user")
                raise RuntimeError("Pipeline cancelled by user")

            src = Path(item["source_path"])
            if not src.exists() or not src.is_file():
                logger.debug(f"Source missing: {src}")
                stats.skipped_missing += 1
            else:
                try:
                    requested_dest = Path(item["destination_path"])
                    dest = requested_dest

                    if requested_dest.exists():
                        if duplicate_policy == "skip":
                            logger.debug(f"Skipping duplicate: {requested_dest}")
                            stats.skipped_duplicate += 1
                            if progress_cb:
                                progress_cb(idx + 1, total, stats)
                            continue
                        if duplicate_policy == "rename":
                            dest = unique_destination(requested_dest)
                            logger.debug(f"Renaming to: {dest}")
                            stats.renamed += 1

                    dest.parent.mkdir(parents=True, exist_ok=True)
                    temp_dest = dest.with_name(f".tmp_{dest.name}_{os.getpid()}")
                    
                    logger.debug(f"Copying {src} to {temp_dest}")
                    shutil.copy2(src, temp_dest)
                    stats.copied += 1

                    src_hash = sha1_file(src)
                    dst_hash = sha1_file(temp_dest)
                    if src_hash != dst_hash:
                        logger.error(f"Hash mismatch for {src}: {src_hash} vs {dst_hash}")
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
                        logger.debug(f"Successfully moved {src} to {dest}")
                
                except Exception as e:
                    logger.error(f"Error moving {src}: {e}", exc_info=True)
                    stats.failed_verify += 1

            if progress_cb:
                progress_cb(idx + 1, total, stats)

        logger.info(
            f"Move complete: {stats.verified} verified, {stats.failed} failed, "
            f"{stats.skipped_duplicate} skipped_duplicate, {stats.renamed} renamed"
        )
        return stats
    
    except Exception as e:
        logger.error(f"Move operation failed: {e}", exc_info=True)
        raise
