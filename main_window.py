"""
Main application window.
"""

import os
import datetime
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog,
    QSizePolicy, QFrame, QButtonGroup, QStatusBar,
    QToolButton, QSpacerItem, QProgressBar, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QSize, pyqtSlot
from PyQt5.QtGui import QIcon, QFont, QColor, QPalette, QFontDatabase

from map_widget     import MapWidget
from simulator      import FlightSimulator
from video_builder  import VideoExportWindow
import log_parser
from log_parser import FlightData
from i18n import lang, tr


# ─────────────────────────────────────────────────────────── helpers ──────────

def fmt_time(seconds):
    s = max(0, int(seconds))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f'{h:02d}:{m:02d}:{s:02d}'
    return f'{m:02d}:{s:02d}'


def fmt_abs_time(pt, tz=datetime.timezone.utc):
    """Return 'HH:MM:SS' in the given timezone, or relative fallback."""
    if pt.abs_time > 0:
        return datetime.datetime.fromtimestamp(pt.abs_time, tz=tz).strftime('%H:%M:%S')
    return fmt_time(pt.time)


# ─────────────────────────────────────────── custom slider (vertical) ─────────

class TimelineSlider(QSlider):
    """Horizontal slider styled to look like a progress/layer bar."""

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 0)
        self.setSingleStep(1)
        self.setPageStep(10)
        self.setTickPosition(QSlider.NoTicks)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #1e2d45;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0066cc, stop:1 #00aaff);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                height: 18px;
                margin: -6px 0;
                background: #00aaff;
                border: 2px solid #ffffff;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #33bbff;
                border-color: #aaddff;
            }
            QSlider::handle:horizontal:pressed {
                background: #ffffff;
            }
        """)


# ─────────────────────────────────────── icon-only flat tool button ───────────

def _make_btn(text, tooltip, min_w=44, checkable=False):
    b = QPushButton(text)
    b.setToolTip(tooltip)
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    b.setMinimumWidth(min_w)
    b.setFixedHeight(34)
    b.setFont(QFont('Segoe UI', 10))
    return b


def _make_speed_btn(label):
    b = QPushButton(label)
    b.setCheckable(True)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedSize(42, 30)
    b.setFont(QFont('Segoe UI', 9, QFont.Bold))
    b.setStyleSheet("""
        QPushButton {
            background: #0d1828;
            color: #5090c0;
            border: 1px solid #1e3050;
            border-radius: 4px;
        }
        QPushButton:hover { background: #162540; color: #80b8e0; }
        QPushButton:checked {
            background: #0055aa;
            color: #ffffff;
            border-color: #0077dd;
        }
    """)
    return b


# ─────────────────────────────────────────── draggable title bar widget ───────

class _TitleBar(QWidget):
    """Toolbar that also acts as the frameless window's drag handle."""

    def __init__(self, main_win: 'MainWindow', parent=None):
        super().__init__(parent)
        self._win  = main_win
        self._drag = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._win.isMaximized():
                self._drag = e.globalPos()
            else:
                self._drag = e.globalPos() - self._win.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if (e.buttons() & Qt.LeftButton) and self._drag is not None:
            if self._win.isMaximized():
                self._win.showNormal()
                self._drag = e.globalPos() - self._win.frameGeometry().topLeft()
            self._win.move(e.globalPos() - self._drag)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._win.isMaximized():
                self._win.showNormal()
            else:
                self._win.showMaximized()
        super().mouseDoubleClickEvent(e)


# ─────────────────────────────────────────────────────── main window ──────────

class MainWindow(QMainWindow):

    # ── global dark stylesheet ──────────────────────────────────────────────
    _STYLE = """
        QMainWindow, QWidget#root {
            background: #070d18;
        }
        QWidget {
            color: #c0d4f0;
            font-family: 'Segoe UI', sans-serif;
        }
        QStatusBar {
            background: #050b14;
            color: #3a5c80;
            font-size: 11px;
        }
        QLabel#section-label {
            color: #2a4a70;
            font-size: 10px;
            letter-spacing: 1px;
        }
        QPushButton {
            background: #0d1828;
            color: #7ab0e0;
            border: 1px solid #1a3050;
            border-radius: 5px;
            padding: 0 10px;
        }
        QPushButton:hover   { background: #152238; color: #a0c8f8; border-color: #2a5080; }
        QPushButton:pressed { background: #0a1520; }
        QPushButton:disabled { color: #2a3a50; border-color: #0d1828; }

        QPushButton#play-btn {
            background: #003d7a;
            color: #ffffff;
            border: 1px solid #005ab0;
            border-radius: 5px;
            font-size: 16px;
        }
        QPushButton#play-btn:hover   { background: #0055aa; border-color: #0077dd; }
        QPushButton#play-btn:pressed { background: #002a55; }
        QPushButton#play-btn:disabled { background: #0d1828; color: #2a3a50; }

        QPushButton#stop-btn {
            background: #3a0d10;
            color: #ff6070;
            border: 1px solid #5a1820;
            border-radius: 5px;
            font-size: 13px;
        }
        QPushButton#stop-btn:hover { background: #550d15; border-color: #882030; }

        QLabel#time-label {
            color: #4080b0;
            font-family: 'Courier New', monospace;
            font-size: 12px;
        }
        QLabel#time-total {
            color: #2a5070;
            font-family: 'Courier New', monospace;
            font-size: 12px;
        }
        QFrame#divider {
            background: #0e1e30;
            max-height: 1px;
        }
    """

    def __init__(self):
        super().__init__()
        self.setObjectName('root')
        self.setWindowTitle(tr('app_title'))
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(self._STYLE)

        self._sim  = FlightSimulator(self)
        self._data: FlightData | None = None
        self._user_seeking = False
        self._current_folder = ''
        self._video_win: VideoExportWindow | None = None
        self._drag_pos = None          # for frameless window dragging

        self._build_ui()
        self._connect_signals()
        self._set_controls_enabled(False)

    # ── UI construction ─────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        central.setObjectName('root')
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── toolbar ──────────────────────────────────────────────────────────
        toolbar = self._build_toolbar()
        root_layout.addWidget(toolbar)

        divider0 = QFrame()
        divider0.setObjectName('divider')
        divider0.setFrameShape(QFrame.HLine)
        root_layout.addWidget(divider0)

        # ── map + file panel ─────────────────────────────────────────────────
        map_area = QWidget()
        map_h = QHBoxLayout(map_area)
        map_h.setContentsMargins(0, 0, 0, 0)
        map_h.setSpacing(0)

        self.file_panel = self._build_file_panel()
        map_h.addWidget(self.file_panel)

        self.map_widget = MapWidget()
        map_h.addWidget(self.map_widget, stretch=1)

        root_layout.addWidget(map_area, stretch=1)

        divider1 = QFrame()
        divider1.setObjectName('divider')
        divider1.setFrameShape(QFrame.HLine)
        root_layout.addWidget(divider1)

        # ── control panel ─────────────────────────────────────────────────────
        ctrl = self._build_control_panel()
        root_layout.addWidget(ctrl)

        # ── compact video build panel (hidden until build starts) ─────────────
        self._compact_panel = self._build_compact_panel()
        root_layout.addWidget(self._compact_panel)

        # ── status bar ────────────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage(tr('status_ready'))

        self.lbl_filename = QLabel('')
        self.lbl_filename.setStyleSheet(
            'color:#2a5070; font-size:11px; padding-right:6px;'
        )
        self.status.addPermanentWidget(self.lbl_filename)

    # -- toolbar ----------------------------------------------------------

    def _build_toolbar(self):
        bar = _TitleBar(self)
        bar.setFixedHeight(46)
        bar.setStyleSheet('background:#060e1c; border-bottom:1px solid #0e1e30;')
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 0, 4, 0)
        h.setSpacing(8)

        _blue_btn = """
            QPushButton {
                background:#003d7a; color:#80c8ff;
                border:1px solid #005ab0; border-radius:5px;
                padding:0 14px; font-size:12px;
            }
            QPushButton:hover { background:#0055aa; color:#fff; }
        """

        self.btn_open = _make_btn(tr('btn_open'), tr('tip_open'))
        self.btn_open.setStyleSheet(_blue_btn)

        self.btn_open_folder = _make_btn(tr('btn_open_folder'), tr('tip_folder'))
        self.btn_open_folder.setStyleSheet("""
            QPushButton {
                background:#0d1e30; color:#5a90c0;
                border:1px solid #1a3550; border-radius:5px;
                padding:0 14px; font-size:12px;
            }
            QPushButton:hover { background:#162840; color:#88bce8; }
            QPushButton:checked { background:#003055; color:#80c8ff; border-color:#005580; }
        """)
        self.btn_open_folder.setCheckable(True)

        self.btn_fit    = _make_btn(tr('btn_fit'),         tr('tip_fit'))
        self.btn_center = _make_btn(tr('btn_follow'),      tr('tip_follow'), checkable=True)
        self.btn_video  = _make_btn(tr('btn_build_video'), tr('tip_build_video'))
        self.btn_center.setStyleSheet("""
            QPushButton {
                background:#0d1828; color:#7ab0e0;
                border:1px solid #1a3050; border-radius:5px; padding:0 10px;
            }
            QPushButton:hover   { background:#152238; color:#a0c8f8; border-color:#2a5080; }
            QPushButton:checked {
                background:#003d7a; color:#80c8ff;
                border:1px solid #005ab0;
            }
            QPushButton:checked:hover { background:#0055aa; color:#fff; }
        """)

        self.btn_video.setStyleSheet("""
            QPushButton {
                background:#0d1e2e; color:#6090b0;
                border:1px solid #1a3050; border-radius:5px;
                padding:0 14px; font-size:12px;
            }
            QPushButton:hover    { background:#162840; color:#90c0e0; }
            QPushButton:disabled { color:#1e3050; border-color:#0d1828; }
        """)

        self.lbl_title = QLabel(tr('map_title'))
        self.lbl_title.setStyleSheet(
            'color:#2a5080; font-size:13px; font-weight:600; letter-spacing:2px;'
        )
        self.lbl_title.setAlignment(Qt.AlignCenter)

        # Language toggle button
        self.btn_lang = QPushButton(f'🌐 {lang.current.upper()}')
        self.btn_lang.setFixedSize(58, 30)
        self.btn_lang.setFont(QFont('Segoe UI', 9, QFont.Bold))
        self.btn_lang.setToolTip('Switch language / Tilni o\'zgartirish')
        self.btn_lang.setStyleSheet("""
            QPushButton {
                background:#0a1828; color:#3a6888;
                border:1px solid #1a3555; border-radius:4px; font-size:10px;
            }
            QPushButton:hover { background:#122040; color:#70b0d8; }
            QPushButton:pressed { background:#070e1c; }
        """)

        h.addWidget(self.btn_open)
        h.addWidget(self.btn_open_folder)
        h.addWidget(self.btn_fit)
        h.addWidget(self.btn_center)
        h.addWidget(self.btn_video)
        h.addStretch()
        h.addWidget(self.lbl_title)
        h.addStretch()
        h.addWidget(self.btn_lang)

        # ── Window controls: Minimize · Restore · Close ───────────────────────
        _wc_base = (
            'border:none; border-radius:4px;'
            'font-size:15px; font-family:Segoe UI Symbol, sans-serif;'
        )
        self.btn_win_min = QPushButton('–')
        self.btn_win_min.setFixedSize(43, 30)
        self.btn_win_min.setToolTip('Yashirish (Minimize)')
        self.btn_win_min.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:#3a5878; {_wc_base} }}
            QPushButton:hover {{ background:#0d1e30; color:#88aac8; }}
            QPushButton:pressed {{ background:#070e1c; }}
        """)

        self.btn_win_restore = QPushButton('❐')
        self.btn_win_restore.setFixedSize(43, 30)
        self.btn_win_restore.setToolTip('Kattalashtirish / Tiklash (Maximize / Restore)')
        self.btn_win_restore.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:#3a5878; {_wc_base} }}
            QPushButton:hover {{ background:#0d1e30; color:#88aac8; }}
            QPushButton:pressed {{ background:#070e1c; }}
        """)

        self.btn_win_close = QPushButton('✕')
        self.btn_win_close.setFixedSize(43, 30)
        self.btn_win_close.setToolTip('Yopish (Close)')
        self.btn_win_close.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:#3a5878; {_wc_base} }}
            QPushButton:hover {{ background:#3a0a0a; color:#ff5555; }}
            QPushButton:pressed {{ background:#550808; color:#ff7777; }}
        """)

        h.addWidget(self.btn_win_min)
        h.addWidget(self.btn_win_restore)
        h.addWidget(self.btn_win_close)

        return bar

    def _build_file_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(220)
        panel.setStyleSheet(
            'background:#04080f; border-right:1px solid #0d1828;'
        )
        panel.hide()

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet('background:#060e1c; border-bottom:1px solid #0d1828;')
        hdr_h = QHBoxLayout(header)
        hdr_h.setContentsMargins(10, 0, 6, 0)

        self.lbl_folder = QLabel(tr('no_folder'))
        self.lbl_folder.setStyleSheet(
            'color:#2a5070; font-size:10px; letter-spacing:.5px;'
        )
        self.lbl_folder.setFixedHeight(32)

        hdr_h.addWidget(self.lbl_folder, stretch=1)
        layout.addWidget(header)

        # File list
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget {
                background: #04080f;
                color: #5a8ab0;
                border: none;
                font-family: 'Segoe UI', monospace;
                font-size: 11px;
                outline: none;
            }
            QListWidget::item {
                padding: 7px 12px;
                border-bottom: 1px solid #090f1a;
            }
            QListWidget::item:hover {
                background: #0a1628;
                color: #88bce0;
            }
            QListWidget::item:selected {
                background: #002a55;
                color: #80c8ff;
            }
        """)
        self.file_list.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.file_list, stretch=1)

        return panel

    # -- control panel ----------------------------------------------------

    def _build_control_panel(self):
        panel = QWidget()
        panel.setFixedHeight(102)
        panel.setStyleSheet('background:#060e1c;')
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(14, 8, 14, 8)
        vbox.setSpacing(6)

        # ── row 1: slider ───────────────────────────────────────────────────
        slider_row = QHBoxLayout()
        slider_row.setSpacing(10)

        self.lbl_time = QLabel('--:--:--')
        self.lbl_time.setObjectName('time-label')
        self.lbl_time.setFixedWidth(64)

        self.slider = TimelineSlider()

        self.lbl_total = QLabel('--:--:--')
        self.lbl_total.setObjectName('time-total')
        self.lbl_total.setFixedWidth(64)
        self.lbl_total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        slider_row.addWidget(self.lbl_time)
        slider_row.addWidget(self.slider, stretch=1)
        slider_row.addWidget(self.lbl_total)
        vbox.addLayout(slider_row)

        # ── row 2: transport + speed ────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        # Play / Pause
        self.btn_play = QPushButton('▶')
        self.btn_play.setObjectName('play-btn')
        self.btn_play.setFixedSize(46, 38)
        self.btn_play.setFont(QFont('Segoe UI', 13))
        self.btn_play.setToolTip(tr('tip_play'))

        # Stop
        self.btn_stop = QPushButton('■')
        self.btn_stop.setObjectName('stop-btn')
        self.btn_stop.setFixedSize(38, 38)
        self.btn_stop.setFont(QFont('Segoe UI', 11))
        self.btn_stop.setToolTip(tr('tip_stop'))

        # Step buttons
        self.btn_prev = _make_btn('⏮', tr('tip_goto_start'), 38)
        self.btn_prev.setFixedSize(38, 38)

        # Speed selector
        self.lbl_spd = QLabel(tr('speed_label'))
        self.lbl_spd.setObjectName('section-label')
        self.lbl_spd.setAlignment(Qt.AlignVCenter)

        self._speed_btns = {}
        self._speed_group = QButtonGroup(self)
        self._speed_group.setExclusive(True)
        spd_widget = QWidget()
        spd_layout = QHBoxLayout(spd_widget)
        spd_layout.setContentsMargins(0, 0, 0, 0)
        spd_layout.setSpacing(4)
        for s in FlightSimulator.SPEEDS:
            b = _make_speed_btn(f'{s}×')
            self._speed_btns[s] = b
            self._speed_group.addButton(b)
            spd_layout.addWidget(b)
        self._speed_btns[1].setChecked(True)

        # Frame info
        self.lbl_frame = QLabel('— / —')
        self.lbl_frame.setStyleSheet('color:#1e3c5c; font-size:11px; font-family:monospace;')
        self.lbl_frame.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        ctrl_row.addWidget(self.btn_prev)
        ctrl_row.addWidget(self.btn_play)
        ctrl_row.addWidget(self.btn_stop)
        ctrl_row.addSpacing(12)
        ctrl_row.addWidget(self.lbl_spd)
        ctrl_row.addWidget(spd_widget)
        ctrl_row.addStretch()
        ctrl_row.addWidget(self.lbl_frame)

        vbox.addLayout(ctrl_row)
        return panel

    def _build_compact_panel(self) -> QWidget:
        """Thin bar shown while a video build is running (hidden otherwise)."""
        panel = QWidget()
        panel.setFixedHeight(38)
        panel.setStyleSheet(
            'background:#04080f; border-top:1px solid #0d1828;'
        )
        panel.hide()

        row = QHBoxLayout(panel)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(10)

        self._cp_lbl = QLabel(tr('cp_building'))
        self._cp_lbl.setStyleSheet(
            'color:#3a6888; font-size:11px; font-family:"Segoe UI";'
        )

        self._cp_bar = QProgressBar()
        self._cp_bar.setRange(0, 100)
        self._cp_bar.setValue(0)
        self._cp_bar.setTextVisible(True)
        self._cp_bar.setFormat('%p%')
        self._cp_bar.setFixedHeight(16)
        self._cp_bar.setStyleSheet("""
            QProgressBar {
                background:#070d18; border:1px solid #1a3050;
                border-radius:3px; color:#3a6888; font-size:10px;
            }
            QProgressBar::chunk {
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #003366,stop:1 #0077cc);
                border-radius:2px;
            }
        """)

        self._btn_cp_show = QPushButton(tr('cp_show'))
        self._btn_cp_show.setFixedSize(62, 24)
        self._btn_cp_show.setStyleSheet("""
            QPushButton {
                background:#0a1828; color:#3a6070;
                border:1px solid #1a3050; border-radius:3px; font-size:10px;
            }
            QPushButton:hover { background:#122040; color:#70a0c0; }
        """)

        self._btn_cp_save = QPushButton(tr('cp_save'))
        self._btn_cp_save.setFixedSize(80, 24)
        self._btn_cp_save.setEnabled(False)
        self._btn_cp_save.setStyleSheet("""
            QPushButton {
                background:#003366; color:#80c8ff;
                border:1px solid #005ab0; border-radius:3px;
                font-size:10px; font-weight:600;
            }
            QPushButton:hover   { background:#0055aa; color:#fff; }
            QPushButton:disabled {
                background:#070d18; color:#1a3050; border-color:#0d1828;
            }
        """)

        self._btn_cp_cancel = QPushButton('✕')
        self._btn_cp_cancel.setFixedSize(26, 24)
        self._btn_cp_cancel.setStyleSheet("""
            QPushButton {
                background:transparent; color:#2a4060;
                border:none; font-size:12px;
            }
            QPushButton:hover { color:#cc4444; }
        """)

        row.addWidget(self._cp_lbl)
        row.addWidget(self._cp_bar, stretch=1)
        row.addWidget(self._btn_cp_show)
        row.addWidget(self._btn_cp_save)
        row.addWidget(self._btn_cp_cancel)

        return panel

    # ── signal wiring ───────────────────────────────────────────────────────

    def _connect_signals(self):
        self.btn_open.clicked.connect(self._open_file)
        self.btn_open_folder.clicked.connect(self._open_folder)
        self.btn_video.clicked.connect(self._build_video)
        self._btn_cp_show.clicked.connect(self._show_video_win)
        self._btn_cp_cancel.clicked.connect(self._cancel_video_build)
        self._btn_cp_save.clicked.connect(self._save_built_video)
        self.btn_lang.clicked.connect(self._toggle_language)
        lang.language_changed.connect(self._retranslate_ui)
        self.btn_win_min.clicked.connect(self.showMinimized)
        self.btn_win_restore.clicked.connect(self._toggle_maximize)
        self.btn_win_close.clicked.connect(self.close)
        self.btn_fit.clicked.connect(self.map_widget.fit_all)
        self.btn_center.toggled.connect(self._on_follow_toggled)
        self.map_widget.follow_disabled.connect(self._on_follow_disabled)
        self.file_list.itemClicked.connect(self._on_file_selected)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_prev.clicked.connect(lambda: self._sim.stop())

        self.slider.sliderPressed.connect(self._slider_pressed)
        self.slider.sliderMoved.connect(self._slider_moved)
        self.slider.sliderReleased.connect(self._slider_released)

        self._sim.frame_changed.connect(self._on_frame_changed)
        self._sim.state_changed.connect(self._on_state_changed)
        self._sim.playback_finished.connect(self._on_finished)

        for speed, btn in self._speed_btns.items():
            btn.clicked.connect(lambda checked, s=speed: self._sim.set_speed(s))

    # ── slots ───────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _open_file(self):
        start_dir = self._current_folder or os.path.join(os.path.dirname(__file__), 'logs')
        path, _ = QFileDialog.getOpenFileName(
            self, tr('dlg_open_log'), start_dir, tr('dlg_filter_bin')
        )
        if path:
            self._load_file(path)

    @pyqtSlot()
    def _open_folder(self):
        start_dir = self._current_folder or os.path.join(os.path.dirname(__file__), 'logs')
        folder = QFileDialog.getExistingDirectory(self, tr('dlg_open_folder'), start_dir)
        if not folder:
            self.btn_open_folder.setChecked(False)
            return

        self._current_folder = folder
        bin_files = sorted(
            f for f in os.listdir(folder) if f.lower().endswith('.bin')
        )

        self.file_list.clear()
        for name in bin_files:
            self.file_list.addItem(name)

        short = os.path.basename(folder) or folder
        self.lbl_folder.setText(short)
        self.file_panel.show()
        self.btn_open_folder.setChecked(True)

        if not bin_files:
            self.status.showMessage(tr('no_bin_files'))

    def _on_file_selected(self, item: QListWidgetItem):
        path = os.path.join(self._current_folder, item.text())
        self._load_file(path)

    def _load_file(self, path: str):
        self.status.showMessage(tr('status_parsing', os.path.basename(path)))
        try:
            data = log_parser.parse_file(path)
        except Exception as e:
            self.status.showMessage(tr('status_error', e))
            return
        self._apply_data(data)

    def _apply_data(self, data):
        self._data = data
        self._sim.load(data)
        self.map_widget.load_flight(data)

        n = len(data.points)
        self.slider.setRange(0, max(0, n - 1))
        self.slider.setValue(0)

        # Absolyut GPS vaqti mavjud bo'lsa, uni ko'rsat
        if n > 0:
            self.lbl_time.setText(fmt_abs_time(data.points[0], data.tz))
            self.lbl_total.setText(fmt_abs_time(data.points[-1], data.tz))
        else:
            self.lbl_time.setText('--:--:--')
            self.lbl_total.setText('--:--:--')

        self.lbl_frame.setText(f'1 / {n}')
        self.lbl_filename.setText(str(data.filename))
        self._set_controls_enabled(True)

        utc_info = ''
        if data.start_utc:
            local_start = data.start_utc.astimezone(data.tz)
            utc_info = tr('status_utc_info',
                          dt=local_start.strftime('%Y-%m-%d %H:%M:%S'),
                          tz=data.tz_label,
                          off=data.tz_offset_min)
        dist_km = data.total_distance / 1000
        self.status.showMessage(
            tr('status_loaded',
               n=n,
               dur=fmt_time(data.duration),
               dist=f'{dist_km:.2f}',
               alt=f'{data.max_alt:.0f}',
               spd=f'{data.max_spd * 3.6:.1f}')
            + utc_info
        )

    @pyqtSlot(bool)
    def _on_follow_toggled(self, checked: bool):
        self.map_widget.set_follow(checked)

    @pyqtSlot()
    def _on_follow_disabled(self):
        self.btn_center.blockSignals(True)
        self.btn_center.setChecked(False)
        self.btn_center.blockSignals(False)

    @pyqtSlot()
    def _build_video(self):
        data = self._data
        if data is None:
            return
        # If a build is already running, just show that window
        if self._video_win is not None and self._video_win.isVisible():
            self._video_win.show_or_raise()
            return
        win = VideoExportWindow()
        win.sig_frame.connect(self._on_video_frame)
        win.sig_done.connect(self._on_video_done)
        win.sig_cancel.connect(self._on_video_end)
        win.sig_failed.connect(self._on_video_end)
        self._video_win = win
        # Disable playback and Build Video button while building
        self._sim.stop()
        self._set_controls_enabled(False)
        self.btn_video.setEnabled(False)
        # Show compact panel
        self._cp_bar.setValue(0)
        self._cp_lbl.setText(tr('cp_building'))
        self._cp_lbl.setStyleSheet('color:#3a6888; font-size:11px; font-family:"Segoe UI";')
        self._btn_cp_save.setEnabled(False)
        self._compact_panel.show()
        win.start_build(self.map_widget, data)

    @pyqtSlot(int, int)
    def _on_video_frame(self, cur: int, total: int):
        pct = int(cur / total * 100) if total > 0 else 0
        self._cp_bar.setValue(pct)
        self._cp_lbl.setText(tr('cp_building_n', cur=cur, total=total))

    @pyqtSlot(str)
    def _on_video_done(self, _path: str):
        self._cp_bar.setValue(100)
        self._cp_lbl.setText(tr('cp_done'))
        self._cp_lbl.setStyleSheet('color:#00cc88; font-size:11px; font-weight:bold;')
        self._btn_cp_save.setEnabled(True)
        # Re-enable app controls
        if self._data is not None:
            self._set_controls_enabled(True)
        self.btn_video.setEnabled(self._data is not None)

    @pyqtSlot()
    def _on_video_end(self):
        """Called on cancel or save-complete."""
        self._compact_panel.hide()
        self._btn_cp_save.setEnabled(False)
        self._video_win = None
        if self._data is not None:
            self._set_controls_enabled(True)
        self.btn_video.setEnabled(self._data is not None)

    @pyqtSlot()
    def _show_video_win(self):
        if self._video_win is not None:
            self._video_win.show_or_raise()

    @pyqtSlot()
    def _cancel_video_build(self):
        if self._video_win is not None:
            self._video_win.cancel_build()

    @pyqtSlot()
    def _save_built_video(self):
        if self._video_win is not None:
            self._video_win._save_video()

    @pyqtSlot()
    def _toggle_play(self):
        if self._sim.is_playing:
            self._sim.pause()
        else:
            self._sim.play()

    @pyqtSlot()
    def _on_stop(self):
        self._sim.stop()

    @pyqtSlot(int)
    def _on_frame_changed(self, idx):
        if not self._data:
            return
        pt = self._data.points[idx]
        if not self._user_seeking:
            self.slider.blockSignals(True)
            self.slider.setValue(idx)
            self.slider.blockSignals(False)
        self.lbl_time.setText(fmt_abs_time(pt, self._data.tz))
        self.lbl_frame.setText(f'{idx + 1} / {len(self._data.points)}')
        self.map_widget.update_frame(idx)

    @pyqtSlot(str)
    def _on_state_changed(self, state):
        if state == 'playing':
            self.btn_play.setText('⏸')
            self.btn_play.setToolTip(tr('tip_stop'))
        else:
            self.btn_play.setText('▶')
            self.btn_play.setToolTip(tr('tip_play'))

    @pyqtSlot()
    def _on_finished(self):
        self.status.showMessage(tr('status_done'))

    @pyqtSlot()
    def _slider_pressed(self):
        self._user_seeking = True
        if self._sim.is_playing:
            self._sim.pause()

    @pyqtSlot(int)
    def _slider_moved(self, value):
        self._sim.seek(value)

    @pyqtSlot()
    def _slider_released(self):
        self._user_seeking = False

    # ── helpers ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            from PyQt5.QtWidgets import QApplication
            scr = QApplication.primaryScreen()
            if scr is not None:
                avail = scr.availableGeometry()
                w = int(avail.width()  * 0.80)
                h = int(avail.height() * 0.80)
                x = avail.x() + (avail.width()  - w) // 2
                y = avail.y() + (avail.height() - h) // 2
                self.setGeometry(x, y, w, h)
        else:
            self.showMaximized()

    def changeEvent(self, event):
        super().changeEvent(event)
        from PyQt5.QtCore import QEvent
        from PyQt5.QtWidgets import QApplication
        if event.type() == QEvent.WindowStateChange:
            if self.isMaximized():
                # Frameless windows on Windows can overflow behind the taskbar;
                # clamp to the available work area explicitly.
                scr = QApplication.primaryScreen()
                if scr is not None:
                    self.setGeometry(scr.availableGeometry())
                self.btn_win_restore.setText('❒')
                self.btn_win_restore.setToolTip('Tiklash (Restore)')
            else:
                self.btn_win_restore.setText('❐')
                self.btn_win_restore.setToolTip('Kattalashtirish (Maximize)')

    def _toggle_language(self):
        lang.toggle()

    @pyqtSlot(str)
    def _retranslate_ui(self, _code: str = ''):
        self.setWindowTitle(tr('app_title'))
        self.lbl_title.setText(tr('map_title'))
        self.btn_lang.setText(f'🌐 {lang.current.upper()}')
        # Toolbar
        self.btn_open.setText(tr('btn_open'))
        self.btn_open.setToolTip(tr('tip_open'))
        self.btn_open_folder.setText(tr('btn_open_folder'))
        self.btn_open_folder.setToolTip(tr('tip_folder'))
        self.btn_fit.setText(tr('btn_fit'))
        self.btn_fit.setToolTip(tr('tip_fit'))
        self.btn_center.setText(tr('btn_follow'))
        self.btn_center.setToolTip(tr('tip_follow'))
        self.btn_video.setText(tr('btn_build_video'))
        self.btn_video.setToolTip(tr('tip_build_video'))
        # File panel
        if not self._current_folder:
            self.lbl_folder.setText(tr('no_folder'))
        # Control panel
        self.lbl_spd.setText(tr('speed_label'))
        self.btn_play.setToolTip(tr('tip_play'))
        self.btn_stop.setToolTip(tr('tip_stop'))
        self.btn_prev.setToolTip(tr('tip_goto_start'))
        # Compact video panel buttons
        self._btn_cp_show.setText(tr('cp_show'))
        self._btn_cp_save.setText(tr('cp_save'))
        # Compact label — update only if in "building" state (not done)
        if not self._btn_cp_save.isEnabled():
            self._cp_lbl.setText(tr('cp_building'))
        else:
            self._cp_lbl.setText(tr('cp_done'))
        # Status bar — update if no file loaded yet
        if self._data is None:
            self.status.showMessage(tr('status_ready'))
        # Video export window — refresh if open
        if self._video_win is not None:
            self._video_win.retranslate()

    def _set_controls_enabled(self, enabled):
        for w in (self.btn_play, self.btn_stop, self.btn_prev,
                  self.slider, self.btn_fit, self.btn_center, self.btn_video):
            w.setEnabled(enabled)
        for b in self._speed_btns.values():
            b.setEnabled(enabled)

    # ── keyboard shortcuts ──────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Space:
            self._toggle_play()
        elif key == Qt.Key_Escape:
            self._sim.stop()
        elif key == Qt.Key_Right:
            self._sim.seek(self._sim.current_index + 5)
        elif key == Qt.Key_Left:
            self._sim.seek(max(0, self._sim.current_index - 5))
        elif key == Qt.Key_F:
            self.map_widget.fit_all()
        elif key == Qt.Key_C:
            self.map_widget.center_on_drone()
        else:
            super().keyPressEvent(event)
