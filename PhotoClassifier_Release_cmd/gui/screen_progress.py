"""
Screen 2: Progress bar, live counters, cancel button.
"""
# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.pipeline import STEP_CLASSIFY, STEP_EXTRACT, STEP_MOVE


_STEP_ORDER = [STEP_EXTRACT, STEP_CLASSIFY, STEP_MOVE]
_STEP_NAMES = {
    STEP_EXTRACT: "메타데이터 추출",
    STEP_CLASSIFY: "국가/도시 분류",
    STEP_MOVE: "파일 이동",
}


class StatCard(QWidget):
    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self._value_lbl = QLabel("0")
        self._value_lbl.setAlignment(Qt.AlignCenter)
        self._value_lbl.setStyleSheet("font-size: 22px; font-weight: bold;")

        desc_lbl = QLabel(f"{icon}  {label}")
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setStyleSheet("color: #555; font-size: 11px;")

        layout.addWidget(self._value_lbl)
        layout.addWidget(desc_lbl)
        self.setStyleSheet("StatCard { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }")

    def set_value(self, v: int) -> None:
        self._value_lbl.setText(str(v))


class ProgressScreen(QWidget):
    def __init__(self, on_cancel, parent=None):
        super().__init__(parent)
        self._on_cancel = on_cancel
        self._current_step = STEP_EXTRACT
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(32, 28, 32, 28)

        self._step_lbl = QLabel("준비 중...")
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

        overall_lbl = QLabel("전체 진행률")
        overall_lbl.setStyleSheet("color: #888; font-size: 11px; margin-top: 4px;")
        root.addWidget(overall_lbl)

        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 300)
        self._overall_bar.setValue(0)
        self._overall_bar.setTextVisible(False)
        self._overall_bar.setFixedHeight(10)
        self._overall_bar.setStyleSheet(
            "QProgressBar { border-radius: 5px; background: #e2e8f0; }"
            "QProgressBar::chunk { background: #10b981; border-radius: 5px; }"
        )
        root.addWidget(self._overall_bar)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #e2e8f0;")
        root.addWidget(divider)

        cards_layout = QHBoxLayout()
        self._card_success = StatCard("OK", "성공")
        self._card_dup = StatCard("DUP", "중복")
        self._card_skip = StatCard("SKIP", "건너뜀")
        self._card_fail = StatCard("ERR", "실패")
        for card in (self._card_success, self._card_dup, self._card_skip, self._card_fail):
            cards_layout.addWidget(card)
        root.addLayout(cards_layout)

        self._file_lbl = QLabel("")
        self._file_lbl.setAlignment(Qt.AlignCenter)
        self._file_lbl.setStyleSheet("color: #888; font-size: 11px;")
        self._file_lbl.setWordWrap(True)
        root.addWidget(self._file_lbl)

        root.addStretch()

        self._cancel_btn = QPushButton("취소")
        self._cancel_btn.setFixedHeight(38)
        self._cancel_btn.setStyleSheet(
            "QPushButton { border: 1px solid #dc2626; color: #dc2626; border-radius: 6px; }"
            "QPushButton:hover { background: #fef2f2; }"
        )
        self._cancel_btn.clicked.connect(self._confirm_cancel)
        root.addWidget(self._cancel_btn)

        self._step_offsets = {STEP_EXTRACT: 0, STEP_CLASSIFY: 100, STEP_MOVE: 200}

    def reset(self) -> None:
        self._current_step = STEP_EXTRACT
        self._step_lbl.setText("준비 중...")
        self._step_counter_lbl.setText("0 / 0")
        self._step_bar.setValue(0)
        self._overall_bar.setValue(0)
        self._file_lbl.setText("")
        for card in (self._card_success, self._card_dup, self._card_skip, self._card_fail):
            card.set_value(0)

    @Slot(str, int, int)
    def on_progress(self, step_key: str, done: int, total: int) -> None:
        if step_key in _STEP_NAMES:
            self._current_step = step_key
            step_num = _STEP_ORDER.index(step_key) + 1
            step_name = _STEP_NAMES[step_key]
        else:
            step_num = "?"
            step_name = step_key

        self._step_lbl.setText(f"{step_num}/3단계: {step_name}")
        self._step_counter_lbl.setText(f"{done} / {total}")

        pct = int((done / total * 100)) if total > 0 else 0
        self._step_bar.setValue(pct)
        
        # overall_bar max is 300 (100 per step)
        offset = self._step_offsets.get(self._current_step, 0)
        # Scale current step pct to fill exactly 100 points
        self._overall_bar.setValue(offset + pct)

    def update_stats(self, success: int, duplicates: int, skipped: int, failed: int) -> None:
        self._card_success.set_value(success)
        self._card_dup.set_value(duplicates)
        self._card_skip.set_value(skipped)
        self._card_fail.set_value(failed)

    def set_current_file(self, filename: str) -> None:
        self._file_lbl.setText(filename)

    def _confirm_cancel(self) -> None:
        reply = QMessageBox.question(
            self,
            "작업 취소 확인",
            "진행 중인 작업을 취소할까요? 이미 이동된 파일은 그대로 유지됩니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._on_cancel()
            self._cancel_btn.setEnabled(False)
            self._step_lbl.setText("취소 중...")
