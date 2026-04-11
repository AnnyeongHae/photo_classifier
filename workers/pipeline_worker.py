"""
QThread worker for running the full pipeline in the background.
Emits signals so the GUI stays responsive.
"""
# -*- coding: utf-8 -*-
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.mover import MoveStats
from core.pipeline import (
    PipelineConfig,
    PipelineResult,
    STEP_CLASSIFY,
    STEP_EXTRACT,
    STEP_MOVE,
    run_full_pipeline,
)


class PipelineWorker(QThread):
    # (step_label, done, total)
    progress = Signal(str, int, int)
    # Emitted on success
    finished = Signal(object)  # PipelineResult
    # Emitted on unhandled exception
    error = Signal(str)

    STEP_LABELS = {
        STEP_EXTRACT: "메타데이터 추출 중...",
        STEP_CLASSIFY: "국가/도시 분류 중...",
        STEP_MOVE: "파일 이동 중...",
    }

    def __init__(self, config: PipelineConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._cancel_flag = threading.Event()

    def cancel(self) -> None:
        self._cancel_flag.set()

    def run(self) -> None:
        def progress_cb(step: str, done: int, total: int) -> None:
            label = self.STEP_LABELS.get(step, step)
            self.progress.emit(label, done, total)

        try:
            result = run_full_pipeline(
                config=self._config,
                progress_cb=progress_cb,
                cancel_flag=self._cancel_flag,
            )
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
