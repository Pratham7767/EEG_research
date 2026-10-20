"""
Device Manager — handles discovery, connection, resistance monitoring,
battery tracking, and EEG streaming via pyneurosdk2 (NeuroSDK).

Uses Headphones2Sensor with 4 EEG channels:
  Ch1 -> A1,  Ch2 -> C3,  Ch3 -> C4,  Ch4 -> A2
"""
import sys
import os
import time
import threading
import logging

# ── SDK paths ────────────────────────────────────────────────────
NEUROSDK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "brain_bit", "pyneurosdk2-1.0.15"
)

CAPSULE_SDK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "brain_bit", "Capsule_API", "Capsule v2.0.40",
    "CapsuleAPI", "Windows", "Capsule Python", "CapsuleClientPython"
)

CAPSULE_DLL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "brain_bit", "Capsule_API", "Capsule v2.0.40",
    "CapsuleAPI", "Windows", "Lib", "CapsuleClient.dll"
)

# Add pyneurosdk2 to path
if NEUROSDK_PATH not in sys.path:
    sys.path.insert(0, NEUROSDK_PATH)

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily, SensorCommand

logger = logging.getLogger(__name__)

# Channel mapping: SDK Ch1-Ch4 → electrode names
CHANNEL_MAP = {0: "A1", 1: "C3", 2: "C4", 3: "A2"}
CHANNEL_NAMES = ["A1", "C3", "C4", "A2"]


class _EventBus:
    """Simple pub/sub: multiple listeners per event, no overwrites."""

    def __init__(self):
        self._listeners = {}

    def subscribe(self, event, callback):
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        def _unsub():
            try:
                self._listeners[event].remove(callback)
            except ValueError:
                pass
        return _unsub

    def emit(self, event, *args, **kwargs):
        for cb in self._listeners.get(event, []):
            try:
                cb(*args, **kwargs)
            except Exception as e:
                logger.error(f"EventBus error in {event}: {e}")


