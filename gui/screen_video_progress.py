# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from gui.screen_progress import StatCard

class VideoProgressScreen(QWidget):
    def __init__(self, on_cancel, parent=None):
        super().__init__(parent)
        self._on_cancel = on_cancel
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(32, 28, 32, 28)

        self._step_lbl = QLabel("Scanning Videos...")
        self._step_lbl.setAlignment(Qt.AlignCenter)
        self._step_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        root.addWidget(self._step_lbl)

        step_header = QHBoxLayout()
        self._step_counter_lbl = QLabel("0 / 0")
        self._step_counter_lbl.setStyleSheet("color: #666; font-size: 12px;")
        step_header.addStretch()
        step_header.addWidget(self._step_counter_lbl)
        root.addLayout(step_header)

        self._step_bar = QProgressBar()
        self._step_bar.setRange(0, 100)
        self._step_bar.setValue(0)
        self._step_bar.setTextVisible(False)
        self._step_bar.setFixedHeight(16)
        self._step_bar.setStyleSheet(
            "QProgressBar { border-radius: 8px; background: #e2e8f0; }"
            "QProgressBar::chunk { background: #2563eb; border-radius: 8px; }"
        )
        root.addWidget(self._step_bar)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #e2e8f0;")
        root.addWidget(divider)

        cards_layout = QHBoxLayout()
        self._card_success = StatCard("OK", "Converted")
        self._card_skip = StatCard("SKIP", "Small/Skipped")
        self._card_fail = StatCard("ERR", "Failed")
        for card in (self._card_success, self._card_skip, self._card_fail):
            cards_layout.addWidget(card)
        root.addLayout(cards_layout)

        root.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedHeight(38)
        self._cancel_btn.setStyleSheet(
            "QPushButton { border: 1px solid #dc2626; color: #dc2626; border-radius: 6px; }"
            "QPushButton:hover { background: #fef2f2; }"
        )
        self._cancel_btn.clicked.connect(self._confirm_cancel)
        root.addWidget(self._cancel_btn)

    def reset(self) -> None:
        self._step_lbl.setText("Scanning...")
        self._step_counter_lbl.setText("0 / 0")
        self._step_bar.setValue(0)
        for card in (self._card_success, self._card_skip, self._card_fail):
            card.set_value(0)
        self._cancel_btn.setEnabled(True)

    @Slot(str, int, int)
    def on_progress(self, step_key: str, done: int, total: int) -> None:
        self._step_lbl.setText(step_key)
        self._step_counter_lbl.setText(f"{done} / {total}")
        pct = int((done / total * 100)) if total > 0 else 0
        self._step_bar.setValue(pct)

    def update_stats(self, success: int, duplicates: int, skipped: int, failed: int) -> None:
        self._card_success.set_value(success)
        self._card_skip.set_value(skipped)
        self._card_fail.set_value(failed)

    def _confirm_cancel(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirm Cancel",
            "Cancel the running job? Files already converted will be kept.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._on_cancel()
            self._cancel_btn.setEnabled(False)
            self._step_lbl.setText("Cancelling...")
