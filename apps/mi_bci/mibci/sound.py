"""Beeps that are always heard.

Found on 2026-10-26: Windows' default output was "Headphones (USAMS-YX05)", i.e. the EEG headset itself,
over Bluetooth. Beeps there were sometimes lost: the Bluetooth audio link sleeps when idle and needs a
few hundred ms to wake, and the headset's radio is busy streaming EEG. Sending audio through the device
that records the EEG is also a bad idea in itself.

So:
  * the output device is chosen explicitly; by default the laptop speakers (any output whose name
    contains 'Speaker' and is not the headset), never the EEG headset unless asked
  * ONE output stream stays open all the time (sounddevice / PortAudio callback). Tones are mixed into it,
    so nothing is ever cut off and there is no wake-up delay
  * tones are 300 ms with 10 ms soft edges
Falls back to winsound if sounddevice is missing.
The beep is only a 'get ready' warning: markers are stamped on the screen change, not the sound.
"""
import threading

import numpy as np

HEADSET_WORDS = ("USAMS", "YX05", "LEHeadPhones", "Capsule", "Neiry")
FS_AUDIO = 44100


def tone(freq, ms, amp=0.5, fs=FS_AUDIO):
    t = np.arange(int(fs * ms / 1000)) / fs
    y = amp * np.sin(2 * np.pi * freq * t)
    r = int(0.01 * fs)
    y[:r] *= np.linspace(0, 1, r)
    y[-r:] *= np.linspace(1, 0, r)
    return y.astype(np.float32)


TONES = {"beep": (1000, 300), "high": (1500, 350)}


def list_outputs():
    """[(index, name)] of output devices on the default host API."""
    import sounddevice as sd
    api = sd.default.hostapi
    return [(i, d["name"]) for i, d in enumerate(sd.query_devices())
            if d["max_output_channels"] > 0 and d["hostapi"] == api]


def pick_output(prefer=None):
    """prefer: part of a device name. Default: laptop speakers, never the EEG headset."""
    outs = list_outputs()
    if prefer:
        for i, n in outs:
            if prefer.lower() in n.lower():
                return i, n
    for i, n in outs:
        if "speaker" in n.lower() and not any(w.lower() in n.lower() for w in HEADSET_WORDS):
            return i, n
    for i, n in outs:
        if not any(w.lower() in n.lower() for w in HEADSET_WORDS) and "mapper" not in n.lower():
            return i, n
    return outs[0] if outs else (None, "none")


class Sound:
    def __init__(self, prefer=None, muted=False):
        self.muted = muted
        self.lock = threading.Lock()
        self.queue = []               # [buffer, position]
        self.stream = None
        self.device = None
        self.played = 0               # tones fully rendered (for the self-check)
        self.error = None
        try:
            import sounddevice as sd
            self.sd = sd
            self.open(prefer)
        except Exception as e:        # no sounddevice or no device: winsound fallback
            self.sd = None
            self.error = str(e)
        self.bufs = {k: tone(f, ms) for k, (f, ms) in TONES.items()}

    def open(self, prefer=None):
        self.close()
        idx, name = pick_output(prefer)
        self.stream = self.sd.OutputStream(device=idx, samplerate=FS_AUDIO, channels=1, dtype="float32",
                                           callback=self._callback, latency="low")
        self.stream.start()
        self.device = name
        return name

    def _callback(self, out, frames, time_info, status):
        out.fill(0)
        with self.lock:
            keep = []
            for item in self.queue:
                buf, pos = item
                n = min(frames, len(buf) - pos)
                out[:n, 0] += buf[pos:pos + n]
                item[1] = pos + n
                if item[1] < len(buf):
                    keep.append(item)
                else:
                    self.played += 1
            self.queue = keep

    def play(self, name="beep", *_):
        if self.muted:
            return
        if self.stream is not None:
            with self.lock:
                self.queue.append([self.bufs[name], 0])
            return
        try:                                          # fallback
            import winsound
            f, ms = TONES[name]
            threading.Thread(target=winsound.Beep, args=(f, ms), daemon=True).start()
        except Exception:
            pass

    # kept for the app's run start/stop calls; the stream is always open now
    def start_keepalive(self):
        pass

    def stop(self):
        pass

    def close(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
