# -*- coding: utf-8 -*-
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QVBoxLayout, QWidget, QLabel, QPushButton, QGroupBox, QMessageBox
)

from gui.screen_setup import FolderRow
from core.video_converter import resolve_ffmpeg_path, resolve_ffprobe_path, VideoConverterConfig, detect_hardware_encoder
from core.extractor import resolve_exiftool_path
from core.video_converter import logger

class VideoSetupScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._check_dependencies()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(32, 24, 32, 24)

        title = QLabel("Video Resolution Converter")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 4px;")
        root.addWidget(title)

        subtitle = QLabel("Downscale large videos (4K/8K) to HD/FHD while keeping original files intact.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666; margin-bottom: 12px;")
        root.addWidget(subtitle)

        # Folder group
        folder_group = QGroupBox("Folders")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(8)

        self._input_row = FolderRow("Input Folder", "Folder containing videos to convert")
        self._output_row = FolderRow("Output Folder", "Folder to write HD videos")
        folder_layout.addWidget(self._input_row)
        folder_layout.addWidget(self._output_row)
        root.addWidget(folder_group)

        # Resolution Setting
        res_group = QGroupBox("Target Resolution & Acceleration")
        res_layout = QVBoxLayout(res_group)
        
        res_info = QLabel("Videos larger than target will be downscaled. Smaller videos skipped.")
        res_info.setStyleSheet("color: #555;")
        res_layout.addWidget(res_info)

        self._res_cb = QComboBox()
        self._res_cb.addItem("FHD - 1080p (1920x1080) - Recommended", "fhd")
        self._res_cb.addItem("HD - 720p (1280x720) - Extra Small", "hd")
        self._res_cb.addItem("4K - 2160p (3840x2160) - High Quality", "4k")
        self._res_cb.setCurrentIndex(0)
        self._res_cb.setFixedHeight(30)
        res_layout.addWidget(self._res_cb)
        
        self._codec_cb = QComboBox()
        self._codec_cb.addItem("H.264 (Maximum Compatibility, 8-bit SDR Forced)", "h264")
        self._codec_cb.addItem("H.265 / HEVC (Preserve 10-bit HDR Colors, High Quality)", "hevc")
        self._codec_cb.setCurrentIndex(0)
        self._codec_cb.setFixedHeight(30)
        self._codec_cb.currentIndexChanged.connect(self._on_codec_changed)
        res_layout.addWidget(self._codec_cb)

        self._gpu_label = QLabel("GPU Status: Checking...")
        self._gpu_label.setStyleSheet("color: #666; font-weight: bold; margin-top: 5px;")
        res_layout.addWidget(self._gpu_label)
        
        root.addWidget(res_group)
        
        # Dependencies status
        self._deps_label = QLabel()
        self._deps_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self._deps_label)

        root.addStretch()

        # Buttons
        self._run_btn = QPushButton("Start Conversion")
        self._run_btn.setFixedHeight(44)
        self._run_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; font-size: 15px; "
            "border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
            "QPushButton:disabled { background-color: #93c5fd; }"
        )
        root.addWidget(self._run_btn)
        
        self._back_btn = QPushButton("← Back to Hub")
        self._back_btn.setStyleSheet("color: #4b5563; font-weight: bold; border: none; padding: 8px;")
        root.addWidget(self._back_btn)

    def _on_codec_changed(self):
        try:
            ffmpeg_path = resolve_ffmpeg_path()
            self._detect_gpu(ffmpeg_path)
        except Exception:
            pass

    def _check_dependencies(self):
        missing = []
        ffmpeg_path = None
        try:
            ffmpeg_path = resolve_ffmpeg_path()
        except FileNotFoundError:
            missing.append("FFmpeg")
            
        try:
            resolve_ffprobe_path()
        except FileNotFoundError:
            missing.append("FFprobe")
            
        if missing:
            self._deps_label.setText(f"Missing: {', '.join(missing)} (Place in assets/)")
            self._deps_label.setStyleSheet("color: #dc2626; font-weight: bold;")
            self._gpu_label.setText("GPU Status: Cannot detect (FFmpeg missing)")
            self._gpu_label.setStyleSheet("color: #dc2626;")
        else:
            self._deps_label.setText("✔ All required dependencies found (FFmpeg, FFprobe)")
            self._deps_label.setStyleSheet("color: #16a34a; font-weight: bold;")
            
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, lambda: self._detect_gpu(ffmpeg_path))

    def _detect_gpu(self, ffmpeg_path: str):
        self._gpu_label.setText(f"GPU Status: Scanning hardware for {self.codec_choice.upper()}...")
        self._gpu_label.repaint()
        encoder = detect_hardware_encoder(ffmpeg_path, Path.home(), self.codec_choice)
        if encoder not in ["libx264", "libx265"]:
            name = "NVIDIA NVENC" if "nvenc" in encoder else "Intel QSV" if "qsv" in encoder else "AMD AMF" if "amf" in encoder else encoder
            self._gpu_label.setText(f"⚡ GPU Acceleration Active ({name} for {self.codec_choice.upper()}) - Hyper speed encoding ready!")
            self._gpu_label.setStyleSheet("color: #059669; font-weight: bold;")
        else:
            self._gpu_label.setText(f"⚠️ No compatible GPU detected for {self.codec_choice.upper()}. Falling back to CPU encoding (Slower)")
            self._gpu_label.setStyleSheet("color: #d97706; font-weight: bold;")

    def validate(self) -> bool:
        if not self._input_row.path:
            QMessageBox.warning(self, "Missing Input", "Please select Input Folder.")
            return False
        if not Path(self._input_row.path).is_dir():
            QMessageBox.warning(self, "Input Not Found", "Input folder does not exist.")
            return False
        if not self._output_row.path:
            QMessageBox.warning(self, "Missing Output", "Please select Output Folder.")
            return False
            
        try:
            resolve_ffmpeg_path()
            resolve_ffprobe_path()
        except FileNotFoundError:
            QMessageBox.critical(self, "Missing Dependencies", "FFmpeg or FFprobe missing.")
            return False
            
        return True

    def build_config(self) -> VideoConverterConfig:
        res_key = self._res_cb.currentData()
        w, h = 1920, 1080
        if res_key == "hd":
            w, h = 1280, 720
        elif res_key == "4k":
            w, h = 3840, 2160
            
        return VideoConverterConfig(
            input_folder=Path(self._input_row.path),
            output_folder=Path(self._output_row.path),
            max_width=w,
            max_height=h,
            codec=self.codec_choice
        )

    @property
    def output_folder(self) -> str:
        return self._output_row.path
        
    @property
    def target_resolution(self) -> str:
        return self._res_cb.currentData()
        
    @property
    def codec_choice(self) -> str:
        return self._codec_cb.currentData()

    @property
    def run_button(self) -> QPushButton:
        return self._run_btn
        
    @property
    def back_button(self) -> QPushButton:
        return self._back_btn
