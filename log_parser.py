"""
ArduPilot / PX4 log file parser.
Supports binary .bin (DataFlash) and text .log files.
"""

import os
import math
import bisect
import datetime
import zoneinfo

# GPS epoch = Jan 6, 1980 00:00:00 UTC  (Unix: 315964800)
# Current GPS–UTC leap seconds = 18
_GPS_EPOCH      = 315964800
_GPS_LEAP_SECS  = 18

_COPTER_MODES = {
    0:'STABILIZE', 1:'ACRO', 2:'ALT_HOLD', 3:'AUTO',
    4:'GUIDED', 5:'LOITER', 6:'RTL', 7:'CIRCLE',
    9:'LAND', 11:'DRIFT', 13:'SPORT', 14:'FLIP',
    15:'AUTOTUNE', 16:'POS_HOLD', 17:'BRAKE', 18:'THROW',
    19:'AVOID_ADSB', 20:'GUIDED_NOGPS', 21:'SMART_RTL',
    22:'FLOWHOLD', 23:'FOLLOW', 24:'ZIGZAG',
}

_EV_NAMES = {
    10:'Armed', 11:'Disarmed', 15:'Auto Armed',
    17:'Takeoff', 18:'Landing', 25:'Home Set', 28:'Pre-arm OK',
}


def _gps_to_unix(gps_week, gps_ms):
    """Return UTC Unix timestamp (float) from GPS week + milliseconds."""
    return _GPS_EPOCH + int(gps_week) * 7 * 86400 + gps_ms / 1000.0 - _GPS_LEAP_SECS


def _fmt_ts(unix_ts, tz=datetime.timezone.utc):
    """Format unix timestamp as 'HH:MM:SS' in the given timezone."""
    return datetime.datetime.fromtimestamp(unix_ts, tz=tz).strftime('%H:%M:%S')


# Keep for internal use where offset not yet known
def _utc_str(unix_ts):
    return _fmt_ts(unix_ts) + ' UTC'


class FlightPoint:
    __slots__ = (
        'time', 'lat', 'lng', 'alt', 'spd', 'heading',
        'rc_roll', 'rc_pitch', 'rc_throttle', 'rc_yaw',
        'rcout',
        'gps_time_str',
        'abs_time',
        'bat_volt',
        'bat_pct',
        'dist',          # cumulative distance from takeoff (metres)
    )

    def __init__(self, time, lat, lng, alt, spd, heading,
                 rc_roll=1500, rc_pitch=1500, rc_throttle=1000, rc_yaw=1500,
                 rcout=None, gps_time_str='', abs_time=0.0,
                 bat_volt=0.0, bat_pct=0, dist=0.0):
        self.time         = time
        self.lat          = lat
        self.lng          = lng
        self.alt          = alt
        self.spd          = spd
        self.heading      = heading
        self.rc_roll      = rc_roll
        self.rc_pitch     = rc_pitch
        self.rc_throttle  = rc_throttle
        self.rc_yaw       = rc_yaw
        self.rcout        = rcout or []
        self.gps_time_str = gps_time_str
        self.abs_time     = abs_time
        self.bat_volt     = bat_volt
        self.bat_pct      = bat_pct
        self.dist         = dist

    def to_dict(self):
        return {
            'time':         self.time,
            'lat':          self.lat,
            'lng':          self.lng,
            'alt':          self.alt,
            'spd':          self.spd,
            'heading':      self.heading,
            'rc_roll':      self.rc_roll,
            'rc_pitch':     self.rc_pitch,
            'rc_throttle':  self.rc_throttle,
            'rc_yaw':       self.rc_yaw,
            'rcout':        self.rcout,
            'gps_time_str': self.gps_time_str,
            'bat_volt':     self.bat_volt,
            'bat_pct':      self.bat_pct,
            'dist':         self.dist,
        }


