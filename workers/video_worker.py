# -*- coding: utf-8 -*-
import threading
from PySide6.QtCore import QThread, Signal

from core.video_converter import VideoConverterConfig, VideoConverterResult, run_video_conversion

class VideoWorker(QThread):
    progress = Signal(str, int, int)
    stats_updated = Signal(int, int, int, int) # success, dup, skip, fail
    file_progress = Signal(float) # for the sub-progress bar
    finished = Signal(object) # VideoConverterResult
    error = Signal(str)

    def __init__(self, config: VideoConverterConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._cancel_flag = threading.Event()
        self.active_process = None

    def cancel(self) -> None:
        self._cancel_flag.set()
        if self.active_process:
            try:
                self.active_process.terminate()
            except Exception:
                pass

    def run(self) -> None:
        def progress_cb(step: str, done: int, total: int, stats: dict = None) -> None:
            self.progress.emit(step, done, total)
            if stats:
                self.stats_updated.emit(
                    stats.get("success", 0), 
                    stats.get("duplicates", 0), 
                    stats.get("skipped", 0), 
                    stats.get("failed", 0)
                )
                if "_current_pct" in stats:
                    self.file_progress.emit(stats["_current_pct"])

        try:
            result = run_video_conversion(
                config=self._config,
                progress_cb=progress_cb,
                cancel_flag=self._cancel_flag,
                worker_context=self
            )
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
