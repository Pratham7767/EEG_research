"""
Calibration management: Electrode impedance measurement and quality assessment.
"""

import numpy as np
from typing import Callable, Optional, Dict, List
import time
from collections import deque


class CalibrationManager:
    """Manages electrode calibration and impedance quality checking."""
    
    IMPEDANCE_THRESHOLDS = {
        'good': 5000,      # < 5 kΩ
        'acceptable': 20000  # < 20 kΩ
    }
    
    def __init__(self, calibration_duration=3.0):
        """
        Initialize calibration manager.
        
        Args:
            calibration_duration: How long to collect resistance data (seconds)
        """
        self.calibration_duration = calibration_duration
        self.is_calibrating = False
        self.calibration_start_time = None
        
        # Store resistance readings
        self.resist_buffer = deque(maxlen=1000)  # Store up to 1000 samples
        self.baseline_impedance = None
        self.calibration_results = None
        
        # Callbacks
        self.on_calibration_progress: Optional[Callable] = None
        self.on_calibration_complete: Optional[Callable] = None
    
    def start_calibration(self):
        """Begin electrode calibration process."""
        self.is_calibrating = True
        self.calibration_start_time = time.time()
        self.resist_buffer.clear()
        self.calibration_results = None
        
        if self.on_calibration_progress:
            self.on_calibration_progress(0, "Starting calibration...")
    
    def stop_calibration(self):
        """End calibration and analyze results."""
        self.is_calibrating = False
        
        if len(self.resist_buffer) == 0:
            if self.on_calibration_progress:
                self.on_calibration_progress(100, "No resistance data collected")
            return
        
        # Calculate statistics from buffer
        self._analyze_calibration_data()
        
        if self.on_calibration_complete:
            self.on_calibration_complete(self.calibration_results)
    
    def add_resistance_data(self, resist_data):
        """
        Add resistance measurement to calibration buffer.
        
        Args:
            resist_data: Resistance data from device (should have 4 channels)
        """
        if not self.is_calibrating:
            return
        
        try:
            # Extract impedance values from resistance data
            # Format depends on device, but typically has attributes for each channel
            if hasattr(resist_data, 'Ch1') and hasattr(resist_data, 'Ch2'):
                impedances = [
                    resist_data.Ch1,
                    resist_data.Ch2,
                    resist_data.Ch3,
                    resist_data.Ch4
                ]
            elif isinstance(resist_data, (list, tuple)):
                impedances = list(resist_data[:4])
            elif isinstance(resist_data, np.ndarray):
                impedances = resist_data[:4].tolist()
            else:
                return
            
            # Store average of this sample
            avg_impedance = np.mean(impedances)
            self.resist_buffer.append({
                'timestamp': time.time(),
                'impedances': impedances,
                'average': avg_impedance
            })
            
            # Check if calibration time is complete
            elapsed = time.time() - self.calibration_start_time
            progress = min(100, int((elapsed / self.calibration_duration) * 100))
            
            if self.on_calibration_progress:
                self.on_calibration_progress(
                    progress,
                    f"Calibrating... {elapsed:.1f}s / {self.calibration_duration}s"
                )
            
            # Auto-stop when duration reached
            if elapsed >= self.calibration_duration:
                self.stop_calibration()
                
        except Exception as e:
            print(f"Error adding resistance data: {e}")
    
    def _analyze_calibration_data(self):
        """Analyze collected calibration data."""
        if len(self.resist_buffer) == 0:
            self.calibration_results = {
                'status': 'No data',
                'channels': {}
            }
            return
        
        # Extract all impedance readings
        all_impedances = []
        for sample in self.resist_buffer:
            all_impedances.append(sample['impedances'])
        
        all_impedances = np.array(all_impedances)
        
        # Calculate statistics per channel
        channel_stats = {}
        for ch in range(4):
            ch_data = all_impedances[:, ch]
            quality = self._assess_electrode_quality(ch_data)
            
            channel_stats[f'Ch{ch+1}'] = {
                'mean_impedance': float(np.mean(ch_data)),
                'std_impedance': float(np.std(ch_data)),
                'min_impedance': float(np.min(ch_data)),
                'max_impedance': float(np.max(ch_data)),
                'quality': quality['status'],
                'color': quality['color']
            }
        
        # Overall status: all channels must be acceptable or better
        all_good = all(
            channel_stats[f'Ch{ch+1}']['quality'] != 'Bad'
            for ch in range(4)
        )
        
        self.calibration_results = {
            'status': 'Ready' if all_good else 'Warning',
            'timestamp': time.time(),
            'samples_collected': len(self.resist_buffer),
            'channels': channel_stats,
            'overall_quality': 'Good' if all_good else 'Check electrodes'
        }
        
        self.baseline_impedance = channel_stats
    
    def _assess_electrode_quality(self, impedance_values):
        """
        Assess electrode contact quality.
        
        Args:
            impedance_values: Array of impedance measurements
            
        Returns:
            Dict with status and color
        """
        median_impedance = np.median(impedance_values)
        
        if median_impedance <= self.IMPEDANCE_THRESHOLDS['good']:
            return {'status': 'Good', 'color': 'green'}
        elif median_impedance <= self.IMPEDANCE_THRESHOLDS['acceptable']:
            return {'status': 'Acceptable', 'color': 'yellow'}
        else:
            return {'status': 'Bad', 'color': 'red'}
    
    def get_calibration_results(self) -> Optional[Dict]:
        """Get calibration results."""
        return self.calibration_results
    
    def is_ready_to_record(self) -> bool:
        """Check if all electrodes are ready for recording."""
        if not self.calibration_results:
            return False
        
        # All channels must not be 'Bad'
        for ch, data in self.calibration_results['channels'].items():
            if data['quality'] == 'Bad':
                return False
        
        return True
    
    def reset_calibration(self):
        """Reset calibration data."""
        self.is_calibrating = False
        self.calibration_start_time = None
        self.resist_buffer.clear()
        self.baseline_impedance = None
        self.calibration_results = None
