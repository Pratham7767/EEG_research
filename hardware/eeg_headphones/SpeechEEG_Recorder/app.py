"""
Speech + EEG Recorder
=====================
Simultaneous speech and EEG recording application using pyneurosdk2 (NeuroSDK)
for Capsule Headphones2 (4 EEG channels: A1, C3, C4, A2 @ 250 Hz)
and PvRecorder for microphone audio (16 kHz mono).

Supports IAPF calibration, electrode resistance monitoring,
trial-based word prompting with time-synchronized data export.

Usage:
    python app.py
"""
import os
import sys
import logging

# Setup logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "app.log")),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("SpeechEEG")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    logger.info("Starting Speech + EEG Recorder")

    # Initialize core modules
    from core.device_manager import DeviceManager
    from core.calibration_manager import CalibrationManager
    from core.recording_engine import RecordingEngine
    from core.trial_manager import TrialManager
    from core.export_manager import ExportManager

    # Create data directory
    data_dir = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(data_dir, exist_ok=True)

    # Create managers
    device_manager = DeviceManager()
    calibration_manager = CalibrationManager(device_manager)
    recording_engine = RecordingEngine(device_manager)
    trial_manager = TrialManager(recording_engine)
    export_manager = ExportManager(base_dir=data_dir)

    # Initialize NeuroSDK (validates that pyneurosdk2 native library loads)
    if not device_manager.initialize():
        logger.error("Failed to initialize NeuroSDK (pyneurosdk2).")
        print("\nERROR: Could not initialize NeuroSDK")
        print("Make sure pyneurosdk2-1.0.15 is in the expected location:")
        print("  D:\\sit_secrets\\brain_bit\\pyneurosdk2-1.0.15\\")
        print("\nAlso ensure the native library (neurosdk-shared) is accessible.")
        sys.exit(1)

    logger.info("NeuroSDK initialized successfully")

    # Launch GUI
    from ui.main_window import MainWindow
    app = MainWindow(device_manager, calibration_manager, recording_engine, trial_manager, export_manager)
    logger.info("GUI launched")
    app.mainloop()

    logger.info("Application closed")


if __name__ == "__main__":
    main()
