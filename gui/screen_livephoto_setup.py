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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.screen_setup import FolderRow
from workers.live_photo_worker import LIVE_PHOTO_VIDEO_EXTENSIONS, LivePhotoConfig


GROUPBOX_STYLE = """
    QGroupBox {
        font-size: 13px;
        font-weight: 700;
        color: #1f2937;
        border: 1.5px solid #e5e7eb;
        border-radius: 8px;
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

COMBO_STYLE = """
    QComboBox {
        border: 1.5px solid #d1d5db;
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 13px;
        color: #111827;
        background: #f9fafb;
        min-height: 36px;
    }
    QComboBox:hover  { border-color: #9ca3af; background: #f3f4f6; }
    QComboBox:focus  { border-color: #7c3aed; background: #ffffff; }
    QComboBox::drop-down { border: none; width: 28px; }
"""


def _flabel(text: str) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    label.setStyleSheet("font-size: 13px; font-weight: 600; color: #111827; background: transparent;")
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("font-size: 11px; color: #6b7280; background: transparent;")
    return label


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

        title = QLabel("라이브 포토 변환기")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 26px; font-weight: 800; color: #111827; background: transparent;")
        root.addWidget(title)

        ext_list = ", ".join(sorted(ext.upper() for ext in LIVE_PHOTO_VIDEO_EXTENSIONS))
        subtitle = QLabel(f"Live Photo 영상 파일({ext_list})에서 정지 이미지를 추출합니다.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 13px; color: #374151; background: transparent; margin-bottom: 8px;")
        root.addWidget(subtitle)

        self._exif_card = QFrame()
        self._exif_card.setFixedHeight(52)
        exif_layout = QHBoxLayout(self._exif_card)
        exif_layout.setContentsMargins(20, 0, 20, 0)
        self._exif_label = QLabel("exiftool 확인 중...")
        self._exif_label.setAlignment(Qt.AlignCenter)
        self._exif_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #166534; background: transparent; border: none;"
        )
        exif_layout.addWidget(self._exif_label)
        root.addWidget(self._exif_card)

        folder_group = QGroupBox("파일 경로")
        folder_group.setStyleSheet(GROUPBOX_STYLE)
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(10)
        folder_layout.setContentsMargins(20, 16, 20, 20)

        self._input_row = FolderRow("입력 폴더", "Live Photo 영상 파일이 있는 폴더 선택")
        self._output_row = FolderRow("출력 폴더", "추출된 이미지가 저장될 폴더 선택")
        folder_layout.addWidget(self._input_row)
        folder_layout.addWidget(self._output_row)
        root.addWidget(folder_group)

        out_group = QGroupBox("출력 설정")
        out_group.setStyleSheet(GROUPBOX_STYLE)
        out_layout = QFormLayout(out_group)
        out_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        out_layout.setContentsMargins(20, 16, 20, 20)
        out_layout.setSpacing(10)
        out_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._format_cb = QComboBox()
        self._format_cb.addItem("JPEG - 호환성 좋음, EXIF 보존에 유리", "jpg")
        self._format_cb.addItem("PNG - 무손실 프레임 출력", "png")
        self._format_cb.setStyleSheet(COMBO_STYLE)
        self._format_cb.currentIndexChanged.connect(self._on_format_changed)
        out_layout.addRow(_flabel("이미지 포맷"), self._format_cb)
        out_layout.addRow("", _hint("GPS/날짜/카메라 메타데이터 보존이 필요하면 JPEG를 권장합니다."))

        self._quality_cb = QComboBox()
        self._quality_cb.addItem("95 - 고화질", 95)
        self._quality_cb.addItem("100 - 최고 품질", 100)
        self._quality_cb.addItem("85 - 용량 균형", 85)
        self._quality_cb.setStyleSheet(COMBO_STYLE)
        self._quality_row_label = _flabel("JPEG 품질")
        out_layout.addRow(self._quality_row_label, self._quality_cb)

        self._frame_cb = QComboBox()
        self._frame_cb.addItem("최선명 프레임 - 권장", "sharpest")
        self._frame_cb.addItem("첫 프레임", "first")
        self._frame_cb.addItem("중간 프레임", "middle")
        self._frame_cb.setStyleSheet(COMBO_STYLE)
        out_layout.addRow(_flabel("프레임"), self._frame_cb)
        out_layout.addRow("", _hint("최선명 모드는 영상을 샘플링해 가장 선명한 프레임을 선택합니다."))

        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 120)
        self._duration_spin.setValue(6)
        self._duration_spin.setSuffix("초")
        self._duration_spin.setStyleSheet(
            "QSpinBox { border: 1.5px solid #d1d5db; border-radius: 6px; padding: 5px 10px;"
            " font-size: 13px; color: #111827; background: #f9fafb; min-height: 36px; }"
        )
        out_layout.addRow(_flabel("최대 영상 길이"), self._duration_spin)
        out_layout.addRow("", _hint("이 길이를 넘는 영상은 출력 폴더의 no_livephoto 폴더로 이동합니다."))
        root.addWidget(out_group)

        meta_group = QGroupBox("메타데이터 설정")
        meta_group.setStyleSheet(GROUPBOX_STYLE)
        meta_layout = QFormLayout(meta_group)
        meta_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        meta_layout.setContentsMargins(20, 16, 20, 20)
        meta_layout.setSpacing(10)

        self._metadata_cb = QComboBox()
        self._metadata_cb.addItem("EXIF/GPS/날짜 메타데이터 보존", True)
        self._metadata_cb.addItem("메타데이터 복사 안 함", False)
        self._metadata_cb.setStyleSheet(COMBO_STYLE)
        meta_layout.addRow(_flabel("EXIF"), self._metadata_cb)

        self._skip_cb = QComboBox()
        self._skip_cb.addItem("기존 출력 파일 건너뛰기", True)
        self._skip_cb.addItem("기존 출력 파일 덮어쓰기", False)
        self._skip_cb.setStyleSheet(COMBO_STYLE)
        meta_layout.addRow(_flabel("중복 파일"), self._skip_cb)
        root.addWidget(meta_group)

        self._deps_label = QLabel()
        self._deps_label.setAlignment(Qt.AlignCenter)
        self._deps_label.setStyleSheet("font-size: 12px; color: #374151; background: transparent;")
        root.addWidget(self._deps_label)
        root.addStretch()

        footer = QWidget()
        footer.setStyleSheet("QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(40, 16, 40, 16)
        footer_layout.setSpacing(8)

        self._run_btn = QPushButton("변환 시작")
        self._run_btn.setFixedHeight(52)
        self._run_btn.setCursor(Qt.PointingHandCursor)
        self._run_btn.setStyleSheet(
            "QPushButton { background: #7c3aed; color: white; font-size: 16px;"
            "  border-radius: 8px; font-weight: 800; border: none; }"
            "QPushButton:hover { background: #6d28d9; }"
            "QPushButton:pressed { background: #5b21b6; }"
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

        self._on_format_changed()

    def _on_format_changed(self) -> None:
        is_jpg = self._format_cb.currentData() == "jpg"
        self._quality_cb.setVisible(is_jpg)
        self._quality_row_label.setVisible(is_jpg)

    def _check_exiftool(self) -> None:
        try:
            from LivePhotoConverter.core.metadata_handler import MetadataHandler

            MetadataHandler()
            self._exif_label.setText("exiftool 감지됨 - 메타데이터 보존 사용 가능")
            self._exif_card.setStyleSheet(
                "QFrame { background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 8px; }"
            )
            self._deps_label.setText("exiftool 정상 로드됨")
            self._deps_label.setStyleSheet("color: #10b981; font-weight: 700; font-size: 12px;")
        except FileNotFoundError:
            self._exif_label.setText("exiftool 없음 - 메타데이터 보존이 제한됩니다")
            self._exif_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #92400e; background: transparent; border: none;"
            )
            self._exif_card.setStyleSheet(
                "QFrame { background: #fffbeb; border: 1.5px solid #fde68a; border-radius: 8px; }"
            )
            self._deps_label.setText("exiftool을 assets 폴더에 넣거나 PATH에 추가해 주세요.")
            self._deps_label.setStyleSheet("color: #f59e0b; font-weight: 700; font-size: 12px;")

    def validate(self) -> bool:
        if not self._input_row.path:
            QMessageBox.warning(self, "입력 폴더 없음", "입력 폴더를 선택해 주세요.")
            return False
        if not Path(self._input_row.path).is_dir():
            QMessageBox.warning(self, "입력 폴더 없음", "선택한 입력 폴더가 존재하지 않습니다.")
            return False
        if not self._output_row.path:
            QMessageBox.warning(self, "출력 폴더 없음", "출력 폴더를 선택해 주세요.")
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
            max_duration_seconds=float(self._duration_spin.value()),
        )

    @property
    def run_button(self) -> QPushButton:
        return self._run_btn

    @property
    def back_button(self) -> QPushButton:
        return self._back_btn
