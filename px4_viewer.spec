# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for PX4 Flight Log Viewer
"""

import os

VENV = r'C:\Users\AKA\OneDrive\Documents\PythonQt\PX4-Log-Viewer\.venv\Lib\site-packages'
QT5  = os.path.join(VENV, 'PyQt5', 'Qt5')

# ── Data files to bundle ─────────────────────────────────────────────────────
ICON = r'resources\app_icon.ico'

datas = [
    ('resources/map.html', 'resources'),

    # timezonefinder binary data — subdirektoriyalarni alohida ko'rsatish kerak
    (os.path.join(VENV, 'timezonefinder', 'data'),                  'timezonefinder/data'),
    (os.path.join(VENV, 'timezonefinder', 'data', 'boundaries'),    'timezonefinder/data/boundaries'),
    (os.path.join(VENV, 'timezonefinder', 'data', 'holes'),         'timezonefinder/data/holes'),
    (os.path.join(VENV, 'timezonefinder', 'flatbuf'),               'timezonefinder/flatbuf'),

    # IANA tzdata (zoneinfo backend)
    (os.path.join(VENV, 'tzdata'), 'tzdata'),

    # pymavlink — tüm paket (dialects + message_definitions)
    (os.path.join(VENV, 'pymavlink'), 'pymavlink'),

    # Qt WebEngine pak fayllar va icudtl.dat
    (os.path.join(QT5, 'resources'), 'PyQt5/Qt5/resources'),

    # Qt WebEngine tarjimalar
    (os.path.join(QT5, 'translations', 'qtwebengine_locales'),
     'PyQt5/Qt5/translations/qtwebengine_locales'),
]

# ── Hidden imports ───────────────────────────────────────────────────────────
hidden = [
    # pymavlink — try/except ichida import bo'lgani uchun qo'lda yoziladi
    'pymavlink',
    'pymavlink.mavutil',
    'pymavlink.mavparm',
    'pymavlink.mavwp',
    'pymavlink.DFReader',
    'pymavlink.dialects',
    'pymavlink.dialects.v20',
    'pymavlink.dialects.v10',
    'pymavlink.dialects.v20.ardupilotmega',
    'pymavlink.dialects.v10.ardupilotmega',
    'pymavlink.dialects.v20.common',
    'pymavlink.dialects.v10.common',
    'pymavlink.dialects.v20.minimal',
    'pymavlink.dialects.v10.minimal',
    'pymavlink.dialects.v20.all',
    'pymavlink.dialects.v10.all',

    # Qt WebEngine
    'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtWebEngineCore',
    'PyQt5.QtWebChannel',
    'PyQt5.QtNetwork',
    'PyQt5.QtPrintSupport',

    # Timezone
    'timezonefinder',
    'zoneinfo',
    'zoneinfo._common',
    'zoneinfo._czoneinfo',
    'tzdata',
    'tzdata.zoneinfo',

    # stdlib
    'bisect',
    'json',
    'datetime',
    'os',
    'math',
]

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[
        (os.path.join(QT5, 'bin', 'QtWebEngineProcess.exe'), '.'),
    ],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_tzdata.py'],
    excludes=[
        'matplotlib', 'scipy', 'pandas',
        'tkinter', '_tkinter', 'unittest',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PX4-FlightViewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='PX4-FlightViewer',
)
