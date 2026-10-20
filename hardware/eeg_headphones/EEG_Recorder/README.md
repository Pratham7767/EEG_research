# EEG + Voice Recording Application

A PyQt5-based desktop application for simultaneous EEG and voice recording with electrode impedance calibration.

## Features

- **Simultaneous Recording**: Captures EEG data (4 channels at 250Hz) and audio (16kHz) in parallel
- **Auto-Calibration**: Measures electrode impedance and displays contact quality (Good/Acceptable/Bad)
- **Multi-Format Export**: 
  - CSV files (separate EEG, audio, resistance data)
  - HDF5 (optimal for long recordings)
  - WAV (audio backup)
- **Real-time Monitoring**: Live electrode status, battery level, recording duration, sample counts
- **Signal Processing**: Butterworth bandpass filter (4-30Hz) for EEG data
- **Thread-Safe**: Parallel device communication and UI updates

## Project Structure

```
EEG_Recorder/
├── app.py                        # Main entry point
├── requirements.txt              # Python dependencies
├── README.md                     # This file
├── config/
│   └── config.json              # Configuration settings
├── core/
│   ├── device_manager.py        # Device scanner & communication
│   ├── calibration_manager.py   # Impedance measurement & quality check
│   ├── recording_worker.py      # QThread for parallel data acquisition
│   ├── export_manager.py        # CSV/HDF5 export logic
│   └── signal_processor.py      # Filtering & synchronization
├── ui/
│   └── main_window.py           # PyQt5 GUI
└── tests/
    └── (test files - future)
```

## Installation

### Prerequisites
- Python 3.7+
- LEHeadphones2 device (powered on and nearby)

### Setup

1. Install Python dependencies:
```powershell
cd d:\sit_secrets\EEG_Recorder
c:/python313/python.exe -m pip install -r requirements.txt --user
```

2. Verify pyneurosdk2 is installed:
```powershell
cd d:\sit_secrets
python -c "import sys; sys.path.insert(0, 'pyneurosdk2-1.0.15'); from neurosdk import Scanner; print('✓ pyneurosdk loaded')"
```

## Running the Application

```powershell
cd d:\sit_secrets\EEG_Recorder
c:/python313/python.exe app.py
```

The GUI will launch with these tabs:

### Tab 1: Connection & Calibration
1. Click **Scan for Devices** to find your LEHeadphones2
2. Select device from list and click **Connect Selected Device**
3. Click **Start Calibration** to measure electrode impedance
4. Wait 3 seconds for calibration to complete
5. Check electrode quality indicators (Green = Good, Yellow = Acceptable, Red = Bad)

### Tab 2: Recording
1. Enter a session name (optional - auto-generated if blank)
2. Click **Start Recording** (enabled only after calibration)
3. Monitor:
   - Recording time (HH:MM:SS format)
   - EEG and audio sample counts
   - Real-time status in log
4. Click **Stop Recording** to end session
5. Data automatically exports to `~/EEG_Recordings/{timestamp}/`

### Tab 3: Settings
- **EEG Sampling Rate**: 250 Hz (fixed)
- **Audio Sampling Rate**: 16 kHz (adjustable 8-48 kHz)
- **Gain**: Select amplification (1x - 16x)
- **Bandpass Filter**: Enable/disable 4-30Hz filter
- **Export Formats**: Choose CSV, HDF5, and/or WAV output

### Tab 4: Log
- Real-time status messages
- Test messages for debugging
- Timestamps for all events

## Output Files

After recording, session directory contains:

```
~/EEG_Recordings/{YYYY-MM-DD_HHMMSS}/
├── session_metadata.json              # Device & session info
├── {session_name}_eeg.csv             # Raw & filtered EEG (timestamp + 8 columns)
├── {session_name}_audio.csv           # Audio samples (timestamp + sample)
├── {session_name}_resistance.csv      # Electrode impedance (timestamp + 4 channels)
├── {session_name}_audio.wav           # Raw audio backup (16-bit WAV)
└── {session_name}.h5                  # All data (HDF5, optimal for long recordings)
```

### CSV Format Examples

**EEG CSV** (`_eeg.csv`):
```
timestamp,Ch1,Ch2,Ch3,Ch4,Ch1_filtered,Ch2_filtered,Ch3_filtered,Ch4_filtered
1712329200.123,45.2,42.1,38.5,41.2,45.1,42.0,38.6,41.1
1712329200.128,44.8,41.9,38.7,40.9,44.9,41.8,38.5,40.8
```

**Audio CSV** (`_audio.csv`):
```
timestamp,audio_sample
1712329200.124,0.0001
1712329200.127,0.0002
```

**Resistance CSV** (`_resistance.csv`):
```
timestamp,Ch1_ohms,Ch2_ohms,Ch3_ohms,Ch4_ohms
1712329200.125,4500,4600,18000,5200
1712329200.135,4520,4610,18100,5210
```

### HDF5 Structure

