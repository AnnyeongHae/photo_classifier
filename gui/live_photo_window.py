# -*- coding: utf-8 -*-
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget

from gui.screen_livephoto_progress import LivePhotoProgressScreen
from gui.screen_livephoto_setup import LivePhotoSetupScreen
from gui.screen_livephoto_summary import LivePhotoSummaryScreen
from workers.live_photo_worker import LivePhotoResult, LivePhotoWorker

SCREEN_SETUP = 0
SCREEN_PROGRESS = 1
SCREEN_SUMMARY = 2


class LivePhotoWindow(QMainWindow):
    def __init__(self, on_back_to_hub=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live Photo Converter")
        self.setMinimumSize(780, 640)
        self.resize(860, 720)

        self._on_back_to_hub = on_back_to_hub
        self._worker: LivePhotoWorker | None = None

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._setup_screen = LivePhotoSetupScreen()
        self._progress_screen = LivePhotoProgressScreen(on_cancel=self._cancel_pipeline)
        self._summary_screen = LivePhotoSummaryScreen(on_process_more=self._go_setup)

        self._stack.addWidget(self._setup_screen)
        self._stack.addWidget(self._progress_screen)
        self._stack.addWidget(self._summary_screen)

        self._setup_screen.run_button.clicked.connect(self._start_pipeline)

        if self._on_back_to_hub:
            self._setup_screen.back_button.clicked.connect(self._back_to_hub)
            self._summary_screen.back_button.clicked.connect(self._back_to_hub)
        else:
            self._setup_screen.back_button.hide()
            self._summary_screen.back_button.hide()

        self._stack.setCurrentIndex(SCREEN_SETUP)

    def _back_to_hub(self) -> None:
        self.hide()
        if self._on_back_to_hub:
            self._on_back_to_hub()

    def _go_setup(self) -> None:
        self._stack.setCurrentIndex(SCREEN_SETUP)

    def _start_pipeline(self) -> None:
        if not self._setup_screen.validate():
            return

        config = self._setup_screen.build_config()

        self._progress_screen.reset()
        self._stack.setCurrentIndex(SCREEN_PROGRESS)

        self._worker = LivePhotoWorker(config=config, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.stats_updated.connect(self._on_stats_updated)
        self._worker.log.connect(self._progress_screen.append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _cancel_pipeline(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    @Slot(str, int, int)
    def _on_progress(self, label: str, done: int, total: int) -> None:
        self._progress_screen.on_progress(label, done, total)

    @Slot(int, int, int)
    def _on_stats_updated(self, processed: int, skipped: int, failed: int) -> None:
        self._progress_screen.update_stats(processed, skipped, failed)

    @Slot(object)
    def _on_finished(self, result: LivePhotoResult) -> None:
        self._worker = None
        if result.cancelled:
            QMessageBox.information(self, "Cancelled", "Conversion was cancelled.")
            self._stack.setCurrentIndex(SCREEN_SETUP)
            return
        self._summary_screen.load_result(result)
        self._stack.setCurrentIndex(SCREEN_SUMMARY)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._worker = None
        QMessageBox.critical(self, "Error", f"Conversion failed:\n\n{message}")
        self._stack.setCurrentIndex(SCREEN_SETUP)

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
                if self._on_back_to_hub:
                    self._on_back_to_hub()
            else:
                event.ignore()
        else:
            event.accept()
            if self._on_back_to_hub:
                self._on_back_to_hub()
