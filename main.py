"""PhotoVault — local photo library manager. Entry point."""

import sys
import os
import logging
from pathlib import Path

# Ensure project root is on path when running directly
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.main_window import MainWindow

APP_DIR = os.path.join(Path.home(), ".photovault")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PhotoVault")
    app.setOrganizationName("PhotoVault")
    app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    app.setFont(font)

    window = MainWindow(app_dir=APP_DIR)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
