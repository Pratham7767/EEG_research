"""CapsuleEngine: owns the Capsule SDK objects and turns callbacks into events.

Threading: the DLL runs in single-threaded mode, so every SDK callback fires
inside `pump()` (which calls `device_locator.update()`). Call `pump()` from
the UI thread (Tk `after`) or a test loop — no locks needed.

Events emitted on `engine.events` (all payloads are plain Python / numpy):
    state(old, new)            devices(list[dict])        status(str)
    connected(info dict)       disconnected()             battery(int)
    resistances({name: ohms})  eeg(ts_ms, processed, raw) psd(freqs, spectrum, sdk_ms)
    artifacts(sdk_ms, [(artifact, quality), ...])
    emotions(dict)             productivity(dict)         indexes(dict)
    calibrated(dict)           calibration_failed(str)
    baseline_progress(float)   baseline(dict)             cardio(dict)
    error(str)
"""
import logging
import os
import time

import numpy as np

from . import config
from .events import EventBus

logger = logging.getLogger(__name__)


class State:
    IDLE = "idle"
    SCANNING = "scanning"
    DEVICES_FOUND = "devices_found"
    CONNECTING = "connecting"
    STREAMING = "streaming"          # connected + started, not yet calibrated
    CALIBRATING = "calibrating"
    CALIBRATED = "calibrated"
    BASELINE = "baseline"
    LIVE = "live"
    DISCONNECTED = "disconnected"
    STOPPED = "stopped"


_STOPPABLE = {State.STREAMING, State.CALIBRATING, State.CALIBRATED, State.BASELINE,
              State.LIVE, State.DISCONNECTED}

TRANSITIONS = {
    State.IDLE:          {State.SCANNING},
    State.SCANNING:      {State.DEVICES_FOUND, State.IDLE},
    State.DEVICES_FOUND: {State.SCANNING, State.CONNECTING},
    State.CONNECTING:    {State.STREAMING, State.DEVICES_FOUND},
    State.STREAMING:     {State.CALIBRATING, State.CALIBRATED, State.DISCONNECTED, State.STOPPED},
    State.CALIBRATING:   {State.CALIBRATED, State.STREAMING, State.DISCONNECTED, State.STOPPED},
    State.CALIBRATED:    {State.BASELINE, State.LIVE, State.CALIBRATING, State.DISCONNECTED, State.STOPPED},
    State.BASELINE:      {State.LIVE, State.CALIBRATED, State.DISCONNECTED, State.STOPPED},
    State.LIVE:          {State.DISCONNECTED, State.STOPPED},
    State.DISCONNECTED:  {State.STOPPED},
    State.STOPPED:       set(),
}


class InvalidTransition(RuntimeError):
    pass


class Flow:
    """Pure state machine: refuses steps out of order (e.g. baseline before calibration)."""

    def __init__(self, on_change=None):
        self.state = State.IDLE
        self._on_change = on_change

    def can(self, new):
        return new in TRANSITIONS[self.state]

    def go(self, new):
        if not self.can(new):
            raise InvalidTransition(f"{self.state} -> {new}")
        old, self.state = self.state, new
        if self._on_change:
            self._on_change(old, new)

    def require(self, *states):
        if self.state not in states:
            raise InvalidTransition(f"action needs state {states}, current {self.state}")


def _int(value):
    """ctypes enum objects (c_int subclasses) → plain int."""
    return int(getattr(value, "value", value))


