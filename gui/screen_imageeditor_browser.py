# -*- coding: utf-8 -*-
"""Combined file browser screen: lazy folder tree + file list + preview + drop zone."""
from __future__ import annotations

import ctypes
import string
from pathlib import Path
from typing import List, Optional

from PIL import Image
from PySide6.QtCore import Qt, QMimeData, QUrl, QRect
from PySide6.QtGui import QColor, QDrag, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ImageEditor.core.image_loader import is_supported, load_image

_DUMMY = "__dummy__"


def _get_quick_access() -> list[tuple[str, Path]]:
    home = Path.home()
    candidates = [
        ("바탕화면", home / "Desktop"),
        ("바탕화면", home / "OneDrive" / "Desktop"),
        ("바탕화면", home / "OneDrive" / "바탕 화면"),
        ("문서", home / "Documents"),
        ("문서", home / "OneDrive" / "Documents"),
        ("문서", home / "OneDrive" / "문서"),
        ("사진", home / "Pictures"),
        ("사진", home / "OneDrive" / "Pictures"),
        ("사진", home / "OneDrive" / "사진"),
        ("다운로드", home / "Downloads"),
    ]
    seen_labels: set[str] = set()
    result: list[tuple[str, Path]] = []
    for label, path in candidates:
        if label not in seen_labels and path.exists():
            seen_labels.add(label)
            result.append((label, path))
    return result


def _get_drive_label(letter: str) -> str:
    buf = ctypes.create_unicode_buffer(256)
    try:
        ctypes.windll.kernel32.GetVolumeInformationW(
            f"{letter}:\\", buf, len(buf),
            None, None, None, None, 0,
        )
    except Exception:
        return ""
    return buf.value


def _get_drives() -> list[tuple[str, Path]]:
    result = []
    for letter in string.ascii_uppercase:
        p = Path(f"{letter}:\\")
        if p.exists():
            label = _get_drive_label(letter)
            display = f"{label} ({letter}:)" if label else f"로컬 디스크 ({letter}:)"
            result.append((display, p))
    return result


def _pil_to_pixmap(img: Image.Image, max_w: int, max_h: int) -> QPixmap:
    tmp = img.copy()
    tmp.thumbnail((max_w, max_h), Image.LANCZOS)
    rgb = tmp.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)


# ── Simple preview canvas ─────────────────────────────────────────────────────

class _SimplePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 6px;")

    def set_pixmap(self, px: Optional[QPixmap]) -> None:
        self._pixmap = px
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._pixmap is None:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(self.rect(), Qt.AlignCenter, "파일을 클릭하면\n미리보기가 표시됩니다")
            return
        pw, ph = self._pixmap.width(), self._pixmap.height()
        cw, ch = self.width(), self.height()
        if pw == 0 or ph == 0 or cw == 0 or ch == 0:
            return
        scale = min(cw / pw, ch / ph)
        nw, nh = int(pw * scale), int(ph * scale)
        x = (cw - nw) // 2
        y = (ch - nh) // 2
        painter.drawPixmap(QRect(x, y, nw, nh), self._pixmap)


# ── Draggable file list ───────────────────────────────────────────────────────

class _DraggableFileList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)

    def startDrag(self, supported_actions) -> None:
        item = self.currentItem()
        if not item:
            return
        path: Optional[Path] = item.data(Qt.UserRole)
        if not path:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


# ── File chip widget ──────────────────────────────────────────────────────────

class _FileChip(QWidget):
    def __init__(self, path: Path, on_remove, parent=None):
        super().__init__(parent)
        self.path = path
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        lbl = QLabel(path.name)
        lbl.setStyleSheet(
            "font-size: 11px; color: #1f2937; background: transparent; border: none;"
        )
        lbl.setMaximumWidth(130)
        lbl.setToolTip(str(path))

        btn = QPushButton("✕")
        btn.setFixedSize(16, 16)
        btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9ca3af; font-size: 10px; border: none; }"
            "QPushButton:hover { color: #ef4444; }"
        )
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: on_remove(path))

        layout.addWidget(lbl)
        layout.addWidget(btn)
        self.setStyleSheet(
            "QWidget { background: #fef3c7; border: 1px solid #d97706; border-radius: 10px; }"
        )
        self.setFixedHeight(24)


# ── Drop zone ─────────────────────────────────────────────────────────────────

