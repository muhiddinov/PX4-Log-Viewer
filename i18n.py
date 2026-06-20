"""
Simple two-language (uz / en) translation system.

Usage:
    from i18n import tr, lang
    label.setText(tr('btn_open'))
    lang.language_changed.connect(my_retranslate_slot)
    lang.set_language('en')
"""

from PyQt5.QtCore import QObject, QSettings, pyqtSignal

# ── String table ─────────────────────────────────────────────────────────────

_S: dict[str, dict[str, str]] = {

    # ── Uzbek ────────────────────────────────────────────────────────────────
    'uz': {
        # App
        'app_title':        "PX4 Parvoz Jurnali Ko'ruvchi",
        'map_title':        "PX4  Parvoz  Jurnali  Ko'ruvchi",

        # Toolbar
        'btn_open':         '📂  Jurnalni ochish',
        'btn_open_folder':  '🗁  Papkani ochish',
        'btn_fit':          '⊞  Xaritaga moslashtirish',
        'btn_follow':       '⊙  Kuzatish',
        'btn_build_video':  '🎬  Video yaratish',
        'tip_open':         'ArduPilot .bin faylini ochish',
        'tip_folder':       'Papkani ochib .bin fayllar ro\'yxatini ko\'rsatish',
        'tip_fit':          'Xaritani parvoz yo\'liga moslashtirish',
        'tip_follow':       'Dronni kuzatish rejimi',
        'tip_build_video':  'Parvozni MP4 video sifatida eksport qilish',

        # File panel
        'no_folder':        '— papka tanlanmagan —',
        'no_bin_files':     'Tanlangan papkada .bin fayl topilmadi.',

        # Control panel
        'speed_label':      'TEZLIK',
        'tip_play':         'Ijro / Pauza  (Bo\'sh joy)',
        'tip_stop':         'To\'xtatish',
        'tip_goto_start':   'Boshiga qaytish',

        # Status bar
        'status_ready':     'ArduPilot .bin yoki .log faylini oching.',
        'status_parsing':   'Tahlil qilinmoqda: {}…',
        'status_error':     'Xatolik: {}',
        'status_loaded':    ('{n} GPS nuqta  |  Davomiyligi {dur}'
                             '  |  Masofa {dist} km'
                             '  |  Maks. balandlik {alt} m'
                             '  |  Maks. tezlik {spd} km/soat'),
        'status_done':      'Ijro tugadi.',
        'status_utc_info':  '  |  Boshlanish {dt} {tz}  (BRD_RTC_TZ_MIN={off})',

        # Compact video panel
        'cp_building':      '🎬  Video yaratilmoqda…',
        'cp_building_n':    '🎬  Video yaratilmoqda…  {cur} / {total}',
        'cp_done':          '✔  Video tayyor!',
        'cp_show':          'Oyna',
        'cp_save':          '💾 Saqlash',

        # Video export window
        'vw_title':         '🎬  PX4 Video Yaratish',
        'vw_header':        'PX4 PARVOZ JURNALI  ·  VIDEO EKSPORT',
        'vw_building':      ('Video yaratilmoqda…\n'
                             '{w}×{h}  ·  {fps} FPS  ·  Uchish vaqti: {dur}'),
        'vw_done':          '✔  Video tayyor!',
        'vw_info_total':    'Jami video kadrlar: {n}',
        'vw_info_frames':   'Video kadr:  {done} / {total}',
        'vw_info_written':  'Jami {n} log kadr  →  {vf} video kadr yozildi.',
        'vw_btn_save':      '💾  Video saqlash',
        'vw_btn_cancel':    '✕  Bekor qilish',
        'vw_btn_close':     'Yopish',

        # Dialogs
        'dlg_open_log':     "ArduPilot Jurnalini Ochish",
        'dlg_open_folder':  "Jurnallar Papkasini Tanlang",
        'dlg_save_video':   "Videoni Saqlash",
        'dlg_filter_bin':   'ArduPilot Ikkilik Jurnallar (*.bin);;Barcha Fayllar (*)',
        'dlg_filter_mp4':   'MP4 Video (*.mp4);;Barcha Fayllar (*)',

        # Message boxes
        'msg_no_gps':       'Hech qanday GPS kadr yo\'q.',
        'msg_writer_fail':  'VideoWriter ochib bo\'lmadi:\n{}',
        'msg_saved_title':  'Saqlandi',
        'msg_saved_body':   'Video muvaffaqiyatli saqlandi:\n{}',
        'msg_save_err':     'Saqlash xatosi',
        'msg_video_err':    'Video xatolik',
        'msg_error':        'Xatolik',
    },

    # ── English ──────────────────────────────────────────────────────────────
    'en': {
        # App
        'app_title':        'PX4 Flight Log Viewer',
        'map_title':        'PX4  Flight  Log  Viewer',

        # Toolbar
        'btn_open':         '📂  Open Log',
        'btn_open_folder':  '🗁  Open Folder',
        'btn_fit':          '⊞  Fit Map',
        'btn_follow':       '⊙  Follow',
        'btn_build_video':  '🎬  Build Video',
        'tip_open':         'Open ArduPilot .bin file',
        'tip_folder':       'Open folder and list .bin files',
        'tip_fit':          'Fit map to flight path',
        'tip_follow':       'Toggle follow drone mode',
        'tip_build_video':  'Export flight as MP4 video',

        # File panel
        'no_folder':        '— no folder —',
        'no_bin_files':     'No .bin files found in selected folder.',

        # Control panel
        'speed_label':      'SPEED',
        'tip_play':         'Play / Pause  (Space)',
        'tip_stop':         'Stop',
        'tip_goto_start':   'Go to start',

        # Status bar
        'status_ready':     'Open an ArduPilot .bin or .log file to begin.',
        'status_parsing':   'Parsing {}…',
        'status_error':     'Error: {}',
        'status_loaded':    ('{n} GPS points  |  Duration {dur}'
                             '  |  Distance {dist} km'
                             '  |  Max alt {alt} m'
                             '  |  Max speed {spd} km/h'),
        'status_done':      'Playback complete.',
        'status_utc_info':  '  |  Start {dt} {tz}  (BRD_RTC_TZ_MIN={off})',

        # Compact video panel
        'cp_building':      '🎬  Building video…',
        'cp_building_n':    '🎬  Building video…  {cur} / {total}',
        'cp_done':          '✔  Video ready!',
        'cp_show':          'Window',
        'cp_save':          '💾 Save',

        # Video export window
        'vw_title':         '🎬  PX4 Build Video',
        'vw_header':        'PX4 FLIGHT LOG  ·  VIDEO EXPORT',
        'vw_building':      ('Building video…\n'
                             '{w}×{h}  ·  {fps} FPS  ·  Flight time: {dur}'),
        'vw_done':          '✔  Video ready!',
        'vw_info_total':    'Total video frames: {n}',
        'vw_info_frames':   'Video frame:  {done} / {total}',
        'vw_info_written':  'Total {n} log frames  →  {vf} video frames written.',
        'vw_btn_save':      '💾  Save Video',
        'vw_btn_cancel':    '✕  Cancel',
        'vw_btn_close':     'Close',

        # Dialogs
        'dlg_open_log':     'Open ArduPilot Log',
        'dlg_open_folder':  'Select Log Folder',
        'dlg_save_video':   'Save Video',
        'dlg_filter_bin':   'ArduPilot Binary Logs (*.bin);;All Files (*)',
        'dlg_filter_mp4':   'MP4 Video (*.mp4);;All Files (*)',

        # Message boxes
        'msg_no_gps':       'No GPS frames found.',
        'msg_writer_fail':  'VideoWriter failed to open:\n{}',
        'msg_saved_title':  'Saved',
        'msg_saved_body':   'Video saved successfully:\n{}',
        'msg_save_err':     'Save error',
        'msg_video_err':    'Video error',
        'msg_error':        'Error',
    },
}


