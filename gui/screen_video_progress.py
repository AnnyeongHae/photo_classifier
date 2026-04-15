# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
    QScrollArea
)

from gui.screen_progress import StatCard

class VideoProgressScreen(QWidget):
    def __init__(self, on_cancel, parent=None):
        super().__init__(parent)
        self._on_cancel = on_cancel
        self._task_bars = {}  # {task_num: (progress_bar, label)}
        self._max_concurrent = 1
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

        # Task progress bars container (scrollable)
        self._tasks_container = QWidget()
        self._tasks_layout = QVBoxLayout(self._tasks_container)
        self._tasks_layout.setSpacing(10)
        self._tasks_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidget(self._tasks_container)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        root.addWidget(scroll, 1)

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

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedHeight(38)
        self._cancel_btn.setStyleSheet(
            "QPushButton { border: 1px solid #dc2626; color: #dc2626; border-radius: 6px; }"
            "QPushButton:hover { background: #fef2f2; }"
        )
        self._cancel_btn.clicked.connect(self._confirm_cancel)
        root.addWidget(self._cancel_btn)

    def set_max_concurrent(self, max_concurrent: int) -> None:
        """Set the number of concurrent tasks and create corresponding progress bars."""
        self._max_concurrent = max_concurrent
        # Clear existing task bars
        for bar, lbl in self._task_bars.values():
            bar.deleteLater()
            lbl.deleteLater()
        self._task_bars.clear()
        
        # Create new task bars
        for task_num in range(1, max_concurrent + 1):
            # Task label
            task_lbl = QLabel(f"Task {task_num}: Ready")
            task_lbl.setStyleSheet("color: #333; font-size: 11px; font-weight: bold;")
            self._tasks_layout.addWidget(task_lbl)
            
            # Progress bar
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setTextVisible(True)
            progress_bar.setFixedHeight(18)
            progress_bar.setStyleSheet(
                "QProgressBar { border-radius: 5px; background: #e2e8f0; text-align: center; color: white; font-size: 10px; font-weight: bold;}"
                "QProgressBar::chunk { background: #10b981; border-radius: 5px; }"
            )
            self._tasks_layout.addWidget(progress_bar)
            
            self._task_bars[task_num] = (progress_bar, task_lbl)
        
        self._tasks_layout.addStretch()

    def reset(self) -> None:
        self._step_lbl.setText("Scanning...")
        self._step_counter_lbl.setText("0 / 0")
        self._step_bar.setValue(0)
        for task_num, (bar, lbl) in self._task_bars.items():
            bar.setValue(0)
            bar.setFormat("0%")
            lbl.setText(f"Task {task_num}: Ready")
        for card in (self._card_success, self._card_skip, self._card_fail):
            card.set_value(0)
        self._cancel_btn.setEnabled(True)

    @Slot(str, int, int)
    def on_progress(self, step_key: str, done: int, total: int) -> None:
        self._step_lbl.setText(step_key)
        self._step_counter_lbl.setText(f"{done} / {total}")
        pct = int((done / total * 100)) if total > 0 else 0
        self._step_bar.setValue(pct)

    def on_task_progress(self, task_num: int, file_name: str, pct: float) -> None:
        """Update progress for a specific task."""
        if task_num in self._task_bars:
            bar, lbl = self._task_bars[task_num]
            bar.setValue(int(pct))
            bar.setFormat(f"{pct:.1f}%")
            lbl.setText(f"Task {task_num}: {file_name} ({pct:.1f}%)")

    def on_task_finished(self, task_num: int, file_name: str) -> None:
        """Mark a task as finished and reset for next video."""
        if task_num in self._task_bars:
            bar, lbl = self._task_bars[task_num]
            bar.setValue(100)
            bar.setFormat("Done ✓")
            lbl.setText(f"Task {task_num}: {file_name} - Done")
    
    def reset_task(self, task_num: int) -> None:
        """Reset a task's progress bar for the next video."""
        if task_num in self._task_bars:
            bar, lbl = self._task_bars[task_num]
            bar.setValue(0)
            bar.setFormat("0%")
            lbl.setText(f"Task {task_num}: Ready")

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
