# -*- coding: utf-8 -*-
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.screen_setup import FolderRow
from workers.live_photo_worker import LivePhotoConfig


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

_COMBO_STYLE = """
    QComboBox {
        border: 1.5px solid #d1d5db;
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 13px;
        color: #111827;
        background: #f9fafb;
        min-height: 36px;
    }
    QComboBox:hover  { border-color: #9ca3af; background: #f3f4f6; color: #111827; }
    QComboBox:focus  { border-color: #7c3aed; background: #ffffff; color: #111827; }
    QComboBox::drop-down { border: none; width: 28px; }
    QComboBox QAbstractItemView {
        border: 1.5px solid #d1d5db;
        border-radius: 6px;
        background: #ffffff;
        color: #111827;
        selection-background-color: #f5f3ff;
        selection-color: #5b21b6;
        font-size: 13px;
        padding: 4px;
    }
"""


def _flabel(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "font-size: 13px; font-weight: 600; color: #111827; background: transparent;"
    )
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return lbl


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "font-size: 11px; color: #6b7280; margin-top: -4px; background: transparent;"
    )
    lbl.setWordWrap(True)
    return lbl


class LivePhotoSetupScreen(QWidget):
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

        # ── 헤더 ────────────────────────────────────────────────────────────
        title = QLabel("라이브 포토 변환기")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #111827;"
            "background: transparent; padding-bottom: 2px;"
        )
        root.addWidget(title)

        subtitle = QLabel("Live Photo(MP4/MOV)에서 최고 화질의 정지 이미지를 추출합니다.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 13px; color: #374151; background: transparent; margin-bottom: 8px;"
        )
        root.addWidget(subtitle)

        # ── EXIF 상태 카드 ───────────────────────────────────────────────────
        self._exif_card = QFrame()
        self._exif_card.setFrameShape(QFrame.NoFrame)
        self._exif_card.setFixedHeight(52)
        self._exif_card.setStyleSheet(
            "QFrame { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 10px; }"
        )
        exif_card_inner = QHBoxLayout(self._exif_card)
        exif_card_inner.setContentsMargins(20, 0, 20, 0)
        self._exif_label = QLabel("exiftool 상태: 확인 중...")
        self._exif_label.setAlignment(Qt.AlignCenter)
        self._exif_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #166534; background: transparent; border: none;"
        )
        exif_card_inner.addWidget(self._exif_label)
        root.addWidget(self._exif_card)

        # ── 1. 파일 경로 ─────────────────────────────────────────────────────
        folder_group = QGroupBox("  파일 경로")
        folder_group.setStyleSheet(_GROUPBOX_STYLE)
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(10)
        folder_layout.setContentsMargins(20, 16, 20, 20)

        self._input_row = FolderRow("입력 폴더", "Live Photo(MP4/MOV)가 있는 폴더 선택")
        self._output_row = FolderRow("출력 폴더", "추출된 이미지가 저장될 폴더 선택")
        folder_layout.addWidget(self._input_row)
        folder_layout.addWidget(self._output_row)
        root.addWidget(folder_group)

        # ── 2. 출력 설정 ──────────────────────────────────────────────────────
        out_group = QGroupBox("  출력 설정")
        out_group.setStyleSheet(_GROUPBOX_STYLE)
        out_layout = QFormLayout(out_group)
        out_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        out_layout.setContentsMargins(20, 16, 20, 20)
        out_layout.setSpacing(10)
        out_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._format_cb = QComboBox()
        self._format_cb.addItem("PNG  — 무손실 (권장, 파일 큼)", "png")
        self._format_cb.addItem("JPEG — 손실 압축 (파일 작음)", "jpg")
        self._format_cb.setStyleSheet(_COMBO_STYLE)
        self._format_cb.currentIndexChanged.connect(self._on_format_changed)
        out_layout.addRow(_flabel("이미지 포맷"), self._format_cb)
        out_layout.addRow(
            "",
            _hint("PNG는 픽셀 완전 보존. JPEG는 압축률로 인해 원본 대비 손실이 발생합니다."),
        )

        self._quality_cb = QComboBox()
        self._quality_cb.addItem("100  — 최고 화질 (거의 무손실)", 100)
        self._quality_cb.addItem("95   — 고화질 (기본값)", 95)
        self._quality_cb.addItem("85   — 균형", 85)
        self._quality_cb.setStyleSheet(_COMBO_STYLE)
        self._quality_row_label = _flabel("JPEG 품질")
        out_layout.addRow(self._quality_row_label, self._quality_cb)

        self._frame_cb = QComboBox()
        self._frame_cb.addItem("최선명 프레임  — 포커스 점수가 가장 높은 프레임 (권장)", "sharpest")
        self._frame_cb.addItem("첫 번째 프레임 — 촬영 시작 직후", "first")
        self._frame_cb.addItem("중간 프레임   — 영상 중앙 지점", "middle")
        self._frame_cb.setStyleSheet(_COMBO_STYLE)
        out_layout.addRow(_flabel("프레임 선택"), self._frame_cb)
        out_layout.addRow(
            "",
            _hint("최선명 모드는 Laplacian+Brenner 앙상블로 가장 선명한 프레임을 자동 탐색합니다."),
        )

        root.addWidget(out_group)

        # ── 3. 메타데이터 설정 ────────────────────────────────────────────────
        meta_group = QGroupBox("  메타데이터 설정")
        meta_group.setStyleSheet(_GROUPBOX_STYLE)
        meta_layout = QFormLayout(meta_group)
        meta_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        meta_layout.setContentsMargins(20, 16, 20, 20)
        meta_layout.setSpacing(10)
        meta_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._metadata_cb = QComboBox()
        self._metadata_cb.addItem("보전  — EXIF/GPS/날짜 정보를 출력 이미지에 복사 (권장)", True)
        self._metadata_cb.addItem("무시  — 메타데이터 없이 이미지만 저장", False)
        self._metadata_cb.setStyleSheet(_COMBO_STYLE)
        meta_layout.addRow(_flabel("EXIF 보전"), self._metadata_cb)
        meta_layout.addRow(
            "",
            _hint("exiftool이 필요합니다. 미탐지 시 메타데이터 없이 저장됩니다."),
        )

        self._skip_cb = QComboBox()
        self._skip_cb.addItem("건너뛰기  — 이미 변환된 파일 재처리 안 함 (권장)", True)
        self._skip_cb.addItem("덮어쓰기  — 기존 출력 파일을 덮어씀", False)
        self._skip_cb.setStyleSheet(_COMBO_STYLE)
        meta_layout.addRow(_flabel("중복 파일 처리"), self._skip_cb)

        root.addWidget(meta_group)

        # ── exiftool 상태 ────────────────────────────────────────────────────
        self._deps_label = QLabel()
        self._deps_label.setAlignment(Qt.AlignCenter)
        self._deps_label.setStyleSheet(
            "font-size: 12px; color: #374151; background: transparent;"
        )
        root.addWidget(self._deps_label)

        root.addStretch()

        # ── 고정 하단 버튼 ────────────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            "QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }"
        )
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(40, 16, 40, 16)
        footer_layout.setSpacing(8)

        self._run_btn = QPushButton("변환 시작")
        self._run_btn.setFixedHeight(52)
        self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.setStyleSheet(
            "QPushButton { background: #7c3aed; color: white; font-size: 16px;"
            "  border-radius: 10px; font-weight: 800; border: none; }"
            "QPushButton:hover { background: #6d28d9; }"
            "QPushButton:pressed { background: #5b21b6; }"
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

        # Initial quality visibility
        self._on_format_changed()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _on_format_changed(self) -> None:
        is_jpg = self._format_cb.currentData() == "jpg"
        self._quality_cb.setVisible(is_jpg)
        self._quality_row_label.setVisible(is_jpg)

    def _check_exiftool(self) -> None:
        try:
            from LivePhotoConverter.core.metadata_handler import MetadataHandler
            MetadataHandler()
            self._exif_label.setText("✓ exiftool 탐지됨 — EXIF 보전 사용 가능")
            self._exif_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #166534; background: transparent; border: none;"
            )
            self._exif_card.setStyleSheet(
                "QFrame { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 10px; }"
            )
            self._deps_label.setText("✓ exiftool 정상 로드됨")
            self._deps_label.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px;")
        except FileNotFoundError:
            self._exif_label.setText("⚠️ exiftool 미탐지 — 메타데이터 보전 불가")
            self._exif_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #92400e; background: transparent; border: none;"
            )
            self._exif_card.setStyleSheet(
                "QFrame { background: #fffbeb; border: 1.5px solid #fde68a; border-radius: 10px; }"
            )
            self._deps_label.setText("⚠️ exiftool 없음 — assets 폴더 또는 PATH 확인")
            self._deps_label.setStyleSheet("color: #f59e0b; font-weight: bold; font-size: 12px;")

    def validate(self) -> bool:
        if not self._input_row.path:
            QMessageBox.warning(self, "입력 폴더 누락", "입력 폴더를 선택해 주세요.")
            return False
        if not Path(self._input_row.path).is_dir():
            QMessageBox.warning(self, "입력 폴더 없음", "입력 폴더가 존재하지 않습니다.")
            return False
        if not self._output_row.path:
            QMessageBox.warning(self, "출력 폴더 누락", "출력 폴더를 선택해 주세요.")
            return False
        return True

    def build_config(self) -> LivePhotoConfig:
        return LivePhotoConfig(
            input_folder=Path(self._input_row.path),
            output_folder=Path(self._output_row.path),
            output_format=self._format_cb.currentData(),
            jpeg_quality=self._quality_cb.currentData(),
            frame_mode=self._frame_cb.currentData(),
            preserve_metadata=bool(self._metadata_cb.currentData()),
            skip_existing=bool(self._skip_cb.currentData()),
        )

    @property
    def run_button(self) -> QPushButton:
        return self._run_btn

    @property
    def back_button(self) -> QPushButton:
        return self._back_btn
