# -*- coding: utf-8 -*-
"""Pipeline builder screen: file list + interactive preview + inline transform controls."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PIL import Image
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QVBoxLayout, QWidget,
)

from ImageEditor.core.image_loader import load_image
from ImageEditor.core.transform_pipeline import (
    CropMode, CropTransform, ResizeMode, ResizeTransform,
    RotateTransform, TransformPipeline,
)
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
_SECTION_STYLE = """
    QGroupBox {
        font-size: 12px; font-weight: 700; color: #374151;
        border: 1px solid #e5e7eb; border-radius: 8px;
        margin-top: 10px; padding-top: 14px; background: #fafafa;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #374151;
    }
"""
_COMBO_STYLE = """
    QComboBox {
        border: 1.5px solid #d1d5db; border-radius: 6px; padding: 4px 8px;
        font-size: 12px; color: #111827; background: #f9fafb; min-height: 28px;
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
_SPIN_STYLE = (
    "QSpinBox, QDoubleSpinBox {"
    "  border: 1.5px solid #d1d5db; border-radius: 6px; padding: 3px 6px;"
    "  font-size: 12px; color: #111827; background: #f9fafb; min-height: 26px; }"
    "QSpinBox:focus, QDoubleSpinBox:focus { border-color: #d97706; }"
)
_ROT_BTN_STYLE = (
    "QPushButton { background: #f3f4f6; color: #374151; font-size: 13px; font-weight: 700;"
    "  border: 1.5px solid #d1d5db; border-radius: 6px; padding: 4px 0; }"
    "QPushButton:hover { background: #e5e7eb; border-color: #9ca3af; }"
    "QPushButton:pressed { background: #d1d5db; }"
)
_RESET_BTN_STYLE = (
    "QPushButton { background: white; color: #6b7280; font-size: 11px;"
    "  border: 1px solid #e5e7eb; border-radius: 5px; padding: 2px 8px; }"
    "QPushButton:hover { border-color: #ef4444; color: #ef4444; }"
)
_MANUAL_BTN_STYLE = (
    "QPushButton { background: #d97706; color: white; font-size: 12px; font-weight: 700;"
    "  border-radius: 6px; border: none; padding: 6px 10px; }"
    "QPushButton:hover { background: #b45309; }"
)

_CROP_PRESETS = [
    ("1:1 (정사각)", 1, 1),
    ("4:3", 4, 3),
    ("3:4 (세로)", 3, 4),
    ("16:9 (와이드)", 16, 9),
    ("9:16 (세로)", 9, 16),
    ("3:2 (DSLR)", 3, 2),
    ("2:3 (세로 DSLR)", 2, 3),
    ("직접 입력", 0, 0),
]


@dataclass
class OutputData:
    output_folder:     Path
    output_format:     str
    jpeg_quality:      int
    preserve_metadata: bool
    skip_existing:     bool


def _pil_to_pixmap(img: Image.Image, max_w: int, max_h: int) -> QPixmap:
    tmp = img.copy()
    tmp.thumbnail((max_w, max_h), Image.LANCZOS)
    rgb = tmp.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


# ── PreviewCanvas: interactive drag-to-crop ───────────────────────────────────

class PreviewCanvas(QWidget):
    """Image preview widget with optional drag-to-crop overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._crop_mode = False
        self._drag_start: Optional[QPoint] = None
        self._drag_end:   Optional[QPoint] = None
        self.setMinimumSize(360, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setStyleSheet(
            "background: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 6px;"
        )

    def set_pixmap(self, px: Optional[QPixmap]) -> None:
        self._pixmap = None if (px is None or px.isNull()) else px
        self._drag_start = None
        self._drag_end   = None
        self.update()

    def set_crop_mode(self, active: bool) -> None:
        self._crop_mode = active
        self._drag_start = None
        self._drag_end   = None
        self.setCursor(Qt.CrossCursor if active else Qt.ArrowCursor)
        self.update()

    def has_selection(self) -> bool:
        return self._drag_start is not None and self._drag_end is not None

    def get_crop_rect_normalized(self) -> Optional[tuple]:
        if not self.has_selection():
            return None
        ir = self._image_rect()
        if ir.width() == 0 or ir.height() == 0:
            return None

        x1 = min(self._drag_start.x(), self._drag_end.x())
        y1 = min(self._drag_start.y(), self._drag_end.y())
        x2 = max(self._drag_start.x(), self._drag_end.x())
        y2 = max(self._drag_start.y(), self._drag_end.y())

        ir_right  = ir.x() + ir.width()
        ir_bottom = ir.y() + ir.height()
        x1 = max(ir.left(),  x1)
        y1 = max(ir.top(),   y1)
        x2 = min(ir_right,   x2)
        y2 = min(ir_bottom,  y2)

        if x2 <= x1 or y2 <= y1:
            return None

        left   = (x1 - ir.left()) / ir.width()
        top    = (y1 - ir.top())  / ir.height()
        right  = (x2 - ir.left()) / ir.width()
        bottom = (y2 - ir.top())  / ir.height()
        return (
            max(0.0, min(1.0, left)),
            max(0.0, min(1.0, top)),
            max(0.0, min(1.0, right)),
            max(0.0, min(1.0, bottom)),
        )

    def mousePressEvent(self, event) -> None:
        if self._crop_mode and event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            self._drag_end   = event.pos()
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._crop_mode and self._drag_start is not None:
            self._drag_end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._crop_mode and event.button() == Qt.LeftButton and self._drag_start:
            self._drag_end = event.pos()
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._pixmap is None:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(self.rect(), Qt.AlignCenter, "← 파일을 선택하세요")
            return

        ir = self._image_rect()
        painter.drawPixmap(ir, self._pixmap)

        if self._crop_mode and self.has_selection():
            self._draw_crop_overlay(painter, ir)

    def _image_rect(self) -> QRect:
        if self._pixmap is None:
            return QRect(0, 0, self.width(), self.height())
        pw, ph = self._pixmap.width(), self._pixmap.height()
        cw, ch = self.width(), self.height()
        if pw == 0 or ph == 0 or cw == 0 or ch == 0:
            return QRect(0, 0, cw, ch)
        scale = min(cw / pw, ch / ph)
        nw = int(pw * scale)
        nh = int(ph * scale)
        x = (cw - nw) // 2
        y = (ch - nh) // 2
        return QRect(x, y, nw, nh)

    def _draw_crop_overlay(self, painter: QPainter, ir: QRect) -> None:
        x1 = min(self._drag_start.x(), self._drag_end.x())
        y1 = min(self._drag_start.y(), self._drag_end.y())
        x2 = max(self._drag_start.x(), self._drag_end.x())
        y2 = max(self._drag_start.y(), self._drag_end.y())

        ir_right  = ir.x() + ir.width()
        ir_bottom = ir.y() + ir.height()
        x1 = max(ir.left(), x1);  y1 = max(ir.top(),  y1)
        x2 = min(ir_right,  x2);  y2 = min(ir_bottom, y2)

        cw, ch = x2 - x1, y2 - y1
        if cw <= 0 or ch <= 0:
            return

        overlay = QColor(0, 0, 0, 120)
        painter.fillRect(ir.left(), ir.top(),  ir.width(),      y1 - ir.top(),    overlay)
        painter.fillRect(ir.left(), y2,         ir.width(),      ir_bottom - y2,   overlay)
        painter.fillRect(ir.left(), y1,         x1 - ir.left(), ch,               overlay)
        painter.fillRect(x2,        y1,         ir_right - x2,  ch,               overlay)

        pen = QPen(QColor("#d97706"))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(x1, y1, cw, ch)

        pen2 = QPen(QColor(255, 255, 255, 80))
        pen2.setWidth(1)
        painter.setPen(pen2)
        for i in (1, 2):
            painter.drawLine(x1 + cw * i // 3, y1, x1 + cw * i // 3, y2)
            painter.drawLine(x1, y1 + ch * i // 3, x2, y1 + ch * i // 3)

        if self._pixmap and ir.width() > 0 and ir.height() > 0:
            img_cw = round(cw / ir.width()  * self._pixmap.width())
            img_ch = round(ch / ir.height() * self._pixmap.height())
            g = math.gcd(img_cw, img_ch) if (img_cw > 0 and img_ch > 0) else 1
            ratio_str = f"{img_cw // g}:{img_ch // g}"
            painter.setPen(QColor("white"))
            painter.drawText(
                QRect(x1, y1, cw, ch), Qt.AlignCenter,
                f"{img_cw} × {img_ch}  ({ratio_str})"
            )


# ── Main pipeline screen ──────────────────────────────────────────────────────

class ImageEditorPipelineScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: List[Path] = []
        self._current_file: Optional[Path] = None
        self._original_img: Optional[Image.Image] = None
        self._pipeline = TransformPipeline()
        self._crop_active = False
        self._rotate_angle: int = 0
        self._manual_crop_coords: Optional[tuple] = None
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ────────────────────────────────────────────────────────────
        header_widget = QWidget()
        header_widget.setStyleSheet("background: #f3f4f6;")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(40, 20, 40, 8)
        header_layout.setSpacing(4)

        title = QLabel("변환 파이프라인 설정")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #111827; background: transparent;"
        )
        subtitle = QLabel(
            "파일 클릭으로 미리보기 → 오른쪽 패널에서 변환 설정 → 변환 시작"
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

        # Panel 1: File list ──────────────────────────────────────────────────
        left_group = QGroupBox("  파일 목록")
        left_group.setStyleSheet(_GROUPBOX_STYLE)
        left_group.setFixedWidth(210)
        left_layout = QVBoxLayout(left_group)
        left_layout.setContentsMargins(8, 12, 8, 12)
        left_layout.setSpacing(6)

        self._file_list = QListWidget()
        self._file_list.setStyleSheet(
            "QListWidget { border: none; background: #f9fafb; font-size: 12px; color: #111827; }"
            "QListWidget::item { padding: 4px 6px; border-radius: 4px; color: #111827; }"
            "QListWidget::item:selected { background: #fef3c7; color: #92400e; }"
            "QListWidget::item:hover { background: #f3f4f6; color: #111827; }"
        )
        self._file_list.currentRowChanged.connect(self._on_file_selected)
        left_layout.addWidget(self._file_list, 1)

        self._file_count_lbl = QLabel("파일 없음")
        self._file_count_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        self._file_count_lbl.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self._file_count_lbl)

        body.addWidget(left_group)

        # Panel 2: Preview ────────────────────────────────────────────────────
        center_group = QGroupBox("  미리보기")
        center_group.setStyleSheet(_GROUPBOX_STYLE)
        center_layout = QVBoxLayout(center_group)
        center_layout.setContentsMargins(8, 12, 8, 8)
        center_layout.setSpacing(6)

        self._canvas = PreviewCanvas()
        center_layout.addWidget(self._canvas, 1)

        ba_row = QHBoxLayout()
        ba_row.setContentsMargins(0, 0, 0, 0)
        self._before_after_btn = QPushButton("원본 보기")
        self._before_after_btn.setCheckable(True)
        self._before_after_btn.setFixedHeight(26)
        self._before_after_btn.setCursor(Qt.PointingHandCursor)
        self._before_after_btn.setStyleSheet(
            "QPushButton { font-size: 11px; font-weight: 600; border: 1.5px solid #d1d5db;"
            "  border-radius: 5px; padding: 0 10px; background: white; color: #374151; }"
            "QPushButton:hover { border-color: #9ca3af; }"
            "QPushButton:checked { background: #fef3c7; border-color: #d97706; color: #92400e; }"
        )
        self._before_after_btn.clicked.connect(self._toggle_preview)
        ba_row.addStretch()
        ba_row.addWidget(self._before_after_btn)
        center_layout.addLayout(ba_row)

        self._preview_info_lbl = QLabel()
        self._preview_info_lbl.setAlignment(Qt.AlignCenter)
        self._preview_info_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        center_layout.addWidget(self._preview_info_lbl)

        # Crop confirmation bar
        self._crop_bar = QWidget()
        self._crop_bar.setStyleSheet(
            "background: #fffbeb; border: 1.5px solid #d97706; border-radius: 6px;"
        )
        crop_bar_layout = QHBoxLayout(self._crop_bar)
        crop_bar_layout.setContentsMargins(10, 6, 10, 6)
        crop_bar_layout.setSpacing(8)

        crop_hint = QLabel("이미지에서 영역을 드래그하여 선택하세요")
        crop_hint.setStyleSheet("font-size: 12px; color: #92400e;")

        self._confirm_crop_btn = QPushButton("✓ 자르기 확인")
        self._confirm_crop_btn.setStyleSheet(
            "QPushButton { background: #d97706; color: white; font-size: 12px; font-weight: 700;"
            "  border-radius: 6px; border: none; padding: 5px 12px; }"
            "QPushButton:hover { background: #b45309; }"
        )
        self._confirm_crop_btn.setCursor(Qt.PointingHandCursor)
        self._confirm_crop_btn.clicked.connect(self._confirm_manual_crop)

        self._cancel_crop_btn = QPushButton("✕ 취소")
        self._cancel_crop_btn.setStyleSheet(
            "QPushButton { background: white; color: #6b7280; font-size: 12px; font-weight: 700;"
            "  border-radius: 6px; border: 1px solid #d1d5db; padding: 5px 12px; }"
            "QPushButton:hover { border-color: #ef4444; color: #ef4444; }"
        )
        self._cancel_crop_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_crop_btn.clicked.connect(self._cancel_manual_crop)

        crop_bar_layout.addWidget(crop_hint, 1)
        crop_bar_layout.addWidget(self._confirm_crop_btn)
        crop_bar_layout.addWidget(self._cancel_crop_btn)
        self._crop_bar.setVisible(False)
        center_layout.addWidget(self._crop_bar)

        body.addWidget(center_group, 1)

        # Panel 3: Inline transform controls ─────────────────────────────────
        right_group = QGroupBox("  변환 설정")
        right_group.setStyleSheet(_GROUPBOX_STYLE)
        right_group.setFixedWidth(280)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        right_content = QWidget()
        right_content.setStyleSheet("background: transparent;")
        rc_layout = QVBoxLayout(right_content)
        rc_layout.setContentsMargins(8, 4, 8, 8)
        rc_layout.setSpacing(8)

        # ── Rotate ────────────────────────────────────────────────────────
        rot_group = QGroupBox("  회전")
        rot_group.setStyleSheet(_SECTION_STYLE)
        rot_layout = QVBoxLayout(rot_group)
        rot_layout.setContentsMargins(8, 12, 8, 10)
        rot_layout.setSpacing(6)

        rot_btn_row = QHBoxLayout()
        rot_btn_row.setSpacing(4)
        for label, slot in [("90°↻", self._rotate_cw), ("90°↺", self._rotate_ccw), ("180°", self._rotate_180)]:
            btn = QPushButton(label)
            btn.setFixedHeight(34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_ROT_BTN_STYLE)
            btn.clicked.connect(slot)
            rot_btn_row.addWidget(btn)
        rot_layout.addLayout(rot_btn_row)

        rot_status_row = QHBoxLayout()
        rot_status_row.setSpacing(6)
        self._rot_lbl = QLabel("현재: 0°")
        self._rot_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        reset_rot = QPushButton("초기화")
        reset_rot.setFixedHeight(22)
        reset_rot.setCursor(Qt.PointingHandCursor)
        reset_rot.setStyleSheet(_RESET_BTN_STYLE)
        reset_rot.clicked.connect(self._reset_rotate)
        rot_status_row.addWidget(self._rot_lbl, 1)
        rot_status_row.addWidget(reset_rot)
        rot_layout.addLayout(rot_status_row)
        rc_layout.addWidget(rot_group)

        # ── Resize ────────────────────────────────────────────────────────
        resize_group = QGroupBox("  크기 조절")
        resize_group.setStyleSheet(_SECTION_STYLE)
        resize_layout = QVBoxLayout(resize_group)
        resize_layout.setContentsMargins(8, 12, 8, 10)
        resize_layout.setSpacing(6)

        self._resize_cb = QCheckBox("사용")
        self._resize_cb.setStyleSheet("font-size: 12px; color: #374151;")
        self._resize_cb.toggled.connect(self._on_resize_toggled)
        resize_layout.addWidget(self._resize_cb)

        self._resize_controls = QWidget()
        self._resize_controls.setStyleSheet("background: transparent;")
        rcc = QVBoxLayout(self._resize_controls)
        rcc.setContentsMargins(0, 0, 0, 0)
        rcc.setSpacing(5)

        self._resize_mode_cb = QComboBox()
        self._resize_mode_cb.addItem("최대 크기 이내 (비율 유지)", "fit_within")
        self._resize_mode_cb.addItem("너비 지정 (높이 자동)", "by_width")
        self._resize_mode_cb.addItem("높이 지정 (너비 자동)", "by_height")
        self._resize_mode_cb.addItem("비율 (%)", "by_percent")
        self._resize_mode_cb.addItem("정확한 크기", "exact")
        self._resize_mode_cb.setStyleSheet(_COMBO_STYLE)
        self._resize_mode_cb.currentIndexChanged.connect(self._on_resize_mode_changed)
        rcc.addWidget(self._resize_mode_cb)

        self._resize_w_row = QWidget()
        self._resize_w_row.setStyleSheet("background: transparent;")
        rw_l = QHBoxLayout(self._resize_w_row)
        rw_l.setContentsMargins(0, 0, 0, 0)
        rw_l.setSpacing(6)
        self._resize_w_lbl = QLabel("너비")
        self._resize_w_lbl.setStyleSheet("font-size: 12px; color: #374151; min-width: 36px;")
        self._resize_w_spin = QSpinBox()
        self._resize_w_spin.setRange(1, 99999)
        self._resize_w_spin.setValue(1920)
        self._resize_w_spin.setSuffix(" px")
        self._resize_w_spin.setStyleSheet(_SPIN_STYLE)
        self._resize_w_spin.valueChanged.connect(self._rebuild_pipeline)
        rw_l.addWidget(self._resize_w_lbl)
        rw_l.addWidget(self._resize_w_spin, 1)
        rcc.addWidget(self._resize_w_row)

        self._resize_h_row = QWidget()
        self._resize_h_row.setStyleSheet("background: transparent;")
        rh_l = QHBoxLayout(self._resize_h_row)
        rh_l.setContentsMargins(0, 0, 0, 0)
        rh_l.setSpacing(6)
        self._resize_h_lbl = QLabel("높이")
        self._resize_h_lbl.setStyleSheet("font-size: 12px; color: #374151; min-width: 36px;")
        self._resize_h_spin = QSpinBox()
        self._resize_h_spin.setRange(1, 99999)
        self._resize_h_spin.setValue(1080)
        self._resize_h_spin.setSuffix(" px")
        self._resize_h_spin.setStyleSheet(_SPIN_STYLE)
        self._resize_h_spin.valueChanged.connect(self._rebuild_pipeline)
        rh_l.addWidget(self._resize_h_lbl)
        rh_l.addWidget(self._resize_h_spin, 1)
        rcc.addWidget(self._resize_h_row)

        self._resize_pct_row = QWidget()
        self._resize_pct_row.setStyleSheet("background: transparent;")
        rp_l = QHBoxLayout(self._resize_pct_row)
        rp_l.setContentsMargins(0, 0, 0, 0)
        rp_l.setSpacing(6)
        rp_l.addWidget(QLabel("비율"))
        self._resize_pct_spin = QDoubleSpinBox()
        self._resize_pct_spin.setRange(1.0, 1000.0)
        self._resize_pct_spin.setValue(50.0)
        self._resize_pct_spin.setSuffix(" %")
        self._resize_pct_spin.setSingleStep(5.0)
        self._resize_pct_spin.setStyleSheet(_SPIN_STYLE)
        self._resize_pct_spin.valueChanged.connect(self._rebuild_pipeline)
        rp_l.addWidget(self._resize_pct_spin, 1)
        rcc.addWidget(self._resize_pct_row)

        resize_layout.addWidget(self._resize_controls)
        self._resize_controls.setVisible(False)
        rc_layout.addWidget(resize_group)

        # ── Crop ──────────────────────────────────────────────────────────
        crop_group = QGroupBox("  자르기")
        crop_group.setStyleSheet(_SECTION_STYLE)
        crop_layout = QVBoxLayout(crop_group)
        crop_layout.setContentsMargins(8, 12, 8, 10)
        crop_layout.setSpacing(6)

        self._crop_mode_cb = QComboBox()
        self._crop_mode_cb.addItem("사용 안함", "off")
        self._crop_mode_cb.addItem("비율 중앙 자르기", "aspect")
        self._crop_mode_cb.addItem("픽셀 크기 중앙 자르기", "pixels")
        self._crop_mode_cb.addItem("영역 직접 선택", "manual")
        self._crop_mode_cb.setStyleSheet(_COMBO_STYLE)
        self._crop_mode_cb.currentIndexChanged.connect(self._on_crop_mode_changed)
        crop_layout.addWidget(self._crop_mode_cb)

        # Aspect ratio controls
        self._crop_aspect_widget = QWidget()
        self._crop_aspect_widget.setStyleSheet("background: transparent;")
        ca_layout = QVBoxLayout(self._crop_aspect_widget)
        ca_layout.setContentsMargins(0, 0, 0, 0)
        ca_layout.setSpacing(4)

        self._crop_preset_cb = QComboBox()
        for label, _, _ in _CROP_PRESETS:
            self._crop_preset_cb.addItem(label)
        self._crop_preset_cb.setCurrentIndex(3)
        self._crop_preset_cb.setStyleSheet(_COMBO_STYLE)
        self._crop_preset_cb.currentIndexChanged.connect(self._on_crop_preset_changed)
        ca_layout.addWidget(self._crop_preset_cb)

        self._crop_custom_row = QWidget()
        self._crop_custom_row.setStyleSheet("background: transparent;")
        cc_l = QHBoxLayout(self._crop_custom_row)
        cc_l.setContentsMargins(0, 0, 0, 0)
        cc_l.setSpacing(4)
        self._crop_ar_num = QSpinBox()
        self._crop_ar_num.setRange(1, 999)
        self._crop_ar_num.setValue(16)
        self._crop_ar_num.setStyleSheet(_SPIN_STYLE)
        self._crop_ar_num.valueChanged.connect(self._rebuild_pipeline)
        colon = QLabel(":")
        colon.setAlignment(Qt.AlignCenter)
        colon.setStyleSheet("font-size: 14px; font-weight: 700; color: #374151;")
        self._crop_ar_den = QSpinBox()
        self._crop_ar_den.setRange(1, 999)
        self._crop_ar_den.setValue(9)
        self._crop_ar_den.setStyleSheet(_SPIN_STYLE)
        self._crop_ar_den.valueChanged.connect(self._rebuild_pipeline)
        cc_l.addWidget(self._crop_ar_num, 1)
        cc_l.addWidget(colon)
        cc_l.addWidget(self._crop_ar_den, 1)
        self._crop_custom_row.setVisible(False)
        ca_layout.addWidget(self._crop_custom_row)
        self._crop_aspect_widget.setVisible(False)
        crop_layout.addWidget(self._crop_aspect_widget)

        # Pixel crop controls
        self._crop_pixel_widget = QWidget()
        self._crop_pixel_widget.setStyleSheet("background: transparent;")
        cp_layout = QVBoxLayout(self._crop_pixel_widget)
        cp_layout.setContentsMargins(0, 0, 0, 0)
        cp_layout.setSpacing(4)

        pw_row = QHBoxLayout()
        pw_row.setSpacing(6)
        pw_row.addWidget(QLabel("너비"))
        self._crop_px_w = QSpinBox()
        self._crop_px_w.setRange(1, 99999)
        self._crop_px_w.setValue(1920)
        self._crop_px_w.setSuffix(" px")
        self._crop_px_w.setStyleSheet(_SPIN_STYLE)
        self._crop_px_w.valueChanged.connect(self._rebuild_pipeline)
        pw_row.addWidget(self._crop_px_w, 1)
        cp_layout.addLayout(pw_row)

        ph_row = QHBoxLayout()
        ph_row.setSpacing(6)
        ph_row.addWidget(QLabel("높이"))
        self._crop_px_h = QSpinBox()
        self._crop_px_h.setRange(1, 99999)
        self._crop_px_h.setValue(1080)
        self._crop_px_h.setSuffix(" px")
        self._crop_px_h.setStyleSheet(_SPIN_STYLE)
        self._crop_px_h.valueChanged.connect(self._rebuild_pipeline)
        ph_row.addWidget(self._crop_px_h, 1)
        cp_layout.addLayout(ph_row)
        self._crop_pixel_widget.setVisible(False)
        crop_layout.addWidget(self._crop_pixel_widget)

        # Manual crop controls
        self._crop_manual_widget = QWidget()
        self._crop_manual_widget.setStyleSheet("background: transparent;")
        cm_layout = QVBoxLayout(self._crop_manual_widget)
        cm_layout.setContentsMargins(0, 0, 0, 0)
        cm_layout.setSpacing(4)
        drag_btn = QPushButton("이미지에서 영역 드래그")
        drag_btn.setCursor(Qt.PointingHandCursor)
        drag_btn.setStyleSheet(_MANUAL_BTN_STYLE)
        drag_btn.clicked.connect(self._start_manual_crop)
        cm_layout.addWidget(drag_btn)
        self._manual_coords_lbl = QLabel("선택된 영역 없음")
        self._manual_coords_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        self._manual_coords_lbl.setAlignment(Qt.AlignCenter)
        cm_layout.addWidget(self._manual_coords_lbl)
        self._crop_manual_widget.setVisible(False)
        crop_layout.addWidget(self._crop_manual_widget)

        rc_layout.addWidget(crop_group)

        # Pipeline summary
        self._pipeline_summary_lbl = QLabel("변환 없음 (파일 그대로 저장)")
        self._pipeline_summary_lbl.setStyleSheet(
            "font-size: 11px; color: #6b7280; padding: 6px 8px;"
            "background: #f3f4f6; border-radius: 6px; border: none;"
        )
        self._pipeline_summary_lbl.setWordWrap(True)
        self._pipeline_summary_lbl.setAlignment(Qt.AlignCenter)
        rc_layout.addWidget(self._pipeline_summary_lbl)
        rc_layout.addStretch()

        right_scroll.setWidget(right_content)
        right_outer_layout = QVBoxLayout(right_group)
        right_outer_layout.setContentsMargins(0, 0, 0, 0)
        right_outer_layout.addWidget(right_scroll, 1)

        body.addWidget(right_group)
        outer.addLayout(body, 1)

        # ── Output Settings Bar ────────────────────────────────────────────────
        _SCOMBO = (
            "QComboBox { border: 1.5px solid #d1d5db; border-radius: 5px; padding: 2px 6px;"
            "  font-size: 12px; font-weight: 600; color: #111827; background: #ffffff; min-height: 28px; }"
            "QComboBox:hover { border-color: #9ca3af; background: #f9fafb; }"
            "QComboBox:focus { border-color: #d97706; background: #ffffff; }"
            "QComboBox::drop-down { border: none; width: 16px; subcontrol-origin: padding;"
            "  subcontrol-position: right center; }"
            "QComboBox QAbstractItemView { font-size: 12px; color: #111827; background: #ffffff;"
            "  selection-background-color: #fef3c7; selection-color: #92400e;"
            "  border: 1.5px solid #d1d5db; outline: none; }"
        )

        def _blbl(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: #374151;"
            )
            return lbl

        out_bar = QWidget()
        out_bar.setObjectName("outBar")
        out_bar.setStyleSheet(
            "#outBar { background: #f8fafc; border-top: 1.5px solid #e2e8f0; }"
        )
        out_bar_layout = QHBoxLayout(out_bar)
        out_bar_layout.setContentsMargins(16, 8, 16, 8)
        out_bar_layout.setSpacing(8)

        out_bar_layout.addWidget(_blbl("출력 폴더"))
        self._out_folder_edit = QLineEdit()
        self._out_folder_edit.setPlaceholderText("출력 폴더를 선택하세요...")
        self._out_folder_edit.setReadOnly(True)
        self._out_folder_edit.setStyleSheet(
            "font-size: 11px; padding: 2px 8px; border: 1.5px solid #d1d5db;"
            "border-radius: 5px; background: #f9fafb; color: #111827; min-height: 26px;"
        )
        out_bar_layout.addWidget(self._out_folder_edit, 3)

        browse_out_btn = QPushButton("찾기")
        browse_out_btn.setFixedHeight(28)
        browse_out_btn.setCursor(Qt.PointingHandCursor)
        browse_out_btn.setStyleSheet(
            "QPushButton { font-size: 11px; font-weight: 600; background: #f3f4f6;"
            "  border: 1.5px solid #d1d5db; border-radius: 5px; padding: 0 10px; color: #374151; }"
            "QPushButton:hover { background: #e5e7eb; }"
        )
        browse_out_btn.clicked.connect(self._browse_output_folder)
        out_bar_layout.addWidget(browse_out_btn)

        _vsep1 = QFrame()
        _vsep1.setFrameShape(QFrame.VLine)
        _vsep1.setStyleSheet("color: #e2e8f0;")
        out_bar_layout.addWidget(_vsep1)

        out_bar_layout.addWidget(_blbl("포맷"))
        self._format_cb = QComboBox()
        self._format_cb.addItem("JPEG", OutputFormat.JPEG)
        self._format_cb.addItem("PNG",  OutputFormat.PNG)
        self._format_cb.addItem("WebP", OutputFormat.WEBP)
        self._format_cb.addItem("원본",  OutputFormat.KEEP)
        self._format_cb.setFixedWidth(80)
        self._format_cb.setStyleSheet(_SCOMBO)
        self._format_cb.currentIndexChanged.connect(self._on_format_changed)
        out_bar_layout.addWidget(self._format_cb)

        self._quality_bar_lbl = _blbl("품질")
        self._quality_cb = QComboBox()
        self._quality_cb.addItem("92", 92)
        self._quality_cb.addItem("95", 95)
        self._quality_cb.addItem("85", 85)
        self._quality_cb.addItem("75", 75)
        self._quality_cb.setFixedWidth(55)
        self._quality_cb.setStyleSheet(_SCOMBO)
        out_bar_layout.addWidget(self._quality_bar_lbl)
        out_bar_layout.addWidget(self._quality_cb)

        _vsep2 = QFrame()
        _vsep2.setFrameShape(QFrame.VLine)
        _vsep2.setStyleSheet("color: #e2e8f0;")
        out_bar_layout.addWidget(_vsep2)

        out_bar_layout.addWidget(_blbl("EXIF"))
        self._meta_cb = QComboBox()
        self._meta_cb.addItem("보전", True)
        self._meta_cb.addItem("무시", False)
        self._meta_cb.setFixedWidth(60)
        self._meta_cb.setStyleSheet(_SCOMBO)
        out_bar_layout.addWidget(self._meta_cb)

        out_bar_layout.addWidget(_blbl("중복"))
        self._skip_cb = QComboBox()
        self._skip_cb.addItem("건너뜀", True)
        self._skip_cb.addItem("덮어쓰기", False)
        self._skip_cb.setFixedWidth(75)
        self._skip_cb.setStyleSheet(_SCOMBO)
        out_bar_layout.addWidget(self._skip_cb)

        outer.addWidget(out_bar)
        self._on_format_changed()

        # ── Footer ────────────────────────────────────────────────────────────
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

        self._update_resize_fields()

    # ── Public API ────────────────────────────────────────────────────────────

    def load_files(self, files: List[Path], root_folder: Optional[Path] = None) -> None:
        self._files = list(files)
        self._current_file = None
        self._original_img = None
        self._cancel_manual_crop()

        # Set default output folder
        base = root_folder or (files[0].parent if files else None)
        if base:
            self._out_folder_edit.setText(str(base / "output"))

        self._file_list.clear()
        for f in self._files:
            item = QListWidgetItem(f.name)
            item.setToolTip(str(f))
            self._file_list.addItem(item)
        count = len(self._files)
        self._file_count_lbl.setText(f"총 {count}개 파일" if count else "지원 이미지 없음")
        self._canvas.set_pixmap(None)
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

    # ── File selection ────────────────────────────────────────────────────────

    def _on_file_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._files):
            return
        self._cancel_manual_crop()
        self._current_file = self._files[row]
        self._before_after_btn.setChecked(False)
        self._before_after_btn.setText("원본 보기")
        self._load_preview(apply_pipeline=not self._pipeline.is_empty())

    def _load_preview(self, apply_pipeline: bool) -> None:
        if not self._current_file:
            return
        try:
            img, _ = load_image(self._current_file, preview_only=True)
            self._original_img = img
            disp = (
                self._pipeline.apply(img.copy())
                if apply_pipeline and not self._pipeline.is_empty()
                else img
            )
            px = _pil_to_pixmap(disp, 1200, 900)
            self._canvas.set_pixmap(px)
            w, h = img.size
            tag = " [파이프라인 적용됨]" if apply_pipeline and not self._pipeline.is_empty() else ""
            self._preview_info_lbl.setText(f"{self._current_file.name}  {w}×{h}{tag}")
        except Exception as e:
            self._canvas.set_pixmap(None)
            self._preview_info_lbl.setText(f"미리보기 불가: {e}")

    # ── Rotate controls ───────────────────────────────────────────────────────

    def _rotate_cw(self) -> None:
        self._rotate_angle = (self._rotate_angle + 90) % 360
        self._rebuild_pipeline()

    def _rotate_ccw(self) -> None:
        self._rotate_angle = (self._rotate_angle - 90) % 360
        self._rebuild_pipeline()

    def _rotate_180(self) -> None:
        self._rotate_angle = (self._rotate_angle + 180) % 360
        self._rebuild_pipeline()

    def _reset_rotate(self) -> None:
        self._rotate_angle = 0
        self._rebuild_pipeline()

    # ── Resize controls ───────────────────────────────────────────────────────

    def _on_resize_toggled(self, checked: bool) -> None:
        self._resize_controls.setVisible(checked)
        self._rebuild_pipeline()

    def _on_resize_mode_changed(self) -> None:
        self._update_resize_fields()
        self._rebuild_pipeline()

    def _update_resize_fields(self) -> None:
        mode = self._resize_mode_cb.currentData()
        fit   = mode == "fit_within"
        byw   = mode == "by_width"
        byh   = mode == "by_height"
        pct   = mode == "by_percent"
        exact = mode == "exact"

        self._resize_w_row.setVisible(fit or byw or exact)
        self._resize_h_row.setVisible(fit or byh or exact)
        self._resize_pct_row.setVisible(pct)

        if fit:
            self._resize_w_lbl.setText("최대 너비")
            self._resize_h_lbl.setText("최대 높이")
        else:
            self._resize_w_lbl.setText("너비")
            self._resize_h_lbl.setText("높이")

    # ── Crop controls ─────────────────────────────────────────────────────────

    def _on_crop_mode_changed(self) -> None:
        mode = self._crop_mode_cb.currentData()
        self._crop_aspect_widget.setVisible(mode == "aspect")
        self._crop_pixel_widget.setVisible(mode == "pixels")
        self._crop_manual_widget.setVisible(mode == "manual")
        if mode != "manual":
            self._cancel_manual_crop()
        if mode == "manual":
            self._manual_crop_coords = None
            self._manual_coords_lbl.setText("선택된 영역 없음")
        self._rebuild_pipeline()

    def _on_crop_preset_changed(self) -> None:
        idx = self._crop_preset_cb.currentIndex()
        _, n, d = _CROP_PRESETS[idx]
        is_custom = (n == 0 and d == 0)
        self._crop_custom_row.setVisible(is_custom)
        if not is_custom and n > 0:
            self._crop_ar_num.blockSignals(True)
            self._crop_ar_den.blockSignals(True)
            self._crop_ar_num.setValue(n)
            self._crop_ar_den.setValue(d)
            self._crop_ar_num.blockSignals(False)
            self._crop_ar_den.blockSignals(False)
        self._rebuild_pipeline()

    def _start_manual_crop(self) -> None:
        if not self._current_file:
            QMessageBox.information(self, "파일 없음", "먼저 파일 목록에서 이미지를 선택하세요.")
            return
        self._load_preview(apply_pipeline=False)
        self._crop_active = True
        self._canvas.set_crop_mode(True)
        self._crop_bar.setVisible(True)

    def _confirm_manual_crop(self) -> None:
        coords = self._canvas.get_crop_rect_normalized()
        if coords is None:
            QMessageBox.information(self, "선택 없음", "이미지에서 영역을 드래그하여 선택하세요.")
            return
        self._manual_crop_coords = coords
        lp = round(coords[0] * 100)
        tp = round(coords[1] * 100)
        rp = round(coords[2] * 100)
        bp = round(coords[3] * 100)
        self._manual_coords_lbl.setText(f"({lp}%,{tp}%) → ({rp}%,{bp}%)")
        self._cancel_manual_crop()
        self._rebuild_pipeline()

    def _cancel_manual_crop(self) -> None:
        self._crop_active = False
        self._canvas.set_crop_mode(False)
        self._crop_bar.setVisible(False)

    # ── Pipeline rebuilding ───────────────────────────────────────────────────

    def _rebuild_pipeline(self) -> None:
        transforms = []

        if self._rotate_angle % 360 != 0:
            transforms.append(RotateTransform(angle=self._rotate_angle))

        if self._resize_cb.isChecked():
            mode_key = self._resize_mode_cb.currentData()
            mode_map = {
                "fit_within": ResizeMode.FIT_WITHIN,
                "by_width":   ResizeMode.BY_WIDTH,
                "by_height":  ResizeMode.BY_HEIGHT,
                "by_percent": ResizeMode.BY_PERCENT,
                "exact":      ResizeMode.EXACT,
            }
            transforms.append(ResizeTransform(
                mode=mode_map[mode_key],
                width=self._resize_w_spin.value(),
                height=self._resize_h_spin.value(),
                percent=self._resize_pct_spin.value(),
            ))

        crop_mode = self._crop_mode_cb.currentData()
        if crop_mode == "aspect":
            idx = self._crop_preset_cb.currentIndex()
            _, n, d = _CROP_PRESETS[idx]
            if n == 0 and d == 0:
                n = self._crop_ar_num.value()
                d = self._crop_ar_den.value()
            transforms.append(CropTransform(mode=CropMode.ASPECT_RATIO, ar_num=n, ar_den=d))
        elif crop_mode == "pixels":
            transforms.append(CropTransform(
                mode=CropMode.FIXED_PIXELS,
                width=self._crop_px_w.value(),
                height=self._crop_px_h.value(),
            ))
        elif crop_mode == "manual" and self._manual_crop_coords is not None:
            l, t, r, b = self._manual_crop_coords
            transforms.append(CropTransform(
                mode=CropMode.MANUAL, left=l, top=t, right=r, bottom=b,
            ))

        self._pipeline = TransformPipeline(transforms=transforms)
        self._update_summary()

        if self._current_file and not self._crop_active:
            self._load_preview(apply_pipeline=not self._before_after_btn.isChecked())

        # Update rotation label
        angle_display = self._rotate_angle % 360
        if angle_display == 0:
            self._rot_lbl.setText("현재: 0°")
        elif angle_display == 90:
            self._rot_lbl.setText("현재: 90° 시계방향")
        elif angle_display == 180:
            self._rot_lbl.setText("현재: 180°")
        elif angle_display == 270:
            self._rot_lbl.setText("현재: 90° 반시계방향")
        else:
            self._rot_lbl.setText(f"현재: {angle_display}°")

    def _update_summary(self) -> None:
        descs = self._pipeline.descriptions()
        if descs:
            self._pipeline_summary_lbl.setText(" → ".join(descs))
            self._pipeline_summary_lbl.setStyleSheet(
                "font-size: 11px; color: #92400e; padding: 6px 8px;"
                "background: #fef3c7; border-radius: 6px; border: none;"
            )
        else:
            self._pipeline_summary_lbl.setText("변환 없음 (파일 그대로 저장)")
            self._pipeline_summary_lbl.setStyleSheet(
                "font-size: 11px; color: #6b7280; padding: 6px 8px;"
                "background: #f3f4f6; border-radius: 6px; border: none;"
            )

    # ── Output settings ───────────────────────────────────────────────────────

    def _browse_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "출력 폴더 선택", self._out_folder_edit.text() or ""
        )
        if folder:
            self._out_folder_edit.setText(folder)

    def _on_format_changed(self) -> None:
        fmt = self._format_cb.currentData()
        show = fmt in (OutputFormat.JPEG, OutputFormat.WEBP)
        self._quality_bar_lbl.setVisible(show)
        self._quality_cb.setVisible(show)

    def validate_output(self) -> bool:
        if not self._out_folder_edit.text().strip():
            QMessageBox.warning(self, "출력 폴더 누락", "출력 폴더를 선택해 주세요.")
            return False
        return True

    def get_output_data(self) -> OutputData:
        return OutputData(
            output_folder=Path(self._out_folder_edit.text().strip()),
            output_format=self._format_cb.currentData(),
            jpeg_quality=self._quality_cb.currentData() or 92,
            preserve_metadata=bool(self._meta_cb.currentData()),
            skip_existing=bool(self._skip_cb.currentData()),
        )

    # ── Before/After toggle ───────────────────────────────────────────────────

    def _toggle_preview(self) -> None:
        show_original = self._before_after_btn.isChecked()
        self._before_after_btn.setText("결과 보기" if show_original else "원본 보기")
        if self._current_file:
            self._load_preview(apply_pipeline=not show_original)
