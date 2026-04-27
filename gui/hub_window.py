# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.image_editor_window import ImageEditorWindow
from gui.live_photo_window import LivePhotoWindow
from gui.main_window import MainWindow
from gui.video_window import VideoWindow


class HubWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Media Pipeline Hub")
        self.setMinimumSize(1180, 560)
        self.resize(1320, 620)

        self._classifier_window = None
        self._video_window = None
        self._live_photo_window = None
        self._image_editor_window = None

        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        central.setStyleSheet("background: #f8fafc;")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(36, 32, 36, 32)
        root.setSpacing(24)

        title = QLabel("Media Management Hub")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 800; color: #111827;")

        subtitle = QLabel("Choose a workflow")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #4b5563;")

        root.addWidget(title)
        root.addWidget(subtitle)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(18)
        buttons_layout.addStretch()

        btn_classifier = self._tool_button(
            "Photo Organizer",
            "Sort photos and videos into country/city folders using GPS metadata.",
            "#2563eb",
            "#1d4ed8",
        )
        btn_video = self._tool_button(
            "Video Converter",
            "Downscale large videos while preserving metadata.",
            "#059669",
            "#047857",
        )
        btn_live = self._tool_button(
            "Live Photo Converter",
            "Extract a still image from Live Photo video files.",
            "#7c3aed",
            "#6d28d9",
        )
        btn_editor = self._tool_button(
            "Image Batch Editor",
            "Batch resize, crop, convert formats, and preserve EXIF.",
            "#d97706",
            "#b45309",
        )

        buttons_layout.addWidget(btn_classifier)
        buttons_layout.addWidget(btn_video)
        buttons_layout.addWidget(btn_live)
        buttons_layout.addWidget(btn_editor)
        buttons_layout.addStretch()

        root.addLayout(buttons_layout)
        root.addStretch()

        btn_classifier.clicked.connect(self._open_classifier)
        btn_video.clicked.connect(self._open_converter)
        btn_live.clicked.connect(self._open_live_photo)
        btn_editor.clicked.connect(self._open_image_editor)

    def _tool_button(self, title: str, description: str, bg_color: str, hover_color: str) -> QPushButton:
        button = QPushButton()
        button.setFixedSize(270, 220)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {bg_color};
                border-radius: 10px;
                border: none;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {hover_color};
                padding-top: 3px;
            }}
            """
        )

        layout = QVBoxLayout(button)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: white; background: transparent; border: none;"
        )

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255,255,255,0.35); border: none;")

        desc_label = QLabel(description)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            "font-size: 13px; line-height: 1.35; color: rgba(255,255,255,0.88); "
            "background: transparent; border: none;"
        )

        layout.addStretch()
        layout.addWidget(title_label)
        layout.addWidget(line)
        layout.addWidget(desc_label)
        layout.addStretch()
        return button

    def _back_from_child(self, child) -> None:
        if child:
            child.hide()
        self.show()

    def _open_classifier(self) -> None:
        self.hide()
        if not self._classifier_window:
            self._classifier_window = MainWindow(
                on_back_to_hub=lambda: self._back_from_child(self._classifier_window)
            )
        self._classifier_window.show()

    def _open_converter(self) -> None:
        self.hide()
        if not self._video_window:
            self._video_window = VideoWindow(
                on_back_to_hub=lambda: self._back_from_child(self._video_window)
            )
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
