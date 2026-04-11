"""
Screen 1: Folder selection, ExifTool path, and duplicate policy.
"""
# -*- coding: utf-8 -*-
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from core.extractor import resolve_exiftool_path
from core.pipeline import PipelineConfig


class FolderRow(QWidget):
    def __init__(self, label: str, placeholder: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(label)
        lbl.setFixedWidth(110)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(placeholder)

        btn = QPushButton("Browse")
        btn.setFixedWidth(90)
        btn.clicked.connect(self._browse)

        layout.addWidget(lbl)
        layout.addWidget(self.line_edit)
        layout.addWidget(btn)

    def _browse(self) -> None:
        current = self.line_edit.text().strip()
        start = current if current and Path(current).exists() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", start)
        if folder:
            self.line_edit.setText(folder)

    @property
    def path(self) -> str:
        return self.line_edit.text().strip()

    @path.setter
    def path(self, value: str) -> None:
        self.line_edit.setText(value)


class SetupScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._auto_detect_exiftool()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(32, 24, 32, 24)

        title = QLabel("Photo Classifier")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 4px;")
        root.addWidget(title)

        subtitle = QLabel("Classify photos/videos by country and city.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666; margin-bottom: 12px;")
        root.addWidget(subtitle)

        folder_group = QGroupBox("Folders")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(8)

        self._input_row = FolderRow("Input Folder", "Folder containing files to classify")
        self._output_row = FolderRow("Output Folder", "Folder to write organized output")
        folder_layout.addWidget(self._input_row)
        folder_layout.addWidget(self._output_row)
        root.addWidget(folder_group)

        exif_group = QGroupBox("ExifTool")
        exif_layout = QHBoxLayout(exif_group)

        exif_lbl = QLabel("ExifTool Path:")
        exif_lbl.setFixedWidth(110)
        exif_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._exiftool_line = QLineEdit()
        self._exiftool_line.setPlaceholderText("Auto-detecting...")

        exif_btn = QPushButton("Change")
        exif_btn.setFixedWidth(60)
        exif_btn.clicked.connect(self._browse_exiftool)

        exif_layout.addWidget(exif_lbl)
        exif_layout.addWidget(self._exiftool_line)
        exif_layout.addWidget(exif_btn)
        root.addWidget(exif_group)

        dup_group = QGroupBox("Duplicate Policy")
        dup_layout = QVBoxLayout(dup_group)

        self._rb_rename = QRadioButton("Rename (recommended)")
        self._rb_skip = QRadioButton("Skip")
        self._rb_overwrite = QRadioButton("Overwrite")
        self._rb_rename.setChecked(True)
        self._rb_overwrite.toggled.connect(self._warn_overwrite)

        dup_layout.addWidget(self._rb_rename)
        dup_layout.addWidget(self._rb_skip)
        dup_layout.addWidget(self._rb_overwrite)
        root.addWidget(dup_group)

        adv_group = QGroupBox("Advanced")
        adv_layout = QHBoxLayout(adv_group)

        adv_lbl = QLabel("Max city distance (km):")
        self._city_dist = QDoubleSpinBox()
        self._city_dist.setRange(1.0, 500.0)
        self._city_dist.setValue(30.0)
        self._city_dist.setSingleStep(5.0)
        self._city_dist.setFixedWidth(80)

        adv_layout.addWidget(adv_lbl)
        adv_layout.addWidget(self._city_dist)
        adv_layout.addStretch()
        root.addWidget(adv_group)

        root.addStretch()

        self._run_btn = QPushButton("Run")
        self._run_btn.setFixedHeight(44)
        self._run_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; font-size: 15px; "
            "border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
            "QPushButton:disabled { background-color: #93c5fd; }"
        )
        root.addWidget(self._run_btn)

    def _auto_detect_exiftool(self) -> None:
        path = resolve_exiftool_path()
        if path:
            self._exiftool_line.setText(path)
            self._exiftool_line.setStyleSheet("color: #16a34a;")
        else:
            self._exiftool_line.setPlaceholderText("ExifTool not detected. Please set path manually.")
            self._exiftool_line.setStyleSheet("color: #dc2626;")

    def _browse_exiftool(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ExifTool executable", str(Path.home()), "Executable (*.exe);;All Files (*)"
        )
        if path:
            self._exiftool_line.setText(path)
            self._exiftool_line.setStyleSheet("")

    def _warn_overwrite(self, checked: bool) -> None:
        if checked:
            QMessageBox.warning(
                self,
                "Warning: Overwrite",
                "Overwrite will replace existing files with the same name.\n"
                "Choose this only when you are sure.",
            )

    def validate(self) -> bool:
        if not self._input_row.path:
            QMessageBox.warning(self, "Missing Input", "Please select Input Folder.")
            return False
        if not Path(self._input_row.path).is_dir():
            QMessageBox.warning(self, "Input Not Found", f"Input folder does not exist:\n{self._input_row.path}")
            return False
        if not self._output_row.path:
            QMessageBox.warning(self, "Missing Output", "Please select Output Folder.")
            return False
        if not self._exiftool_line.text().strip():
            QMessageBox.warning(self, "Missing ExifTool", "Please provide ExifTool executable path.")
            return False
        return True

    def build_config(self, assets_dir: Path, db_path: Path) -> PipelineConfig:
        policy = "rename"
        if self._rb_skip.isChecked():
            policy = "skip"
        elif self._rb_overwrite.isChecked():
            policy = "overwrite"

        return PipelineConfig(
            input_folder=Path(self._input_row.path),
            output_folder=Path(self._output_row.path),
            exiftool_path=self._exiftool_line.text().strip(),
            assets_dir=assets_dir,
            db_path=db_path,
            duplicate_policy=policy,
            max_city_distance_km=self._city_dist.value(),
        )

    @property
    def run_button(self) -> QPushButton:
        return self._run_btn

    @property
    def output_path(self) -> str:
        return self._output_row.path