class DeviceManager:
    """Manages Capsule headphones via pyneurosdk2."""

    MAX_RETRY = 3
    RETRY_DELAYS = [2, 5, 10]

    # Event names
    EVT_DEVICE_LIST     = "device_list"
    EVT_CONNECTION      = "connection"
    EVT_RESISTANCE      = "resistance"
    EVT_BATTERY         = "battery"
    EVT_EEG             = "eeg"
    EVT_EEG_ARTIFACTS   = "eeg_artifacts"
    EVT_PSD             = "psd"
    EVT_ARTIFACT_STATUS = "artifact_status"
    EVT_ERROR           = "error"
    EVT_MODE            = "mode"

    def __init__(self):
        self._scanner = None
        self._sensor = None
        self._connected = False
        self._streaming = False
        self._resist_streaming = False
        self._battery = 0
        self._eeg_sample_rate = 250.0
        self._channel_names = list(CHANNEL_NAMES)

        # Pub/sub event bus
        self.events = _EventBus()

        # Legacy single-callback attributes (recording engine uses on_eeg_data)
        self.on_device_list_updated = None
        self.on_connection_changed  = None
        self.on_resistance_update   = None
        self.on_battery_update      = None
        self.on_eeg_data            = None
        self.on_eeg_artifacts       = None
        self.on_psd_data            = None
        self.on_artifact_status     = None
        self.on_error               = None
        self.on_mode_changed        = None

        self._device_list_event = threading.Event()
        self._scan_fail_reason  = None

    def initialize(self):
        """Verify NeuroSDK is loadable. Returns True on success."""
        try:
            # Scanner creation validates that the native library loads
            test_scanner = Scanner([SensorFamily.LEHeadPhones2])
            del test_scanner
            logger.info("NeuroSDK (pyneurosdk2) initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize NeuroSDK: {e}")
            if self.on_error:
                self.on_error(f"SDK init failed: {e}")
            return False

    def scan_devices(self, search_time=10):
        """Scan for Headphones2 devices. Non-blocking."""
        self._device_list_event.clear()

        def _scan():
            try:
                self._scanner = Scanner([SensorFamily.LEHeadPhones2])
                self._scanner.start()

                deadline = time.time() + search_time
                while time.time() < deadline:
                    time.sleep(0.2)

                self._scanner.stop()
                sensors = self._scanner.sensors()

                devices = []
                for s in sensors:
                    devices.append({
                        "name": s.Name,
                        "serial": s.SerialNumber,
                        "type": "Headphones2",
                        "address": s.Address,
                        "_sensor_info": s,   # keep for create_sensor
                    })

                self._device_list_event.set()
                if self.on_device_list_updated:
                    self.on_device_list_updated(devices)
                self.events.emit(self.EVT_DEVICE_LIST, devices)

            except Exception as e:
                logger.error(f"Scan error: {e}")
                self._device_list_event.set()
                self.events.emit(self.EVT_ERROR, f"Scan failed: {e}")

        threading.Thread(target=_scan, daemon=True).start()

    def connect(self, serial_or_info, bipolar=True):
        """Connect to a device by serial or sensor_info dict."""

        def _attempt_connect():
            sensor_info = None

            # Resolve sensor_info from serial string
            if isinstance(serial_or_info, str):
                if self._scanner is None:
                    self._emit_connection(False, "Scan for devices first")
                    return
                for s in self._scanner.sensors():
                    if s.SerialNumber == serial_or_info:
                        sensor_info = s
                        break
                if sensor_info is None:
                    self._emit_connection(False, f"Device {serial_or_info} not found")
                    return
            elif isinstance(serial_or_info, dict):
                sensor_info = serial_or_info.get("_sensor_info")
            else:
                sensor_info = serial_or_info

            for attempt in range(self.MAX_RETRY):
                try:
                    logger.info(f"Connection attempt {attempt + 1}/{self.MAX_RETRY}")
                    self._emit_connection(False,
                        f"Connecting... (attempt {attempt + 1}/{self.MAX_RETRY})")

                    # create_sensor auto-connects
                    self._sensor = self._scanner.create_sensor(sensor_info)

                    self._connected = True
                    self._channel_names = list(CHANNEL_NAMES)

                    # Get battery
                    try:
                        self._battery = self._sensor.batt_power
                    except Exception:
                        self._battery = 0

                    # Start resistance monitoring by default
                    self._start_resistance()

                    logger.info(f"Connected | Channels={self._channel_names} | SR={self._eeg_sample_rate}")
                    self._emit_connection(True, "Connected")
                    return

                except Exception as e:
                    logger.error(f"Connection error: {e}")
                    if attempt < self.MAX_RETRY - 1:
                        delay = self.RETRY_DELAYS[attempt]
                        self._emit_connection(False,
                            f"Failed, retrying in {delay}s...")
                        time.sleep(delay)

            self._emit_connection(False, "Connection failed after 3 attempts")

        threading.Thread(target=_attempt_connect, daemon=True).start()

    def disconnect(self):
        if self._sensor:
            try:
                self._sensor.exec_command(SensorCommand.StopSignal)
            except Exception:
                pass
            try:
                self._sensor.exec_command(SensorCommand.StopResist)
            except Exception:
                pass
            try:
                self._sensor.disconnect()
            except Exception:
                pass
            self._connected = False
            self._streaming = False
            self._resist_streaming = False
            self._emit_connection(False, "Disconnected")

    def start_resistance(self):
        """Public: start resistance monitoring and wire callback."""
        self._start_resistance()

    def _start_resistance(self):
        """Start resistance monitoring and wire callback."""
        if not self._sensor or self._resist_streaming:
            return
        try:
            self._sensor.resistDataReceived = self._on_resist_data
            self._sensor.exec_command(SensorCommand.StartResist)
            self._resist_streaming = True
            logger.info("Resistance monitoring started")
        except Exception as e:
            logger.error(f"Failed to start resistance: {e}")

    def start_signal(self):
        """Start EEG signal streaming."""
        if not self._sensor or not self._connected or self._streaming:
            return
        try:
            # Stop resist first (SDK may not support both simultaneously on headphones)
            if self._resist_streaming:
                try:
                    self._sensor.exec_command(SensorCommand.StopResist)
                    self._resist_streaming = False
                except Exception:
                    pass

            self._sensor.signalDataReceived = self._on_signal_data
            self._sensor.exec_command(SensorCommand.StartSignal)
            self._streaming = True
            logger.info("EEG signal streaming started")
        except Exception as e:
            logger.error(f"Failed to start signal: {e}")

    def stop_signal(self):
        if self._sensor and self._connected and self._streaming:
            try:
                self._sensor.exec_command(SensorCommand.StopSignal)
                self._streaming = False
                logger.info("EEG signal streaming stopped")
            except Exception:
                pass

    @property
    def is_streaming(self):
        return self._streaming

    @property
    def is_resist_streaming(self):
        return self._resist_streaming

    @property
    def is_connected(self):
        return self._connected

    @property
    def eeg_sample_rate(self):
        return self._eeg_sample_rate

    @property
    def channel_names(self):
        return self._channel_names

    @property
    def battery(self):
        return self._battery

    def get_sensor(self):
        return self._sensor

    def update(self):
        """Periodic update — refresh battery if connected."""
        if self._sensor and self._connected:
            try:
                self._battery = self._sensor.batt_power
            except Exception:
                pass

    # ── Internal callbacks ─────────────────────────────────────────

    def _emit_connection(self, connected, msg):
        if self.on_connection_changed:
            self.on_connection_changed(connected, msg)
        self.events.emit(self.EVT_CONNECTION, connected, msg)

    def _on_resist_data(self, sensor, data_list):
        """Resistance callback from NeuroSDK."""
        result = []
        for sample in data_list:
            result.append({"channel": "A1", "value": sample.Ch1})
            result.append({"channel": "C3", "value": sample.Ch2})
            result.append({"channel": "C4", "value": sample.Ch3})
            result.append({"channel": "A2", "value": sample.Ch4})

        if self.on_resistance_update:
            self.on_resistance_update(result)
        self.events.emit(self.EVT_RESISTANCE, result)

    def _on_signal_data(self, sensor, data_list):
        """EEG signal callback from NeuroSDK.
        data_list is List[Headphones2SignalData] with .Ch1-.Ch4 attributes.
        We forward to both legacy callback and event bus."""
        if self.on_eeg_data:
            self.on_eeg_data(data_list)
        self.events.emit(self.EVT_EEG, data_list)

    # Compatibility getters (used by calibration_manager)
    def get_device(self):
        return self._sensor

    def get_lib(self):
        """Load and return the Capsule ctypes CDLL lib (lazy, cached).
        Required by Calibrator, Productivity, PhysiologicalStates."""
        if not hasattr(self, '_capsule_lib'):
            self._capsule_lib = None
        if self._capsule_lib is not None:
            return self._capsule_lib
        try:
            import ctypes
            dll_path = os.path.normpath(CAPSULE_DLL_PATH)
            if os.path.isfile(dll_path):
                lib = ctypes.CDLL(dll_path)
                lib.clCCapsule_SetSingleThreaded.argtypes = [ctypes.c_bool]
                lib.clCCapsule_SetSingleThreaded(True)
                self._capsule_lib = lib
                logger.info(f"Capsule DLL loaded: {dll_path}")
                return self._capsule_lib
            else:
                logger.warning(f"Capsule DLL not found: {dll_path}")
                return None
        except Exception as e:
            logger.error(f"Failed to load Capsule DLL: {e}")
            return None

    def get_locator(self):
        return self._scanner
