"""
Offline video exporter.
- VideoBuilder: QTimer-based frame capturer on the main thread.
- VideoExportWindow: standalone top-level window (separate from main app),
  non-modal, can be hidden while build continues.
"""

from __future__ import annotations

import os
import tempfile
import shutil
from typing import TYPE_CHECKING

import cv2
import numpy as np

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QFileDialog, QMessageBox,
)
from PyQt5.QtGui import QFont, QImage

if TYPE_CHECKING:
    from log_parser import FlightData, FlightPoint
    from map_widget import MapWidget

from i18n import lang, tr


# ──────────────────────────────────────────────────── VideoBuilder ─────────────

class VideoBuilder(QObject):
    """
    Captures map_widget frame-by-frame via QTimer (main thread) and writes
    an MP4 at 1920×1080 / 15 FPS.  Each data point is repeated as many
    video frames as its real timestamp requires → video duration = flight duration.
    """

    frame_done = pyqtSignal(int, int)   # (data_points_done, total_data_points)
    finished   = pyqtSignal(str)        # temp output path
    failed     = pyqtSignal(str)        # error message

    VIDEO_FPS = 15
    VIDEO_W   = 1920
    VIDEO_H   = 1080
    RENDER_MS = 90          # ms to wait after updateFrame() before grabbing

    def __init__(self, map_widget: MapWidget, points: list[FlightPoint],
                 output_path: str, parent=None):
        super().__init__(parent)
        self._map       = map_widget
        self._pts       = points
        self._path      = output_path
        self._writer    = None
        self._idx       = 0
        self._cancelled = False
        self._counts    = self._calc_counts(points)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._grab_and_advance)

    # ------------------------------------------------------------------

    @classmethod
    def _calc_counts(cls, pts: list[FlightPoint]) -> list[int]:
        n = len(pts)
        out: list[int] = []
        for i in range(n):
            dt = (pts[i + 1].time - pts[i].time if i < n - 1
                  else pts[-1].time - pts[-2].time if n >= 2
                  else 1.0 / cls.VIDEO_FPS)
            out.append(max(1, round(dt * cls.VIDEO_FPS)))
        return out

    def total_video_frames(self) -> int:
        return sum(self._counts)

    def frame_counts(self) -> list[int]:
        return self._counts

    # ------------------------------------------------------------------

    def start(self):
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self._writer = cv2.VideoWriter(
            self._path, fourcc, float(self.VIDEO_FPS), (self.VIDEO_W, self.VIDEO_H)
        )
        if not self._writer.isOpened():
            self.failed.emit(f"VideoWriter ochib bo'lmadi:\n{self._path}")
            return
        self._idx = 0
        self._cancelled = False
        self._step()

    def cancel(self):
        self._cancelled = True
        self._timer.stop()
        if self._writer and self._writer.isOpened():
            self._writer.release()

    @property
    def current_index(self) -> int:
        return self._idx

    # ------------------------------------------------------------------

    def _step(self):
        if self._cancelled or self._idx >= len(self._pts):
            if not self._cancelled:
                self._writer.release()
                self.finished.emit(self._path)
            return
        self._map.update_frame(self._idx)
        self._timer.start(self.RENDER_MS)

    def _grab_and_advance(self):
        if self._cancelled:
            return
        pix = self._map.grab()
        img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
        img = img.scaled(self.VIDEO_W, self.VIDEO_H,
                         Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        ptr = img.bits()
        ptr.setsize(self.VIDEO_W * self.VIDEO_H * 4)
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape(
            (self.VIDEO_H, self.VIDEO_W, 4)
        )
        bgr = np.ascontiguousarray(arr[:, :, :3])
        for _ in range(self._counts[self._idx]):
            self._writer.write(bgr)

        self.frame_done.emit(self._idx + 1, len(self._pts))
        self._idx += 1
        self._step()


# ──────────────────────────────────────────────── VideoExportWindow ────────────

_WIN_STYLE = """
    QWidget#video-win {
        background: #04080f;
        border: 1px solid #0e1e30;
    }
    QLabel {
        color: #7ab0e0;
        font-family: 'Segoe UI', sans-serif;
        font-size: 12px;
        background: transparent;
    }
    QLabel#title-lbl {
        color: #2a6090;
        font-size: 11px;
        letter-spacing: 1px;
    }
    QLabel#status-lbl {
        color: #5090c0;
        font-size: 12px;
    }
    QLabel#done-lbl {
        color: #00cc88;
        font-size: 14px;
        font-weight: bold;
    }
    QLabel#info-lbl {
        color: #2a5070;
        font-size: 11px;
        font-family: 'Courier New', monospace;
    }
    QProgressBar {
        background: #070d18;
        border: 1px solid #1a3050;
        border-radius: 5px;
        height: 22px;
        text-align: center;
        color: #4a80a0;
        font-size: 11px;
    }
    QProgressBar::chunk {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #003366, stop:1 #0077dd);
        border-radius: 4px;
    }
    QPushButton {
        background: #0a1628;
        color: #5a90c0;
        border: 1px solid #1a3050;
        border-radius: 5px;
        padding: 5px 18px;
        font-family: 'Segoe UI', sans-serif;
        font-size: 11px;
    }
    QPushButton:hover   { background: #122040; color: #90c0e0; }
    QPushButton:pressed { background: #070e1c; }
    QPushButton#save-btn {
        background: #003d7a;
        color: #80c8ff;
        border-color: #005ab0;
        font-weight: 600;
        font-size: 12px;
    }
    QPushButton#save-btn:hover    { background: #0055aa; color: #fff; }
    QPushButton#save-btn:disabled {
        background: #070d18;
        color: #1a3050;
        border-color: #0d1828;
    }
    QPushButton#cancel-btn { color: #3a6080; font-size: 11px; }
    QPushButton#cancel-btn:hover { color: #7090a8; }
"""


class VideoExportWindow(QWidget):
    """
    Standalone top-level window — completely separate from the main app.
    Closing it hides it (build continues); the main window compact bar
    still shows progress and lets the user re-open this window.

    Signals (for main window compact bar):
      sig_frame  (cur, total)  — frame progress
      sig_done   (temp_path)   — build finished
      sig_failed (msg)         — build error
      sig_cancel ()            — user clicked Cancel
    """

    sig_frame  = pyqtSignal(int, int)
    sig_done   = pyqtSignal(str)
    sig_failed = pyqtSignal(str)
    sig_cancel = pyqtSignal()

    def __init__(self):
        super().__init__(None, Qt.Window)          # no parent → truly separate
        self.setObjectName("video-win")
        self.setWindowTitle(tr('vw_title'))
        self.setFixedWidth(500)
        self.setStyleSheet(_WIN_STYLE)

        self._builder   = None
        self._temp_path = None
        self._building  = False

        # ── widgets ──────────────────────────────────────────────────────────
        self._lbl_title = QLabel(tr('vw_header'))
        self._lbl_title.setObjectName("title-lbl")
        self._lbl_title.setAlignment(Qt.AlignCenter)

        self._lbl_status = QLabel("—")
        self._lbl_status.setObjectName("status-lbl")
        self._lbl_status.setWordWrap(True)

        self._bar = QProgressBar()
        self._bar.setTextVisible(True)
        self._bar.setFormat("%p%  (%v / %m log kadr)")

        self._lbl_info = QLabel("")
        self._lbl_info.setObjectName("info-lbl")
        self._lbl_info.setAlignment(Qt.AlignCenter)

        self._btn_save = QPushButton(tr('vw_btn_save'))
        self._btn_save.setObjectName("save-btn")
        self._btn_save.setEnabled(False)
        self._btn_save.setFixedHeight(36)
        self._btn_save.clicked.connect(self._save_video)

        self._btn_cancel = QPushButton(tr('vw_btn_cancel'))
        self._btn_cancel.setObjectName("cancel-btn")
        self._btn_cancel.clicked.connect(self._on_cancel)

        # divider line
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet("background: #0e1e30;")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_save)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(self._lbl_title)
        lay.addWidget(div)
        lay.addWidget(self._lbl_status)
        lay.addWidget(self._bar)
        lay.addWidget(self._lbl_info)
        lay.addSpacing(4)
        lay.addLayout(btn_row)

    # ── public API ───────────────────────────────────────────────────────────

    def start_build(self, map_widget: MapWidget, flight_data: FlightData):
        pts = flight_data.points
        if not pts:
            QMessageBox.warning(None, "Xato", "Hech qanday GPS kadr yo'q.")
            return

        self._temp_path = tempfile.mktemp(suffix='.mp4', prefix='px4_video_')
        self._builder   = VideoBuilder(map_widget, pts, self._temp_path, self)
        self._building  = True

        # info header
        duration = pts[-1].time - pts[0].time
        m, s = divmod(int(duration), 60)
        h, m = divmod(m, 60)
        dur_str  = f'{h:02d}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'
        total_vf = self._builder.total_video_frames()

        self._lbl_status.setText(tr('vw_building',
            w=VideoBuilder.VIDEO_W, h=VideoBuilder.VIDEO_H,
            fps=VideoBuilder.VIDEO_FPS, dur=dur_str))
        self._bar.setRange(0, len(pts))
        self._bar.setValue(0)
        self._lbl_info.setText(tr('vw_info_total', n=total_vf))
        self._btn_save.setEnabled(False)
        self._btn_cancel.setText(tr('vw_btn_cancel'))

        self._builder.frame_done.connect(self._on_frame)
        self._builder.finished.connect(self._on_done)
        self._builder.failed.connect(self._on_failed)

        lang.language_changed.connect(self.retranslate)
        self.show()
        self._builder.start()

    def show_or_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def cancel_build(self):
        """Called externally (e.g. from main window compact bar)."""
        self._on_cancel()

    # ── private slots ────────────────────────────────────────────────────────

    def _on_frame(self, cur, total):
        self._bar.setValue(cur)
        counts   = self._builder.frame_counts() if self._builder else []
        done_vf  = sum(counts[:cur])
        total_vf = sum(counts)
        self._lbl_info.setText(tr('vw_info_frames', done=done_vf, total=total_vf))
        self.sig_frame.emit(cur, total)

    def _on_done(self, path):
        self._temp_path = path
        self._building  = False
        self._lbl_status.setStyleSheet(
            "color: #00cc88; font-size: 14px; font-weight: bold;"
        )
        self._lbl_status.setText(tr('vw_done'))
        n    = self._bar.maximum()
        n_vf = self._builder.total_video_frames() if self._builder else 0
        self._lbl_info.setText(tr('vw_info_written', n=n, vf=n_vf))
        self._btn_save.setEnabled(True)
        self._btn_cancel.setText(tr('vw_btn_close'))
        self.show_or_raise()
        self.sig_done.emit(path)

    def _on_failed(self, msg):
        self._building = False
        self._cleanup()
        self.hide()
        QMessageBox.critical(None, tr('msg_video_err'), msg)
        self.sig_failed.emit(msg)

    def _on_cancel(self):
        if self._builder:
            self._builder.cancel()
        self._building = False
        self._cleanup()
        self.hide()
        self.sig_cancel.emit()

    def _save_video(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr('dlg_save_video'),
            os.path.join(os.path.expanduser("~"), "Desktop", "flight_log.mp4"),
            tr('dlg_filter_mp4')
        )
        if not path:
            return
        if not path.lower().endswith('.mp4'):
            path += '.mp4'
        try:
            shutil.copy2(self._temp_path, path)
        except Exception as e:
            QMessageBox.critical(self, tr('msg_save_err'), str(e))
            return
        QMessageBox.information(self, tr('msg_saved_title'),
                                tr('msg_saved_body', path))
        self._cleanup()
        self.hide()
        self.sig_cancel.emit()   # notify main window compact bar to hide

    def closeEvent(self, event):
        if self._building:
            event.ignore()        # hide instead of closing during build
            self.hide()
        else:
            self._cleanup()
            event.accept()

    def retranslate(self, _code: str = '') -> None:
        """Called by main window when language changes."""
        self.setWindowTitle(tr('vw_title'))
        self._lbl_title.setText(tr('vw_header'))
        self._btn_save.setText(tr('vw_btn_save'))
        if self._building:
            self._btn_cancel.setText(tr('vw_btn_cancel'))
        elif not self._building and self._btn_save.isEnabled():
            self._btn_cancel.setText(tr('vw_btn_close'))
            self._lbl_status.setText(tr('vw_done'))

    def _cleanup(self):
        if self._temp_path and os.path.exists(self._temp_path):
            try:
                os.remove(self._temp_path)
            except Exception:
                pass
        self._temp_path = None
        self._builder   = None
