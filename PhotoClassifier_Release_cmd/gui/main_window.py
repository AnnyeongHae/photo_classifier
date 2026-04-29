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
    def __init__(self, on_back_to_hub=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("사진/영상 분류기")
        self.setMinimumSize(820, 620)
        self.resize(860, 660)

        self._on_back_to_hub = on_back_to_hub
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
        
        if self._on_back_to_hub:
            self._setup_screen.back_button.clicked.connect(self._on_back_to_hub)
            self._summary_screen.back_button.clicked.connect(self._on_back_to_hub)
        else:
            self._setup_screen.back_button.hide()
            self._summary_screen.back_button.hide()

        self._stack.setCurrentIndex(_SCREEN_SETUP)

        QTimer.singleShot(300, self._startup_check)

    def _startup_check(self) -> None:
        from core.extractor import resolve_exiftool_path

        issues: List[str] = []

        if not resolve_exiftool_path():
            issues.append(
                "ExifTool을 찾지 못했습니다.\n"
                "- 설정 화면에서 경로를 직접 지정하거나\n"
                "- 앱 폴더의 assets/exiftool.exe 위치에 파일을 넣어 주세요."
            )

        assets_dir = _resolve_assets_dir()
        shapefile = assets_dir / "Natural Earth_10m_admin_0_countries" / "ne_10m_admin_0_countries.shp"
        cities_csv = assets_dir / "my_cities.csv"

        if not shapefile.exists():
            issues.append(f"Shapefile 파일이 없습니다:\n{shapefile}")
        if not cities_csv.exists():
            issues.append(f"도시 CSV 파일이 없습니다:\n{cities_csv}")

        if issues:
            body = "필수 파일 일부가 없어 분류 작업이 실패할 수 있습니다.\n\n" + "\n\n".join(issues)
            QMessageBox.warning(self, "시작 전 확인", body)

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
            QMessageBox.information(self, "취소됨", "분류 작업이 취소되었습니다.")
            self._stack.setCurrentIndex(_SCREEN_SETUP)
            return
        self._summary_screen.load_result(result)
        self._stack.setCurrentIndex(_SCREEN_SUMMARY)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._worker = None
        QMessageBox.critical(self, "오류", f"분류 작업이 실패했습니다:\n\n{message}")
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "종료 확인",
                "작업이 진행 중입니다. 그래도 종료할까요?",
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