class FlightData:
    def __init__(self, points=None, filename='', tz_offset_min=0, tz_name=None, events=None):
        self.points        = points or []
        self.filename      = filename
        self.tz_offset_min = int(tz_offset_min)
        self.tz_name       = tz_name or ''
        self.events        = events or []   # [{time, type, label, time_str}]

    @property
    def duration(self):
        if len(self.points) < 2:
            return 0.0
        return self.points[-1].time - self.points[0].time

    @property
    def max_alt(self):
        return max((p.alt for p in self.points), default=0)

    @property
    def max_spd(self):
        return max((p.spd for p in self.points), default=0)

    @property
    def total_distance(self):
        """Total 2-D flight path length in metres."""
        return self.points[-1].dist if self.points else 0.0

    @property
    def tz(self):
        """datetime.timezone for this flight's BRD_RTC_TZ_MIN offset."""
        return datetime.timezone(datetime.timedelta(minutes=self.tz_offset_min))

    @property
    def tz_label(self):
        """Human-readable timezone label, e.g. 'UTC+5' or 'Asia/Kabul (UTC+4:30)'."""
        h, m = divmod(abs(self.tz_offset_min), 60)
        sign = '+' if self.tz_offset_min >= 0 else '-'
        offset_str = f'UTC{sign}{h}:{m:02d}' if m else (f'UTC{sign}{h}' if h else 'UTC')
        if self.tz_name:
            return f'{self.tz_name} ({offset_str})'
        return offset_str

    @property
    def start_utc(self):
        """First GPS fix as UTC datetime (or None)."""
        for p in self.points:
            if p.abs_time > 0:
                return datetime.datetime.fromtimestamp(p.abs_time, tz=datetime.timezone.utc)
        return None

    def to_js_array(self):
        import json
        return json.dumps([p.to_dict() for p in self.points])

    def to_js_events(self):
        import json
        return json.dumps(self.events)


# ─────────────────────────────────────────────────────── public ───────────────