class CapsuleEngine:
    """One engine per process: the vendor wrapper keeps callbacks in module globals."""

    SIMULATORS = {"noise": "Noise", "sinwave": "SinWave"}

    def __init__(self, simulate=None, record_eeg=False, clock=time.monotonic):
        from . import capsule_sdk  # noqa: F401  (import here so pure modules never need the DLL)
        from .capsule_sdk.Capsule import Capsule
        from .capsule_sdk.DeviceLocator import DeviceLocator
        from .capsule_sdk.DeviceType import DeviceType

        if simulate and simulate not in self.SIMULATORS:
            raise ValueError(f"simulate must be one of {list(self.SIMULATORS)}")
        self.simulate = simulate
        self.device_type = getattr(DeviceType, self.SIMULATORS[simulate]) if simulate else DeviceType.Headphones
        self.record_eeg = record_eeg
        self._clock = clock
        self.events = EventBus()
        self.flow = Flow(on_change=lambda old, new: self.events.emit("state", old, new))

        self._capsule = Capsule(capsule_sdk.DLL_PATH)
        self.lib = self._capsule.get_lib()
        self.sdk_version = self._capsule.get_version()
        os.makedirs(config.SDK_LOG_DIR, exist_ok=True)
        self._locator = DeviceLocator(config.SDK_LOG_DIR, self.lib)
        self._locator.set_on_devices_list(self._on_devices_list)

        self.device = None
        self.device_info = {}
        self.channel_names = []
        self.sample_rate = None
        self.battery = None
        self.ppg_supported = None           # None = unknown yet, False = module refused
        self.ppg_seen = False
        self.calibration = None
        self.baseline = None

        self._devices = []
        self._scan_deadline = None
        self._connect_serial = None
        self._connect_attempt = 0
        self._connect_deadline = None
        self._retry_at = None
        self._calibration_deadline = None
        self._baseline_deadline = None
        self._last_psd = -1e9
        self._psd_bins = None               # (indices, freqs) of 1-30 Hz bins, cached
        self._calibrator = self._productivity = self._emotions = self._cardio = None

    # ── public API ───────────────────────────────────────────────
    @property
    def state(self):
        return self.flow.state

    def pump(self):
        """Deliver SDK callbacks and handle timeouts. Call every ~20 ms."""
        self._locator.update()
        now = self._clock()
        st = self.state
        if st == State.SCANNING and now > self._scan_deadline:
            self.flow.go(State.IDLE)
            self.events.emit("error", "No response from Bluetooth while scanning. Check the dongle and try again.")
        elif st == State.CONNECTING:
            if self._retry_at is not None and now >= self._retry_at:
                self._retry_at = None
                self._attempt_connect()
            elif self._retry_at is None and now > self._connect_deadline:
                self._connect_failed("timed out")
        elif st == State.CALIBRATING and now > self._calibration_deadline:
            self.flow.go(State.STREAMING)
            self.events.emit("calibration_failed", "Calibration timed out (no result from the SDK).")
        elif st == State.BASELINE and now > self._baseline_deadline:
            self.flow.go(State.CALIBRATED)
            self.events.emit("error", "Baseline timed out. Try again.")

    def scan(self, seconds=config.SCAN_SECONDS):
        if self.state == State.DEVICES_FOUND:
            self.flow.go(State.SCANNING)
        else:
            self.flow.require(State.IDLE)
            self.flow.go(State.SCANNING)
        self._devices = []
        self._scan_deadline = self._clock() + seconds + 5
        self.events.emit("status", "Searching for devices...")
        self._locator.request_devices(self.device_type, seconds)

    def connect(self, serial):
        self.flow.require(State.DEVICES_FOUND)
        from .capsule_sdk.Device import Device
        self.flow.go(State.CONNECTING)
        self._connect_serial = serial
        self._connect_attempt = 0
        self._retry_at = None
        if self.device is None:
            self.device = Device(self._locator, serial, self.lib)
            self._wire_device_callbacks()
        self._attempt_connect()

    def start_calibration(self):
        self.flow.require(State.STREAMING, State.CALIBRATED)
        self.flow.go(State.CALIBRATING)
        self._calibration_deadline = self._clock() + config.CALIBRATION_TIMEOUT_S
        self._calibrator.calibrate_quick()
        self.events.emit("status", "Calibrating: keep your eyes closed")

    def import_calibration(self, iapf=None):
        """Skip the 30 s wait (simulator/dev only): import typical iAPF values."""
        self.flow.require(State.STREAMING, State.CALIBRATED)
        from .capsule_sdk.Calibrator import IndividualNFBData
        self._calibrator.import_alpha(IndividualNFBData(**(iapf or config.FAST_IAPF)))
        data = dict(iapf or config.FAST_IAPF, imported=True, fail_reason=0)
        data["iapf"] = data.get("individual_peak_frequency")
        self.calibration = data
        if self.state != State.CALIBRATED:
            self.flow.go(State.CALIBRATED)
        self.events.emit("calibrated", data)

    def start_baseline(self):
        self.flow.require(State.CALIBRATED)
        self.flow.go(State.BASELINE)
        self._baseline_deadline = self._clock() + config.BASELINE_TIMEOUT_S
        self._productivity.calibrate_baselines()
        self.events.emit("status", "Recording baseline: eyes open, relaxed")

    def import_baseline(self, values=None):
        """Skip the baseline wait (simulator/dev only)."""
        self.flow.require(State.CALIBRATED)
        from .capsule_sdk.Productivity import Productivity_Baselines
        values = values or config.FAST_BASELINE
        self._productivity.import_baselines(Productivity_Baselines(**values, timestamp=0))
        self.baseline = {"concentration": values["concentration"], "relaxation": values["relax"],
                         "fatigue": values["fatigue"], "reverse_fatigue": values["reverse_fatigue"],
                         "gravity": values["gravity"], "productivity": values["productivity"],
                         "imported": True}
        self.flow.go(State.LIVE)
        self.events.emit("baseline", self.baseline)

    def reset_accumulated_fatigue(self):
        if self._productivity is not None:
            self._productivity.reset_accumulated_fatigue()

    def stop(self):
        if self.state in _STOPPABLE:
            self.flow.go(State.STOPPED)
        if self.device is not None:
            for action in (self.device.stop, self.device.disconnect):
                try:
                    action()
                except Exception as exc:          # already disconnected etc.
                    logger.info("stop: %s", exc)
            end = self._clock() + 1.0
            while self._clock() < end:
                self._locator.update()
                time.sleep(0.02)

    # ── connection internals ─────────────────────────────────────
    def _attempt_connect(self):
        from .capsule_sdk.Error import CapsuleException
        self._connect_attempt += 1
        total = len(config.CONNECT_RETRY_DELAYS_S) + 1
        self.events.emit("status", f"Connecting... (attempt {self._connect_attempt}/{total})")
        self._connect_deadline = self._clock() + config.CONNECT_TIMEOUT_S
        try:
            self.device.connect(bipolarChannels=config.BIPOLAR)
        except CapsuleException as exc:
            self._connect_failed(_message(exc))

    def _connect_failed(self, why):
        if self._connect_attempt <= len(config.CONNECT_RETRY_DELAYS_S):
            delay = config.CONNECT_RETRY_DELAYS_S[self._connect_attempt - 1]
            self.events.emit("status", f"Connection failed ({why}); retrying in {delay} s...")
            self._retry_at = self._clock() + delay
        else:
            self.flow.go(State.DEVICES_FOUND)
            self.events.emit("error", f"Could not connect after {self._connect_attempt} attempts ({why}).")

    def _on_connected(self):
        """Create classifiers BEFORE start() (SDK requirement), then start streaming."""
        from .capsule_sdk.Calibrator import Calibrator
        from .capsule_sdk.Productivity import Productivity
        from .capsule_sdk.Emotions import Emotions
        from .capsule_sdk.Cardio import Cardio
        from .capsule_sdk.Error import CapsuleException

        lib = self.lib
        if self._calibrator is None:
            self._calibrator = Calibrator(self.device, lib)
            self._calibrator.set_on_calibration_finished(self._on_calibration_finished)

            self._productivity = Productivity(self.device, lib)
            self._productivity.set_on_metrics_update(self._on_productivity)
            self._productivity.set_on_indexes_update(self._on_indexes)
            self._productivity.set_on_baseline_update(self._on_baseline)
            self._productivity.set_on_calibration_progress(
                lambda _p, progress: self.events.emit("baseline_progress", float(progress)))

            self._emotions = Emotions(self.device, lib)
            self._emotions.set_on_states_update(self._on_emotions)

            try:
                self._cardio = Cardio(self.device, lib)
                self._cardio.set_on_indexes_update(self._on_cardio)
                self.ppg_supported = None
            except CapsuleException as exc:
                self.ppg_supported = False
                logger.info("Cardio not supported: %s", _message(exc))

        names = self.device.get_channel_names()
        self.channel_names = [names.get_name_by_index(i) for i in range(len(names))]
        self.device.start()
        self.sample_rate = self.device.get_eeg_sample_rate()
        try:
            info = self.device.get_info()
            self.device_info = {"name": info.get_name(), "serial": info.get_serial(), "type": info.get_type()}
        except Exception:
            self.device_info = {"serial": self._connect_serial}
        self.device_info.update(channels=self.channel_names, sample_rate=self.sample_rate,
                                sdk_version=self.sdk_version, simulated=bool(self.simulate))
        self.flow.go(State.STREAMING)
        self.events.emit("connected", dict(self.device_info))

    def _wire_device_callbacks(self):
        d = self.device
        d.set_on_connection_status_changed(self._on_connection_status)
        d.set_on_battery_charge_changed(self._on_battery)
        d.set_on_resistances(self._on_resistances)
        d.set_on_eeg(self._on_eeg)
        d.set_on_psd(self._on_psd)
        d.set_on_eeg_artifacts(self._on_artifacts)
        d.set_on_error(lambda _d, msg: self.events.emit("error", f"Device: {msg}"))

    # ── SDK callbacks (run inside pump) ──────────────────────────
    def _on_devices_list(self, _locator, info, fail_reason):
        if self.state != State.SCANNING:
            return
        fail = _int(fail_reason)
        self._devices = [{"name": info[i].get_name(), "serial": info[i].get_serial(), "type": info[i].get_type()}
                         for i in range(len(info))]
        if self._devices:
            self.flow.go(State.DEVICES_FOUND)
            self.events.emit("devices", list(self._devices))
        else:
            self.flow.go(State.IDLE)
            why = "Bluetooth is disabled." if fail == 1 else "No device found."
            self.events.emit("error", f"{why} Check the checklist and scan again.")

    def _on_connection_status(self, _device, status):
        status = _int(status)
        if status == 1 and self.state == State.CONNECTING:
            self._retry_at = None
            try:
                self._on_connected()
            except Exception as exc:
                logger.exception("setup after connect failed")
                self.flow.go(State.DEVICES_FOUND)
                self.events.emit("error", f"Connected but setup failed: {exc}")
        elif status == 0 and self.state in _STOPPABLE - {State.DISCONNECTED}:
            self.flow.go(State.DISCONNECTED)
            self.events.emit("disconnected")
        elif status == 2:
            self.events.emit("error", "This device does not support the requested connection.")

    def _on_battery(self, _device, charge):
        self.battery = int(charge)
        self.events.emit("battery", self.battery)

    def _on_resistances(self, _device, res):
        values = {res.get_channel_name(i): float(res.get_value(i)) for i in range(len(res))}
        self.events.emit("resistances", values)

    def _on_eeg(self, _device, eeg):
        n, ch = eeg.get_samples_count(), eeg.get_channels_count()
        if n <= 0 or ch <= 0:
            return
        ts = [eeg.get_timestamp(i) for i in range(n)]
        processed = np.array([[eeg.get_processed_value(c, i) for c in range(ch)] for i in range(n)], dtype=float)
        # Raw is always read: the band-power chart needs delta and gamma, which the SDK's
        # processed signal (band-passed ~4-30 Hz) removes. record_eeg only controls saving.
        raw = np.array([[eeg.get_raw_value(c, i) for c in range(ch)] for i in range(n)], dtype=float)
        self.events.emit("eeg", ts, processed, raw)

    def _on_psd(self, _device, psd):
        now = self._clock()
        if now - self._last_psd < config.PSD_PROCESS_INTERVAL_S:
            return                                    # ~23 frames/s from the SDK; 2/s is plenty
        self._last_psd = now
        if self._psd_bins is None:
            lo, hi = config.TOTAL_RANGE
            freqs = [psd.get_frequency(i) for i in range(psd.get_frequencies_count())]
            idx = [i for i, f in enumerate(freqs) if lo <= f <= hi]
            self._psd_bins = (idx, np.array([freqs[i] for i in idx]))
        idx, freqs = self._psd_bins
        spectrum = np.array([[psd.get_psd(c, i) for i in idx] for c in range(psd.get_channels_count())], dtype=float)
        self.events.emit("psd", freqs, spectrum, psd.get_timestamp())

    def _on_artifacts(self, _device, art):
        flags = [(int(art.get_artifacts_by_channel(c)), int(art.get_eeg_quality(c)))
                 for c in range(art.get_channels_count())]
        self.events.emit("artifacts", art.get_timestamp(), flags)

    def _on_emotions(self, _emotions, s):
        self.events.emit("emotions", {
            "sdk_ms": s.timestampMilli, "attention": s.attention, "relaxation": s.relaxation,
            "cognitive_load": s.cognitiveLoad, "cognitive_control": s.cognitiveControl,
            "self_control": s.selfControl})

    def _on_productivity(self, _prod, m):
        self.events.emit("productivity", {
            "sdk_ms": m.timestampMilli, "concentration": m.concentrationScore,
            "relaxation": m.relaxationScore, "fatigue": m.fatigueScore,
            "reverse_fatigue": m.reverseFatigueScore, "gravity": m.gravityScore,
            "productivity": m.productivityScore, "current_value": m.currentValue, "alpha": m.alpha,
            "accumulated_fatigue": m.accumulatedFatigue, "fatigue_growth_rate": _int(m.fatigueGrowthRate)})

    def _on_indexes(self, _prod, ix):
        self.events.emit("indexes", {
            "sdk_ms": ix.timestampMilli, "recommendation": _int(ix.relaxation),
            "stress": _int(ix.stress), "has_artifacts": bool(ix.hasArtifacts)})

    def _on_calibration_finished(self, _cal, d):
        if self.state != State.CALIBRATING:
            return
        fail = _int(d.failReason)
        data = {"fail_reason": fail, "iapf": d.individualPeakFrequency, "iaf": d.individualFrequency,
                "peak_power": d.individualPeakFrequencyPower, "bandwidth": d.individualBandwidth,
                "normalized_power": d.individualNormalizedPower,
                "lower_frequency": d.lowerFrequency, "upper_frequency": d.upperFrequency, "imported": False}
        if fail == 0:
            self.calibration = data
            self.flow.go(State.CALIBRATED)
            self.events.emit("calibrated", data)
        else:
            self.flow.go(State.STREAMING)
            reason = {1: "Too many artifacts: sit still, relax your jaw, and try again.",
                      2: "Alpha peak at the edge of the range: close your eyes fully and try again."}
            self.events.emit("calibration_failed", reason.get(fail, f"failed (code {fail})"))

    def _on_baseline(self, _prod, b):
        if self.state != State.BASELINE:
            return
        self.baseline = {"concentration": b.concentration, "relaxation": b.relaxation, "fatigue": b.fatigue,
                         "reverse_fatigue": b.reverseFatigue, "gravity": b.gravity,
                         "productivity": b.productivity, "imported": False}
        self.flow.go(State.LIVE)
        self.events.emit("baseline", dict(self.baseline))

    def _on_cardio(self, _cardio, c):
        data = {"sdk_ms": c.timestampMilli, "heart_rate": c.heartRate, "stress_index": c.stressIndex,
                "kaplan_index": c.kaplanIndex, "has_artifacts": bool(c.hasArtifacts),
                "skin_contact": bool(c.skinContact), "motion_artifacts": bool(c.motionArtifacts),
                "metrics_available": bool(c.metricsAvailable)}
        if data["skin_contact"] or data["metrics_available"]:
            self.ppg_seen = True
            self.ppg_supported = True
        self.events.emit("cardio", data)


def _message(exc):
    msg = getattr(exc, "message", exc)
    return msg.decode("utf-8", "replace").strip("\x00 ") if isinstance(msg, bytes) else str(msg)
