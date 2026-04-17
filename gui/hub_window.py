# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from gui.main_window import MainWindow
from gui.video_window import VideoWindow
from gui.live_photo_window import LivePhotoWindow
from gui.image_editor_window import ImageEditorWindow

class HubWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Media Pipeline Hub")
        self.setMinimumSize(1340, 500)
        self.resize(1400, 560)

        # Store child windows to keep them alive
        self._classifier_window = None
        self._video_window = None
        self._live_photo_window = None
        self._image_editor_window = None
        
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(24)

        # Header
        header_layout = QVBoxLayout()
        title = QLabel("Media Management Hub")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #1e293b;")
        
        subtitle = QLabel("Select a media pipeline tool to continue")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #64748b; margin-bottom: 20px;")
        
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addLayout(header_layout)

        # Buttons wrapper
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(20)

        # Classifier Button
        btn_classifier = QPushButton()
        btn_classifier.setFixedSize(300, 220)
        btn_classifier.setStyleSheet(self._button_style("#2563eb", "#1d4ed8"))
        btn_classifier.setCursor(Qt.PointingHandCursor)
        
        cls_layout = QVBoxLayout(btn_classifier)
        cls_icon = QLabel("📂")
        cls_icon.setAlignment(Qt.AlignCenter)
        cls_icon.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        cls_title = QLabel("Photo/Video\nOrganizer")
        cls_title.setAlignment(Qt.AlignCenter)
        cls_title.setStyleSheet("font-size: 20px; font-weight: bold; color: white; background: transparent; border: none;")
        cls_desc = QLabel("Classify files into country/city folders folders using GPS EXIF.")
        cls_desc.setAlignment(Qt.AlignCenter)
        cls_desc.setWordWrap(True)
        cls_desc.setStyleSheet("font-size: 13px; color: #bfdbfe; background: transparent; border: none; padding: 0 10px;")
        
        cls_layout.addWidget(cls_icon)
        cls_layout.addWidget(cls_title)
        cls_layout.addWidget(cls_desc)
        cls_layout.setAlignment(Qt.AlignCenter)

        # Video Converter Button
        btn_video = QPushButton()
        btn_video.setFixedSize(300, 220)
        btn_video.setStyleSheet(self._button_style("#059669", "#047857"))
        btn_video.setCursor(Qt.PointingHandCursor)
        
        vid_layout = QVBoxLayout(btn_video)
        vid_icon = QLabel("🎞️")
        vid_icon.setAlignment(Qt.AlignCenter)
        vid_icon.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        vid_title = QLabel("Video Resolution\nConverter")
        vid_title.setAlignment(Qt.AlignCenter)
        vid_title.setStyleSheet("font-size: 20px; font-weight: bold; color: white; background: transparent; border: none;")
        vid_desc = QLabel("Downscale 4K/8K videos to HD/FHD while keeping all EXIF data.")
        vid_desc.setAlignment(Qt.AlignCenter)
        vid_desc.setWordWrap(True)
        vid_desc.setStyleSheet("font-size: 13px; color: #a7f3d0; background: transparent; border: none; padding: 0 10px;")
        
        vid_layout.addWidget(vid_icon)
        vid_layout.addWidget(vid_title)
        vid_layout.addWidget(vid_desc)
        vid_layout.setAlignment(Qt.AlignCenter)

        # Live Photo Converter Button
        btn_live = QPushButton()
        btn_live.setFixedSize(300, 220)
        btn_live.setStyleSheet(self._button_style("#7c3aed", "#6d28d9"))
        btn_live.setCursor(Qt.PointingHandCursor)

        live_layout = QVBoxLayout(btn_live)
        live_icon = QLabel("📸")
        live_icon.setAlignment(Qt.AlignCenter)
        live_icon.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        live_title = QLabel("Live Photo\nConverter")
        live_title.setAlignment(Qt.AlignCenter)
        live_title.setStyleSheet("font-size: 20px; font-weight: bold; color: white; background: transparent; border: none;")
        live_desc = QLabel("Extract the sharpest still image from Live Photos (MP4/MOV) with EXIF preserved.")
        live_desc.setAlignment(Qt.AlignCenter)
        live_desc.setWordWrap(True)
        live_desc.setStyleSheet("font-size: 13px; color: #ddd6fe; background: transparent; border: none; padding: 0 10px;")

        live_layout.addWidget(live_icon)
        live_layout.addWidget(live_title)
        live_layout.addWidget(live_desc)
        live_layout.setAlignment(Qt.AlignCenter)

        # Image Editor Button
        btn_editor = QPushButton()
        btn_editor.setFixedSize(300, 220)
        btn_editor.setStyleSheet(self._button_style("#d97706", "#b45309"))
        btn_editor.setCursor(Qt.PointingHandCursor)

        ed_layout = QVBoxLayout(btn_editor)
        ed_icon = QLabel("🖼️")
        ed_icon.setAlignment(Qt.AlignCenter)
        ed_icon.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        ed_title = QLabel("이미지\n일괄 편집기")
        ed_title.setAlignment(Qt.AlignCenter)
        ed_title.setStyleSheet("font-size: 20px; font-weight: bold; color: white; background: transparent; border: none;")
        ed_desc = QLabel("모든 포맷(RAW·HEIC 포함) 일괄 크기 조절·자르기 및 EXIF 보전.")
        ed_desc.setAlignment(Qt.AlignCenter)
        ed_desc.setWordWrap(True)
        ed_desc.setStyleSheet("font-size: 13px; color: #fde68a; background: transparent; border: none; padding: 0 10px;")

        ed_layout.addWidget(ed_icon)
        ed_layout.addWidget(ed_title)
        ed_layout.addWidget(ed_desc)
        ed_layout.setAlignment(Qt.AlignCenter)

        # Add to layout
        buttons_layout.addStretch()
        buttons_layout.addWidget(btn_classifier)
        buttons_layout.addWidget(btn_video)
        buttons_layout.addWidget(btn_live)
        buttons_layout.addWidget(btn_editor)
        buttons_layout.addStretch()

        root.addLayout(buttons_layout)
        root.addStretch()

        # Connect actions
        btn_classifier.clicked.connect(self._open_classifier)
        btn_video.clicked.connect(self._open_converter)
        btn_live.clicked.connect(self._open_live_photo)
        btn_editor.clicked.connect(self._open_image_editor)

    def _button_style(self, bg_color: str, hover_color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg_color};
                border-radius: 12px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {hover_color};
                padding-top: 4px;
            }}
        """

    def _open_classifier(self) -> None:
        self.hide()
        if not self._classifier_window:
            self._classifier_window = MainWindow(on_back_to_hub=self.show)
        # Position slightly offset or centered
        self._classifier_window.show()

    def _open_converter(self) -> None:
        self.hide()
        if not self._video_window:
            self._video_window = VideoWindow(on_back_to_hub=self.show)
        self._video_window.show()

    def _open_live_photo(self) -> None:
        self.hide()
        if not self._live_photo_window:
            self._live_photo_window = LivePhotoWindow(on_back_to_hub=self.show)
        self._live_photo_window.show()

    def _open_image_editor(self) -> None:
        self.hide()
        if not self._image_editor_window:
            self._image_editor_window = ImageEditorWindow(on_back_to_hub=self.show)
        self._image_editor_window.show()
