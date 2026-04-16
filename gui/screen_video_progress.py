# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

_GROUPBOX_STYLE = """
    QGroupBox {
        font-size: 13px;
        font-weight: 700;
        color: #1f2937;
        border: 1.5px solid #e5e7eb;
        border-radius: 10px;
        margin-top: 14px;
        padding-top: 18px;
        background: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: #1f2937;
    }
"""


class _StatCard(QWidget):
    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)

        self._value_lbl = QLabel("0")
        self._value_lbl.setAlignment(Qt.AlignCenter)
        self._value_lbl.setStyleSheet(
            f"font-size: 28px; font-weight: 800; color: {color}; background: transparent;"
        )

        desc = QLabel(label)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(
            "color: #374151; font-size: 12px; font-weight: 600; background: transparent;"
        )

        layout.addWidget(self._value_lbl)
        layout.addWidget(desc)
        self.setStyleSheet(
            "background: #f9fafb; border: 1.5px solid #e5e7eb; border-radius: 10px;"
        )

    def set_value(self, v: int) -> None:
        self._value_lbl.setText(str(v))


class VideoProgressScreen(QWidget):
    def __init__(self, on_cancel, parent=None):
        super().__init__(parent)
        self._on_cancel = on_cancel
        self._task_bars: dict = {}
        self._max_concurrent = 1
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── 스크롤 영역 ───────────────────────────────────────────────────
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

        # ── 헤더 ─────────────────────────────────────────────────────────
        title = QLabel("영상 변환 중...")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #111827;"
            "background: transparent; padding-bottom: 2px;"
        )
        root.addWidget(title)

        subtitle = QLabel("창을 닫거나 취소하기 전까지 변환이 계속됩니다.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 13px; color: #374151; background: transparent; margin-bottom: 8px;"
        )
        root.addWidget(subtitle)

        # ── 단계 진행률 ───────────────────────────────────────────────────
        step_group = QGroupBox("  단계 진행률")
        step_group.setStyleSheet(_GROUPBOX_STYLE)
        step_layout = QVBoxLayout(step_group)
        step_layout.setContentsMargins(20, 12, 20, 20)
        step_layout.setSpacing(10)

        step_header = QHBoxLayout()
        self._step_lbl = QLabel("스캔 중...")
        self._step_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #111827; background: transparent;"
        )
        self._step_counter_lbl = QLabel("0 / 0")
        self._step_counter_lbl.setStyleSheet(
            "font-size: 13px; color: #6b7280; background: transparent;"
        )
        step_header.addWidget(self._step_lbl)
        step_header.addStretch()
        step_header.addWidget(self._step_counter_lbl)
        step_layout.addLayout(step_header)

        self._step_bar = QProgressBar()
        self._step_bar.setRange(0, 100)
        self._step_bar.setValue(0)
        self._step_bar.setTextVisible(False)
        self._step_bar.setFixedHeight(14)
        self._step_bar.setStyleSheet(
            "QProgressBar { border-radius: 7px; background: #e5e7eb; border: none; }"
            "QProgressBar::chunk { background: #2563eb; border-radius: 7px; }"
        )
        step_layout.addWidget(self._step_bar)
        root.addWidget(step_group)

        # ── 개별 작업 ─────────────────────────────────────────────────────
        tasks_group = QGroupBox("  개별 작업")
        tasks_group.setStyleSheet(_GROUPBOX_STYLE)
        tasks_outer_layout = QVBoxLayout(tasks_group)
        tasks_outer_layout.setContentsMargins(16, 12, 16, 16)
        tasks_outer_layout.setSpacing(0)

        self._tasks_container = QWidget()
        self._tasks_container.setStyleSheet("background: transparent;")
        self._tasks_layout = QVBoxLayout(self._tasks_container)
        self._tasks_layout.setSpacing(10)
        self._tasks_layout.setContentsMargins(0, 0, 0, 0)

        task_scroll = QScrollArea()
        task_scroll.setWidget(self._tasks_container)
        task_scroll.setWidgetResizable(True)
        task_scroll.setFrameShape(QFrame.NoFrame)
        task_scroll.setFixedHeight(160)
        task_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        tasks_outer_layout.addWidget(task_scroll)
        root.addWidget(tasks_group)

        # ── 처리 현황 ─────────────────────────────────────────────────────
        stats_group = QGroupBox("  처리 현황")
        stats_group.setStyleSheet(_GROUPBOX_STYLE)
        stats_layout = QHBoxLayout(stats_group)
        stats_layout.setContentsMargins(20, 12, 20, 20)
        stats_layout.setSpacing(12)

        self._card_success = _StatCard("변환 완료", "#10b981")
        self._card_skip = _StatCard("건너뜀", "#3b82f6")
        self._card_fail = _StatCard("실패", "#ef4444")
        for card in (self._card_success, self._card_skip, self._card_fail):
            stats_layout.addWidget(card)
        root.addWidget(stats_group)

        root.addStretch()

        # ── 고정 하단: 취소 버튼 ──────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            "QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }"
        )
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

    def set_max_concurrent(self, max_concurrent: int) -> None:
        self._max_concurrent = max_concurrent
        while self._tasks_layout.count():
            item = self._tasks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._task_bars.clear()

        for task_num in range(1, max_concurrent + 1):
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background: #f9fafb; border: 1.5px solid #e5e7eb; border-radius: 8px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(6)

            task_lbl = QLabel(f"작업 {task_num}: 대기 중")
            task_lbl.setStyleSheet(
                "color: #374151; font-size: 12px; font-weight: 600;"
                "background: transparent; border: none;"
            )
            card_layout.addWidget(task_lbl)

            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setTextVisible(True)
            progress_bar.setFixedHeight(20)
            progress_bar.setStyleSheet(
                "QProgressBar { border-radius: 6px; background: #e5e7eb; color: #111827;"
                "  text-align: center; font-size: 11px; font-weight: 700; border: none; }"
                "QProgressBar::chunk { background: #10b981; border-radius: 6px; }"
            )
            card_layout.addWidget(progress_bar)

            self._tasks_layout.addWidget(card)
            self._task_bars[task_num] = (progress_bar, task_lbl)

        self._tasks_layout.addStretch()

    def reset(self) -> None:
        self._step_lbl.setText("스캔 중...")
        self._step_counter_lbl.setText("0 / 0")
        self._step_bar.setValue(0)
        for task_num, (bar, lbl) in self._task_bars.items():
            bar.setValue(0)
            bar.setFormat("0%")
            lbl.setText(f"작업 {task_num}: 대기 중")
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
        if task_num in self._task_bars:
            bar, lbl = self._task_bars[task_num]
            bar.setValue(int(pct))
            bar.setFormat(f"{pct:.1f}%")
            lbl.setText(f"작업 {task_num}: {file_name} ({pct:.1f}%)")

    def on_task_finished(self, task_num: int, file_name: str) -> None:
        if task_num in self._task_bars:
            bar, lbl = self._task_bars[task_num]
            bar.setValue(100)
            bar.setFormat("완료 ✓")
            lbl.setText(f"작업 {task_num}: {file_name} — 완료")

    def reset_task(self, task_num: int) -> None:
        if task_num in self._task_bars:
            bar, lbl = self._task_bars[task_num]
            bar.setValue(0)
            bar.setFormat("0%")
            lbl.setText(f"작업 {task_num}: 대기 중")

    def update_stats(self, success: int, duplicates: int, skipped: int, failed: int) -> None:
        self._card_success.set_value(success)
        self._card_skip.set_value(skipped)
        self._card_fail.set_value(failed)

    def _confirm_cancel(self) -> None:
        reply = QMessageBox.question(
            self,
            "변환 취소 확인",
            "진행 중인 변환을 취소할까요?\n이미 완료된 파일은 유지됩니다.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._on_cancel()
            self._cancel_btn.setEnabled(False)
            self._step_lbl.setText("취소 중...")
