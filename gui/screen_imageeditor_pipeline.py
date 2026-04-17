# -*- coding: utf-8 -*-
"""Pipeline builder screen: file list + preview + transform pipeline editor."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PIL import Image
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget,
)

from ImageEditor.core.image_loader import get_image_files, load_image
from ImageEditor.core.transform_pipeline import (
    CropMode, CropTransform, ResizeMode, ResizeTransform, TransformPipeline,
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
_COMBO_STYLE = """
    QComboBox {
        border: 1.5px solid #d1d5db; border-radius: 6px; padding: 4px 8px;
        font-size: 12px; color: #111827; background: #f9fafb; min-height: 30px;
    }
    QComboBox:hover { border-color: #9ca3af; }
    QComboBox:focus { border-color: #d97706; background: #ffffff; }
    QComboBox::drop-down { border: none; width: 24px; }
    QComboBox QAbstractItemView {
        border: 1.5px solid #d1d5db; background: #ffffff;
        color: #111827; selection-background-color: #fef3c7;
        selection-color: #92400e; font-size: 12px; padding: 4px;
    }
"""
_INPUT_STYLE = (
    "font-size: 12px; padding: 4px 8px; border: 1.5px solid #d1d5db; "
    "border-radius: 6px; background: #f9fafb; color: #111827; min-height: 28px;"
)
_BTN_ADD_STYLE = (
    "QPushButton { background: #d97706; color: white; font-size: 12px; font-weight: 700;"
    "  border-radius: 6px; border: none; padding: 6px 12px; }"
    "QPushButton:hover { background: #b45309; }"
)
_BTN_REMOVE_STYLE = (
    "QPushButton { background: transparent; color: #ef4444; font-size: 14px; font-weight: 700;"
    "  border: none; padding: 0 4px; min-width: 24px; }"
    "QPushButton:hover { color: #dc2626; }"
)


def _pil_to_pixmap(img: Image.Image, max_w: int, max_h: int) -> QPixmap:
    """Scale PIL image to fit within (max_w, max_h), return QPixmap."""
    tmp = img.copy()
    tmp.thumbnail((max_w, max_h), Image.LANCZOS)
    rgb = tmp.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


# ── Resize dialog ─────────────────────────────────────────────────────────────

class ResizeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("크기 조절 설정")
        self.setModal(True)
        self.setMinimumWidth(400)
        self._transform: Optional[ResizeTransform] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 20)

        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._mode_cb = QComboBox()
        self._mode_cb.addItem("최대 크기 이내 (비율 유지, 이미 작으면 그대로)", "fit_within")
        self._mode_cb.addItem("너비 지정 — 높이는 비율 자동", "by_width")
        self._mode_cb.addItem("높이 지정 — 너비는 비율 자동", "by_height")
        self._mode_cb.addItem("비율(%) 로 축소/확대", "by_percent")
        self._mode_cb.addItem("정확한 크기 (비율 무시)", "exact")
        self._mode_cb.setStyleSheet(_COMBO_STYLE)
        self._mode_cb.currentIndexChanged.connect(self._update_fields)
        form.addRow(QLabel("조절 방식"), self._mode_cb)

        self._width_lbl  = QLabel("최대 너비 (px)")
        self._width_edit = QLineEdit("1920")
        self._width_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow(self._width_lbl, self._width_edit)

        self._height_lbl  = QLabel("최대 높이 (px)")
        self._height_edit = QLineEdit("1080")
        self._height_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow(self._height_lbl, self._height_edit)

        self._pct_lbl  = QLabel("비율 (%)")
        self._pct_edit = QLineEdit("50")
        self._pct_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow(self._pct_lbl, self._pct_edit)

        layout.addLayout(form)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("추가")
        btn_box.button(QDialogButtonBox.Cancel).setText("취소")
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._update_fields()

    def _update_fields(self) -> None:
        mode = self._mode_cb.currentData()
        fit = mode == "fit_within"
        byw = mode == "by_width"
        byh = mode == "by_height"
        pct = mode == "by_percent"
        exact = mode == "exact"

        self._width_lbl.setVisible(fit or byw or exact)
        self._width_edit.setVisible(fit or byw or exact)
        self._height_lbl.setVisible(fit or byh or exact)
        self._height_edit.setVisible(fit or byh or exact)
        self._pct_lbl.setVisible(pct)
        self._pct_edit.setVisible(pct)

        if fit:
            self._width_lbl.setText("최대 너비 (px)")
            self._height_lbl.setText("최대 높이 (px)")
        elif exact:
            self._width_lbl.setText("너비 (px)")
            self._height_lbl.setText("높이 (px)")
        elif byw:
            self._width_lbl.setText("너비 (px)")
        elif byh:
            self._height_lbl.setText("높이 (px)")

    def _on_ok(self) -> None:
        mode = self._mode_cb.currentData()
        try:
            w = int(self._width_edit.text()) if self._width_edit.isVisible() else 0
            h = int(self._height_edit.text()) if self._height_edit.isVisible() else 0
            p = float(self._pct_edit.text()) if self._pct_edit.isVisible() else 100.0
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "숫자 값을 입력해 주세요.")
            return

        mode_map = {
            "fit_within": ResizeMode.FIT_WITHIN,
            "by_width":   ResizeMode.BY_WIDTH,
            "by_height":  ResizeMode.BY_HEIGHT,
            "by_percent": ResizeMode.BY_PERCENT,
            "exact":      ResizeMode.EXACT,
        }
        self._transform = ResizeTransform(
            mode=mode_map[mode], width=w, height=h, percent=p
        )
        self.accept()

    def get_transform(self) -> Optional[ResizeTransform]:
        return self._transform


# ── Crop dialog ───────────────────────────────────────────────────────────────

_ASPECT_PRESETS = [
    ("원본 비율", None),
    ("1:1 (정사각)", (1, 1)),
    ("4:3 (기본 화면)", (4, 3)),
    ("3:4 (세로 사진)", (3, 4)),
    ("16:9 (와이드)", (16, 9)),
    ("9:16 (세로 영상)", (9, 16)),
    ("3:2 (DSLR 기본)", (3, 2)),
    ("2:3 (세로 DSLR)", (2, 3)),
    ("직접 입력", "custom"),
]


class CropDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("자르기 설정")
        self.setModal(True)
        self.setMinimumWidth(400)
        self._transform: Optional[CropTransform] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 20)

        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._mode_cb = QComboBox()
        self._mode_cb.addItem("가로세로 비율로 자르기 (중앙 기준)", "aspect")
        self._mode_cb.addItem("픽셀 크기로 자르기 (중앙 기준)", "pixels")
        self._mode_cb.setStyleSheet(_COMBO_STYLE)
        self._mode_cb.currentIndexChanged.connect(self._update_fields)
        form.addRow(QLabel("자르기 방식"), self._mode_cb)

        self._preset_lbl = QLabel("비율 프리셋")
        self._preset_cb = QComboBox()
        for label, _ in _ASPECT_PRESETS:
            self._preset_cb.addItem(label)
        self._preset_cb.setCurrentIndex(4)  # 16:9 default
        self._preset_cb.setStyleSheet(_COMBO_STYLE)
        self._preset_cb.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow(self._preset_lbl, self._preset_cb)

        self._ar_row_lbl = QLabel("비율 (가로:세로)")
        ar_row = QHBoxLayout()
        self._ar_num = QLineEdit("16")
        self._ar_num.setStyleSheet(_INPUT_STYLE)
        self._ar_den = QLineEdit("9")
        self._ar_den.setStyleSheet(_INPUT_STYLE)
        ar_colon = QLabel(":")
        ar_colon.setAlignment(Qt.AlignCenter)
        ar_row.addWidget(self._ar_num)
        ar_row.addWidget(ar_colon)
        ar_row.addWidget(self._ar_den)
        self._ar_row_widget = QWidget()
        self._ar_row_widget.setLayout(ar_row)
        form.addRow(self._ar_row_lbl, self._ar_row_widget)

        self._px_w_lbl  = QLabel("너비 (px)")
        self._px_w_edit = QLineEdit("1920")
        self._px_w_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow(self._px_w_lbl, self._px_w_edit)

        self._px_h_lbl  = QLabel("높이 (px)")
        self._px_h_edit = QLineEdit("1080")
        self._px_h_edit.setStyleSheet(_INPUT_STYLE)
        form.addRow(self._px_h_lbl, self._px_h_edit)

        layout.addLayout(form)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("추가")
        btn_box.button(QDialogButtonBox.Cancel).setText("취소")
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._update_fields()
        self._on_preset_changed()

    def _update_fields(self) -> None:
        is_aspect = self._mode_cb.currentData() == "aspect"
        for w in (self._preset_lbl, self._preset_cb, self._ar_row_lbl, self._ar_row_widget):
            w.setVisible(is_aspect)
        for w in (self._px_w_lbl, self._px_w_edit, self._px_h_lbl, self._px_h_edit):
            w.setVisible(not is_aspect)

    def _on_preset_changed(self) -> None:
        idx = self._preset_cb.currentIndex()
        _, val = _ASPECT_PRESETS[idx]
        is_custom = val == "custom"
        self._ar_row_lbl.setVisible(is_custom or val is None)
        self._ar_row_widget.setVisible(is_custom or val is None)
        if isinstance(val, tuple):
            self._ar_num.setText(str(val[0]))
            self._ar_den.setText(str(val[1]))
            self._ar_row_lbl.setVisible(True)
            self._ar_row_widget.setVisible(True)

    def _on_ok(self) -> None:
        mode = self._mode_cb.currentData()
        try:
            if mode == "aspect":
                n = int(self._ar_num.text())
                d = int(self._ar_den.text())
                if n <= 0 or d <= 0:
                    raise ValueError
                self._transform = CropTransform(mode=CropMode.ASPECT_RATIO, ar_num=n, ar_den=d)
            else:
                w = int(self._px_w_edit.text())
                h = int(self._px_h_edit.text())
                if w <= 0 or h <= 0:
                    raise ValueError
                self._transform = CropTransform(mode=CropMode.FIXED_PIXELS, width=w, height=h)
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "양수 숫자 값을 입력해 주세요.")
            return
        self.accept()

    def get_transform(self) -> Optional[CropTransform]:
        return self._transform


# ── Pipeline item widget ──────────────────────────────────────────────────────

class _PipelineItem(QWidget):
    """One row in the pipeline list: index + description + remove button."""

    def __init__(self, index: int, description: str, on_remove, parent=None):
        super().__init__(parent)
        self._on_remove = on_remove
        self._index = index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 4, 4)
        layout.setSpacing(6)

        num = QLabel(f"{index}.")
        num.setStyleSheet("font-size: 12px; font-weight: 700; color: #d97706; min-width: 20px;")
        num.setAlignment(Qt.AlignCenter)

        desc = QLabel(description)
        desc.setStyleSheet("font-size: 12px; color: #111827;")
        desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        remove_btn = QPushButton("✕")
        remove_btn.setStyleSheet(_BTN_REMOVE_STYLE)
        remove_btn.setFixedSize(24, 24)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.clicked.connect(lambda: on_remove(self._index - 1))

        layout.addWidget(num)
        layout.addWidget(desc, 1)
        layout.addWidget(remove_btn)

        self.setStyleSheet(
            "background: #fafafa; border: 1px solid #e5e7eb; border-radius: 6px;"
        )


# ── Main pipeline screen ──────────────────────────────────────────────────────

class ImageEditorPipelineScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: List[Path] = []
        self._current_file: Optional[Path] = None
        self._original_img: Optional[Image.Image] = None
        self._pipeline = TransformPipeline()
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── 헤더 (스크롤 밖) ───────────────────────────────────────────────────
        header_widget = QWidget()
        header_widget.setStyleSheet("background: #f3f4f6;")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(40, 24, 40, 8)
        header_layout.setSpacing(4)

        title = QLabel("변환 파이프라인 설정")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #111827; background: transparent;"
        )
        subtitle = QLabel(
            "파일을 클릭하여 미리보기 → 크기 조절·자르기를 파이프라인에 추가 → 변환 시작"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 12px; color: #6b7280; background: transparent;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        outer.addWidget(header_widget)

        # ── 3-panel body ───────────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setSpacing(12)
        body.setContentsMargins(16, 8, 16, 8)

        # ── Panel 1: File list ────────────────────────────────────────────────
        left_group = QGroupBox("  파일 목록")
        left_group.setStyleSheet(_GROUPBOX_STYLE)
        left_group.setFixedWidth(210)
        left_layout = QVBoxLayout(left_group)
        left_layout.setContentsMargins(8, 12, 8, 12)
        left_layout.setSpacing(6)

        self._file_list = QListWidget()
        self._file_list.setStyleSheet(
            "QListWidget { border: none; background: #f9fafb; font-size: 12px; }"
            "QListWidget::item { padding: 4px 6px; border-radius: 4px; }"
            "QListWidget::item:selected { background: #fef3c7; color: #92400e; }"
            "QListWidget::item:hover { background: #f3f4f6; }"
        )
        self._file_list.currentRowChanged.connect(self._on_file_selected)
        left_layout.addWidget(self._file_list, 1)

        self._file_count_lbl = QLabel("파일 없음")
        self._file_count_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        self._file_count_lbl.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self._file_count_lbl)

        body.addWidget(left_group)

        # ── Panel 2: Preview ──────────────────────────────────────────────────
        center_group = QGroupBox("  미리보기")
        center_group.setStyleSheet(_GROUPBOX_STYLE)
        center_layout = QVBoxLayout(center_group)
        center_layout.setContentsMargins(8, 12, 8, 12)
        center_layout.setSpacing(8)

        self._preview_lbl = QLabel("← 파일을 선택하세요")
        self._preview_lbl.setAlignment(Qt.AlignCenter)
        self._preview_lbl.setStyleSheet(
            "background: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 6px;"
            "color: #94a3b8; font-size: 13px;"
        )
        self._preview_lbl.setMinimumSize(360, 260)
        self._preview_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        center_layout.addWidget(self._preview_lbl, 1)

        self._preview_info_lbl = QLabel()
        self._preview_info_lbl.setAlignment(Qt.AlignCenter)
        self._preview_info_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        center_layout.addWidget(self._preview_info_lbl)

        self._preview_btn = QPushButton("파이프라인 적용 미리보기 새로고침")
        self._preview_btn.setCursor(Qt.PointingHandCursor)
        self._preview_btn.setStyleSheet(
            "QPushButton { border: 1.5px solid #d97706; color: #d97706; background: white;"
            "  font-size: 12px; font-weight: 700; border-radius: 6px; padding: 6px 12px; }"
            "QPushButton:hover { background: #fef3c7; }"
            "QPushButton:disabled { border-color: #d1d5db; color: #9ca3af; }"
        )
        self._preview_btn.clicked.connect(self._refresh_preview)
        center_layout.addWidget(self._preview_btn)

        body.addWidget(center_group, 1)

        # ── Panel 3: Pipeline ─────────────────────────────────────────────────
        right_group = QGroupBox("  변환 파이프라인")
        right_group.setStyleSheet(_GROUPBOX_STYLE)
        right_group.setFixedWidth(250)
        right_layout = QVBoxLayout(right_group)
        right_layout.setContentsMargins(8, 12, 8, 12)
        right_layout.setSpacing(8)

        add_resize_btn = QPushButton("+ 크기 조절 추가")
        add_resize_btn.setStyleSheet(_BTN_ADD_STYLE)
        add_resize_btn.setCursor(Qt.PointingHandCursor)
        add_resize_btn.clicked.connect(self._add_resize)

        add_crop_btn = QPushButton("+ 자르기 추가")
        add_crop_btn.setStyleSheet(_BTN_ADD_STYLE)
        add_crop_btn.setCursor(Qt.PointingHandCursor)
        add_crop_btn.clicked.connect(self._add_crop)

        right_layout.addWidget(add_resize_btn)
        right_layout.addWidget(add_crop_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border: 1px solid #e5e7eb;")
        right_layout.addWidget(sep)

        # scrollable pipeline item list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._pipeline_content = QWidget()
        self._pipeline_content.setStyleSheet("background: transparent;")
        self._pipeline_items_layout = QVBoxLayout(self._pipeline_content)
        self._pipeline_items_layout.setContentsMargins(0, 0, 0, 0)
        self._pipeline_items_layout.setSpacing(4)
        self._pipeline_items_layout.addStretch()
        scroll.setWidget(self._pipeline_content)
        right_layout.addWidget(scroll, 1)

        self._empty_lbl = QLabel("파이프라인이 비어있습니다.\n위 버튼으로 변환을 추가하세요.")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet("font-size: 11px; color: #9ca3af;")
        self._empty_lbl.setWordWrap(True)
        right_layout.addWidget(self._empty_lbl)

        clear_btn = QPushButton("파이프라인 초기화")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(
            "QPushButton { border: 1px solid #e5e7eb; color: #6b7280; background: white;"
            "  font-size: 11px; border-radius: 6px; padding: 4px 8px; }"
            "QPushButton:hover { border-color: #ef4444; color: #ef4444; }"
        )
        clear_btn.clicked.connect(self._clear_pipeline)
        right_layout.addWidget(clear_btn)

        body.addWidget(right_group)

        outer.addLayout(body, 1)

        # ── 고정 하단 버튼 ─────────────────────────────────────────────────────
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

        self._update_pipeline_ui()

    # ── public API ────────────────────────────────────────────────────────────

    def load_files(self, input_folder: Path) -> None:
        """Populate file list from the given folder."""
        self._files = get_image_files(input_folder)
        self._file_list.clear()
        for f in self._files:
            item = QListWidgetItem(f.name)
            item.setToolTip(str(f))
            self._file_list.addItem(item)
        count = len(self._files)
        self._file_count_lbl.setText(f"총 {count}개 파일" if count else "지원 이미지 없음")
        if self._files:
            self._file_list.setCurrentRow(0)

    def get_pipeline(self) -> TransformPipeline:
        return self._pipeline

    @property
    def run_button(self) -> QPushButton:
        return self._run_btn

    @property
    def back_button(self) -> QPushButton:
        return self._back_btn

    # ── slots / handlers ──────────────────────────────────────────────────────

    def _on_file_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._files):
            return
        self._current_file = self._files[row]
        self._load_preview(apply_pipeline=False)

    def _load_preview(self, apply_pipeline: bool) -> None:
        if not self._current_file:
            return
        try:
            img, _ = load_image(self._current_file, preview_only=True)
            self._original_img = img
            if apply_pipeline and not self._pipeline.is_empty():
                disp = self._pipeline.apply(img.copy())
            else:
                disp = img
            self._show_pixmap(disp)
            w, h = img.size
            tag = " [파이프라인 적용됨]" if apply_pipeline and not self._pipeline.is_empty() else ""
            self._preview_info_lbl.setText(f"{self._current_file.name}  {w}×{h}{tag}")
        except Exception as e:
            self._preview_lbl.setPixmap(QPixmap())
            self._preview_lbl.setText(f"미리보기 불가: {e}")
            self._preview_info_lbl.setText("")

    def _show_pixmap(self, img: Image.Image) -> None:
        pw = self._preview_lbl.width()  - 16
        ph = self._preview_lbl.height() - 16
        if pw < 50 or ph < 50:
            pw, ph = 400, 300
        px = _pil_to_pixmap(img, pw, ph)
        self._preview_lbl.setPixmap(px)

    def _refresh_preview(self) -> None:
        self._load_preview(apply_pipeline=True)

    # ── pipeline management ───────────────────────────────────────────────────

    def _add_resize(self) -> None:
        dlg = ResizeDialog(self)
        if dlg.exec() == QDialog.Accepted:
            t = dlg.get_transform()
            if t:
                self._pipeline.transforms.append(t)
                self._update_pipeline_ui()

    def _add_crop(self) -> None:
        dlg = CropDialog(self)
        if dlg.exec() == QDialog.Accepted:
            t = dlg.get_transform()
            if t:
                self._pipeline.transforms.append(t)
                self._update_pipeline_ui()

    def _remove_transform(self, index: int) -> None:
        if 0 <= index < len(self._pipeline.transforms):
            self._pipeline.transforms.pop(index)
            self._update_pipeline_ui()

    def _clear_pipeline(self) -> None:
        self._pipeline.transforms.clear()
        self._update_pipeline_ui()

    def _update_pipeline_ui(self) -> None:
        # Remove existing item widgets (not the stretch)
        while self._pipeline_items_layout.count() > 1:
            item = self._pipeline_items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        descs = self._pipeline.descriptions()
        for i, desc in enumerate(descs):
            widget = _PipelineItem(i + 1, desc, self._remove_transform)
            self._pipeline_items_layout.insertWidget(i, widget)

        self._empty_lbl.setVisible(not descs)
