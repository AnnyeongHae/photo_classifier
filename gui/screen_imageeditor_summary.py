# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from PySide6.QtGui import QFont

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


class _SummaryCard(QWidget):
    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        self._value_lbl = QLabel("0")
        self._value_lbl.setAlignment(Qt.AlignCenter)
        self._value_lbl.setStyleSheet(
            f"font-size: 36px; font-weight: 800; color: {color}; background: transparent;"
        )
        desc = QLabel(label)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(
            "color: #374151; font-size: 13px; font-weight: 600; background: transparent;"
        )
        layout.addWidget(self._value_lbl)
        layout.addWidget(desc)
        self.setStyleSheet("background: #f9fafb; border: 1.5px solid #e5e7eb; border-radius: 10px;")

    def set_value(self, v: int) -> None:
        self._value_lbl.setText(str(v))


class ImageEditorSummaryScreen(QWidget):
    def __init__(self, on_process_more, parent=None):
        super().__init__(parent)
        self._on_process_more = on_process_more
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
        root.setContentsMargins(40, 48, 40, 24)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        icon_lbl = QLabel("✅")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 56px; background: transparent;")
        root.addWidget(icon_lbl)

        title = QLabel("편집 완료!")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #111827;"
            "background: transparent; padding-bottom: 2px;"
        )
        root.addWidget(title)

        subtitle = QLabel("이미지 일괄 편집이 완료되었습니다.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 13px; color: #374151; background: transparent; margin-bottom: 8px;"
        )
        root.addWidget(subtitle)

        # ── 처리 결과 카드 ────────────────────────────────────────────────────
        stats_group = QGroupBox("  처리 결과")
        stats_group.setStyleSheet(_GROUPBOX_STYLE)
        stats_layout = QHBoxLayout(stats_group)
        stats_layout.setContentsMargins(20, 12, 20, 24)
        stats_layout.setSpacing(16)

        self._card_ok   = _SummaryCard("변환 완료", "#10b981")
        self._card_skip = _SummaryCard("건너뜀",   "#3b82f6")
        self._card_fail = _SummaryCard("실패",      "#ef4444")
        for card in (self._card_ok, self._card_skip, self._card_fail):
            stats_layout.addWidget(card)
        root.addWidget(stats_group)

        # ── 오류 목록 (실패가 있을 때만 표시) ────────────────────────────────
        self._error_group = QGroupBox("  실패 목록")
        self._error_group.setStyleSheet(_GROUPBOX_STYLE)
        err_layout = QVBoxLayout(self._error_group)
        err_layout.setContentsMargins(20, 12, 20, 16)

        self._error_log = QPlainTextEdit()
        self._error_log.setReadOnly(True)
        self._error_log.setFixedHeight(140)
        mono = QFont("Consolas", 11)
        mono.setStyleHint(QFont.Monospace)
        self._error_log.setFont(mono)
        self._error_log.setStyleSheet(
            "QPlainTextEdit { background: #1e1e2e; color: #f38ba8;"
            "  border: none; border-radius: 6px; padding: 8px; }"
        )
        err_layout.addWidget(self._error_log)
        root.addWidget(self._error_group)
        self._error_group.hide()

        root.addStretch()

        # ── 고정 하단 버튼 ────────────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet("QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(40, 16, 40, 16)
        footer_layout.setSpacing(8)

        self._btn_more = QPushButton("다시 처리하기")
        self._btn_more.setFixedHeight(52)
        self._btn_more.setCursor(Qt.PointingHandCursor)
        self._btn_more.setStyleSheet(
            "QPushButton { background: #d97706; color: white; font-size: 16px;"
            "  border-radius: 10px; font-weight: 800; border: none; }"
            "QPushButton:hover { background: #b45309; }"
            "QPushButton:pressed { background: #92400e; }"
        )
        self._btn_more.clicked.connect(self._on_process_more)
        footer_layout.addWidget(self._btn_more)

        self._btn_back = QPushButton("← 허브로 돌아가기")
        self._btn_back.setCursor(Qt.PointingHandCursor)
        self._btn_back.setStyleSheet(
            "QPushButton { color: #374151; font-size: 13px; font-weight: 600;"
            "  border: none; padding: 4px; background: transparent; }"
            "QPushButton:hover { color: #111827; }"
        )
        footer_layout.addWidget(self._btn_back, alignment=Qt.AlignCenter)
        outer.addWidget(footer)

    def load_result(self, result) -> None:
        self._card_ok.set_value(result.processed)
        self._card_skip.set_value(result.skipped)
        self._card_fail.set_value(result.failed)

        if result.errors:
            self._error_log.setPlainText("\n".join(result.errors))
            self._error_group.show()
        else:
            self._error_group.hide()

    @property
    def back_button(self) -> QPushButton:
        return self._btn_back
