# -*- coding: utf-8 -*-
"""Output settings screen: folder, format, quality, metadata, duplicate handling."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from gui.screen_setup import FolderRow
from workers.image_editor_worker import OutputFormat

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
_COMBO_STYLE = """
    QComboBox {
        border: 1.5px solid #d1d5db; border-radius: 6px; padding: 5px 10px;
        font-size: 13px; color: #111827; background: #f9fafb; min-height: 36px;
    }
    QComboBox:hover  { border-color: #9ca3af; background: #f3f4f6; }
    QComboBox:focus  { border-color: #d97706; background: #ffffff; }
    QComboBox::drop-down { border: none; width: 28px; }
    QComboBox QAbstractItemView {
        border: 1.5px solid #d1d5db; border-radius: 6px; background: #ffffff;
        color: #111827; selection-background-color: #fef3c7;
        selection-color: #92400e; font-size: 13px; padding: 4px;
    }
"""


def _flabel(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #111827; background: transparent;")
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return lbl


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 11px; color: #6b7280; margin-top: -4px; background: transparent;")
    lbl.setWordWrap(True)
    return lbl


@dataclass
class OutputData:
    output_folder:     Path
    output_format:     str
    jpeg_quality:      int
    preserve_metadata: bool
    skip_existing:     bool


class ImageEditorOutputScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
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

        title = QLabel("출력 설정")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #111827;"
            "background: transparent; padding-bottom: 2px;"
        )
        root.addWidget(title)

        subtitle = QLabel("변환된 이미지의 저장 위치와 포맷을 설정하세요.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px; color: #374151; background: transparent; margin-bottom: 8px;")
        root.addWidget(subtitle)

        # output folder
        folder_group = QGroupBox("  출력 폴더")
        folder_group.setStyleSheet(_GROUPBOX_STYLE)
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(10)
        folder_layout.setContentsMargins(20, 16, 20, 20)
        self._output_row = FolderRow("출력 폴더", "편집된 이미지가 저장될 폴더 선택")
        folder_layout.addWidget(self._output_row)
        root.addWidget(folder_group)

        # output format
        out_group = QGroupBox("  출력 포맷")
        out_group.setStyleSheet(_GROUPBOX_STYLE)
        out_layout = QFormLayout(out_group)
        out_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        out_layout.setContentsMargins(20, 16, 20, 20)
        out_layout.setSpacing(10)
        out_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._format_cb = QComboBox()
        self._format_cb.addItem("JPEG — 범용 호환, 손실 압축 (권장)", OutputFormat.JPEG)
        self._format_cb.addItem("PNG  — 무손실, 파일 크기 큼", OutputFormat.PNG)
        self._format_cb.addItem("WebP — 현대적, 작은 파일 크기", OutputFormat.WEBP)
        self._format_cb.addItem("원본 포맷 유지 (RAW는 JPEG로 변환)", OutputFormat.KEEP)
        self._format_cb.setStyleSheet(_COMBO_STYLE)
        self._format_cb.currentIndexChanged.connect(self._on_format_changed)
        out_layout.addRow(_flabel("출력 포맷"), self._format_cb)

        self._quality_lbl = _flabel("JPEG/WebP 품질")
        self._quality_cb = QComboBox()
        self._quality_cb.addItem("92   — 고화질 (권장)", 92)
        self._quality_cb.addItem("95   — 최고 화질 (파일 큼)", 95)
        self._quality_cb.addItem("85   — 균형", 85)
        self._quality_cb.addItem("75   — 용량 절약", 75)
        self._quality_cb.setStyleSheet(_COMBO_STYLE)
        out_layout.addRow(self._quality_lbl, self._quality_cb)
        root.addWidget(out_group)

        # metadata & duplicates
        meta_group = QGroupBox("  메타데이터 및 중복 처리")
        meta_group.setStyleSheet(_GROUPBOX_STYLE)
        meta_layout = QFormLayout(meta_group)
        meta_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        meta_layout.setContentsMargins(20, 16, 20, 20)
        meta_layout.setSpacing(10)
        meta_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._meta_cb = QComboBox()
        self._meta_cb.addItem("보전  — GPS·날짜·카메라 EXIF를 출력 이미지에 복사 (권장)", True)
        self._meta_cb.addItem("무시  — 메타데이터 없이 이미지만 저장", False)
        self._meta_cb.setStyleSheet(_COMBO_STYLE)
        meta_layout.addRow(_flabel("EXIF 보전"), self._meta_cb)
        meta_layout.addRow("", _hint("exiftool이 필요합니다. 미탐지 시 JPEG는 Pillow로 기본 EXIF만 복사됩니다."))

        self._skip_cb = QComboBox()
        self._skip_cb.addItem("건너뛰기  — 이미 출력된 파일 재처리 안 함 (권장)", True)
        self._skip_cb.addItem("덮어쓰기  — 기존 출력 파일을 덮어씀", False)
        self._skip_cb.setStyleSheet(_COMBO_STYLE)
        meta_layout.addRow(_flabel("중복 파일 처리"), self._skip_cb)
        root.addWidget(meta_group)
        root.addStretch()

        # footer
        footer = QWidget()
        footer.setStyleSheet("QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(40, 16, 40, 16)
        footer_layout.setSpacing(16)

        self._back_btn = QPushButton("← 뒤로")
        self._back_btn.setFixedHeight(48)
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setStyleSheet(
            "QPushButton { border: 2px solid #d1d5db; color: #374151; border-radius: 10px;"
            "  font-size: 14px; font-weight: 700; background: white; padding: 0 24px; }"
            "QPushButton:hover { border-color: #9ca3af; }"
        )

        self._run_btn = QPushButton("변환 시작 →")
        self._run_btn.setFixedHeight(48)
        self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.setStyleSheet(
            "QPushButton { background: #d97706; color: white; font-size: 15px;"
            "  border-radius: 10px; font-weight: 800; border: none; padding: 0 32px; }"
            "QPushButton:hover { background: #b45309; }"
            "QPushButton:pressed { background: #92400e; }"
            "QPushButton:disabled { background: #9ca3af; }"
        )

        footer_layout.addStretch()
        footer_layout.addWidget(self._back_btn)
        footer_layout.addWidget(self._run_btn)
        outer.addWidget(footer)

        self._on_format_changed()

    def _on_format_changed(self) -> None:
        fmt = self._format_cb.currentData()
        show = fmt in (OutputFormat.JPEG, OutputFormat.WEBP)
        self._quality_cb.setVisible(show)
        self._quality_lbl.setVisible(show)

    def validate(self) -> bool:
        if not self._output_row.path:
            QMessageBox.warning(self, "출력 폴더 누락", "출력 폴더를 선택해 주세요.")
            return False
        return True

    def get_data(self) -> OutputData:
        return OutputData(
            output_folder=Path(self._output_row.path),
            output_format=self._format_cb.currentData(),
            jpeg_quality=self._quality_cb.currentData() or 92,
            preserve_metadata=bool(self._meta_cb.currentData()),
            skip_existing=bool(self._skip_cb.currentData()),
        )

    @property
    def run_button(self) -> QPushButton:
        return self._run_btn

    @property
    def back_button(self) -> QPushButton:
        return self._back_btn
