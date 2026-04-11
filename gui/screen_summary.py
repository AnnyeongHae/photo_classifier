"""
Screen 3: Summary cards, filterable result table, CSV export.
"""
# -*- coding: utf-8 -*-
import csv
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, QSortFilterProxyModel, QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QFrame,
    QSizePolicy,
)

from core.pipeline import PipelineResult


_TABLE_COLUMNS = [
    ("file_name", "파일명"),
    ("geo_country", "국가"),
    ("geo_city", "도시"),
    ("sort_status", "상태"),
    ("is_duplicate", "중복"),
    ("geo_city_distance_km", "도시거리(km)"),
    ("datetime_original", "촬영일시"),
    ("device_make", "제조사"),
    ("device_model", "모델"),
    ("file_size_bytes", "크기(bytes)"),
]

_STATUS_FILTER_OPTIONS = [
    ("전체", None),
    ("Success", "Success"),
    ("No GPS", "No_GPS"),
    ("기타 지역", "Other_Regions"),
    ("오류", "Error"),
    ("중복", "__duplicate__"),
]


class SummaryCard(QWidget):
    def __init__(self, icon: str, label: str, color: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(2)

        self._val_lbl = QLabel("0")
        self._val_lbl.setAlignment(Qt.AlignCenter)
        self._val_lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")

        desc = QLabel(f"{icon}  {label}")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #555; font-size: 11px;")

        layout.addWidget(self._val_lbl)
        layout.addWidget(desc)
        self.setStyleSheet(
            f"SummaryCard {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }}"
        )

    def set_value(self, v: int) -> None:
        self._val_lbl.setText(str(v))


class SummaryScreen(QWidget):
    def __init__(self, on_process_more, parent=None):
        super().__init__(parent)
        self._on_process_more = on_process_more
        self._all_rows: List[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(24, 20, 24, 20)

        # Title
        self._title_lbl = QLabel("완료!")
        self._title_lbl.setAlignment(Qt.AlignCenter)
        self._title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        root.addWidget(self._title_lbl)

        # Summary cards
        cards_layout = QHBoxLayout()
        self._card_total = SummaryCard("📁", "전체", "#1e40af")
        self._card_success = SummaryCard("✅", "성공 (이동됨)", "#16a34a")
        self._card_nogps = SummaryCard("📍", "GPS 없음", "#d97706")
        self._card_other = SummaryCard("🌍", "기타 지역", "#7c3aed")
        self._card_fail = SummaryCard("❌", "실패/오류", "#dc2626")
        for card in (self._card_total, self._card_success, self._card_nogps, self._card_other, self._card_fail):
            cards_layout.addWidget(card)
        root.addLayout(cards_layout)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #e2e8f0;")
        root.addWidget(divider)

        # Filter row
        filter_row = QHBoxLayout()

        search_lbl = QLabel("검색:")
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("파일명 / 국가 / 도시...")
        self._search_box.setFixedWidth(200)
        self._search_box.textChanged.connect(self._apply_filter)

        status_lbl = QLabel("상태:")
        self._status_combo = QComboBox()
        for label, _ in _STATUS_FILTER_OPTIONS:
            self._status_combo.addItem(label)
        self._status_combo.currentIndexChanged.connect(self._apply_filter)

        filter_row.addWidget(search_lbl)
        filter_row.addWidget(self._search_box)
        filter_row.addSpacing(12)
        filter_row.addWidget(status_lbl)
        filter_row.addWidget(self._status_combo)
        filter_row.addStretch()

        self._row_count_lbl = QLabel("0개 행")
        self._row_count_lbl.setStyleSheet("color: #888; font-size: 12px;")
        filter_row.addWidget(self._row_count_lbl)
        root.addLayout(filter_row)

        # Table
        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels([col[1] for col in _TABLE_COLUMNS])

        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)  # search all columns

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(QTableView.NoEditTriggers)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(_TABLE_COLUMNS)):
            self._table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._table.setStyleSheet(
            "QTableView { gridline-color: #e2e8f0; }"
            "QHeaderView::section { background: #292929; font-weight: bold; padding: 4px; border: none; border-right: 1px solid #e2e8f0; }"
        )
        root.addWidget(self._table)

        # Bottom buttons
        btn_row = QHBoxLayout()

        self._export_btn = QPushButton("CSV 내보내기")
        self._export_btn.setFixedHeight(36)
        self._export_btn.setStyleSheet(
            "QPushButton { border: 1px solid #2563eb; color: #2563eb; border-radius: 5px; padding: 0 16px; }"
            "QPushButton:hover { background: #eff6ff; }"
        )
        self._export_btn.clicked.connect(self._export_csv)

        more_btn = QPushButton("추가 처리하기")
        more_btn.setFixedHeight(36)
        more_btn.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; border-radius: 5px; padding: 0 16px; font-weight: bold; }"
            "QPushButton:hover { background: #1d4ed8; }"
        )
        more_btn.clicked.connect(self._on_process_more)

        btn_row.addWidget(self._export_btn)
        btn_row.addStretch()
        btn_row.addWidget(more_btn)
        root.addLayout(btn_row)

    def load_result(self, result: PipelineResult) -> None:
        """Populate the screen with pipeline result data."""
        self._all_rows = result.rows

        # Update summary cards
        self._title_lbl.setText(f"완료!  {result.total}개 파일 처리됨")
        self._card_total.set_value(result.total)
        self._card_success.set_value(result.moved if result.move_stats else result.success)
        self._card_nogps.set_value(result.no_gps)
        self._card_other.set_value(result.other_regions)
        self._card_fail.set_value(result.failed + result.move_failed)

        self._populate_table(self._all_rows)
        self._search_box.clear()
        self._status_combo.setCurrentIndex(0)

    def _populate_table(self, rows: List[dict]) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for row in rows:
            items = []
            for col_key, _ in _TABLE_COLUMNS:
                val = row.get(col_key, "")
                item = QStandardItem(str(val) if val else "")
                item.setEditable(False)
                items.append(item)
            self._model.appendRow(items)
        self._update_row_count()

    def _apply_filter(self) -> None:
        text = self._search_box.text().strip()
        status_idx = self._status_combo.currentIndex()
        _, status_filter = _STATUS_FILTER_OPTIONS[status_idx]

        if status_filter is None:
            # All — use text search only
            self._proxy.setFilterFixedString(text)
            self._proxy.setFilterKeyColumn(-1)
        elif status_filter == "__duplicate__":
            # Filter by is_duplicate column (index 4)
            self._proxy.setFilterFixedString("yes")
            self._proxy.setFilterKeyColumn(4)
        else:
            # Filter by sort_status column (index 3)
            self._proxy.setFilterFixedString(status_filter)
            self._proxy.setFilterKeyColumn(3)

        # Additional text filter via re-populate if status filter active
        if status_filter and text:
            # Build filtered subset and repopulate
            col_keys = [c[0] for c in _TABLE_COLUMNS]
            visible_rows = []
            for row in self._all_rows:
                if status_filter == "__duplicate__":
                    if row.get("is_duplicate") != "yes":
                        continue
                elif row.get("sort_status", "") not in (status_filter, status_filter.replace("_", " ")):
                    # exact match
                    if row.get("sort_status", "") != status_filter:
                        continue
                row_str = " ".join(str(row.get(k, "")) for k in col_keys)
                if text.lower() in row_str.lower():
                    visible_rows.append(row)
            self._populate_table(visible_rows)
        else:
            self._update_row_count()

    def _update_row_count(self) -> None:
        visible = self._proxy.rowCount()
        total = self._model.rowCount()
        if visible == total:
            self._row_count_lbl.setText(f"{total}개 행")
        else:
            self._row_count_lbl.setText(f"{visible} / {total}개 행")

    def _export_csv(self) -> None:
        if not self._all_rows:
            QMessageBox.information(self, "내보내기", "내보낼 데이터가 없습니다.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "CSV 저장", "classified_result.csv", "CSV Files (*.csv)"
        )
        if not path:
            return

        # Export currently visible rows
        visible_count = self._proxy.rowCount()
        col_keys = [c[0] for c in _TABLE_COLUMNS]
        col_labels = [c[1] for c in _TABLE_COLUMNS]

        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as fp:
                writer = csv.writer(fp)
                writer.writerow(col_labels)
                for i in range(visible_count):
                    source_idx = self._proxy.mapToSource(self._proxy.index(i, 0))
                    row_idx = source_idx.row()
                    row = [self._model.item(row_idx, j).text() for j in range(len(col_keys))]
                    writer.writerow(row)

            QMessageBox.information(self, "내보내기 완료", f"{visible_count}개 행을 저장했습니다:\n{path}")
        except OSError as exc:
            QMessageBox.critical(self, "내보내기 실패", str(exc))
