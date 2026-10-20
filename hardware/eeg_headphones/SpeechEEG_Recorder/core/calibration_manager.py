"""
Calibration Manager — handles IAPF calibration (quick 30s + full 4-stage),
Productivity baseline, and Physiological States baseline.
Supports save/load of calibration data to JSON.
"""
import os
import json
import time
import logging
import threading

logger = logging.getLogger(__name__)


class CalibrationManager:
    """Manages all calibration workflows for Capsule headphones."""

    def __init__(self, device_manager):
        self._dm = device_manager
        self._calibrator = None
        self._productivity = None
        self._physio_states = None

        # Calibration results
        self.iapf_data = None
        self.productivity_baselines = None
        self.physio_baselines = None

        # Status flags
        self.iapf_calibrated = False
        self.iapf_failed = False
        self.productivity_calibrated = False
        self.physio_calibrated = False

        # Progress
        self.productivity_progress = 0.0
        self.physio_progress = 0.0

        # UI callbacks
        self.on_iapf_done = None            # (dict) -> None
        self.on_iapf_failed = None          # (str) -> None
        self.on_iapf_stage_done = None      # () -> None
        self.on_productivity_progress = None # (float) -> None
        self.on_productivity_done = None     # (dict) -> None
        self.on_physio_progress = None       # (float) -> None
        self.on_physio_done = None           # (dict) -> None

    def _ensure_sdk_imports(self):
        """Lazy import Capsule API classes (v2.0.40) for calibration features."""
        import sys
        from core.device_manager import CAPSULE_SDK_PATH
        if CAPSULE_SDK_PATH not in sys.path:
            sys.path.insert(0, CAPSULE_SDK_PATH)

    def start_quick_iapf(self):
        """Start 30-second quick IAPF calibration. Device must be connected and streaming."""
        self._ensure_sdk_imports()
        from Calibrator import Calibrator, IndividualNFBData, IndividualNFBCalibrationFailReason

        device = self._dm.get_device()
        lib = self._dm.get_lib()
        if not device or not lib:
            if self.on_iapf_failed:
                self.on_iapf_failed("Device not connected")
            return

        try:
            self._calibrator = Calibrator(device, lib)

            def _on_calibrated(calibrator, nfb_data):
                self.iapf_data = {
                    "individualFrequency": nfb_data.individualFrequency,
                    "individualPeakFrequency": nfb_data.individualPeakFrequency,
                    "individualPeakFrequencyPower": nfb_data.individualPeakFrequencyPower,
                    "individualPeakFrequencySuppression": nfb_data.individualPeakFrequencySuppression,
                    "individualBandwidth": nfb_data.individualBandwidth,
                    "individualNormalizedPower": nfb_data.individualNormalizedPower,
                    "lowerFrequency": nfb_data.lowerFrequency,
                    "upperFrequency": nfb_data.upperFrequency,
                    "failReason": nfb_data.failReason.value if hasattr(nfb_data.failReason, 'value') else int(nfb_data.failReason),
                    "timestampMilli": nfb_data.timestampMilli,
                }

                fail = nfb_data.failReason
                fail_val = fail.value if hasattr(fail, 'value') else int(fail)

                if fail_val != 0:
                    self.iapf_failed = True
                    self.iapf_calibrated = False
                    reason = "Too many artifacts" if fail_val == 1 else "Peak is at border"
                    logger.warning(f"IAPF calibration failed: {reason}")
                    if self.on_iapf_failed:
                        self.on_iapf_failed(reason)
                else:
                    self.iapf_calibrated = True
                    self.iapf_failed = False
                    logger.info(f"IAPF calibrated: IAF={nfb_data.individualFrequency:.2f} Hz")
                    if self.on_iapf_done:
                        self.on_iapf_done(self.iapf_data)

            def _on_stage_done(calibrator):
                if self.on_iapf_stage_done:
                    self.on_iapf_stage_done()

            self._calibrator.set_on_calibration_finished(_on_calibrated)
            self._calibrator.set_on_calibration_stage_finished(_on_stage_done)
            self._calibrator.calibrate_quick()
            logger.info("Quick IAPF calibration started (30 seconds)")

        except Exception as e:
            logger.error(f"Failed to start IAPF calibration: {e}")
            if self.on_iapf_failed:
                self.on_iapf_failed(str(e))

    def start_productivity_baseline(self):
        """Start Productivity baseline calibration."""
        self._ensure_sdk_imports()
        from Productivity import Productivity, Productivity_Baselines

        device = self._dm.get_device()
        lib = self._dm.get_lib()
        if not device or not lib:
            return

        try:
            self._productivity = Productivity(device, lib)

            def _on_baseline(prod, baselines):
                self.productivity_baselines = {
                    "gravity": baselines.gravity,
                    "productivity": baselines.productivity,
                    "fatigue": baselines.fatigue,
                    "reverseFatigue": baselines.reverseFatigue,
                    "relaxation": baselines.relaxation,
                    "concentration": baselines.concentration,
                    "timestampMilli": baselines.timestampMilli,
                }
                self.productivity_calibrated = True
                logger.info("Productivity baseline calibrated")
                if self.on_productivity_done:
                    self.on_productivity_done(self.productivity_baselines)

            def _on_progress(prod, progress):
                self.productivity_progress = progress
                if self.on_productivity_progress:
                    self.on_productivity_progress(progress)

            self._productivity.set_on_baseline_update(_on_baseline)
            self._productivity.set_on_calibration_progress(_on_progress)
            self._productivity.calibrate_baselines()
            logger.info("Productivity baseline calibration started")

        except Exception as e:
            logger.error(f"Failed to start Productivity calibration: {e}")

    def start_physio_baseline(self):
        """Start Physiological States baseline calibration."""
        self._ensure_sdk_imports()
        from PhysiologicalStates import PhysiologicalStates, PhysiologicalStates_Baselines

        device = self._dm.get_device()
        lib = self._dm.get_lib()
        if not device or not lib:
            return

        try:
            self._physio_states = PhysiologicalStates(device, lib)

            def _on_calibrated(ps, baselines):
                self.physio_baselines = {
                    "alpha": baselines.alpha,
                    "beta": baselines.beta,
                    "alphaGravity": baselines.alphaGravity,
                    "betaGravity": baselines.betaGravity,
                    "concentration": baselines.concentration,
                    "timestampMilli": baselines.timestampMilli,
                }
                self.physio_calibrated = True
                logger.info("Physiological states baseline calibrated")
                if self.on_physio_done:
                    self.on_physio_done(self.physio_baselines)

            def _on_progress(ps, progress):
                self.physio_progress = progress
                if self.on_physio_progress:
                    self.on_physio_progress(progress)

            self._physio_states.set_on_calibrated(_on_calibrated)
            self._physio_states.set_on_calibration_progress(_on_progress)
            self._physio_states.calibrate_baselines()
            logger.info("Physiological states baseline calibration started")

        except Exception as e:
            logger.error(f"Failed to start Physiological States calibration: {e}")

    def import_iapf(self, data_dict):
        """Import previously saved IAPF calibration data."""
        self._ensure_sdk_imports()
        from Calibrator import Calibrator, IndividualNFBData

        device = self._dm.get_device()
        lib = self._dm.get_lib()
        if not device or not lib:
            return False

        try:
            self._calibrator = Calibrator(device, lib)
            nfb = IndividualNFBData(
                timestamp_milli=int(data_dict.get("timestampMilli", 1)),
                individual_frequency=float(data_dict["individualFrequency"]),
                individual_peak_frequency=float(data_dict["individualPeakFrequency"]),
                individual_peak_frequency_power=float(data_dict["individualPeakFrequencyPower"]),
                individual_peak_frequency_suppression=float(data_dict["individualPeakFrequencySuppression"]),
                individual_bandwidth=float(data_dict["individualBandwidth"]),
                individual_normalized_power=float(data_dict["individualNormalizedPower"]),
                lower_frequency=float(data_dict["lowerFrequency"]),
                upper_frequency=float(data_dict["upperFrequency"]),
            )
            self._calibrator.import_alpha(nfb)
            self.iapf_data = data_dict
            self.iapf_calibrated = True
            self.iapf_failed = False
            logger.info(f"Imported IAPF data: IAF={data_dict['individualFrequency']:.2f} Hz")
            return True
        except Exception as e:
            logger.error(f"Failed to import IAPF data: {e}")
            return False

    def import_productivity_baselines(self, data_dict):
        """Import previously saved productivity baselines."""
        self._ensure_sdk_imports()
        from Productivity import Productivity, Productivity_Baselines

        device = self._dm.get_device()
        lib = self._dm.get_lib()
        if not device or not lib:
            return False

        try:
            self._productivity = Productivity(device, lib)
            baselines = Productivity_Baselines(
                concentration=float(data_dict["concentration"]),
                fatigue=float(data_dict["fatigue"]),
                gravity=float(data_dict["gravity"]),
                productivity=float(data_dict["productivity"]),
                relax=float(data_dict["relaxation"]),
                reverse_fatigue=float(data_dict["reverseFatigue"]),
                timestamp=int(data_dict.get("timestampMilli", -1)),
            )
            self._productivity.import_baselines(baselines)
            self.productivity_baselines = data_dict
            self.productivity_calibrated = True
            logger.info("Imported productivity baselines")
            return True
        except Exception as e:
            logger.error(f"Failed to import productivity baselines: {e}")
            return False

    def import_physio_baselines(self, data_dict):
        """Import previously saved physiological states baselines."""
        self._ensure_sdk_imports()
        from PhysiologicalStates import PhysiologicalStates, PhysiologicalStates_Baselines

        device = self._dm.get_device()
        lib = self._dm.get_lib()
        if not device or not lib:
            return False

        try:
            self._physio_states = PhysiologicalStates(device, lib)
            baselines = PhysiologicalStates_Baselines(
                alpha=float(data_dict["alpha"]),
                beta=float(data_dict["beta"]),
                alpha_gravity=float(data_dict["alphaGravity"]),
                beta_gravity=float(data_dict["betaGravity"]),
                concentration=float(data_dict["concentration"]),
                timestamp_milli=int(data_dict.get("timestampMilli", -1)),
            )
            self._physio_states.import_baselines(baselines)
            self.physio_baselines = data_dict
            self.physio_calibrated = True
            logger.info("Imported physiological states baselines")
            return True
        except Exception as e:
            logger.error(f"Failed to import physio baselines: {e}")
            return False

    def save_calibration(self, filepath):
        """Save all calibration data to a JSON file."""
        data = {
            "saved_at": time.time(),
            "iapf": self.iapf_data,
            "productivity_baselines": self.productivity_baselines,
            "physio_baselines": self.physio_baselines,
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Calibration saved to {filepath}")

    def load_calibration(self, filepath):
        """Load calibration data from JSON. Returns dict or None."""
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r") as f:
            data = json.load(f)
        logger.info(f"Calibration loaded from {filepath}")
        return data

    def get_calibration_summary(self):
        """Get a summary dict of current calibration state."""
        return {
            "iapf_calibrated": self.iapf_calibrated,
            "iapf_failed": self.iapf_failed,
            "iapf_frequency": self.iapf_data.get("individualFrequency") if self.iapf_data else None,
            "productivity_calibrated": self.productivity_calibrated,
            "physio_calibrated": self.physio_calibrated,
        }
