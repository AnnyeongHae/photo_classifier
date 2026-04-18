# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGroupBox, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from gui.screen_setup import FolderRow
from ImageEditor.core.metadata_copier import find_exiftool

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


@dataclass
class SetupData:
    input_folder: Path


class ImageEditorSetupScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._check_exiftool()

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

        title = QLabel("이미지 일괄 편집기")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #111827;"
            "background: transparent; padding-bottom: 2px;"
        )
        root.addWidget(title)

        subtitle = QLabel("편집할 이미지가 있는 폴더를 선택하세요. JPEG·PNG·RAW·HEIC 등 모든 포맷을 지원합니다.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 13px; color: #374151; background: transparent; margin-bottom: 8px;"
        )
        root.addWidget(subtitle)

        # exiftool status card
        self._exif_card = QFrame()
        self._exif_card.setFrameShape(QFrame.NoFrame)
        self._exif_card.setFixedHeight(52)
        self._exif_card.setStyleSheet(
            "QFrame { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 10px; }"
        )
        exif_inner = QHBoxLayout(self._exif_card)
        exif_inner.setContentsMargins(20, 0, 20, 0)
        self._exif_label = QLabel("exiftool 상태: 확인 중...")
        self._exif_label.setAlignment(Qt.AlignCenter)
        self._exif_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #166534; background: transparent; border: none;"
        )
        exif_inner.addWidget(self._exif_label)
        root.addWidget(self._exif_card)

        # input folder
        folder_group = QGroupBox("  입력 폴더")
        folder_group.setStyleSheet(_GROUPBOX_STYLE)
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(10)
        folder_layout.setContentsMargins(20, 16, 20, 20)
        self._input_row = FolderRow("입력 폴더", "편집할 이미지가 있는 폴더 선택")
        folder_layout.addWidget(self._input_row)
        root.addWidget(folder_group)
        root.addStretch()

        # footer
        footer = QWidget()
        footer.setStyleSheet("QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(40, 16, 40, 16)
        footer_layout.setSpacing(8)

        self._run_btn = QPushButton("다음: 파일 선택 →")
        self._run_btn.setFixedHeight(52)
        self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.setStyleSheet(
            "QPushButton { background: #d97706; color: white; font-size: 16px;"
            "  border-radius: 10px; font-weight: 800; border: none; }"
            "QPushButton:hover { background: #b45309; }"
            "QPushButton:pressed { background: #92400e; }"
            "QPushButton:disabled { background: #9ca3af; }"
        )
        footer_layout.addWidget(self._run_btn)

        self._back_btn = QPushButton("← 허브로 돌아가기")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setStyleSheet(
            "QPushButton { color: #374151; font-size: 13px; font-weight: 600;"
            "  border: none; padding: 4px; background: transparent; }"
            "QPushButton:hover { color: #111827; }"
        )
        footer_layout.addWidget(self._back_btn, alignment=Qt.AlignCenter)
        outer.addWidget(footer)

    def _check_exiftool(self) -> None:
        if find_exiftool():
            self._exif_label.setText("✓ exiftool 탐지됨 — EXIF 보전 사용 가능")
            self._exif_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #166534; background: transparent; border: none;"
            )
            self._exif_card.setStyleSheet(
                "QFrame { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 10px; }"
            )
        else:
            self._exif_label.setText("⚠️ exiftool 미탐지 — JPEG 기본 EXIF만 복사됩니다")
            self._exif_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #92400e; background: transparent; border: none;"
            )
            self._exif_card.setStyleSheet(
                "QFrame { background: #fffbeb; border: 1.5px solid #fde68a; border-radius: 10px; }"
            )

    def validate(self) -> bool:
        if not self._input_row.path:
            QMessageBox.warning(self, "입력 폴더 누락", "입력 폴더를 선택해 주세요.")
            return False
        if not Path(self._input_row.path).is_dir():
            QMessageBox.warning(self, "입력 폴더 없음", "선택한 입력 폴더가 존재하지 않습니다.")
            return False
        return True

    def get_data(self) -> SetupData:
        return SetupData(input_folder=Path(self._input_row.path))

    @property
    def run_button(self) -> QPushButton:
        return self._run_btn

    @property
    def back_button(self) -> QPushButton:
        return self._back_btn
