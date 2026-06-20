"""
Map widget wrapping QWebEngineView with Leaflet / Google hybrid tiles.
"""

import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from PyQt5.QtCore import QUrl, pyqtSignal


class SilentPage(QWebEnginePage):
    """Suppress JS console noise; relay __follow__ control messages."""
    follow_disabled = pyqtSignal()

    def javaScriptConsoleMessage(self, level, msg, line, src):
        if msg == '__follow__:disabled':
            self.follow_disabled.emit()


class MapWidget(QWidget):
    follow_disabled = pyqtSignal()   # re-emitted from page → main window

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view = QWebEngineView()
        page = SilentPage(self._view)
        page.follow_disabled.connect(self.follow_disabled)
        self._view.setPage(page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        html_path = os.path.join(os.path.dirname(__file__), 'resources', 'map.html')
        self._view.load(QUrl.fromLocalFile(html_path))
        self._ready = False
        self._pending_data = None
        self._view.loadFinished.connect(self._on_load_finished)

    # ------------------------------------------------------------------

    def _on_load_finished(self, ok):
        self._ready = ok
        if ok and self._pending_data is not None:
            self._run_set_data(self._pending_data)
            self._pending_data = None

    def _js(self, code):
        if self._ready:
            self._view.page().runJavaScript(code)

    def _run_set_data(self, cmd):
        self._js(cmd)

    # ------------------------------------------------------------------

    def load_flight(self, flight_data):
        """Pass FlightData to the map (draws full path, places markers)."""
        js_array    = flight_data.to_js_array()
        events_json = flight_data.to_js_events()
        cmd = f'setFlightData({js_array}); setFlightEvents({events_json});'
        if self._ready:
            self._js(cmd)
        else:
            self._pending_data = cmd

    def update_frame(self, index):
        """Move drone marker and extend traveled-path to `index`."""
        self._js(f'updateFrame({index});')

    def fit_all(self):
        self._js('fitAll();')

    def center_on_drone(self):
        self._js('centerOnDrone();')

    def set_follow(self, enabled: bool):
        self._js(f'setFollowMode({str(enabled).lower()});')
