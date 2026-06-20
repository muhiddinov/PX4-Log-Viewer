# Runtime hook: frozen exe'da zoneinfo tzdata yo'lini sozlash
import sys, os

if getattr(sys, 'frozen', False):
    tzdata_path = os.path.join(sys._MEIPASS, 'tzdata', 'zoneinfo')
    if os.path.isdir(tzdata_path):
        import zoneinfo
        zoneinfo.reset_tzpath(to=[tzdata_path])
