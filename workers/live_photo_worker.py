# -*- coding: utf-8 -*-
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal


@dataclass
class LivePhotoConfig:
    input_folder: Path
    output_folder: Path
    output_format: str = "png"       # "png" or "jpg"
    jpeg_quality: int = 95
    frame_mode: str = "sharpest"     # "sharpest" | "first" | "middle"
    preserve_metadata: bool = True
    skip_existing: bool = True
    exiftool_path: Optional[str] = None


@dataclass
class LivePhotoResult:
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: bool = False
    errors: list = field(default_factory=list)


class LivePhotoWorker(QThread):
    """QThread worker for Live Photo batch conversion.

    Uses FrameExtractor / ImageConverter / MetadataHandler directly
    (not BatchProcessor) so logging doesn't conflict with the main app.
    """

    progress = Signal(str, int, int)   # step_label, done, total
    stats_updated = Signal(int, int, int)  # processed, skipped, failed
    finished = Signal(object)          # LivePhotoResult
    error = Signal(str)

    def __init__(self, config: LivePhotoConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._cancel_flag = threading.Event()

    def cancel(self) -> None:
        self._cancel_flag.set()

    # ── main thread logic ─────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            result = self._process()
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    def _process(self) -> LivePhotoResult:
        from LivePhotoConverter.core.frame_extractor import FrameExtractor
        from LivePhotoConverter.core.image_converter import ImageConverter
        from LivePhotoConverter.core.metadata_handler import MetadataHandler

        cfg = self._config
        result = LivePhotoResult()

        # Initialise tools
        frame_extractor = FrameExtractor(use_ensemble=True)
        image_converter = ImageConverter(jpeg_quality=cfg.jpeg_quality)

        metadata_handler: Optional[MetadataHandler] = None
        if cfg.preserve_metadata:
            try:
                metadata_handler = MetadataHandler(cfg.exiftool_path or None)
            except FileNotFoundError:
                # exiftool not found — continue without metadata
                metadata_handler = None

        # Collect video files
        patterns = ["*.mov", "*.mp4", "*.MP4", "*.MOV"]
        seen: set = set()
        video_files = []
        for pattern in patterns:
            for f in cfg.input_folder.glob(f"**/{pattern}"):
                resolved = f.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    video_files.append(f)

        total = len(video_files)
        if total == 0:
            self.progress.emit("파일 없음", 0, 0)
            return result

        cfg.output_folder.mkdir(parents=True, exist_ok=True)
        file_ext = ".png" if cfg.output_format == "png" else ".jpg"

        for i, video_file in enumerate(video_files, 1):
            if self._cancel_flag.is_set():
                result.cancelled = True
                break

            self.progress.emit(
                f"처리 중: {video_file.name}",
                i - 1,
                total,
            )

            output_file = cfg.output_folder / f"{video_file.stem}{file_ext}"

            if output_file.exists() and cfg.skip_existing:
                result.skipped += 1
                self.stats_updated.emit(result.processed, result.skipped, result.failed)
                continue

            try:
                self._convert_single(
                    video_file,
                    output_file,
                    frame_extractor,
                    image_converter,
                    metadata_handler,
                )
                result.processed += 1
            except Exception as exc:  # noqa: BLE001
                result.failed += 1
                result.errors.append(f"{video_file.name}: {exc}")

            self.stats_updated.emit(result.processed, result.skipped, result.failed)

        self.progress.emit("완료", total, total)
        return result

    def _convert_single(
        self,
        video_file: Path,
        output_file: Path,
        frame_extractor,
        image_converter,
        metadata_handler,
    ) -> None:
        cfg = self._config

        frames, metadata = frame_extractor.extract_candidates(
            video_file, return_metadata=True
        )

        # Pick frame according to user choice
        if cfg.frame_mode == "first":
            frame_rgb = frames[0]
        elif cfg.frame_mode == "middle":
            frame_rgb = frames[1]
        else:  # "sharpest" (default)
            frame_rgb = frames[2]

        output_file.parent.mkdir(parents=True, exist_ok=True)

        if cfg.output_format == "png":
            image_converter.save_frame_as_png(frame_rgb, output_file)
        else:
            image_converter.save_frame_as_jpeg(frame_rgb, output_file)

        if metadata_handler:
            metadata_handler.copy_metadata_to_image(video_file, output_file)
