# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QScrollArea
)

from core.video_converter import VideoConverterResult
from gui.screen_summary import SummaryCard

class VideoSummaryScreen(QWidget):
    def __init__(self, on_process_more, parent=None):
        super().__init__(parent)
        self._on_process_more = on_process_more
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(32, 24, 32, 24)

        icon_lbl = QLabel("✅")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 48px; margin-bottom: 8px;")
        root.addWidget(icon_lbl)

        title = QLabel("Video Conversion Complete")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1f2937;")
        root.addWidget(title)

        cards_layout = QHBoxLayout()
        self._card_success = SummaryCard("Converted", "0", "#10b981")
        self._card_skip = SummaryCard("Skipped", "0", "#3b82f6")
        self._card_fail = SummaryCard("Failed", "0", "#ef4444")

        cards_layout.addWidget(self._card_success)
        cards_layout.addWidget(self._card_skip)
        cards_layout.addWidget(self._card_fail)
        root.addLayout(cards_layout)

        root.addStretch()

        self._btn_more = QPushButton("Convert More Videos")
        self._btn_more.setFixedHeight(44)
        self._btn_more.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; font-size: 15px; border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
        )
        self._btn_more.clicked.connect(self._on_process_more)
        root.addWidget(self._btn_more)
        
        self._btn_back = QPushButton("← Back to Hub")
        self._btn_back.setStyleSheet("color: #4b5563; font-weight: bold; border: none; padding: 8px;")
        root.addWidget(self._btn_back)

    def load_result(self, result: VideoConverterResult) -> None:
        self._card_success.set_value(str(result.success))
        self._card_skip.set_value(str(result.skipped))
        self._card_fail.set_value(str(result.failed))
        
    @property
    def back_button(self) -> QPushButton:
        return self._btn_back
