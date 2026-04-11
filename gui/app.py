"""
QApplication entry point.
"""
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gui.main_window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Photo Classifier")
    app.setOrganizationName("PhotoClassifier")

    # Crisp rendering on high-DPI displays
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    window = MainWindow()
    window.show()
    return app.exec()
