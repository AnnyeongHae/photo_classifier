# -*- coding: utf-8 -*-
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal


LIVE_PHOTO_VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".3gp", ".3g2"}


@dataclass
class LivePhotoConfig:
    input_folder: Path
    output_folder: Path
    output_format: str = "jpg"       # "png" or "jpg"
    jpeg_quality: int = 95
    frame_mode: str = "sharpest"     # "sharpest" | "first" | "middle"
    preserve_metadata: bool = True
    skip_existing: bool = True
    max_duration_seconds: float = 6.0
    exiftool_path: Optional[str] = None


@dataclass
class LivePhotoResult:
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: bool = False
    errors: list = field(default_factory=list)


class LivePhotoWorker(QThread):
    """QThread worker for Live Photo still-image extraction."""

    progress = Signal(str, int, int)
    stats_updated = Signal(int, int, int)
    log = Signal(str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, config: LivePhotoConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._cancel_flag = threading.Event()

    def cancel(self) -> None:
        self._cancel_flag.set()

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

        frame_extractor = FrameExtractor(use_ensemble=True)
        image_converter = ImageConverter(jpeg_quality=cfg.jpeg_quality)

        metadata_handler: Optional[MetadataHandler] = None
        if cfg.preserve_metadata:
            try:
                metadata_handler = MetadataHandler(cfg.exiftool_path or None)
                self.log.emit("[INFO] exiftool found - metadata preservation enabled")
            except FileNotFoundError:
                self.log.emit("[WARN] exiftool not found - saving without metadata copy")
        else:
            self.log.emit("[INFO] metadata preservation disabled")

        candidates = self._collect_video_files(cfg.input_folder)
        video_files = self._filter_by_duration(candidates, frame_extractor, result)
        total = len(video_files)
        if total == 0:
            supported = ", ".join(sorted(LIVE_PHOTO_VIDEO_EXTENSIONS))
            self.log.emit(
                f"[WARN] no supported short video files found ({supported}, <= {cfg.max_duration_seconds:g}s)"
            )
            self.progress.emit("No files", 0, 0)
            return result

        self.log.emit(f"[INFO] found {total} short video files")
        cfg.output_folder.mkdir(parents=True, exist_ok=True)
        file_ext = ".png" if cfg.output_format == "png" else ".jpg"

        for i, video_file in enumerate(video_files, 1):
            if self._cancel_flag.is_set():
                result.cancelled = True
                self.log.emit("[INFO] cancelled by user")
                break

            self.progress.emit(f"Processing {video_file.name}", i - 1, total)
            output_file = cfg.output_folder / f"{video_file.stem}{file_ext}"

            if output_file.exists() and cfg.skip_existing:
                result.skipped += 1
                self.log.emit(f"[SKIP] [{i}/{total}] {video_file.name}")
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
                self.log.emit(f"[ OK ] [{i}/{total}] {video_file.name} -> {output_file.name}")
            except Exception as exc:  # noqa: BLE001
                result.failed += 1
                result.errors.append(f"{video_file.name}: {exc}")
                self.log.emit(f"[FAIL] [{i}/{total}] {video_file.name}: {exc}")

            self.stats_updated.emit(result.processed, result.skipped, result.failed)

        self.progress.emit("Complete", total, total)
        self.log.emit(
            f"[INFO] complete - processed {result.processed} / skipped {result.skipped} / failed {result.failed}"
        )
        return result

    def _collect_video_files(self, input_folder: Path) -> list[Path]:
        seen: set[Path] = set()
        video_files: list[Path] = []
        for path in input_folder.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in LIVE_PHOTO_VIDEO_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                video_files.append(path)
        return video_files

    def _filter_by_duration(self, files: list[Path], frame_extractor, result: LivePhotoResult) -> list[Path]:
        max_duration = self._config.max_duration_seconds
        if max_duration <= 0:
            return files

        kept: list[Path] = []
        for path in files:
            try:
                info = frame_extractor.get_video_info(path)
            except Exception as exc:  # noqa: BLE001
                result.failed += 1
                result.errors.append(f"{path.name}: cannot read video duration: {exc}")
                self.log.emit(f"[FAIL] {path.name}: cannot read video duration: {exc}")
                continue

            duration = float(info.get("duration_seconds") or 0)
            if duration <= 0:
                result.failed += 1
                result.errors.append(f"{path.name}: invalid video duration")
                self.log.emit(f"[FAIL] {path.name}: invalid video duration")
                continue
            if duration > max_duration:
                self._move_non_live_photo(path, duration, result)
                continue
            kept.append(path)
        return kept

    def _move_non_live_photo(self, path: Path, duration: float, result: LivePhotoResult) -> None:
        cfg = self._config
        try:
            try:
                relative = path.relative_to(cfg.input_folder)
            except ValueError:
                relative = Path(path.name)

            destination = cfg.output_folder / "no_livephoto" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)

            if destination.exists():
                if cfg.skip_existing:
                    result.skipped += 1
                    self.log.emit(
                        f"[SKIP] {path.name}: no_livephoto target already exists ({duration:.1f}s)"
                    )
                    return
                if destination.is_file():
                    destination.unlink()
                else:
                    raise RuntimeError(f"destination exists and is not a file: {destination}")

            shutil.move(str(path), str(destination))
            result.skipped += 1
            self.log.emit(
                f"[MOVE] {path.name}: {duration:.1f}s exceeds {cfg.max_duration_seconds:g}s limit -> no_livephoto"
            )
        except Exception as exc:  # noqa: BLE001
            result.failed += 1
            result.errors.append(f"{path.name}: failed to move to no_livephoto: {exc}")
            self.log.emit(f"[FAIL] {path.name}: failed to move to no_livephoto: {exc}")

    def _convert_single(
        self,
        video_file: Path,
        output_file: Path,
        frame_extractor,
        image_converter,
        metadata_handler,
    ) -> None:
        cfg = self._config

        frames, _metadata = frame_extractor.extract_candidates(
            video_file, return_metadata=True
        )

        if not frames:
            raise RuntimeError("No frames extracted from video")
        if cfg.frame_mode == "first":
            frame_rgb = frames[0]
        elif cfg.frame_mode == "middle":
            frame_rgb = frames[min(1, len(frames) - 1)]
        else:
            frame_rgb = frames[min(2, len(frames) - 1)]

        output_file.parent.mkdir(parents=True, exist_ok=True)

        if cfg.output_format == "png":
            image_converter.save_frame_as_png(frame_rgb, output_file)
        else:
            image_converter.save_frame_as_jpeg(frame_rgb, output_file)

        if metadata_handler:
            metadata_handler.copy_metadata_to_image(video_file, output_file)
