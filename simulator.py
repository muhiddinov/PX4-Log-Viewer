"""
Flight playback engine — drives the timeline at variable speed.
"""

from PyQt5.QtCore import QObject, QTimer, QElapsedTimer, pyqtSignal


class FlightSimulator(QObject):
    frame_changed      = pyqtSignal(int)   # emits current point index
    playback_finished  = pyqtSignal()
    state_changed      = pyqtSignal(str)   # 'playing' | 'paused' | 'stopped'

    SPEEDS = (1, 2, 4, 8)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data          = None
        self._index         = 0
        self._speed         = 1
        self._playing       = False
        self._virt_start    = 0.0   # virtual time when play/resume began
        self._elapsed       = QElapsedTimer()

        self._timer = QTimer(self)
        self._timer.setInterval(40)  # ~25 fps
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ props

    @property
    def is_playing(self):
        return self._playing

    @property
    def current_index(self):
        return self._index

    @property
    def total_frames(self):
        return len(self._data.points) if self._data else 0

    @property
    def speed(self):
        return self._speed

    # ----------------------------------------------------------------- public

    def load(self, flight_data):
        self._timer.stop()
        self._playing = False
        self._data    = flight_data
        self._index   = 0
        self.state_changed.emit('stopped')

    def play(self):
        if not self._data or not self._data.points:
            return
        if self._index >= self.total_frames - 1:
            self._index = 0
        self._virt_start = self._data.points[self._index].time
        self._elapsed.restart()
        self._playing = True
        self._timer.start()
        self.state_changed.emit('playing')

    def pause(self):
        if not self._playing:
            return
        self._timer.stop()
        self._playing = False
        self.state_changed.emit('paused')

    def stop(self):
        self._timer.stop()
        self._playing = False
        self._seek_to(0)
        self.state_changed.emit('stopped')

    def seek(self, index):
        was_playing = self._playing
        if was_playing:
            self._timer.stop()
        self._seek_to(index)
        if was_playing:
            self._virt_start = self._data.points[self._index].time
            self._elapsed.restart()
            self._timer.start()

    def set_speed(self, speed):
        if speed not in self.SPEEDS:
            return
        if self._playing:
            # Maintain current virtual position when changing speed
            self._virt_start = self._data.points[self._index].time
            self._elapsed.restart()
        self._speed = speed

    # ----------------------------------------------------------------- private

    def _seek_to(self, index):
        pts = self._data.points if self._data else []
        self._index = max(0, min(index, len(pts) - 1))
        if pts:
            self._virt_start = pts[self._index].time
            self._elapsed.restart()
            self.frame_changed.emit(self._index)

    def _tick(self):
        if not self._data:
            return

        pts    = self._data.points
        vtime  = self._virt_start + self._elapsed.elapsed() / 1000.0 * self._speed

        # Advance index to match virtual time
        idx = self._index
        while idx < len(pts) - 1 and pts[idx + 1].time <= vtime:
            idx += 1

        self._index = idx
        self.frame_changed.emit(idx)

        if idx >= len(pts) - 1:
            self._timer.stop()
            self._playing = False
            self.state_changed.emit('stopped')
            self.playback_finished.emit()
