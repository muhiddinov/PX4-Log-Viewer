"""
PX4 / ArduPilot Flight Log Viewer
----------------------------------
Usage:
    python main.py
    python main.py logs/2026-06-18.bin
"""

import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QIcon

# Required for GPU compositing / WebEngine
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS',
                      '--disable-gpu --no-sandbox')

# High-DPI support — must be set BEFORE QApplication
QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)


def main():
    # WebEngine must be imported before QApplication on some platforms
    from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    app = QApplication(sys.argv)
    app.setApplicationName('PX4 Flight Log Viewer')
    app.setOrganizationName('UAV Tools')

    _icon_path = os.path.join(os.path.dirname(__file__), 'resources', 'app_icon.ico')
    if os.path.isfile(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))

    from main_window import MainWindow
    win = MainWindow()
    win.showMaximized()

    # Auto-load if a file was passed on the command line
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        win._load_file(sys.argv[1])

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
