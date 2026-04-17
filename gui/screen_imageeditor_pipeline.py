# -*- coding: utf-8 -*-
"""Pipeline builder screen: file list + interactive preview + transform pipeline editor."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PIL import Image
from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ImageEditor.core.image_loader import get_image_files, load_image
from ImageEditor.core.transform_pipeline import (
    CropMode, CropTransform, ResizeMode, ResizeTransform,
    RotateTransform, TransformPipeline,
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
        """Return (left, top, right, bottom) in 0–1 image-space coords, or None."""
        if not self.has_selection():
            return None
        ir = self._image_rect()
        if ir.width() == 0 or ir.height() == 0:
            return None

        x1 = min(self._drag_start.x(), self._drag_end.x())
        y1 = min(self._drag_start.y(), self._drag_end.y())
        x2 = max(self._drag_start.x(), self._drag_end.x())
        y2 = max(self._drag_start.y(), self._drag_end.y())

        x1 = max(ir.left(),   x1)
        y1 = max(ir.top(),    y1)
        x2 = min(ir.right(),  x2)
        y2 = min(ir.bottom(), y2)

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

    # ── mouse events ─────────────────────────────────────────────────────────

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

    # ── painting ──────────────────────────────────────────────────────────────

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

        x1 = max(ir.left(),   x1)
        y1 = max(ir.top(),    y1)
        x2 = min(ir.right(),  x2)
        y2 = min(ir.bottom(), y2)

        cw, ch = x2 - x1, y2 - y1
        if cw <= 0 or ch <= 0:
            return

        # Darken outside the crop rect
        overlay = QColor(0, 0, 0, 120)
        painter.fillRect(ir.left(), ir.top(),    ir.width(),       y1 - ir.top(),    overlay)
        painter.fillRect(ir.left(), y2,           ir.width(),       ir.bottom() - y2, overlay)
        painter.fillRect(ir.left(), y1,           x1 - ir.left(),   ch,               overlay)
        painter.fillRect(x2,        y1,           ir.right() - x2,  ch,               overlay)

        # Amber dashed border
        pen = QPen(QColor("#d97706"))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(x1, y1, cw, ch)

        # Rule-of-thirds grid
        pen2 = QPen(QColor(255, 255, 255, 80))
        pen2.setWidth(1)
        painter.setPen(pen2)
        for i in (1, 2):
            painter.drawLine(x1 + cw * i // 3, y1, x1 + cw * i // 3, y2)
            painter.drawLine(x1, y1 + ch * i // 3, x2, y1 + ch * i // 3)

        # Pixel-size label
        if self._pixmap and ir.width() > 0 and ir.height() > 0:
            img_cw = round(cw / ir.width()  * self._pixmap.width())
            img_ch = round(ch / ir.height() * self._pixmap.height())
            painter.setPen(QColor("white"))
            painter.drawText(QRect(x1, y1, cw, ch), Qt.AlignCenter, f"{img_cw} × {img_ch}")


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
        mode  = self._mode_cb.currentData()
        fit   = mode == "fit_within"
        byw   = mode == "by_width"
        byh   = mode == "by_height"
        pct   = mode == "by_percent"
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
            w = int(self._width_edit.text())  if self._width_edit.isVisible()  else 0
            h = int(self._height_edit.text()) if self._height_edit.isVisible() else 0
            p = float(self._pct_edit.text())  if self._pct_edit.isVisible()    else 100.0
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
        self._transform = ResizeTransform(mode=mode_map[mode], width=w, height=h, percent=p)
        self.accept()

    def get_transform(self) -> Optional[ResizeTransform]:
        return self._transform


# ── Rotate dialog ─────────────────────────────────────────────────────────────

class RotateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("회전 설정")
        self.setModal(True)
        self.setMinimumWidth(360)
        self._transform: Optional[RotateTransform] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 20)

        preset_lbl = QLabel("빠른 선택")
        preset_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #374151;")
        layout.addWidget(preset_lbl)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(8)
        for label, angle in [("90° 시계방향", 90), ("90° 반시계", -90), ("180°", 180)]:
            btn = QPushButton(label)
            btn.setStyleSheet(_BTN_ADD_STYLE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, a=angle: self._select_preset(a))
            presets_row.addWidget(btn)
        layout.addLayout(presets_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border: 1px solid #e5e7eb; margin: 4px 0;")
        layout.addWidget(sep)

        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._angle_edit = QLineEdit("90")
        self._angle_edit.setStyleSheet(_INPUT_STYLE)
        self._angle_edit.setPlaceholderText("예: 45, -30, 270")
        form.addRow(QLabel("각도 직접 입력 (°)"), self._angle_edit)
        layout.addLayout(form)

        note = QLabel("양수 = 시계방향, 음수 = 반시계방향")
        note.setStyleSheet("font-size: 11px; color: #6b7280;")
        layout.addWidget(note)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("추가")
        btn_box.button(QDialogButtonBox.Cancel).setText("취소")
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _select_preset(self, angle: int) -> None:
        self._transform = RotateTransform(angle=angle)
        self.accept()

    def _on_ok(self) -> None:
        try:
            angle = int(self._angle_edit.text())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "정수 각도를 입력해 주세요.")
            return
        if angle % 360 == 0:
            QMessageBox.warning(self, "입력 오류", "0° 회전은 아무 변화가 없습니다.")
            return
        self._transform = RotateTransform(angle=angle)
        self.accept()

    def get_transform(self) -> Optional[RotateTransform]:
        return self._transform


# ── Crop dialog (center-based) ────────────────────────────────────────────────

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
        self.setWindowTitle("자르기 설정 (중앙 기준)")
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
        self._preset_cb.setCurrentIndex(4)
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
    def __init__(self, index: int, description: str, on_remove, parent=None):
        super().__init__(parent)
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
        self._crop_active = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ────────────────────────────────────────────────────────────
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
            "파일을 클릭하여 미리보기 → 크기 조절·자르기·회전을 파이프라인에 추가 → 변환 시작"
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

        self._preview_info_lbl = QLabel()
        self._preview_info_lbl.setAlignment(Qt.AlignCenter)
        self._preview_info_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        center_layout.addWidget(self._preview_info_lbl)

        # Crop confirmation bar (hidden by default)
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
        self._confirm_crop_btn.clicked.connect(self._confirm_crop)

        self._cancel_crop_btn = QPushButton("✕ 취소")
        self._cancel_crop_btn.setStyleSheet(
            "QPushButton { background: white; color: #6b7280; font-size: 12px; font-weight: 700;"
            "  border-radius: 6px; border: 1px solid #d1d5db; padding: 5px 12px; }"
            "QPushButton:hover { border-color: #ef4444; color: #ef4444; }"
        )
        self._cancel_crop_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_crop_btn.clicked.connect(self._cancel_crop)

        crop_bar_layout.addWidget(crop_hint, 1)
        crop_bar_layout.addWidget(self._confirm_crop_btn)
        crop_bar_layout.addWidget(self._cancel_crop_btn)
        self._crop_bar.setVisible(False)
        center_layout.addWidget(self._crop_bar)

        body.addWidget(center_group, 1)

        # Panel 3: Pipeline ───────────────────────────────────────────────────
        right_group = QGroupBox("  변환 파이프라인")
        right_group.setStyleSheet(_GROUPBOX_STYLE)
        right_group.setFixedWidth(260)
        right_layout = QVBoxLayout(right_group)
        right_layout.setContentsMargins(8, 12, 8, 12)
        right_layout.setSpacing(6)

        add_resize_btn = QPushButton("+ 크기 조절 추가")
        add_resize_btn.setStyleSheet(_BTN_ADD_STYLE)
        add_resize_btn.setCursor(Qt.PointingHandCursor)
        add_resize_btn.clicked.connect(self._add_resize)

        add_crop_btn = QPushButton("+ 자르기 (비율·중앙)")
        add_crop_btn.setStyleSheet(_BTN_ADD_STYLE)
        add_crop_btn.setCursor(Qt.PointingHandCursor)
        add_crop_btn.clicked.connect(self._add_crop)

        add_manual_crop_btn = QPushButton("+ 자르기 (영역 직접 선택)")
        add_manual_crop_btn.setStyleSheet(_BTN_ADD_STYLE)
        add_manual_crop_btn.setCursor(Qt.PointingHandCursor)
        add_manual_crop_btn.clicked.connect(self._add_crop_interactive)

        add_rotate_btn = QPushButton("+ 회전 추가")
        add_rotate_btn.setStyleSheet(_BTN_ADD_STYLE)
        add_rotate_btn.setCursor(Qt.PointingHandCursor)
        add_rotate_btn.clicked.connect(self._add_rotate)

        right_layout.addWidget(add_resize_btn)
        right_layout.addWidget(add_crop_btn)
        right_layout.addWidget(add_manual_crop_btn)
        right_layout.addWidget(add_rotate_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border: 1px solid #e5e7eb;")
        right_layout.addWidget(sep)

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

        self._update_pipeline_ui()

    # ── public API ────────────────────────────────────────────────────────────

    def load_files(self, input_folder: Path) -> None:
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

    # ── file selection ────────────────────────────────────────────────────────

    def _on_file_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._files):
            return
        self._cancel_crop()
        self._current_file = self._files[row]
        self._load_preview(apply_pipeline=not self._pipeline.is_empty())

    def _load_preview(self, apply_pipeline: bool) -> None:
        if not self._current_file:
            return
        try:
            img, _ = load_image(self._current_file, preview_only=True)
            self._original_img = img
            disp = self._pipeline.apply(img.copy()) if (apply_pipeline and not self._pipeline.is_empty()) else img
            px = _pil_to_pixmap(disp, 1200, 900)
            self._canvas.set_pixmap(px)
            w, h = img.size
            tag = " [파이프라인 적용됨]" if apply_pipeline and not self._pipeline.is_empty() else ""
            self._preview_info_lbl.setText(f"{self._current_file.name}  {w}×{h}{tag}")
        except Exception as e:
            self._canvas.set_pixmap(None)
            self._preview_info_lbl.setText(f"미리보기 불가: {e}")

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

    def _add_crop_interactive(self) -> None:
        if not self._current_file:
            QMessageBox.information(self, "파일 없음", "먼저 파일 목록에서 이미지를 선택하세요.")
            return
        self._load_preview(apply_pipeline=False)
        self._crop_active = True
        self._canvas.set_crop_mode(True)
        self._crop_bar.setVisible(True)

    def _confirm_crop(self) -> None:
        coords = self._canvas.get_crop_rect_normalized()
        if coords is None:
            QMessageBox.information(self, "선택 없음", "이미지에서 영역을 드래그하여 선택하세요.")
            return
        left, top, right, bottom = coords
        t = CropTransform(mode=CropMode.MANUAL, left=left, top=top, right=right, bottom=bottom)
        self._pipeline.transforms.append(t)
        self._cancel_crop()
        self._update_pipeline_ui()

    def _cancel_crop(self) -> None:
        self._crop_active = False
        self._canvas.set_crop_mode(False)
        self._crop_bar.setVisible(False)

    def _add_rotate(self) -> None:
        dlg = RotateDialog(self)
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
        while self._pipeline_items_layout.count() > 1:
            item = self._pipeline_items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        descs = self._pipeline.descriptions()
        for i, desc in enumerate(descs):
            widget = _PipelineItem(i + 1, desc, self._remove_transform)
            self._pipeline_items_layout.insertWidget(i, widget)

        self._empty_lbl.setVisible(not descs)

        # Auto real-time preview when not in interactive crop mode
        if self._current_file and not self._crop_active:
            self._load_preview(apply_pipeline=True)
