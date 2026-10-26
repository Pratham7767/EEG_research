"""Where samples come from. Every source gives (n x 4) arrays in microvolts, columns A1, C3, C4, A2,
in order, through read(). Three kinds:

  HeadphonesSource  the real LEHeadPhones2 over Bluetooth (pyneurosdk2, as in SpeechEEG_Recorder)
  SimulatedSource   synthetic EEG with mu/beta rhythms; imagery lowers them on the opposite side
  ReplaySource      a recorded run (ours, or a converted BCI IV 2b session), as fast as asked
"""
import sys
import threading
import time
from collections import deque

import numpy as np
from scipy.signal import butter, sosfilt

from . import config as C


class Source:
    name = "source"
    realtime = True

    def start(self):
        pass

    def stop(self):
        pass

    def read(self):
        """Return all samples that arrived since the last call (may be empty)."""
        raise NotImplementedError

    def set_task(self, cls):
        """Only the simulator uses this: which hand the 'subject' is imagining (None = rest)."""

    def status(self):
        return {}


# --------------------------------------------------------------------------------------------
class SimulatedSource(Source):
    """skill = fraction of mu/beta power lost on the opposite hemisphere during imagery.
    skill 0 = no information at all (a check that nothing leaks into the decoder).
    speed = how many times faster than real time samples are produced (realtime pacing)."""
    name = "simulator"

    def __init__(self, skill=0.5, seed=0, speed=1.0, packet=10, realtime=True):
        self.skill, self.speed, self.packet, self.realtime = skill, speed, packet, realtime
        self.rng = np.random.default_rng(seed)
        fs = C.FS
        self.sos_mu = butter(2, (9, 12), btype="bandpass", fs=fs, output="sos")
        self.sos_beta = butter(2, (18, 24), btype="bandpass", fs=fs, output="sos")
        self.z_mu = np.zeros((self.sos_mu.shape[0], 2, 2))
        self.z_beta = np.zeros((self.sos_beta.shape[0], 2, 2))
        self.pink = np.zeros(4)
        self.task = None
        self.gain = np.ones(2)          # current rhythm gain at C3, C4 (smoothed toward target)
        self.t0 = None
        self.produced = 0
        self.packnum = 0

    def start(self):
        self.t0 = time.perf_counter()

    def set_task(self, cls):
        self.task = cls

    def generate(self, n):
        target = np.ones(2)
        if self.task == C.LEFT:         # left-hand imagery: right hemisphere (C4) desynchronises
            target = np.array([1 - 0.25 * self.skill, 1 - self.skill])
        elif self.task == C.RIGHT:
            target = np.array([1 - self.skill, 1 - 0.25 * self.skill])
        out = np.empty((n, 4))
        a = np.exp(-1 / (0.4 * C.FS))  # ERD builds up / recovers over ~0.4 s
        for i in range(n):
            self.gain = a * self.gain + (1 - a) * target
            out[i, 1:3] = self.gain
        g = out[:, 1:3].copy()
        w = self.rng.standard_normal((n, 2))
        mu, self.z_mu = sosfilt(self.sos_mu, w, axis=0, zi=self.z_mu)
        w = self.rng.standard_normal((n, 2))
        beta, self.z_beta = sosfilt(self.sos_beta, w, axis=0, zi=self.z_beta)
        noise = np.empty((n, 4))
        for i in range(n):              # 1/f-like background
            self.pink = 0.97 * self.pink + self.rng.standard_normal(4)
            noise[i] = self.pink
        out[:, 0] = 3.0 * noise[:, 0]
        out[:, 3] = 3.0 * noise[:, 3]
        out[:, 1:3] = 3.0 * noise[:, 1:3] + g * (60.0 * mu + 25.0 * beta) + 2.0 * self.rng.standard_normal((n, 2))
        self.produced += n
        return out

    def read(self):
        if not self.realtime:
            return self.generate(self.packet)
        if self.t0 is None:
            self.start()
        due = int((time.perf_counter() - self.t0) * C.FS * self.speed)
        n = (due - self.produced) // self.packet * self.packet
        if n <= 0:
            return np.zeros((0, 4))
        return self.generate(n)

    def status(self):
        return {"battery": 100, "resistance": {c: 150e3 for c in C.CHANNELS}}