class _DropZone(QWidget):
    def __init__(self, on_count_changed, parent=None):
        super().__init__(parent)
        self._on_count_changed = on_count_changed
        self._paths: List[Path] = []
        self.setAcceptDrops(True)
        self.setMinimumHeight(70)
        self.setMaximumHeight(100)
        self._normal_style = (
            "QWidget { background: #f9fafb; border: 2px dashed #d97706; border-radius: 8px; }"
        )
        self._hover_style = (
            "QWidget { background: #fef3c7; border: 2px dashed #d97706; border-radius: 8px; }"
        )
        self.setStyleSheet(self._normal_style)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 6)
        outer.setSpacing(4)

        self._hint = QLabel("파일을 여기에 드래그하거나 목록에서 더블클릭하여 선택")
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setStyleSheet(
            "font-size: 12px; color: #9ca3af; border: none; background: transparent;"
        )
        outer.addWidget(self._hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._chip_container = QWidget()
        self._chip_container.setStyleSheet("background: transparent;")
        self._chip_layout = QHBoxLayout(self._chip_container)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(6)
        self._chip_layout.addStretch()

        scroll.setWidget(self._chip_container)
        outer.addWidget(scroll)

    def add_file(self, path: Path) -> None:
        if path not in self._paths and is_supported(path):
            self._paths.append(path)
            self._refresh()
            self._on_count_changed(len(self._paths))

    def remove_file(self, path: Path) -> None:
        if path in self._paths:
            self._paths.remove(path)
            self._refresh()
            self._on_count_changed(len(self._paths))

    def get_files(self) -> List[Path]:
        return list(self._paths)

    def clear_all(self) -> None:
        self._paths.clear()
        self._refresh()
        self._on_count_changed(0)

    def _refresh(self) -> None:
        while self._chip_layout.count() > 1:
            item = self._chip_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for path in self._paths:
            chip = _FileChip(path, self.remove_file)
            self._chip_layout.insertWidget(self._chip_layout.count() - 1, chip)
        self._hint.setVisible(not self._paths)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self._hover_style)

    def dragLeaveEvent(self, event) -> None:
        self.setStyleSheet(self._normal_style)

    def dropEvent(self, event) -> None:
        self.setStyleSheet(self._normal_style)
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file():
                self.add_file(path)
        event.acceptProposedAction()


# ── Main browser screen ───────────────────────────────────────────────────────

class ImageEditorBrowserScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_folder: Optional[Path] = None
        self._build_ui()
        self._load_computer_tree()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #f3f4f6;")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(40, 18, 40, 10)
        h_layout.setSpacing(4)

        title = QLabel("파일 선택")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #111827; background: transparent;"
        )
        subtitle = QLabel(
            "왼쪽 폴더 트리에서 폴더 탐색 → 파일 클릭으로 미리보기 → 더블클릭 또는 드래그로 하단 선택 영역에 추가"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 12px; color: #6b7280; background: transparent;")
        h_layout.addWidget(title)
        h_layout.addWidget(subtitle)
        outer.addWidget(header)

        # ── 3-panel body ───────────────────────────────────────────────────────
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setSpacing(0)
        body_layout.setContentsMargins(0, 0, 0, 0)

        # Panel 1: Folder tree (240px)
        tree_frame = QFrame()
        tree_frame.setStyleSheet("QFrame { border-right: 1px solid #e5e7eb; background: #ffffff; }")
        tree_frame.setFixedWidth(240)
        tree_vlayout = QVBoxLayout(tree_frame)
        tree_vlayout.setContentsMargins(0, 0, 0, 0)
        tree_vlayout.setSpacing(0)

        tree_header = QWidget()
        tree_header.setFixedHeight(34)
        tree_header.setStyleSheet("background: #f9fafb; border-bottom: 1px solid #e5e7eb;")
        th_layout = QHBoxLayout(tree_header)
        th_layout.setContentsMargins(12, 0, 12, 0)
        folder_lbl = QLabel("폴더 탐색")
        folder_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #374151;")
        th_layout.addWidget(folder_lbl)
        tree_vlayout.addWidget(tree_header)

        self._folder_tree = QTreeWidget()
        self._folder_tree.setHeaderHidden(True)
        self._folder_tree.setStyleSheet("""
            QTreeWidget { border: none; background: #ffffff; font-size: 12px; color: #111827; }
            QTreeWidget::item { padding: 3px 4px; }
            QTreeWidget::item:selected { background: #fef3c7; color: #92400e; }
            QTreeWidget::item:hover { background: #f3f4f6; }
        """)
        self._folder_tree.itemExpanded.connect(self._on_folder_expanded)
        self._folder_tree.currentItemChanged.connect(self._on_folder_selected)
        tree_vlayout.addWidget(self._folder_tree, 1)
        body_layout.addWidget(tree_frame)

        # Panel 2: File list (200px)
        file_frame = QFrame()
        file_frame.setStyleSheet("QFrame { border-right: 1px solid #e5e7eb; background: #ffffff; }")
        file_frame.setFixedWidth(200)
        file_vlayout = QVBoxLayout(file_frame)
        file_vlayout.setContentsMargins(0, 0, 0, 0)
        file_vlayout.setSpacing(0)

        file_header = QWidget()
        file_header.setFixedHeight(34)
        file_header.setStyleSheet("background: #f9fafb; border-bottom: 1px solid #e5e7eb;")
        fh_layout = QHBoxLayout(file_header)
        fh_layout.setContentsMargins(10, 0, 10, 0)
        self._folder_path_lbl = QLabel("폴더 없음")
        self._folder_path_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        fh_layout.addWidget(self._folder_path_lbl, 1)
        file_vlayout.addWidget(file_header)

        self._file_list = _DraggableFileList()
        self._file_list.setStyleSheet("""
            QListWidget { border: none; background: #ffffff; font-size: 12px; color: #111827; }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected { background: #fef3c7; color: #92400e; }
            QListWidget::item:hover { background: #f3f4f6; }
        """)
        self._file_list.currentItemChanged.connect(self._on_file_clicked)
        self._file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
        file_vlayout.addWidget(self._file_list, 1)
        body_layout.addWidget(file_frame)

        # Panel 3: Preview (stretch)
        preview_frame = QWidget()
        preview_frame.setStyleSheet("background: #f9fafb;")
        preview_vlayout = QVBoxLayout(preview_frame)
        preview_vlayout.setContentsMargins(12, 12, 12, 8)
        preview_vlayout.setSpacing(6)

        self._preview = _SimplePreview()
        preview_vlayout.addWidget(self._preview, 1)

        self._preview_info = QLabel()
        self._preview_info.setAlignment(Qt.AlignCenter)
        self._preview_info.setStyleSheet(
            "font-size: 11px; color: #6b7280; background: transparent;"
        )
        preview_vlayout.addWidget(self._preview_info)
        body_layout.addWidget(preview_frame, 1)

        outer.addWidget(body_widget, 1)

        # ── Drop zone area ─────────────────────────────────────────────────────
        drop_area = QWidget()
        drop_area.setStyleSheet("QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }")
        drop_area_layout = QVBoxLayout(drop_area)
        drop_area_layout.setContentsMargins(16, 8, 16, 8)
        drop_area_layout.setSpacing(4)

        dz_header = QHBoxLayout()
        sel_lbl = QLabel("선택된 파일")
        sel_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #374151;")
        self._count_lbl = QLabel("0개")
        self._count_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #d97706; margin-left: 6px;"
        )
        clear_btn = QPushButton("전체 지우기")
        clear_btn.setFixedHeight(24)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(
            "QPushButton { font-size: 11px; color: #6b7280; border: 1px solid #e5e7eb;"
            "  border-radius: 5px; padding: 0 8px; background: white; }"
            "QPushButton:hover { color: #ef4444; border-color: #ef4444; }"
        )
        clear_btn.clicked.connect(self._clear_selection)
        dz_header.addWidget(sel_lbl)
        dz_header.addWidget(self._count_lbl)
        dz_header.addStretch()
        dz_header.addWidget(clear_btn)
        drop_area_layout.addLayout(dz_header)

        self._drop_zone = _DropZone(self._on_count_changed)
        drop_area_layout.addWidget(self._drop_zone)
        outer.addWidget(drop_area)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet("QWidget { background: #ffffff; border-top: 1.5px solid #e5e7eb; }")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(40, 14, 40, 14)
        footer_layout.setSpacing(16)

        self._back_btn = QPushButton("← 허브로 돌아가기")
        self._back_btn.setFixedHeight(48)
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setStyleSheet(
            "QPushButton { border: 2px solid #d1d5db; color: #374151; border-radius: 10px;"
            "  font-size: 14px; font-weight: 700; background: white; padding: 0 24px; }"
            "QPushButton:hover { border-color: #9ca3af; }"
        )

        self._next_btn = QPushButton("다음: 파이프라인 설정 →")
        self._next_btn.setFixedHeight(48)
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setStyleSheet(
            "QPushButton { background: #d97706; color: white; font-size: 15px;"
            "  border-radius: 10px; font-weight: 800; border: none; padding: 0 32px; }"
            "QPushButton:hover { background: #b45309; }"
            "QPushButton:pressed { background: #92400e; }"
            "QPushButton:disabled { background: #9ca3af; }"
        )

        footer_layout.addStretch()
        footer_layout.addWidget(self._back_btn)
        footer_layout.addWidget(self._next_btn)
        outer.addWidget(footer)

    # ── Folder tree ───────────────────────────────────────────────────────────

    def _load_computer_tree(self) -> None:
        self._folder_tree.blockSignals(True)
        self._folder_tree.clear()

        # Section: 빠른 접근
        quick_section = QTreeWidgetItem(["빠른 접근"])
        quick_section.setData(0, Qt.UserRole, None)
        quick_section.setFlags(Qt.ItemIsEnabled)
        quick_section.setForeground(0, QColor("#6b7280"))
        font = quick_section.font(0)
        font.setBold(True)
        font.setPointSize(9)
        quick_section.setFont(0, font)
        self._folder_tree.addTopLevelItem(quick_section)

        for label, path in _get_quick_access():
            child = self._make_dir_item(path)
            child.setText(0, label)
            quick_section.addChild(child)
        quick_section.setExpanded(True)

        # Section: 내 컴퓨터
        pc_section = QTreeWidgetItem(["내 컴퓨터"])
        pc_section.setData(0, Qt.UserRole, None)
        pc_section.setFlags(Qt.ItemIsEnabled)
        pc_section.setForeground(0, QColor("#6b7280"))
        font2 = pc_section.font(0)
        font2.setBold(True)
        font2.setPointSize(9)
        pc_section.setFont(0, font2)
        self._folder_tree.addTopLevelItem(pc_section)

        for label, path in _get_drives():
            child = self._make_dir_item(path)
            child.setText(0, label)
            pc_section.addChild(child)
        pc_section.setExpanded(True)

        self._folder_tree.blockSignals(False)

    def _make_dir_item(self, path: Path) -> QTreeWidgetItem:
        label = path.name or str(path)
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.UserRole, path)
        item.addChild(QTreeWidgetItem([_DUMMY]))
        return item

    def _populate_dir(self, item: QTreeWidgetItem) -> None:
        path: Path = item.data(0, Qt.UserRole)
        if path is None:
            return
        for i in range(item.childCount() - 1, -1, -1):
            if item.child(i).text(0) == _DUMMY:
                item.removeChild(item.child(i))
        try:
            dirs = sorted(
                (e for e in path.iterdir() if e.is_dir() and not e.name.startswith('.')),
                key=lambda p: p.name.lower(),
            )
        except PermissionError:
            return
        for d in dirs:
            item.addChild(self._make_dir_item(d))

    def _on_folder_expanded(self, item: QTreeWidgetItem) -> None:
        has_dummy = any(item.child(i).text(0) == _DUMMY for i in range(item.childCount()))
        if has_dummy:
            self._populate_dir(item)

    def _on_folder_selected(self, current: QTreeWidgetItem, _prev) -> None:
        if current is None:
            return
        path: Path = current.data(0, Qt.UserRole)
        if path is None or not path.is_dir():
            return
        self._current_folder = path
        self._load_files_in(path)

    def _load_files_in(self, folder: Path) -> None:
        self._file_list.clear()
        name = folder.name or str(folder)
        self._folder_path_lbl.setText(name)
        self._folder_path_lbl.setToolTip(str(folder))
        try:
            files = sorted(
                (e for e in folder.iterdir() if e.is_file() and is_supported(e)),
                key=lambda p: p.name.lower(),
            )
        except PermissionError:
            return
        for f in files:
            item = QListWidgetItem(f.name)
            item.setData(Qt.UserRole, f)
            item.setToolTip(str(f))
            self._file_list.addItem(item)

    # ── File interactions ─────────────────────────────────────────────────────

    def _on_file_clicked(self, current: QListWidgetItem, _prev) -> None:
        if current is None:
            return
        path: Path = current.data(Qt.UserRole)
        if path:
            self._show_preview(path)

    def _on_file_double_clicked(self, item: QListWidgetItem) -> None:
        path: Path = item.data(Qt.UserRole)
        if path:
            self._drop_zone.add_file(path)

    def _show_preview(self, path: Path) -> None:
        try:
            img, _ = load_image(path, preview_only=True)
            px = _pil_to_pixmap(img, 900, 700)
            self._preview.set_pixmap(px)
            w, h = img.size
            self._preview_info.setText(f"{path.name}   {w} × {h}")
        except Exception:
            self._preview.set_pixmap(None)
            self._preview_info.setText("미리보기 불가")

    # ── Drop zone callbacks ───────────────────────────────────────────────────

    def _on_count_changed(self, count: int) -> None:
        self._count_lbl.setText(f"{count}개")

    def _clear_selection(self) -> None:
        self._drop_zone.clear_all()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_selected_files(self) -> List[Path]:
        return self._drop_zone.get_files()

    def get_root_folder(self) -> Optional[Path]:
        return self._current_folder

    def validate(self) -> bool:
        if not self.get_selected_files():
            QMessageBox.warning(self, "파일 없음", "처리할 파일을 하나 이상 선택해 주세요.")
            return False
        return True

    @property
    def back_button(self) -> QPushButton:
        return self._back_btn

    @property
    def next_button(self) -> QPushButton:
        return self._next_btn