def parse_file(filepath):
    """Parse .bin or .log ArduPilot log file. Returns FlightData."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.bin':
        points, tz_min, events = _parse_bin(filepath)
    elif ext in ('.log', '.txt'):
        points, tz_min = _parse_log_text(filepath)
        events = []
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    _normalize_time(points)

    tz_name = None
    if tz_min == 0 and points:
        tz_min, tz_name = _detect_timezone(points[0].lat, points[0].lng, points[0].abs_time)

    tz = datetime.timezone(datetime.timedelta(minutes=tz_min))

    if tz_min != 0:
        for p in points:
            if p.abs_time > 0:
                p.gps_time_str = _fmt_ts(p.abs_time, tz)

    # Cumulative 3-D distance + 3-D speed per point
    cum = 0.0
    for i, p in enumerate(points):
        if i > 0:
            q    = points[i - 1]
            d2d  = _haversine(q.lat, q.lng, p.lat, p.lng)
            dalt = p.alt - q.alt
            cum += math.sqrt(d2d * d2d + dalt * dalt)
            dt   = p.time - q.time
            if dt > 0:
                v_vert = dalt / dt          # m/s vertical
                p.spd  = math.sqrt(p.spd * p.spd + v_vert * v_vert)
        p.dist = round(cum, 1)

    # Format event time strings using first GPS abs_time as reference
    first_abs = points[0].abs_time if points else 0.0
    for ev in events:
        if first_abs > 0:
            ev['time_str'] = _fmt_ts(first_abs + ev['time'], tz)

    return FlightData(points, os.path.basename(filepath),
                      tz_offset_min=tz_min, tz_name=tz_name, events=events)


# ─────────────────────────────────────────────── binary parser ────────────────

def _parse_bin(filepath):
    try:
        from pymavlink import mavutil
    except ImportError:
        raise ImportError("pymavlink not found. Install: pip install pymavlink")

    mlog = mavutil.mavlink_connection(filepath, dialect='ardupilotmega')
    gps_raw    = []
    rcin_raw   = []
    rcou_raw   = []
    bat_raw    = []
    events_raw = []   # {time_us, type, label}
    tz_min     = 0
    _gps_status = -1   # track GPS status transitions

    while True:
        msg = mlog.recv_match(
            type=['GPS', 'GPS2', 'RCIN', 'RCOU', 'PARM', 'BAT', 'MODE', 'EV', 'ERR'],
            blocking=False
        )
        if msg is None:
            break
        t = msg.get_type()

        if t == 'PARM' and getattr(msg, 'Name', '') == 'BRD_RTC_TZ_MIN':
            tz_min = int(getattr(msg, 'Value', 0))
            continue

        if t in ('GPS', 'GPS2'):
            status = int(getattr(msg, 'Status', 0))
            t_us   = float(getattr(msg, 'TimeUS', 0))
            if status != _gps_status:
                if status >= 3 and _gps_status >= 0 and _gps_status < 3:
                    events_raw.append({'time_us': t_us, 'type': 'GPS', 'label': 'GPS Lock'})
                elif status < 3 and _gps_status >= 3:
                    events_raw.append({'time_us': t_us, 'type': 'GPS', 'label': 'GPS Lost'})
                _gps_status = status
            if status < 3:
                continue
            lat = float(getattr(msg, 'Lat', 0))
            lng = float(getattr(msg, 'Lng', 0))
            if lat == 0.0 and lng == 0.0:
                continue
            if abs(lat) > 180:
                lat /= 1e7
            if abs(lng) > 360:
                lng /= 1e7
            gps_week = int(getattr(msg, 'GWk', 0))
            gps_ms   = float(getattr(msg, 'GMS', 0))
            abs_t, gps_str = 0.0, ''
            if gps_week > 0:
                abs_t   = _gps_to_unix(gps_week, gps_ms)
                gps_str = _utc_str(abs_t)
            gps_raw.append({
                'time':         float(getattr(msg, 'TimeUS', 0)) / 1e6,
                'lat':          lat,  'lng': lng,
                'alt':          float(getattr(msg, 'Alt',  0)),
                'spd':          float(getattr(msg, 'Spd',  0)),
                'heading':      float(getattr(msg, 'GCrs', 0)),
                'abs_time':     abs_t,
                'gps_time_str': gps_str,
            })

        elif t == 'RCIN':
            rcin_raw.append({
                'time': float(msg.TimeUS) / 1e6,
                'roll': int(msg.C1), 'pitch': int(msg.C2),
                'throttle': int(msg.C3), 'yaw': int(msg.C4),
            })

        elif t == 'RCOU':
            channels = []
            for i in range(1, 15):
                v = getattr(msg, f'C{i}', None)
                if v is None or v == 0:
                    break
                channels.append(int(v))
            rcou_raw.append({'time': float(msg.TimeUS) / 1e6, 'channels': channels})

        elif t == 'ERR':
            sub  = int(getattr(msg, 'Subsys', 0))
            code = int(getattr(msg, 'ECode',  0))
            t_us = float(getattr(msg, 'TimeUS', 0))
            if sub == 11:   # GPS subsystem
                label = 'GPS Restored' if code == 0 else 'GPS Glitch'
                events_raw.append({'time_us': t_us, 'type': 'GPS', 'label': label})
            elif sub in (2, 5):  # Radio / RC Failsafe
                if code == 0:
                    label = 'RC Signal OK'
                else:
                    label = 'RC Failsafe' if sub == 5 else 'RC Signal Lost'
                events_raw.append({'time_us': t_us, 'type': 'RC', 'label': label})

        elif t == 'BAT' and getattr(msg, 'Inst', 0) == 0:
            bat_raw.append({
                'time': float(getattr(msg, 'TimeUS', 0)) / 1e6,
                'volt': round(float(getattr(msg, 'Volt', 0)), 2),
                'pct':  int(getattr(msg, 'RemPct', 0)),
            })

        elif t == 'MODE':
            mode_num  = int(getattr(msg, 'ModeNum', getattr(msg, 'Mode', 0)))
            mode_name = _COPTER_MODES.get(mode_num, f'MODE_{mode_num}')
            events_raw.append({
                'time_us': float(getattr(msg, 'TimeUS', 0)),
                'type': 'MODE', 'label': mode_name,
            })

        elif t == 'EV':
            ev_id   = int(getattr(msg, 'Id', 0))
            ev_name = _EV_NAMES.get(ev_id)
            if ev_name:
                events_raw.append({
                    'time_us': float(getattr(msg, 'TimeUS', 0)),
                    'type': 'EV', 'label': ev_name,
                })

    points = [
        FlightPoint(
            time=g['time'], lat=g['lat'], lng=g['lng'],
            alt=g['alt'], spd=g['spd'], heading=g['heading'],
            abs_time=g['abs_time'], gps_time_str=g['gps_time_str'],
        )
        for g in gps_raw
    ]

    _merge_rc(points, rcin_raw)
    _merge_rcout(points, rcou_raw)
    _merge_bat(points, bat_raw)

    # Convert events to relative time (vs first GPS point)
    t0 = gps_raw[0]['time'] if gps_raw else 0.0
    events = []
    for ev in sorted(events_raw, key=lambda x: x['time_us']):
        t_rel = round(ev['time_us'] / 1e6 - t0, 2)
        events.append({'time': t_rel, 'type': ev['type'],
                       'label': ev['label'], 'time_str': ''})

    return points, tz_min, events


# ─────────────────────────────────────────────── text parser ──────────────────

def _parse_log_text(filepath):
    gps_points = []
    rcin_raw   = []
    rcou_raw   = []
    tz_min     = 0

    with open(filepath, 'r', errors='ignore') as fh:
        for line in fh:
            line = line.strip()

            if line.startswith('GPS,') or line.startswith('GPS2,'):
                parts = [p.strip() for p in line.split(',')]
                # GPS, TimeUS, Status, GMS, GWk, NSats, HDop, Lat, Lng, Alt, Spd, GCrs …
                if len(parts) < 9:
                    continue
                try:
                    if int(parts[2]) < 3:
                        continue
                    lat = float(parts[7])
                    lng = float(parts[8])
                    if lat == 0 and lng == 0:
                        continue
                    gps_ms   = float(parts[3]) if len(parts) > 3 else 0
                    gps_week = int(parts[4])   if len(parts) > 4 else 0
                    abs_t, gps_str = 0.0, ''
                    if gps_week > 0:
                        abs_t   = _gps_to_unix(gps_week, gps_ms)
                        gps_str = _utc_str(abs_t)
                    gps_points.append(FlightPoint(
                        time         = float(parts[1]) / 1e6,
                        lat          = lat,
                        lng          = lng,
                        alt          = float(parts[9])  if len(parts) > 9  else 0,
                        spd          = float(parts[10]) if len(parts) > 10 else 0,
                        heading      = float(parts[11]) if len(parts) > 11 else 0,
                        abs_time     = abs_t,
                        gps_time_str = gps_str,
                    ))
                except (ValueError, IndexError):
                    continue

            elif line.startswith('RCIN,'):
                parts = [p.strip() for p in line.split(',')]
                if len(parts) < 6:
                    continue
                try:
                    rcin_raw.append({
                        'time':     float(parts[1]) / 1e6,
                        'roll':     int(parts[2]),
                        'pitch':    int(parts[3]),
                        'throttle': int(parts[4]),
                        'yaw':      int(parts[5]),
                    })
                except (ValueError, IndexError):
                    continue

            elif line.startswith('RCOU,'):
                parts = [p.strip() for p in line.split(',')]
                if len(parts) < 3:
                    continue
                try:
                    channels = [int(parts[i]) for i in range(2, len(parts)) if parts[i]]
                    rcou_raw.append({'time': float(parts[1]) / 1e6, 'channels': channels})
                except (ValueError, IndexError):
                    continue

            elif line.startswith('PARM,'):
                parts = [p.strip() for p in line.split(',')]
                # PARM, TimeUS, Name, Value
                if len(parts) >= 4 and parts[2] == 'BRD_RTC_TZ_MIN':
                    try:
                        tz_min = int(float(parts[3]))
                    except ValueError:
                        pass

    _merge_rc(gps_points, rcin_raw)
    _merge_rcout(gps_points, rcou_raw)
    return gps_points, tz_min


# ─────────────────────────────────────────────── merge helpers ────────────────

def _nearest(sorted_times, t):
    """Return index of nearest value in sorted list."""
    idx = bisect.bisect_left(sorted_times, t)
    if idx == 0:
        return 0
    if idx >= len(sorted_times):
        return len(sorted_times) - 1
    return idx if (sorted_times[idx] - t) < (t - sorted_times[idx-1]) else idx - 1


def _merge_rc(points, rcin_raw):
    if not rcin_raw:
        return
    times = [r['time'] for r in rcin_raw]
    for pt in points:
        rc = rcin_raw[_nearest(times, pt.time)]
        pt.rc_roll     = rc['roll']
        pt.rc_pitch    = rc['pitch']
        pt.rc_throttle = rc['throttle']
        pt.rc_yaw      = rc['yaw']


def _merge_rcout(points, rcou_raw):
    if not rcou_raw:
        return
    times = [r['time'] for r in rcou_raw]
    for pt in points:
        rc = rcou_raw[_nearest(times, pt.time)]
        pt.rcout = rc['channels']


def _merge_bat(points, bat_raw):
    if not bat_raw:
        return
    times = [b['time'] for b in bat_raw]
    for pt in points:
        b = bat_raw[_nearest(times, pt.time)]
        pt.bat_volt = b['volt']
        pt.bat_pct  = b['pct']


# ─────────────────────────────────────────────── time helpers ─────────────────

def _detect_timezone(lat, lng, abs_time=0.0):
    """
    Use GPS coordinates to find the IANA timezone and return
    (offset_minutes, tz_name). Falls back to (0, None) on any error.
    """
    try:
        import sys
        from timezonefinder import TimezoneFinder

        data_dir = None
        if getattr(sys, 'frozen', False):
            meipass = sys._MEIPASS
            data_dir = os.path.join(meipass, 'timezonefinder', 'data')

            tzdata_zi = os.path.join(meipass, 'tzdata', 'zoneinfo')
            if os.path.isdir(tzdata_zi):
                zoneinfo.reset_tzpath(to=[tzdata_zi])

        tf = TimezoneFinder(bin_file_location=data_dir)
        tz_name = tf.timezone_at(lat=lat, lng=lng)
        if not tz_name:
            return 0, None

        tz = zoneinfo.ZoneInfo(tz_name)
        ref_ts = abs_time if abs_time > 0 else datetime.datetime.now(datetime.timezone.utc).timestamp()
        ref_dt = datetime.datetime.fromtimestamp(ref_ts, tz=datetime.timezone.utc).astimezone(tz)
        offset_min = int(ref_dt.utcoffset().total_seconds() / 60)
        return offset_min, tz_name
    except Exception:
        return 0, None


def _haversine(lat1, lng1, lat2, lng2):
    """Distance in metres between two GPS coordinates."""
    R  = 6_371_000
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a  = math.sin(df/2)**2 + math.cos(f1)*math.cos(f2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _normalize_time(points):
    """Set relative time from 0 (keep abs_time unchanged)."""
    if not points:
        return
    t0 = points[0].time
    for p in points:
        p.time -= t0


# ─────────────────────────────────────────────── demo data ───────────────────

def generate_demo_data():
    """Circular demo flight near Tashkent for testing without a log file."""
    center_lat, center_lng = 41.2995, 69.2401
    # Demo start: today 10:00:00 UTC — timezone-aware to avoid local-time conversion
    base_ts = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=10, minute=0, second=0, microsecond=0
    ).timestamp()
    points = []
    n = 300

    for i in range(n):
        phase = i / n
        t = i * 1.2

        if phase < 0.08:
            lat, lng = center_lat, center_lng
            alt = phase / 0.08 * 120
        elif phase < 0.88:
            a = (phase - 0.08) / 0.80 * 2 * math.pi * 3
            r = 0.004 + 0.001 * math.sin(a * 0.5)
            lat = center_lat + r * math.cos(a)
            lng = center_lng + r * math.sin(a) * 1.3
            alt = 120 + 30 * math.sin(a * 0.7)
        else:
            lat, lng = center_lat, center_lng
            alt = (1 - phase) / 0.12 * 120

        heading = math.degrees(math.atan2(
            lng - (points[-1].lng if points else center_lng),
            lat - (points[-1].lat if points else center_lat),
        )) % 360

        thr  = int(1000 + min(alt, 120) / 120 * 880)
        roll = int(1500 + math.sin(phase * math.pi * 6) * 200)
        # 4 simulated motors
        base_pwm = thr
        rcout = [
            min(2000, base_pwm + int(math.sin(phase * 20 + k) * 80))
            for k in range(4)
        ]
        abs_t = base_ts + t

        points.append(FlightPoint(
            time=t, lat=lat, lng=lng, alt=max(0.0, alt),
            spd=12.0 if 0.08 < phase < 0.88 else 3.0,
            heading=heading,
            rc_roll=roll, rc_pitch=1500,
            rc_throttle=thr, rc_yaw=1500,
            rcout=rcout,
            abs_time=abs_t,
            gps_time_str=_utc_str(abs_t),
        ))

    return FlightData(points, 'demo_flight.bin')
