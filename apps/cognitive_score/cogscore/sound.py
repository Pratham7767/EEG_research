"""Beeps on the laptop speakers, never on the EEG headphones.

Windows' default output is "Headphones (USAMS-YX05)" while the headset is connected, so winsound.Beep
played into the headset (found in apps/mi_bci on 2026-10-26: beeps there were also sometimes lost,
because the Bluetooth audio link sleeps when idle and the radio is busy streaming EEG).

So the output is chosen explicitly (an output with "Speaker" in its name that is not the headset), and
ONE sounddevice stream stays open; tones are mixed into it (no wake-up delay, nothing cut off).
Falls back to winsound if sounddevice is missing or no such output opens.
"""
import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

HEADSET_WORDS = ("usams", "yx05", "leheadphones", "capsule", "neiry")
FS = 44100
GAP_MS = 40


def _tone(freq, ms, amp=0.45):
    t = np.arange(int(FS * ms / 1000)) / FS
    y = amp * np.sin(2 * np.pi * freq * t)
    r = min(int(0.01 * FS), len(y) // 2)
    if r:
        y[:r] *= np.linspace(0, 1, r)
        y[-r:] *= np.linspace(1, 0, r)
    return y.astype(np.float32)


def _sequence(tones):
    gap = np.zeros(int(FS * GAP_MS / 1000), dtype=np.float32)
    parts = []
    for freq, ms in tones:
        parts += [_tone(freq, ms), gap]
    return np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)


def pick_output(sd):
    """(index, name): laptop speakers, else any output that is not the headset."""
    api = sd.default.hostapi
    outs = [(i, d["name"]) for i, d in enumerate(sd.query_devices())
            if d["max_output_channels"] > 0 and d["hostapi"] == api]
    not_headset = [(i, n) for i, n in outs if not any(w in n.lower() for w in HEADSET_WORDS)]
    for i, n in not_headset:
        if "speaker" in n.lower():
            return i, n
    for i, n in not_headset:
        if "mapper" not in n.lower():
            return i, n
    return None, None


class Sound:
    def __init__(self, beeps, enabled=True):
        self.enabled = enabled
        self.beeps = beeps                      # kind -> [(freq, ms), ...]
        self.device = None
        self._stream = None
        self._queue = []
        self._lock = threading.Lock()
        if not enabled:
            return
        try:
            import sounddevice as sd
            idx, name = pick_output(sd)
            if idx is None:
                raise RuntimeError("no non-headset output device")
            self._stream = sd.OutputStream(device=idx, samplerate=FS, channels=1, dtype="float32",
                                           callback=self._callback, latency="low")
            self._stream.start()
            self.device = name
            self._bufs = {k: _sequence(v) for k, v in beeps.items()}
            logger.info("beeps on: %s", name)
        except Exception as exc:
            self._stream = None
            logger.warning("sound: %s; falling back to winsound (Windows default output)", exc)

    def _callback(self, out, frames, _time, _status):
        out.fill(0)
        with self._lock:
            keep = []
            for item in self._queue:
                buf, pos = item
                n = min(frames, len(buf) - pos)
                out[:n, 0] += buf[pos:pos + n]
                item[1] = pos + n
                if item[1] < len(buf):
                    keep.append(item)
            self._queue = keep

    def play(self, kind):
        if not self.enabled or kind not in self.beeps:
            return
        if self._stream is not None:
            with self._lock:
                self._queue.append([self._bufs[kind], 0])
            return
        try:
            import winsound
        except ImportError:
            return

        def _play():
            for freq, ms in self.beeps[kind]:
                winsound.Beep(freq, ms)
        threading.Thread(target=_play, daemon=True).start()

    def close(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