# --------------------------------------------------------------------------------------------
class ReplaySource(Source):
    """Feeds a recorded (n x 4) array. chunk = samples per read(); realtime=False goes as fast as possible."""
    name = "replay"

    def __init__(self, data, chunk=10, speed=1.0, realtime=False):
        self.data = np.asarray(data, float)
        self.chunk, self.speed, self.realtime = chunk, speed, realtime
        self.pos = 0
        self.t0 = None

    @property
    def finished(self):
        return self.pos >= len(self.data)

    def read(self):
        if self.finished:
            return np.zeros((0, 4))
        if self.realtime:
            if self.t0 is None:
                self.t0 = time.perf_counter()
            due = min(len(self.data), int((time.perf_counter() - self.t0) * C.FS * self.speed))
            end = max(self.pos, due)
        else:
            end = min(len(self.data), self.pos + self.chunk)
        x = self.data[self.pos:end]
        self.pos = end
        return x


# --------------------------------------------------------------------------------------------
class HeadphonesSource(Source):
    """LEHeadPhones2 through pyneurosdk2 (same calls as SpeechEEG_Recorder/core/device_manager.py).
    Samples arrive in a Bluetooth callback thread; read() drains them. Values come in volts and
    are converted to microvolts. Dropped packets are counted from PackNum."""
    name = "headphones"

    def __init__(self):
        self.scanner = None
        self.sensor = None
        self.q = deque()
        self.lock = threading.Lock()
        self.last_pack = None
        self.dropped_packets = 0
        self.received = 0
        self.resist = {}
        self.streaming = False
        self.arrival = deque(maxlen=2000)       # (perf_counter, samples so far) for delay checks

    @staticmethod
    def _import():
        p = str(C.NEUROSDK_PATH)
        if p not in sys.path:
            sys.path.insert(0, p)
        from neurosdk.scanner import Scanner
        from neurosdk.cmn_types import SensorFamily, SensorCommand
        return Scanner, SensorFamily, SensorCommand

    def scan(self, seconds=8):
        Scanner, SensorFamily, _ = self._import()
        self.scanner = Scanner([SensorFamily.LEHeadPhones2])
        self.scanner.start()
        time.sleep(seconds)
        self.scanner.stop()
        return [dict(name=s.Name, serial=s.SerialNumber, info=s) for s in self.scanner.sensors()]

    def connect(self, info):
        self.sensor = self.scanner.create_sensor(info)      # auto-connects, raises on failure
        return True

    def battery(self):
        try:
            return self.sensor.batt_power
        except Exception:
            return None

    def start_resistance(self):
        _, _, Cmd = self._import()

        def on_resist(sensor, data):
            for s in data:
                self.resist = {"A1": s.Ch1, "C3": s.Ch2, "C4": s.Ch3, "A2": s.Ch4}
        self.sensor.resistDataReceived = on_resist
        self.sensor.exec_command(Cmd.StartResist)

    def stop_resistance(self):
        _, _, Cmd = self._import()
        try:
            self.sensor.exec_command(Cmd.StopResist)
        except Exception:
            pass

    def start(self):
        _, _, Cmd = self._import()
        self.stop_resistance()                                # headphones cannot do both at once

        def on_signal(sensor, data):
            rows = []
            for s in data:
                if self.last_pack is not None and s.PackNum > self.last_pack + 1:
                    gap = s.PackNum - self.last_pack - 1
                    self.dropped_packets += gap
                    # ASSUMPTION (unverified on hardware): PackNum counts samples. Fill the gap
                    # with NaN rows so the sample clock stays right; DSP treats NaN as 0.
                    if gap < C.FS:
                        rows.extend([(np.nan,) * 4] * gap)
                self.last_pack = s.PackNum
                rows.append((s.Ch1 * 1e6, s.Ch2 * 1e6, s.Ch3 * 1e6, s.Ch4 * 1e6))
            with self.lock:
                self.q.extend(rows)
                self.received += len(rows)
                self.arrival.append((time.perf_counter(), self.received))
        self.sensor.signalDataReceived = on_signal
        self.sensor.exec_command(Cmd.StartSignal)
        self.streaming = True

    def stop(self):
        if not self.sensor:
            return
        _, _, Cmd = self._import()
        try:
            self.sensor.exec_command(Cmd.StopSignal)
        except Exception:
            pass
        self.streaming = False

    def disconnect(self):
        self.stop()
        try:
            self.sensor.disconnect()
        except Exception:
            pass
        self.sensor = None

    def read(self):
        with self.lock:
            if not self.q:
                return np.zeros((0, 4))
            x = np.array(self.q, float)
            self.q.clear()
        return x

    def status(self):
        return {"battery": self.battery(), "resistance": dict(self.resist),
                "dropped_packets": self.dropped_packets, "received": self.received}
