# -*- coding: utf-8 -*-
from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget

from core.video_converter import VideoConverterResult
from gui.screen_video_setup import VideoSetupScreen
from gui.screen_video_progress import VideoProgressScreen
from gui.screen_video_summary import VideoSummaryScreen
from workers.video_worker import VideoWorker

_SCREEN_SETUP = 0
_SCREEN_PROGRESS = 1
_SCREEN_SUMMARY = 2

class VideoWindow(QMainWindow):
    def __init__(self, on_back_to_hub=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video Resolution Converter")
        self.setMinimumSize(820, 620)
        self.resize(860, 660)

        self._on_back_to_hub = on_back_to_hub
        self._worker: VideoWorker | None = None

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._setup_screen = VideoSetupScreen()
        self._progress_screen = VideoProgressScreen(on_cancel=self._cancel_pipeline)
        self._summary_screen = VideoSummaryScreen(on_process_more=self._go_setup)

        self._stack.addWidget(self._setup_screen)
        self._stack.addWidget(self._progress_screen)
        self._stack.addWidget(self._summary_screen)

        self._setup_screen.run_button.clicked.connect(self._start_pipeline)
        
        if self._on_back_to_hub:
            self._setup_screen.back_button.clicked.connect(self._on_back_to_hub)
            self._summary_screen.back_button.clicked.connect(self._on_back_to_hub)
        else:
            self._setup_screen.back_button.hide()
            self._summary_screen.back_button.hide()
            
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def _go_setup(self) -> None:
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def _start_pipeline(self) -> None:
        if not self._setup_screen.validate():
            return

        config = self._setup_screen.build_config()

        self._progress_screen.reset()
        self._stack.setCurrentIndex(_SCREEN_PROGRESS)

        self._worker = VideoWorker(config=config, parent=self)
        self._worker.max_concurrent_updated.connect(self._on_max_concurrent_updated)
        self._worker.progress.connect(self._on_progress)
        self._worker.task_progress.connect(self._on_task_progress)
        self._worker.task_finished.connect(self._on_task_finished)
        self._worker.stats_updated.connect(self._on_stats_updated)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _cancel_pipeline(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    @Slot(int)
    def _on_max_concurrent_updated(self, max_concurrent: int) -> None:
        """Update GUI when max concurrent encodes is determined."""
        self._progress_screen.set_max_concurrent(max_concurrent)

    @Slot(str, int, int, int, int)
    def _on_stats_updated(self, success: int, dup: int, skip: int, fail: int) -> None:
        self._progress_screen.update_stats(success, dup, skip, fail)

    @Slot(str, int, int)
    def _on_progress(self, step_key: str, done: int, total: int) -> None:
        self._progress_screen.on_progress(step_key, done, total)
        
    @Slot(int, str, float)
    def _on_task_progress(self, task_num: int, file_name: str, pct: float) -> None:
        self._progress_screen.on_task_progress(task_num, file_name, pct)

    @Slot(int, str)
    def _on_task_finished(self, task_num: int, file_name: str) -> None:
        self._progress_screen.on_task_finished(task_num, file_name)
        # Schedule reset for next video (after a short delay for visual feedback)
        QTimer.singleShot(500, lambda: self._progress_screen.reset_task(task_num))

    @Slot(object)
    def _on_finished(self, result: VideoConverterResult) -> None:
        self._worker = None
        if result.cancelled:
            QMessageBox.information(self, "Cancelled", "Conversion was cancelled.")
            self._stack.setCurrentIndex(_SCREEN_SETUP)
            return
        self._summary_screen.load_result(result)
        self._stack.setCurrentIndex(_SCREEN_SUMMARY)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._worker = None
        QMessageBox.critical(self, "Error", f"Conversion failed:\n\n{message}")
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "A conversion is running. Exit anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._worker.cancel()
                self._worker.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

