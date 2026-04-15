# -*- coding: utf-8 -*-
import threading
from PySide6.QtCore import QThread, Signal

from core.video_converter import VideoConverterConfig, VideoConverterResult, run_video_conversion

class VideoWorker(QThread):
    max_concurrent_updated = Signal(int)  # Emitted when max concurrent is determined
    progress = Signal(str, int, int)
    task_progress = Signal(int, str, float)  # task_num, file_name, pct
    task_finished = Signal(int, str)  # task_num, file_name
    stats_updated = Signal(int, int, int, int)  # success, dup, skip, fail
    finished = Signal(object)  # VideoConverterResult
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

        def task_progress_cb(task_num: int, file_name: str, pct: float) -> None:
            """Called to update task progress."""
            self.task_progress.emit(task_num, file_name, pct)

        def task_finished_cb(task_num: int, file_name: str) -> None:
            """Called when a task finishes."""
            self.task_finished.emit(task_num, file_name)

        def max_concurrent_cb(max_concurrent: int) -> None:
            """Called when max concurrent is determined."""
            self.max_concurrent_updated.emit(max_concurrent)

        try:
            result = run_video_conversion(
                config=self._config,
                progress_cb=progress_cb,
                task_progress_cb=task_progress_cb,
                task_finished_cb=task_finished_cb,
                max_concurrent_cb=max_concurrent_cb,
                cancel_flag=self._cancel_flag,
                worker_context=self
            )
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
