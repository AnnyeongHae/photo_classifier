# -*- coding: utf-8 -*-
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from ImageEditor.core.image_loader import load_image, get_image_files, RAW_EXTENSIONS
from ImageEditor.core.transform_pipeline import TransformPipeline
from ImageEditor.core.metadata_copier import find_exiftool, copy_metadata_exiftool, embed_pillow_exif


class OutputFormat:
    JPEG        = "JPEG"
    PNG         = "PNG"
    WEBP        = "WEBP"
    KEEP        = "KEEP"


@dataclass
class ImageEditorConfig:
    input_folder:      Path
    output_folder:     Path
    pipeline:          TransformPipeline
    output_format:     str  = OutputFormat.JPEG
    jpeg_quality:      int  = 92
    preserve_metadata: bool = True
    skip_existing:     bool = True
    exiftool_path:     Optional[str] = None


@dataclass
class ImageEditorResult:
    processed:    int       = 0
    skipped:      int       = 0
    failed:       int       = 0
    total_files:  int       = 0
    cancelled:    bool      = False
    errors:       List[str] = field(default_factory=list)


_EXT_MAP = {
    OutputFormat.JPEG: ".jpg",
    OutputFormat.PNG:  ".png",
    OutputFormat.WEBP: ".webp",
}


class ImageEditorWorker(QThread):
    """QThread worker for batch image editing."""

    progress     = Signal(str, int, int)      # label, done, total
    stats_updated = Signal(int, int, int)     # processed, skipped, failed
    log          = Signal(str)
    finished     = Signal(object)             # ImageEditorResult
    error        = Signal(str)

    def __init__(self, config: ImageEditorConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            result = self._process()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

    # ── core processing ───────────────────────────────────────────────────────

    def _process(self) -> ImageEditorResult:
        cfg = self._config
        result = ImageEditorResult()

        exiftool = cfg.exiftool_path or find_exiftool()
        if cfg.preserve_metadata:
            if exiftool:
                self.log.emit("[INFO] exiftool 탐지됨 — EXIF 보전 활성화")
            else:
                self.log.emit("[WARN] exiftool 미탐지 — Pillow EXIF 임베딩으로 폴백 (JPEG만)")

        files = get_image_files(cfg.input_folder)
        result.total_files = len(files)

        if not files:
            self.log.emit("[WARN] 처리할 이미지 파일이 없습니다.")
            self.progress.emit("파일 없음", 0, 0)
            return result

        self.log.emit(f"[INFO] 총 {result.total_files}개 파일 발견")
        cfg.output_folder.mkdir(parents=True, exist_ok=True)

        for i, src in enumerate(files):
            if self._cancel.is_set():
                result.cancelled = True
                self.log.emit("[INFO] 사용자 취소 요청")
                break

            self.progress.emit(f"처리 중: {src.name}", i, result.total_files)

            dst = self._dst_path(src, cfg)

            if cfg.skip_existing and dst.exists():
                result.skipped += 1
                self.log.emit(f"[SKIP] [{i+1}/{result.total_files}] {src.name}")
                self.stats_updated.emit(result.processed, result.skipped, result.failed)
                continue

            try:
                self._process_one(src, dst, cfg, exiftool)
                result.processed += 1
                self.log.emit(f"[ OK ] [{i+1}/{result.total_files}] {src.name} → {dst.name}")
            except Exception as exc:
                result.failed += 1
                result.errors.append(f"{src.name}: {exc}")
                self.log.emit(f"[FAIL] [{i+1}/{result.total_files}] {src.name}: {exc}")

            self.stats_updated.emit(result.processed, result.skipped, result.failed)

        self.progress.emit("완료", result.total_files, result.total_files)
        self.log.emit(
            f"[INFO] 완료 — 변환 {result.processed} / 건너뜀 {result.skipped} / 실패 {result.failed}"
        )
        return result

    def _dst_path(self, src: Path, cfg: ImageEditorConfig) -> Path:
        if cfg.output_format == OutputFormat.KEEP:
            ext = src.suffix.lower()
            if ext in RAW_EXTENSIONS:
                ext = ".jpg"  # RAW must always be output as raster
        else:
            ext = _EXT_MAP.get(cfg.output_format, ".jpg")
        return cfg.output_folder / (src.stem + ext)

    def _process_one(
        self,
        src: Path,
        dst: Path,
        cfg: ImageEditorConfig,
        exiftool: Optional[str],
    ) -> None:
        img, exif_bytes = load_image(src, preview_only=False)
        img = cfg.pipeline.apply(img)

        dst.parent.mkdir(parents=True, exist_ok=True)

        save_kw: dict = {}
        ext = dst.suffix.lower()

        if ext in (".jpg", ".jpeg"):
            save_kw["quality"]  = cfg.jpeg_quality
            save_kw["optimize"] = True
            if exif_bytes and cfg.preserve_metadata and not exiftool:
                save_kw["exif"] = exif_bytes
        elif ext == ".webp":
            save_kw["quality"] = cfg.jpeg_quality
            save_kw["method"]  = 6

        img.save(str(dst), **save_kw)

        if cfg.preserve_metadata:
            if exiftool:
                copy_metadata_exiftool(src, dst, exiftool)
            elif exif_bytes and ext in (".jpg", ".jpeg"):
                embed_pillow_exif(dst, exif_bytes, cfg.jpeg_quality)
