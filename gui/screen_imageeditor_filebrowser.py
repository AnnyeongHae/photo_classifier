# -*- coding: utf-8 -*-
"""Hierarchical file browser screen for selecting images to process."""
from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ImageEditor.core.image_loader import is_supported


class ImageEditorFileBrowserScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._root_folder: Path | None = None
        self._propagating = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # header
        header = QWidget()
        header.setStyleSheet("background: #f3f4f6;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(40, 24, 40, 12)
        header_layout.setSpacing(4)

        title = QLabel("파일 선택")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #111827; background: transparent;"
        )
        subtitle = QLabel("편집할 파일을 선택하세요. 폴더 체크박스로 하위 파일을 일괄 선택할 수 있습니다.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 12px; color: #6b7280; background: transparent;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        outer.addWidget(header)

        # toolbar
        toolbar = QWidget()
        toolbar.setStyleSheet("background: #ffffff; border-bottom: 1px solid #e5e7eb;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 8, 20, 8)
        toolbar_layout.setSpacing(8)

        self._folder_label = QLabel("폴더: —")
        self._folder_label.setStyleSheet("font-size: 12px; color: #374151;")

        select_all_btn = QPushButton("전체 선택")
        select_all_btn.setFixedHeight(30)
        select_all_btn.setCursor(Qt.PointingHandCursor)
        select_all_btn.setStyleSheet(
            "QPushButton { font-size: 12px; font-weight: 600; background: #f3f4f6;"
            "  border: 1px solid #d1d5db; border-radius: 6px; padding: 0 12px; color: #374151; }"
            "QPushButton:hover { background: #e5e7eb; }"
        )
        select_all_btn.clicked.connect(self._select_all)

        deselect_all_btn = QPushButton("전체 해제")
        deselect_all_btn.setFixedHeight(30)
        deselect_all_btn.setCursor(Qt.PointingHandCursor)
        deselect_all_btn.setStyleSheet(
            "QPushButton { font-size: 12px; font-weight: 600; background: #f3f4f6;"
            "  border: 1px solid #d1d5db; border-radius: 6px; padding: 0 12px; color: #374151; }"
            "QPushButton:hover { background: #e5e7eb; }"
        )
        deselect_all_btn.clicked.connect(self._deselect_all)

        self._count_label = QLabel("선택: 0개")
        self._count_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #d97706;")

        toolbar_layout.addWidget(self._folder_label, 1)
        toolbar_layout.addWidget(select_all_btn)
        toolbar_layout.addWidget(deselect_all_btn)
        toolbar_layout.addWidget(self._count_label)
        outer.addWidget(toolbar)

        # tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet("""
            QTreeWidget {
                border: none; background: #ffffff;
                font-size: 13px; color: #111827;
            }
            QTreeWidget::item { padding: 3px 4px; }
            QTreeWidget::item:selected { background: #fef3c7; color: #92400e; }
            QTreeWidget::item:hover { background: #f3f4f6; }
        """)
        self._tree.itemChanged.connect(self._on_item_changed)
        outer.addWidget(self._tree, 1)

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

    # ── public API ─────────────────────────────────────────────────────────────

    def load_folder(self, folder: Path) -> None:
        self._root_folder = folder
        self._folder_label.setText(f"폴더: {folder}")
        self._tree.blockSignals(True)
        self._tree.clear()
        self._build_tree(folder, None)
        self._tree.expandAll()
        self._tree.blockSignals(False)
        self._update_count()

    def get_selected_files(self) -> List[Path]:
        files: List[Path] = []
        self._collect_checked(self._tree.invisibleRootItem(), files)
        return files

    @property
    def back_button(self) -> QPushButton:
        return self._back_btn

    @property
    def next_button(self) -> QPushButton:
        return self._next_btn

    # ── tree building ──────────────────────────────────────────────────────────

    def _build_tree(self, folder: Path, parent_item: QTreeWidgetItem | None) -> int:
        """Build tree for folder. Returns count of image files added."""
        try:
            entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return 0

        total = 0
        for entry in entries:
            if entry.is_dir():
                folder_item = QTreeWidgetItem([entry.name])
                folder_item.setData(0, Qt.UserRole, entry)
                folder_item.setFlags(
                    folder_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate
                )
                folder_item.setCheckState(0, Qt.Unchecked)
                if parent_item:
                    parent_item.addChild(folder_item)
                else:
                    self._tree.addTopLevelItem(folder_item)
                count = self._build_tree(entry, folder_item)
                if count == 0:
                    # remove empty folders from tree
                    if parent_item:
                        parent_item.removeChild(folder_item)
                    else:
                        idx = self._tree.indexOfTopLevelItem(folder_item)
                        if idx >= 0:
                            self._tree.takeTopLevelItem(idx)
                else:
                    total += count
            elif entry.is_file() and is_supported(entry):
                file_item = QTreeWidgetItem([entry.name])
                file_item.setData(0, Qt.UserRole, entry)
                file_item.setFlags(
                    file_item.flags() | Qt.ItemIsUserCheckable
                )
                file_item.setCheckState(0, Qt.Checked)
                if parent_item:
                    parent_item.addChild(file_item)
                else:
                    self._tree.addTopLevelItem(file_item)
                total += 1
        return total

    # ── check propagation ──────────────────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._propagating or column != 0:
            return
        path = item.data(0, Qt.UserRole)
        if isinstance(path, Path) and path.is_dir():
            self._propagating = True
            state = item.checkState(0)
            if state != Qt.PartiallyChecked:
                self._set_children_check(item, state)
            self._propagating = False
        self._update_count()

    def _set_children_check(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            child_path = child.data(0, Qt.UserRole)
            if isinstance(child_path, Path) and child_path.is_dir():
                self._set_children_check(child, state)

    def _collect_checked(self, item: QTreeWidgetItem, out: List[Path]) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            path = child.data(0, Qt.UserRole)
            if isinstance(path, Path) and path.is_file():
                if child.checkState(0) == Qt.Checked:
                    out.append(path)
            else:
                self._collect_checked(child, out)

    def _update_count(self) -> None:
        files = self.get_selected_files()
        self._count_label.setText(f"선택: {len(files)}개")

    def _select_all(self) -> None:
        self._propagating = True
        self._tree.blockSignals(True)
        self._set_all_check(self._tree.invisibleRootItem(), Qt.Checked)
        self._tree.blockSignals(False)
        self._propagating = False
        self._update_count()

    def _deselect_all(self) -> None:
        self._propagating = True
        self._tree.blockSignals(True)
        self._set_all_check(self._tree.invisibleRootItem(), Qt.Unchecked)
        self._tree.blockSignals(False)
        self._propagating = False
        self._update_count()

    def _set_all_check(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_all_check(child, state)

    def validate(self) -> bool:
        files = self.get_selected_files()
        if not files:
            QMessageBox.warning(self, "파일 없음", "처리할 파일을 하나 이상 선택해 주세요.")
            return False
        return True