Open HDF5 file with Python:
```python
import h5py

with h5py.File('session_name.h5', 'r') as f:
    # Metadata
    print(f.attrs['eeg_sampling_rate'])  # 250
    
    # EEG data
    eeg_raw = f['eeg/raw'][:]            # (num_samples, 4)
    eeg_timestamps = f['eeg/timestamps'][:]
    
    # Audio data
    audio_samples = f['audio/samples'][:]
    audio_timestamps = f['audio/timestamps'][:]
    
    # Resistance
    resist = f['resistance/channels'][:]  # (num_samples, 4)
    resist_timestamps = f['resistance/timestamps'][:]
```

## Electrode Impedance Thresholds

During calibration, impedance values are classified as:

| Quality  | Impedance Range | Color  | Status |
|----------|-----------------|--------|--------|
| Good     | < 5 kΩ         | Green  | ✓ Ready |
| Acceptable | 5-20 kΩ      | Yellow | ⚠ OK |
| Bad      | > 20 kΩ        | Red    | ✗ Reposition |

All electrodes must be Good or Acceptable to start recording.

## Signal Processing

- **Filter**: Butterworth bandpass (4th order), 4-30 Hz cutoff
- **Sampling**: EEG @ 250Hz, Audio @ 16kHz
- **Channels**: 4 EEG channels (Ch1-4)
- **State**: Filter state preserved per channel during continuous recording

## Troubleshooting

### Device Not Found
- Power on LEHeadphones2 device
- Ensure Bluetooth is enabled (if wireless)
- Check device serial number on battery compartment
- Restart application and scan again

### Calibration Shows Red (Bad Contact)
- Adjust electrode positioning
- Clean electrode tips with dry cloth
- Ensure good skin contact
- Re-run calibration after adjustment

### Audio Not Recording
- Check system audio input (microphone) settings
- Verify PvRecorder installation: `python -c "from pvrecorder import PvRecorder"`
- App will continue EEG recording if audio fails

### Files Not Exported
- Check directory permissions: `~/EEG_Recordings/` must be writable
- Ensure sufficient disk space (HDF5 files can be large for long recordings)
- Check application log for error messages

### High Impedance at Baseline
- This is normal! Impedance changes during recording.
- Just ensure calibration shows Acceptable or Good status.
- If still struggling, check electrode paste/gel.

## Configuration

Edit `config/config.json` to customize:

```json
{
  "eeg": {
    "sampling_rate": 250,              // Fixed for LEHeadphones2
    "filter_lowcut": 4,                // Hz
    "filter_highcut": 30               // Hz
  },
  "calibration": {
    "duration_seconds": 3,
    "impedance_good_threshold": 5000,  // 5 kΩ
    "impedance_acceptable_threshold": 20000  // 20 kΩ
  },
  "export": {
    "formats": ["csv", "hdf5", "wav"]
  }
}
```

## Performance

- **Recording Duration**: Limited by available disk space
  - 1 hour @ 250Hz EEG + 16kHz audio ≈ 150-200 MB (CSV)
  - HDF5 compressed: ~80-100 MB
- **CPU Usage**: ~5-10% (minimal UI overhead)
- **RAM**: ~50-100 MB for typical sessions

## Future Enhancements

- [ ] Real-time waveform visualization
- [ ] Multiple device support (simultaneous recording)
- [ ] BDF/EDF+ export (requires C++ toolchain for compilation)
- [ ] Impedance trend graphs
- [ ] Session replay/analysis tools
- [ ] Database integration for batch processing

## API Usage (Programmatic)

```python
from core.device_manager import DeviceManager
from core.calibration_manager import CalibrationManager
from core.recording_worker import RecordingWorker

# Connect
device_mgr = DeviceManager()
devices = device_mgr.scan_devices()
device_mgr.connect_device(devices[0])

# Calibrate
calib_mgr = CalibrationManager()
device_mgr.start_resist_measurement()
calib_mgr.start_calibration()
# ... collect data
calib_mgr.stop_calibration()
results = calib_mgr.get_calibration_results()
print(f"Ready: {calib_mgr.is_ready_to_record()}")

# Record
worker = RecordingWorker(device_mgr)
worker.start_recording()
# ... wait ...
worker.stop_recording()

# Export
from core.export_manager import ExportManager
export_mgr = ExportManager()
session_dir = export_mgr.create_session_directory()
export_mgr.export_session(
    session_dir,
    {'eeg': worker.get_eeg_data(), 'audio': worker.get_audio_data()},
    {'device': 'LEHeadphones2'}
)
```

## Support

For issues or questions:
1. Check the **Log** tab in the GUI for debug messages
2. Verify device connection with vendor's app
3. Test with shorter recordings first
4. Check disk space on output directory

## License

(Add your license here)

## References

- pyneurosdk2 Documentation: See `pyneurosdk2-1.0.15/README.md`
- PyQt5: https://doc.qt.io/qt-5/
- NumPy/SciPy: https://numpy.org/, https://scipy.org/
- HDF5: https://www.h5py.org/
