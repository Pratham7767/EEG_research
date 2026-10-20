"""
Recording worker thread: Handles parallel EEG, audio, and resistance data acquisition.
"""

import sys
import os
from PyQt5.QtCore import QThread, pyqtSignal
from collections import deque
import numpy as np
import time

# Add pvrecorder to path
try:
    from pvrecorder import PvRecorder
except ImportError:
    PvRecorder = None


class RecordingWorker(QThread):
    """
    Worker thread for parallel EEG + audio recording.
    Emits signals for UI updates.
    """
    
    # Signals
    eeg_data_acquired = pyqtSignal(object)  # EEG data with timestamp
    audio_data_acquired = pyqtSignal(object)  # Audio data with timestamp
    resist_data_acquired = pyqtSignal(object)  # Resistance data
    battery_data_acquired = pyqtSignal(int)  # Battery percentage
    recording_status = pyqtSignal(str)  # Status messages
    error_occurred = pyqtSignal(str)  # Error messages
    recording_stopped = pyqtSignal(dict)  # Final recording stats
    
    def __init__(self, device_manager, sampling_rate_eeg=250, sampling_rate_audio=16000):
        """
        Initialize recording worker.
        
        Args:
            device_manager: DeviceManager instance
            sampling_rate_eeg: EEG sampling rate (Hz)
            sampling_rate_audio: Audio sampling rate (Hz)
        """
        super().__init__()
        self.device_manager = device_manager
        self.eeg_fs = sampling_rate_eeg
        self.audio_fs = sampling_rate_audio
        
        self.is_recording = False
        self.start_time = None
        
        # Data buffers
        self.eeg_buffer = deque()  # (timestamp, Ch1, Ch2, Ch3, Ch4)
        self.audio_buffer = deque()  # (timestamp, sample)
        self.resist_buffer = deque()  # (timestamp, Ch1, Ch2, Ch3, Ch4)
        
        # Recording stats
        self.eeg_count = 0
        self.audio_count = 0
        self.resist_count = 0
        
        # Audio recorder
        self.recorder = None
        self.audio_frame_length_ms = 30  # 30ms frames
    
    def start_recording(self):
        """Start recording session."""
        self.is_recording = True
        self.start_time = time.time()
        self.eeg_count = 0
        self.audio_count = 0
        self.resist_count = 0
        
        # Clear buffers
        self.eeg_buffer.clear()
        self.audio_buffer.clear()
        self.resist_buffer.clear()
        
        # Start this thread
        self.start()
    
    def stop_recording(self):
        """Stop recording session."""
        self.is_recording = False
        
        # Wait for thread to finish
        self.wait(5000)  # 5 second timeout
    
    def run(self):
        """Main recording loop (runs in separate thread)."""
        try:
            if not self.device_manager.is_connected():
                self.error_occurred.emit("Device not connected")
                return
            
            # Register device callbacks
            self.device_manager.on_signal_received = self._on_eeg_data
            self.device_manager.on_resist_received = self._on_resist_data
            self.device_manager.on_battery_received = self._on_battery_data
            
            # Initialize audio recorder
            if not self._init_audio_recorder():
                self.recording_status.emit("Warning: Audio recorder failed, continuing EEG only")
            
            # Start device acquisition
            self.device_manager.start_signal_acquisition()
            self.device_manager.start_resist_measurement()
            
            self.recording_status.emit("Recording started")
            
            # Main recording loop
            while self.is_recording:
                time.sleep(0.01)  # Small delay to prevent CPU spinning
            
            # Stop device acquisition
            self.device_manager.stop_signal_acquisition()
            self.device_manager.stop_resist_measurement()
            
            # Close audio recorder
            if self.recorder:
                self.recorder.stop()
                self.recorder.delete()
            
            # Emit final statistics
            elapsed_time = time.time() - self.start_time
            stats = {
                'elapsed_time': elapsed_time,
                'eeg_samples': self.eeg_count,
                'audio_samples': self.audio_count,
                'resist_samples': self.resist_count,
                'eeg_expected': int(elapsed_time * self.eeg_fs),
                'audio_expected': int(elapsed_time * self.audio_fs)
            }
            
            self.recording_stopped.emit(stats)
            self.recording_status.emit("Recording stopped")
            
        except Exception as e:
            self.error_occurred.emit(f"Recording error: {str(e)}")
        finally:
            # Clean up callbacks
            self.device_manager.on_signal_received = None
            self.device_manager.on_resist_received = None
            self.device_manager.on_battery_received = None
    
    def _init_audio_recorder(self) -> bool:
        """Initialize PvRecorder for audio capture."""
        try:
            if PvRecorder is None:
                return False
            
            # Get default audio device
            devices = PvRecorder.get_available_devices()
            if not devices:
                return False
            
            device_index = PvRecorder.get_default_device_index()
            
            # Create recorder
            self.recorder = PvRecorder(
                device_index=device_index,
                frame_length=int(self.audio_fs * self.audio_frame_length_ms / 1000),
                sample_rate=self.audio_fs
            )
            
            # Start recording
            self.recorder.start()
            
            return True
            
        except Exception as e:
            print(f"Audio recorder init failed: {e}")
            return False
    
    def _on_eeg_data(self, data):
        """Callback for EEG data received."""
        if not self.is_recording:
            return
        
        try:
            # Extract data from device
            timestamp = time.time()
            
            # Extract channel data (assuming data object has Ch1-Ch4 attributes)
            if hasattr(data, 'Ch1'):
                channels = [data.Ch1, data.Ch2, data.Ch3, data.Ch4]
            else:
                return
            
            # Store in buffer
            self.eeg_buffer.append({
                'timestamp': timestamp,
                'channels': channels,
                'packet_num': getattr(data, 'PackNum', self.eeg_count)
            })
            
            self.eeg_count += 1
            
            # Emit signal for UI update
            self.eeg_data_acquired.emit({
                'timestamp': timestamp,
                'channels': channels,
                'count': self.eeg_count
            })
            
        except Exception as e:
            print(f"Error processing EEG data: {e}")
    
    def _on_resist_data(self, data):
        """Callback for resistance data received."""
        if not self.is_recording:
            return
        
        try:
            timestamp = time.time()
            
            # Extract resistance data
            if hasattr(data, 'Ch1'):
                resistances = [data.Ch1, data.Ch2, data.Ch3, data.Ch4]
            else:
                return
            
            # Store in buffer
            self.resist_buffer.append({
                'timestamp': timestamp,
                'channels': resistances
            })
            
            self.resist_count += 1
            
            # Emit signal
            self.resist_data_acquired.emit({
                'timestamp': timestamp,
                'channels': resistances,
                'count': self.resist_count
            })
            
        except Exception as e:
            print(f"Error processing resistance data: {e}")
    
    def _on_battery_data(self, battery_percent):
        """Callback for battery data received."""
        self.battery_data_acquired.emit(battery_percent)
    
    def get_eeg_data(self):
        """Get all collected EEG data."""
        return list(self.eeg_buffer)
    
    def get_audio_data(self):
        """Get all collected audio data."""
        return list(self.audio_buffer)
    
    def get_resist_data(self):
        """Get all collected resistance data."""
        return list(self.resist_buffer)
    
    def get_recording_duration(self) -> float:
        """Get current recording duration."""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time