# ── Language manager (singleton) ─────────────────────────────────────────────

class LanguageManager(QObject):
    """Singleton that holds the active language and broadcasts changes."""

    language_changed = pyqtSignal(str)   # new lang code: 'uz' or 'en'
    _instance: 'LanguageManager | None' = None

    def __init__(self):
        super().__init__()
        cfg = QSettings('UAV Tools', 'PX4 Flight Log Viewer')
        self._lang: str = cfg.value('language', 'uz')
        if self._lang not in _S:
            self._lang = 'uz'

    @classmethod
    def instance(cls) -> 'LanguageManager':
        if cls._instance is None:
            cls._instance = LanguageManager()
        return cls._instance

    # ── public ───────────────────────────────────────────────────────────────

    @property
    def current(self) -> str:
        return self._lang

    def set_language(self, code: str) -> None:
        if code not in _S or code == self._lang:
            return
        self._lang = code
        QSettings('UAV Tools', 'PX4 Flight Log Viewer').setValue('language', code)
        self.language_changed.emit(code)

    def toggle(self) -> None:
        self.set_language('en' if self._lang == 'uz' else 'uz')

    def tr(self, key: str, *args, **kw) -> str:
        s = _S.get(self._lang, _S['en']).get(key, key)
        if args:
            return s.format(*args)
        return s.format(**kw) if kw else s


# ── Module-level shortcuts ────────────────────────────────────────────────────

def _get_lang() -> LanguageManager:
    return LanguageManager.instance()


def tr(key: str, *args, **kw) -> str:
    return LanguageManager.instance().tr(key, *args, **kw)


# `lang` is a lazy proxy — safe to use at module level
class _LangProxy:
    def __getattr__(self, name):
        return getattr(LanguageManager.instance(), name)

    def __call__(self):
        return LanguageManager.instance()


lang = _LangProxy()
