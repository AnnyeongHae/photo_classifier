"""
Screen 1: Folder selection, ExifTool path, and duplicate policy.
"""
# -*- coding: utf-8 -*-
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
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
    def __init__(self, label: str, placeholder: str, browse_label: str = "찾기", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl.setStyleSheet("font-weight: 600; color: #111827; font-size: 13px; background: transparent;")

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.setFixedHeight(36)
        self.line_edit.setStyleSheet(
            "QLineEdit {"
            "  border: 1.5px solid #d1d5db;"
            "  border-radius: 6px;"
            "  padding: 4px 10px;"
            "  font-size: 13px;"
            "  color: #111827;"
            "  background: #f9fafb;"
            "}"
            "QLineEdit:focus {"
            "  border-color: #2563eb;"
            "  color: #111827;"
            "  background: #ffffff;"
            "}"
        )

        btn = QPushButton(browse_label)
        btn.setFixedWidth(72)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton {"
            "  background: #f3f4f6;"
            "  border: 1.5px solid #d1d5db;"
            "  border-radius: 6px;"
            "  font-size: 13px;"
            "  font-weight: 600;"
            "  color: #111827;"
            "}"
            "QPushButton:hover { background: #e5e7eb; border-color: #9ca3af; color: #111827; }"
            "QPushButton:pressed { background: #d1d5db; color: #111827; }"
        )
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

        title = QLabel("사진/영상 분류기")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 4px;")
        root.addWidget(title)

        subtitle = QLabel("사진과 영상을 GPS 정보 기준으로 국가/도시 폴더에 분류합니다.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666; margin-bottom: 12px;")
        root.addWidget(subtitle)

        folder_group = QGroupBox("폴더 경로")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(8)

        self._input_row = FolderRow("입력 폴더", "분류할 사진/영상이 있는 폴더 선택")
        self._output_row = FolderRow("출력 폴더", "분류된 파일이 저장될 폴더 선택")
        folder_layout.addWidget(self._input_row)
        folder_layout.addWidget(self._output_row)
        root.addWidget(folder_group)

        exif_group = QGroupBox("ExifTool")
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

        dup_group = QGroupBox("중복 파일 처리")
        dup_layout = QVBoxLayout(dup_group)

        self._rb_rename = QRadioButton("이름 변경 (권장)")
        self._rb_skip = QRadioButton("건너뛰기")
        self._rb_overwrite = QRadioButton("덮어쓰기")
        self._rb_rename.setChecked(True)
        self._rb_overwrite.toggled.connect(self._warn_overwrite)

        dup_layout.addWidget(self._rb_rename)
        dup_layout.addWidget(self._rb_skip)
        dup_layout.addWidget(self._rb_overwrite)
        root.addWidget(dup_group)

        adv_group = QGroupBox("고급 설정")
        adv_layout = QHBoxLayout(adv_group)

        adv_lbl = QLabel("도시 매칭 거리(km):")
        self._city_dist = QDoubleSpinBox()
        self._city_dist.setRange(1.0, 500.0)
        self._city_dist.setValue(30.0)
        self._city_dist.setSingleStep(5.0)
        self._city_dist.setFixedWidth(80)

        depth_lbl = QLabel("출력 폴더 깊이:")
        depth_lbl.setContentsMargins(16, 0, 0, 0)
        self._depth_cb = QComboBox()
        self._depth_cb.addItem("국가", "country")
        self._depth_cb.addItem("국가/도시", "city")
        self._depth_cb.addItem("국가/도시/날짜", "date")
        self._depth_cb.addItem("국가/날짜", "country_date")
        self._depth_cb.setCurrentIndex(1)
        self._depth_cb.setFixedWidth(140)

        no_gps_lbl = QLabel("GPS 없음:")
        no_gps_lbl.setContentsMargins(16, 0, 0, 0)
        self._no_gps_depth_cb = QComboBox()
        self._no_gps_depth_cb.addItem("날짜", "date")
        self._no_gps_depth_cb.addItem("날짜/카메라", "date_model")
        self._no_gps_depth_cb.setCurrentIndex(0)
        self._no_gps_depth_cb.setFixedWidth(120)

        adv_layout.addWidget(adv_lbl)
        adv_layout.addWidget(self._city_dist)
        adv_layout.addWidget(depth_lbl)
        adv_layout.addWidget(self._depth_cb)
        adv_layout.addWidget(no_gps_lbl)
        adv_layout.addWidget(self._no_gps_depth_cb)
        adv_layout.addStretch()
        root.addWidget(adv_group)

        root.addStretch()

        self._run_btn = QPushButton("분류 시작")
        self._run_btn.setFixedHeight(44)
        self._run_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; font-size: 15px; "
            "border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
            "QPushButton:disabled { background-color: #93c5fd; }"
        )
        root.addWidget(self._run_btn)
        
        self._back_btn = QPushButton("← 허브로 돌아가기")
        self._back_btn.setStyleSheet("color: #4b5563; font-weight: bold; border: none; padding: 8px;")
        root.addWidget(self._back_btn)

    def _auto_detect_exiftool(self) -> None:
        path = resolve_exiftool_path()
        if path:
            self._exiftool_line.setText(path)
            self._exiftool_line.setStyleSheet("color: #16a34a;")
        else:
            self._exiftool_line.setPlaceholderText("ExifTool을 찾지 못했습니다. 직접 경로를 지정해 주세요.")
            self._exiftool_line.setStyleSheet("color: #dc2626;")

    def _browse_exiftool(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "ExifTool 실행 파일 선택", str(Path.home()), "실행 파일 (*.exe);;모든 파일 (*)"
        )
        if path:
            self._exiftool_line.setText(path)
            self._exiftool_line.setStyleSheet("")

    def _warn_overwrite(self, checked: bool) -> None:
        if checked:
            QMessageBox.warning(
                self,
                "덮어쓰기 경고",
                "덮어쓰기는 같은 이름의 기존 파일을 교체합니다.\n"
                "확실한 경우에만 선택하세요.",
            )

    def validate(self) -> bool:
        if not self._input_row.path:
            QMessageBox.warning(self, "입력 폴더 없음", "입력 폴더를 선택해 주세요.")
            return False
        if not Path(self._input_row.path).is_dir():
            QMessageBox.warning(self, "입력 폴더 없음", f"입력 폴더가 존재하지 않습니다:\n{self._input_row.path}")
            return False
        if not self._output_row.path:
            QMessageBox.warning(self, "출력 폴더 없음", "출력 폴더를 선택해 주세요.")
            return False
        if not self._exiftool_line.text().strip():
            QMessageBox.warning(self, "ExifTool 경로 없음", "ExifTool 실행 파일 경로를 지정해 주세요.")
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
            folder_depth=self._depth_cb.currentData(),
            no_gps_depth=self._no_gps_depth_cb.currentData(),
        )

    @property
    def run_button(self) -> QPushButton:
        return self._run_btn

    @property
    def output_path(self) -> str:
        return self._output_row.path

    @property
    def back_button(self) -> QPushButton:
        return self._back_btn
