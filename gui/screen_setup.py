"""
Screen 1: Folder selection, ExifTool path, and duplicate policy.
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
    QFrame,
    QSizePolicy,
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

        btn = QPushButton("폴더 열기")
        btn.setFixedWidth(90)
        btn.clicked.connect(self._browse)

        layout.addWidget(lbl)
        layout.addWidget(self.line_edit)
        layout.addWidget(btn)

    def _browse(self) -> None:
        current = self.line_edit.text().strip()
        start = current if current and Path(current).exists() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택", start)
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

        # Title
        title = QLabel("Photo Classifier")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 4px;")
        root.addWidget(title)

        subtitle = QLabel("사진을 국가/도시별로 자동 분류합니다")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666; margin-bottom: 12px;")
        root.addWidget(subtitle)

        # Folder section
        folder_group = QGroupBox("폴더 설정")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(8)

        self._input_row = FolderRow("Input Folder", "분류할 사진이 있는 폴더")
        self._output_row = FolderRow("Output Folder", "분류 결과를 저장할 폴더")
        folder_layout.addWidget(self._input_row)
        folder_layout.addWidget(self._output_row)
        root.addWidget(folder_group)

        # ExifTool section
        exif_group = QGroupBox("ExifTool 설정")
        exif_layout = QHBoxLayout(exif_group)

        exif_lbl = QLabel("ExifTool 경로:")
        exif_lbl.setFixedWidth(110)
        exif_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._exiftool_line = QLineEdit()
        self._exiftool_line.setPlaceholderText("자동 감지 중...")

        exif_btn = QPushButton("변경")
        exif_btn.setFixedWidth(60)
        exif_btn.clicked.connect(self._browse_exiftool)

        exif_layout.addWidget(exif_lbl)
        exif_layout.addWidget(self._exiftool_line)
        exif_layout.addWidget(exif_btn)
        root.addWidget(exif_group)

        # Duplicate policy
        dup_group = QGroupBox("중복 파일 처리")
        dup_layout = QVBoxLayout(dup_group)

        self._rb_rename = QRadioButton("Rename  —  안전 (파일명_1.jpg 형태로 저장)")
        self._rb_skip = QRadioButton("Skip  —  이미 존재하면 건너뜀")
        self._rb_overwrite = QRadioButton("Overwrite  —  기존 파일 덮어씀  ⚠️")
        self._rb_rename.setChecked(True)

        self._rb_overwrite.toggled.connect(self._warn_overwrite)

        dup_layout.addWidget(self._rb_rename)
        dup_layout.addWidget(self._rb_skip)
        dup_layout.addWidget(self._rb_overwrite)
        root.addWidget(dup_group)

        # Advanced options
        adv_group = QGroupBox("고급 옵션")
        adv_layout = QHBoxLayout(adv_group)

        adv_lbl = QLabel("최대 도시 탐색 거리 (km):")
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

        # Run button
        self._run_btn = QPushButton("실행")
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
            self._exiftool_line.setPlaceholderText("감지 실패 — 직접 경로 입력 필요")
            self._exiftool_line.setStyleSheet("color: #dc2626;")

    def _browse_exiftool(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "ExifTool 실행 파일 선택", str(Path.home()), "Executable (*.exe);;All Files (*)"
        )
        if path:
            self._exiftool_line.setText(path)
            self._exiftool_line.setStyleSheet("")

    def _warn_overwrite(self, checked: bool) -> None:
        if checked:
            QMessageBox.warning(
                self,
                "주의: Overwrite 모드",
                "Overwrite 모드에서는 대상 폴더의 동일한 파일명이 덮어씌워집니다.\n"
                "원본 데이터 손실이 발생할 수 있습니다.\n\n"
                "계속하려면 확인을 누르세요.",
            )

    def validate(self) -> bool:
        """Check all required fields. Show error dialog if invalid. Returns True if OK."""
        if not self._input_row.path:
            QMessageBox.warning(self, "입력 필요", "Input Folder를 선택해주세요.")
            return False
        if not Path(self._input_row.path).is_dir():
            QMessageBox.warning(self, "폴더 없음", f"Input Folder가 존재하지 않습니다:\n{self._input_row.path}")
            return False
        if not self._output_row.path:
            QMessageBox.warning(self, "입력 필요", "Output Folder를 선택해주세요.")
            return False
        if not self._exiftool_line.text().strip():
            QMessageBox.warning(self, "ExifTool 없음", "ExifTool 경로를 지정해주세요.")
            return False
        return True

    def build_config(self, assets_dir: Path, db_path: Path) -> PipelineConfig:
        """Build PipelineConfig from current UI state."""
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
