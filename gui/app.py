"""
QApplication entry point.
"""
# -*- coding: utf-8 -*-
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.logging_config import setup_logger
from gui.hub_window import HubWindow


def run() -> int:
    # Initialize logging to logs/ directory
    log_dir = Path(__file__).parent.parent / "logs"
    setup_logger("photo_classifier", log_dir=log_dir)
    
    app = QApplication(sys.argv)
    app.setApplicationName("사진/영상 분류기")
    app.setOrganizationName("PhotoClassifier")

    # Crisp rendering on high-DPI displays
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    window = HubWindow()
    window.show()
    return app.exec()
