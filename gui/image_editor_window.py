# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget

from gui.screen_imageeditor_setup      import ImageEditorSetupScreen
from gui.screen_imageeditor_filebrowser import ImageEditorFileBrowserScreen
from gui.screen_imageeditor_pipeline   import ImageEditorPipelineScreen
from gui.screen_imageeditor_output     import ImageEditorOutputScreen
from gui.screen_imageeditor_progress   import ImageEditorProgressScreen
from gui.screen_imageeditor_summary    import ImageEditorSummaryScreen
from workers.image_editor_worker import (
    ImageEditorConfig, ImageEditorResult, ImageEditorWorker,
)

_SCREEN_SETUP        = 0
_SCREEN_FILEBROWSER  = 1
_SCREEN_PIPELINE     = 2
_SCREEN_OUTPUT       = 3
_SCREEN_PROGRESS     = 4
_SCREEN_SUMMARY      = 5


class ImageEditorWindow(QMainWindow):
    def __init__(self, on_back_to_hub=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("이미지 일괄 편집기")
        self.setMinimumSize(960, 680)
        self.resize(1200, 800)

        self._on_back_to_hub = on_back_to_hub
        self._worker: ImageEditorWorker | None = None
        self._selected_files: List[Path] = []

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._setup_screen      = ImageEditorSetupScreen()
        self._filebrowser_screen = ImageEditorFileBrowserScreen()
        self._pipeline_screen   = ImageEditorPipelineScreen()
        self._output_screen     = ImageEditorOutputScreen()
        self._progress_screen   = ImageEditorProgressScreen(on_cancel=self._cancel_pipeline)
        self._summary_screen    = ImageEditorSummaryScreen(on_process_more=self._go_setup)

        self._stack.addWidget(self._setup_screen)       # 0
        self._stack.addWidget(self._filebrowser_screen) # 1
        self._stack.addWidget(self._pipeline_screen)    # 2
        self._stack.addWidget(self._output_screen)      # 3
        self._stack.addWidget(self._progress_screen)    # 4
        self._stack.addWidget(self._summary_screen)     # 5

        # navigation wiring
        self._setup_screen.run_button.clicked.connect(self._go_filebrowser)
        self._filebrowser_screen.back_button.clicked.connect(self._go_setup)
        self._filebrowser_screen.next_button.clicked.connect(self._go_pipeline)
        self._pipeline_screen.back_button.clicked.connect(self._go_filebrowser)
        self._pipeline_screen.run_button.clicked.connect(self._go_output)
        self._output_screen.back_button.clicked.connect(self._go_pipeline_from_output)
        self._output_screen.run_button.clicked.connect(self._start_pipeline)

        if self._on_back_to_hub:
            self._setup_screen.back_button.clicked.connect(self._back_to_hub)
            self._summary_screen.back_button.clicked.connect(self._back_to_hub)
        else:
            self._setup_screen.back_button.hide()
            self._summary_screen.back_button.hide()

        self._stack.setCurrentIndex(_SCREEN_SETUP)

    # ── navigation ─────────────────────────────────────────────────────────────

    def _back_to_hub(self) -> None:
        self.hide()
        if self._on_back_to_hub:
            self._on_back_to_hub()

    def _go_setup(self) -> None:
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def _go_filebrowser(self) -> None:
        if not self._setup_screen.validate():
            return
        data = self._setup_screen.get_data()
        self._filebrowser_screen.load_folder(data.input_folder)
        self._stack.setCurrentIndex(_SCREEN_FILEBROWSER)

    def _go_pipeline(self) -> None:
        if not self._filebrowser_screen.validate():
            return
        self._selected_files = self._filebrowser_screen.get_selected_files()
        self._pipeline_screen.load_files(self._selected_files)
        self._stack.setCurrentIndex(_SCREEN_PIPELINE)

    def _go_output(self) -> None:
        self._stack.setCurrentIndex(_SCREEN_OUTPUT)

    def _go_pipeline_from_output(self) -> None:
        self._stack.setCurrentIndex(_SCREEN_PIPELINE)

    # ── worker lifecycle ────────────────────────────────────────────────────────

    def _start_pipeline(self) -> None:
        if not self._output_screen.validate():
            return

        pipeline = self._pipeline_screen.get_pipeline()
        if pipeline.is_empty():
            reply = QMessageBox.question(
                self,
                "파이프라인 없음",
                "변환 파이프라인이 비어 있습니다.\n크기 조절·자르기 없이 포맷 변환만 진행할까요?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        out = self._output_screen.get_data()
        config = ImageEditorConfig(
            output_folder=out.output_folder,
            pipeline=pipeline,
            files=self._selected_files,
            output_format=out.output_format,
            jpeg_quality=out.jpeg_quality,
            preserve_metadata=out.preserve_metadata,
            skip_existing=out.skip_existing,
        )

        self._progress_screen.reset()
        self._stack.setCurrentIndex(_SCREEN_PROGRESS)

        self._worker = ImageEditorWorker(config=config, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.stats_updated.connect(self._on_stats_updated)
        self._worker.log.connect(self._progress_screen.append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _cancel_pipeline(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    # ── slots ───────────────────────────────────────────────────────────────────

    @Slot(str, int, int)
    def _on_progress(self, label: str, done: int, total: int) -> None:
        self._progress_screen.on_progress(label, done, total)

    @Slot(int, int, int)
    def _on_stats_updated(self, processed: int, skipped: int, failed: int) -> None:
        self._progress_screen.update_stats(processed, skipped, failed)

    @Slot(object)
    def _on_finished(self, result: ImageEditorResult) -> None:
        self._worker = None
        if result.cancelled:
            QMessageBox.information(self, "취소됨", "편집이 취소되었습니다.")
            self._stack.setCurrentIndex(_SCREEN_SETUP)
            return
        self._summary_screen.load_result(result)
        self._stack.setCurrentIndex(_SCREEN_SUMMARY)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._worker = None
        QMessageBox.critical(self, "오류", f"편집 중 오류가 발생했습니다:\n\n{message}")
        self._stack.setCurrentIndex(_SCREEN_SETUP)

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "종료 확인",
                "편집이 진행 중입니다. 종료하시겠습니까?",
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
