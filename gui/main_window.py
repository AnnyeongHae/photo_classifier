"""
Main application window. Uses QStackedWidget to navigate between 3 screens.
"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget

from core.pipeline import PipelineConfig, PipelineResult
from gui.screen_setup import SetupScreen
from gui.screen_progress import ProgressScreen
from gui.screen_summary import SummaryScreen
from workers.pipeline_worker import PipelineWorker


_SCREEN_SETUP = 0
_SCREEN_PROGRESS = 1
_SCREEN_SUMMARY = 2


def _resolve_assets_dir() -> Path:
    """Find the assets/ directory regardless of dev vs. Nuitka standalone."""
    # Nuitka standalone: assets/ sits next to the .exe
    exe_sibling = Path(sys.executable).parent / "assets"
    if exe_sibling.is_dir():
        return exe_sibling
    # Development: assets/ next to this file's project root
    project_root = Path(__file__).parent.parent
    dev_assets = project_root / "assets"
    if dev_assets.is_dir():
        return dev_assets
    return dev_assets  # let pipeline raise a descriptive error


def _resolve_db_path(output_folder: Path) -> Path:
    """Store the DB alongside the output folder."""
    output_folder.mkdir(parents=True, exist_ok=True)
    return output_folder / "photo_classifier.db"


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Photo Classifier")
        self.setMinimumSize(820, 620)
        self.resize(860, 660)

        self._worker: PipelineWorker | None = None

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._setup_screen = SetupScreen()
        self._progress_screen = ProgressScreen(on_cancel=self._cancel_pipeline)
        self._summary_screen = SummaryScreen(on_process_more=self._go_setup)

        self._stack.addWidget(self._setup_screen)   # index 0
        self._stack.addWidget(self._progress_screen)  # index 1
        self._stack.addWidget(self._summary_screen)  # index 2

        self._setup_screen.run_button.clicked.connect(self._start_pipeline)
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def _go_setup(self) -> None:
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def _start_pipeline(self) -> None:
        if not self._setup_screen.validate():
            return

        assets_dir = _resolve_assets_dir()
        output_folder = Path(self._setup_screen._output_row.path)
        db_path = _resolve_db_path(output_folder)

        config = self._setup_screen.build_config(assets_dir=assets_dir, db_path=db_path)

        self._progress_screen.reset()
        self._stack.setCurrentIndex(_SCREEN_PROGRESS)

        self._worker = PipelineWorker(config=config, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _cancel_pipeline(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    @Slot(str, int, int)
    def _on_progress(self, step_label: str, done: int, total: int) -> None:
        self._progress_screen.on_progress(step_label, done, total)

    @Slot(object)
    def _on_finished(self, result: PipelineResult) -> None:
        self._worker = None
        if result.cancelled:
            QMessageBox.information(self, "취소됨", "작업이 취소되었습니다.")
            self._stack.setCurrentIndex(_SCREEN_SETUP)
            return
        self._summary_screen.load_result(result)
        self._stack.setCurrentIndex(_SCREEN_SUMMARY)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._worker = None
        QMessageBox.critical(self, "오류 발생", f"파이프라인 실행 중 오류가 발생했습니다:\n\n{message}")
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "종료 확인",
                "작업이 진행 중입니다. 종료하시겠습니까?\n이미 처리된 파일은 유지됩니다.",
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
