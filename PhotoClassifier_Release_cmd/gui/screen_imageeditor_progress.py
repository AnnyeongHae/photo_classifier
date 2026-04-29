# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

_GROUPBOX_STYLE = """
    QGroupBox {
        font-size: 13px; font-weight: 700; color: #1f2937;
        border: 1.5px solid #e5e7eb; border-radius: 10px;
        margin-top: 14px; padding-top: 18px; background: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #1f2937;
    }
"""


class _StatCard(QWidget):
    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)

        self._val = QLabel("0")
        self._val.setAlignment(Qt.AlignCenter)
        self._val.setStyleSheet(
            f"font-size: 28px; font-weight: 800; color: {color}; background: transparent;"
        )
        desc = QLabel(label)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #374151; font-size: 12px; font-weight: 600; background: transparent;")

        layout.addWidget(self._val)
        layout.addWidget(desc)
        self.setStyleSheet("background: #f9fafb; border: 1.5px solid #e5e7eb; border-radius: 10px;")

    def set_value(self, v: int) -> None:
        self._val.setText(str(v))


class ImageEditorProgressScreen(QWidget):
    def __init__(self, on_cancel, parent=None):
        super().__init__(parent)
        self._on_cancel = on_cancel
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: #f3f4f6; }")

        content = QWidget()
        content.setStyleSheet("background: #f3f4f6;")
        root = QVBoxLayout(content)
        root.setSpacing(16)
        root.setContentsMargins(40, 32, 40, 24)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        title = QLabel("이미지 일괄 편집 중...")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #111827; background: transparent;"
        )
        root.addWidget(title)

        subtitle = QLabel("창을 닫거나 취소하기 전까지 변환이 계속됩니다.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px; color: #374151; background: transparent; margin-bottom: 8px;")
        root.addWidget(subtitle)

        # ── 진행률 ────────────────────────────────────────────────────────────
        step_group = QGroupBox("  진행률")
        step_group.setStyleSheet(_GROUPBOX_STYLE)
        step_layout = QVBoxLayout(step_group)
        step_layout.setContentsMargins(20, 12, 20, 20)
        step_layout.setSpacing(10)

        hdr = QHBoxLayout()
        self._step_lbl = QLabel("준비 중...")
        self._step_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #111827; background: transparent;"
        )
        self._counter_lbl = QLabel("0 / 0")
        self._counter_lbl.setStyleSheet("font-size: 13px; color: #6b7280; background: transparent;")
        hdr.addWidget(self._step_lbl)
        hdr.addStretch()
        hdr.addWidget(self._counter_lbl)
        step_layout.addLayout(hdr)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(14)
        self._bar.setStyleSheet(
            "QProgressBar { border-radius: 7px; background: #e5e7eb; border: none; }"
            "QProgressBar::chunk { background: #d97706; border-radius: 7px; }"
        )
        step_layout.addWidget(self._bar)
        root.addWidget(step_group)

        # ── 처리 현황 ─────────────────────────────────────────────────────────
        stats_group = QGroupBox("  처리 현황")
        stats_group.setStyleSheet(_GROUPBOX_STYLE)
        stats_layout = QHBoxLayout(stats_group)
        stats_layout.setContentsMargins(20, 12, 20, 20)
        stats_layout.setSpacing(12)

        self._card_ok   = _StatCard("변환 완료", "#10b981")
        self._card_skip = _StatCard("건너뜀",   "#3b82f6")
        self._card_fail = _StatCard("실패",      "#ef4444")
        for card in (self._card_ok, self._card_skip, self._card_fail):
            stats_layout.addWidget(card)
        root.addWidget(stats_group)

        # ── 처리 로그 ─────────────────────────────────────────────────────────
        log_group = QGroupBox("  처리 로그")
        log_group.setStyleSheet(_GROUPBOX_STYLE)
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(20, 12, 20, 16)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(220)
        mono = QFont("Consolas", 11)
        mono.setStyleHint(QFont.Monospace)
        self._log.setFont(mono)
        self._log.setStyleSheet(
            "QPlainTextEdit { background: #1e1e2e; color: #cdd6f4;"
            "  border: none; border-radius: 6px; padding: 8px; }"
        )
        log_layout.addWidget(self._log)
        root.addWidget(log_group)
        root.addStretch()

        # ── 취소 버튼 ─────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet("QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(40, 16, 40, 16)

        self._cancel_btn = QPushButton("변환 취소")
        self._cancel_btn.setFixedHeight(48)
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setStyleSheet(
            "QPushButton { border: 2px solid #dc2626; color: #dc2626; border-radius: 10px;"
            "  font-size: 15px; font-weight: 700; background: transparent; }"
            "QPushButton:hover { background: #fef2f2; }"
            "QPushButton:pressed { background: #fee2e2; }"
            "QPushButton:disabled { border-color: #d1d5db; color: #9ca3af; }"
        )
        self._cancel_btn.clicked.connect(self._confirm_cancel)
        footer_layout.addWidget(self._cancel_btn)
        outer.addWidget(footer)

    # ── public API ─────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self._step_lbl.setText("준비 중...")
        self._counter_lbl.setText("0 / 0")
        self._bar.setValue(0)
        self._card_ok.set_value(0)
        self._card_skip.set_value(0)
        self._card_fail.set_value(0)
        self._log.clear()
        self._cancel_btn.setEnabled(True)

    @Slot(str)
    def append_log(self, line: str) -> None:
        self._log.appendPlainText(line)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    @Slot(str, int, int)
    def on_progress(self, label: str, done: int, total: int) -> None:
        self._step_lbl.setText(label)
        self._counter_lbl.setText(f"{done} / {total}")
        self._bar.setValue(int(done / total * 100) if total > 0 else 0)

    @Slot(int, int, int)
    def update_stats(self, processed: int, skipped: int, failed: int) -> None:
        self._card_ok.set_value(processed)
        self._card_skip.set_value(skipped)
        self._card_fail.set_value(failed)

    def _confirm_cancel(self) -> None:
        reply = QMessageBox.question(
            self, "변환 취소 확인",
            "진행 중인 변환을 취소할까요?\n이미 완료된 파일은 유지됩니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._on_cancel()
            self._cancel_btn.setEnabled(False)
            self._step_lbl.setText("취소 중...")
