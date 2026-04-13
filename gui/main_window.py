"""
Main application window. Uses QStackedWidget to navigate between 3 screens.
"""
# -*- coding: utf-8 -*-
import sys
from pathlib import Path
from typing import List

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget

from core.pipeline import PipelineResult
from gui.screen_progress import ProgressScreen
from gui.screen_setup import SetupScreen
from gui.screen_summary import SummaryScreen
from workers.pipeline_worker import PipelineWorker


_SCREEN_SETUP = 0
_SCREEN_PROGRESS = 1
_SCREEN_SUMMARY = 2


def _resolve_assets_dir() -> Path:
    """Find assets directory for dev and standalone builds."""
    exe_sibling = Path(sys.executable).parent / "assets"
    if exe_sibling.is_dir():
        return exe_sibling
    project_root = Path(__file__).parent.parent
    return project_root / "assets"


def _resolve_db_path(output_folder: Path) -> Path:
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys.executable).parent.parent
    else:
        base_dir = Path(__file__).parent.parent
    
    db_dir = base_dir / "DB"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "photo_classifier.db"


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

        self._stack.addWidget(self._setup_screen)
        self._stack.addWidget(self._progress_screen)
        self._stack.addWidget(self._summary_screen)

        self._setup_screen.run_button.clicked.connect(self._start_pipeline)
        self._stack.setCurrentIndex(_SCREEN_SETUP)

        QTimer.singleShot(300, self._startup_check)

    def _startup_check(self) -> None:
        from core.extractor import resolve_exiftool_path

        issues: List[str] = []

        if not resolve_exiftool_path():
            issues.append(
                "ExifTool was not found.\n"
                "- Set path directly in the setup screen, or\n"
                "- Place assets/exiftool.exe in the app folder."
            )

        assets_dir = _resolve_assets_dir()
        shapefile = assets_dir / "Natural Earth_10m_admin_0_countries" / "ne_10m_admin_0_countries.shp"
        cities_csv = assets_dir / "my_cities.csv"

        if not shapefile.exists():
            issues.append(f"Shapefile missing:\n{shapefile}")
        if not cities_csv.exists():
            issues.append(f"City CSV missing:\n{cities_csv}")

        if issues:
            body = "Some required files are missing. The pipeline may fail.\n\n" + "\n\n".join(issues)
            QMessageBox.warning(self, "Startup Check", body)

    def _go_setup(self) -> None:
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def _start_pipeline(self) -> None:
        if not self._setup_screen.validate():
            return

        assets_dir = _resolve_assets_dir()
        output_folder = Path(self._setup_screen.output_path)
        db_path = _resolve_db_path(output_folder)
        config = self._setup_screen.build_config(assets_dir=assets_dir, db_path=db_path)

        self._progress_screen.reset()
        self._stack.setCurrentIndex(_SCREEN_PROGRESS)

        self._worker = PipelineWorker(config=config, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.stats_updated.connect(self._on_stats_updated)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _cancel_pipeline(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    @Slot(int, int, int, int)
    def _on_stats_updated(self, success: int, dup: int, skip: int, fail: int) -> None:
        self._progress_screen.update_stats(success, dup, skip, fail)

    @Slot(str, int, int)
    def _on_progress(self, step_key: str, done: int, total: int) -> None:
        self._progress_screen.on_progress(step_key, done, total)

    @Slot(object)
    def _on_finished(self, result: PipelineResult) -> None:
        self._worker = None
        if result.cancelled:
            QMessageBox.information(self, "Cancelled", "Pipeline was cancelled.")
            self._stack.setCurrentIndex(_SCREEN_SETUP)
            return
        self._summary_screen.load_result(result)
        self._stack.setCurrentIndex(_SCREEN_SUMMARY)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._worker = None
        QMessageBox.critical(self, "Error", f"Pipeline failed:\n\n{message}")
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "A job is running. Exit anyway?",
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
