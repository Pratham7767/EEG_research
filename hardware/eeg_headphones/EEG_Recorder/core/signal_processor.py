"""
Signal processing utilities for EEG data.
Handles filtering, resampling, and timestamp synchronization.
"""

import numpy as np
from scipy import signal
from collections import deque
import time


class SignalProcessor:
    """Processes EEG and audio signals."""
    
    def __init__(self, eeg_sampling_rate=250, audio_sampling_rate=16000):
        """
        Initialize signal processor.
        
        Args:
            eeg_sampling_rate: EEG sampling rate in Hz (default 250)
            audio_sampling_rate: Audio sampling rate in Hz (default 16000)
        """
        self.eeg_fs = eeg_sampling_rate
        self.audio_fs = audio_sampling_rate
        self.filter_order = 4
        self.lowcut = 4.0  # Hz
        self.highcut = 30.0  # Hz
        
        # Design Butterworth bandpass filter for EEG
        self.sos = signal.butter(
            self.filter_order,
            [self.lowcut, self.highcut],
            btype='band',
            fs=self.eeg_fs,
            output='sos'
        )
        
        # Initialize filter state for each channel
        self.filter_states = [signal.sosfilt_zi(self.sos) for _ in range(4)]
    
    def apply_bandpass_filter(self, channel_idx, data):
        """
        Apply Butterworth bandpass filter (4-30Hz, 4th order) to EEG data.
        
        Args:
            channel_idx: Channel index (0-3)
            data: EEG data sample(s)
            
        Returns:
            Filtered data
        """
        if channel_idx >= len(self.filter_states):
            return data
        
        # Apply filter with state preservation for continuous filtering
        filtered, self.filter_states[channel_idx] = signal.sosfilt(
            self.sos,
            data if isinstance(data, np.ndarray) else np.array([data]),
            zi=self.filter_states[channel_idx] * data if isinstance(data, (int, float)) else self.filter_states[channel_idx]
        )
        
        return filtered
    
    def resample_audio_to_eeg_rate(self, audio_data, num_eeg_samples):
        """
        Resample audio to EEG sampling rate for interleaving.
        
        Args:
            audio_data: Audio samples array
            num_eeg_samples: Number of EEG samples to match
            
        Returns:
            Resampled audio data
        """
        if len(audio_data) == 0:
            return np.zeros(num_eeg_samples)
        
        # Calculate resampling ratio
        num_audio_samples = len(audio_data)
        indices = np.linspace(0, num_audio_samples - 1, num_eeg_samples)
        
        # Linear interpolation
        resampled = np.interp(indices, np.arange(num_audio_samples), audio_data)
        return resampled
    
    def synchronize_timestamps(self, eeg_timestamps, audio_timestamps, start_time):
        """
        Synchronize EEG and audio timestamps to a common reference.
        
        Args:
            eeg_timestamps: List of EEG timestamps (or PackNum)
            audio_timestamps: List of audio timestamps (sample indices)
            start_time: Session start time (time.time())
            
        Returns:
            Tuple of (eeg_timestamps_abs, audio_timestamps_abs)
        """
        # Convert EEG PackNum to seconds (assuming 250Hz)
        eeg_times = np.array(eeg_timestamps) / self.eeg_fs + start_time
        
        # Convert audio sample indices to seconds
        audio_times = np.array(audio_timestamps) / self.audio_fs + start_time
        
        return eeg_times, audio_times
    
    def calculate_impedance_quality(self, impedance_values, thresholds=None):
        """
        Calculate electrode contact quality based on impedance.
        
        Args:
            impedance_values: List/array of impedance values in Ohms
            thresholds: Dict with 'good', 'acceptable' keys (in Ohms)
            
        Returns:
            Dict with quality status for each electrode
        """
        if thresholds is None:
            thresholds = {
                'good': 5000,  # 5 kΩ
                'acceptable': 20000  # 20 kΩ
            }
        
        quality_map = {}
        for i, impedance in enumerate(impedance_values):
            if impedance <= thresholds['good']:
                quality_map[f'Ch{i+1}'] = {
                    'status': 'Good',
                    'impedance': impedance,
                    'color': 'green'
                }
            elif impedance <= thresholds['acceptable']:
                quality_map[f'Ch{i+1}'] = {
                    'status': 'Acceptable',
                    'impedance': impedance,
                    'color': 'yellow'
                }
            else:
                quality_map[f'Ch{i+1}'] = {
                    'status': 'Bad',
                    'impedance': impedance,
                    'color': 'red'
                }
        
        return quality_map
