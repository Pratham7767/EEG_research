"""
PyQt5 Main GUI Window for EEG + Voice Recording Application.
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QComboBox, QLineEdit, QCheckBox,
    QGroupBox, QListWidget, QListWidgetItem, QSpinBox, QDoubleSpinBox,
    QTextEdit, QTabWidget, QFrame, QProgressBar, QSlider
)
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QIcon

from core.device_manager import DeviceManager
from core.calibration_manager import CalibrationManager
from core.recording_worker import RecordingWorker
from core.export_manager import ExportManager
import time


class ElectrodeIndicator(QFrame):
    """Visual indicator for electrode contact quality."""
    
    def __init__(self, channel_name: str):
        super().__init__()
        self.channel_name = channel_name
        self.status = "Unknown"
        self.impedance = 0
        self.color = QColor(128, 128, 128)  # Gray
        
        self.setStyleSheet("border: 2px solid black; border-radius: 10px;")
        self.setMaximumSize(80, 80)
        self.setMinimumSize(80, 80)
        
        layout = QVBoxLayout()
        self.label_name = QLabel(channel_name)
        self.label_name.setAlignment(Qt.AlignCenter)
        self.label_status = QLabel("---")
        self.label_status.setAlignment(Qt.AlignCenter)
        self.label_impedance = QLabel("--kΩ")
        self.label_impedance.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(self.label_name)
        layout.addWidget(self.label_status)
        layout.addWidget(self.label_impedance)
        self.setLayout(layout)
    
    def set_quality(self, status: str, impedance: float, color: str):
        """Update electrode quality display."""
        self.status = status
        self.impedance = impedance
        
        # Convert color name to QColor
        color_map = {
            'green': QColor(0, 200, 0),
            'yellow': QColor(255, 200, 0),
            'red': QColor(255, 0, 0)
        }
        self.color = color_map.get(color, QColor(128, 128, 128))
        
        # Update labels
        self.label_status.setText(status)
        self.label_impedance.setText(f"{impedance/1000:.1f}kΩ")
        
        # Update background color
        rgb = self.color.getRgb()
        self.setStyleSheet(f"""
            border: 2px solid black;
            border-radius: 10px;
            background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}, 100);
        """)


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EEG + Voice Recorder")
        self.setGeometry(100, 100, 1200, 800)
        
        # Initialize managers
        self.device_manager = DeviceManager()
        self.calibration_manager = CalibrationManager()
        self.export_manager = ExportManager()
        self.recording_worker = None
        
        # Recording state
        self.is_connected = False
        self.is_calibrated = False
        self.is_recording = False
        self.session_start_time = None
        self.session_dir = None
        
        # Timer for status updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status_display)
        self.update_timer.start(500)  # Update every 500ms
        
        # Create UI
        self._create_ui()
        
        # Set up manager callbacks
        self._setup_callbacks()
    
    def _create_ui(self):
        """Create the main UI layout."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        main_layout = QVBoxLayout()
        
        # Create tabs for different sections
        tabs = QTabWidget()
        
        # Tab 1: Connection & Calibration
        connection_tab = self._create_connection_tab()
        tabs.addTab(connection_tab, "Connection & Calibration")
        
        # Tab 2: Recording
        recording_tab = self._create_recording_tab()
        tabs.addTab(recording_tab, "Recording")
        
        # Tab 3: Settings
        settings_tab = self._create_settings_tab()
        tabs.addTab(settings_tab, "Settings")
        
        # Tab 4: Log
        log_tab = self._create_log_tab()
        tabs.addTab(log_tab, "Log")
        
        main_layout.addWidget(tabs)
        
        # Status bar at bottom
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Status: Disconnected")
        self.battery_label = QLabel("Battery: N/A")
        self.time_label = QLabel("Time: 00:00:00")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.battery_label)
        status_layout.addWidget(self.time_label)
        
        status_frame = QFrame()
        status_frame.setLayout(status_layout)
        main_layout.addWidget(status_frame)
        
        main_widget.setLayout(main_layout)
    
    def _create_connection_tab(self):
        """Create connection and calibration tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Device selection group
        device_group = QGroupBox("Device Connection")
        device_layout = QVBoxLayout()
        
        # Scan options
        scan_options_layout = QHBoxLayout()
        
        scan_options_layout.addWidget(QLabel("Scan Duration:"))
        self.scan_duration_spinbox = QSpinBox()
        self.scan_duration_spinbox.setValue(10)
        self.scan_duration_spinbox.setRange(3, 60)
        self.scan_duration_spinbox.setSuffix(" sec")
        scan_options_layout.addWidget(self.scan_duration_spinbox)
        
        button_scan = QPushButton("Scan for Devices")
        button_scan.clicked.connect(self._scan_devices)
        button_scan.setStyleSheet("background-color: #2196F3; color: white;")
        scan_options_layout.addWidget(button_scan)
        
        button_scan_com = QPushButton("Scan COM Ports")
        button_scan_com.clicked.connect(self._scan_com_ports)
        button_scan_com.setStyleSheet("background-color: #FF9800; color: white;")
        button_scan_com.setToolTip("Alternative scan for Bluetooth devices on COM ports\n(use if normal scan fails)")
        scan_options_layout.addWidget(button_scan_com)
        
        scan_options_layout.addStretch()
        device_layout.addLayout(scan_options_layout)
        
        # Device info
        info_label = QLabel(
            "Supported devices: LEHeadphones2, LEHeadband, LEBrainBit, LEBrainBitBlack, \n"
            "LECallibri, LEKolibri, LEBrainBit2, LEBrainBitPro, LEBrainBitFlex\n\n"
            "If device is not found: Try 'Scan COM Ports' (for Bluetooth over serial)"
        )
        info_label.setStyleSheet("color: #666; font-size: 9pt;")
        device_layout.addWidget(info_label)
        
        device_layout.addWidget(QLabel("Available Devices:"))
        self.device_list = QListWidget()
        self.device_list.setMaximumHeight(150)
        device_layout.addWidget(self.device_list)
        
        button_connect = QPushButton("Connect Selected Device")
        button_connect.setStyleSheet("background-color: #4CAF50; color: white;")
        button_connect.clicked.connect(self._connect_device)
        device_layout.addWidget(button_connect)
        
        button_disconnect = QPushButton("Disconnect")
        button_disconnect.setStyleSheet("background-color: #f44336; color: white;")
        button_disconnect.clicked.connect(self._disconnect_device)
        device_layout.addWidget(button_disconnect)
        
        device_group.setLayout(device_layout)
        layout.addWidget(device_group)
        
        # Calibration group
        calibration_group = QGroupBox("Electrode Calibration")
        calibration_layout = QVBoxLayout()
        
        calibration_info = QLabel(
            "Calibration measures electrode impedance (contact quality).\n"
            "All electrodes must be Good or Acceptable to start recording."
        )
        calibration_info.setStyleSheet("color: #666;")
        calibration_layout.addWidget(calibration_info)
        
        button_calibrate = QPushButton("Start Calibration")
        button_calibrate.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        button_calibrate.clicked.connect(self._start_calibration)
        calibration_layout.addWidget(button_calibrate)
        
        self.calibration_progress = QProgressBar()
        self.calibration_progress.setValue(0)
        self.calibration_progress.setVisible(False)
        calibration_layout.addWidget(self.calibration_progress)
        
        self.calibration_status = QLabel("Not calibrated")
        calibration_layout.addWidget(self.calibration_status)
        
        # Electrode indicators
        electrodes_layout = QGridLayout()
        self.electrode_indicators = {}
        for i in range(4):
            indicator = ElectrodeIndicator(f"Ch{i+1}")
            self.electrode_indicators[f"Ch{i+1}"] = indicator
            electrodes_layout.addWidget(indicator, 0, i)
        
        calibration_layout.addLayout(electrodes_layout)
        
        calibration_group.setLayout(calibration_layout)
        layout.addWidget(calibration_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_recording_tab(self):
        """Create recording control tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Session info
        session_group = QGroupBox("Session Information")
        session_layout = QGridLayout()
        
        session_layout.addWidget(QLabel("Session Name:"), 0, 0)
        self.session_name_input = QLineEdit()
        self.session_name_input.setPlaceholderText("Auto-generated if blank")
        session_layout.addWidget(self.session_name_input, 0, 1)
        
        session_layout.addWidget(QLabel("Device:"), 1, 0)
        self.session_device_label = QLabel("Not connected")
        session_layout.addWidget(self.session_device_label, 1, 1)
        
        session_group.setLayout(session_layout)
        layout.addWidget(session_group)
        
        # Recording controls
        control_group = QGroupBox("Recording Controls")
        control_layout = QVBoxLayout()
        
        # Start/Stop buttons
        button_layout = QHBoxLayout()
        
        self.button_start_recording = QPushButton("Start Recording")
        self.button_start_recording.setStyleSheet(
            "background-color: #2196F3; color: white; font-weight: bold; padding: 10px;"
        )
        self.button_start_recording.setEnabled(False)
        self.button_start_recording.clicked.connect(self._start_recording)
        button_layout.addWidget(self.button_start_recording)
        
        self.button_stop_recording = QPushButton("Stop Recording")
        self.button_stop_recording.setStyleSheet(
            "background-color: #f44336; color: white; font-weight: bold; padding: 10px;"
        )
        self.button_stop_recording.setEnabled(False)
        self.button_stop_recording.clicked.connect(self._stop_recording)
        button_layout.addWidget(self.button_stop_recording)
        
        control_layout.addLayout(button_layout)
        
        # Recording stats
        stats_layout = QGridLayout()
        
        stats_layout.addWidget(QLabel("Recording Time:"), 0, 0)
        self.recording_time_label = QLabel("00:00:00")
        self.recording_time_label.setFont(QFont("Courier", 12, QFont.Bold))
        stats_layout.addWidget(self.recording_time_label, 0, 1)
        
        stats_layout.addWidget(QLabel("EEG Samples:"), 1, 0)
        self.eeg_samples_label = QLabel("0")
        stats_layout.addWidget(self.eeg_samples_label, 1, 1)
        
        stats_layout.addWidget(QLabel("Audio Samples:"), 1, 2)
        self.audio_samples_label = QLabel("0")
        stats_layout.addWidget(self.audio_samples_label, 1, 3)
        
        control_layout.addLayout(stats_layout)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_settings_tab(self):
        """Create settings tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        settings_group = QGroupBox("Recording Settings")
        settings_layout = QGridLayout()
        
        settings_layout.addWidget(QLabel("EEG Sampling Rate:"), 0, 0)
        self.eeg_fs_spinbox = QSpinBox()
        self.eeg_fs_spinbox.setValue(250)
        self.eeg_fs_spinbox.setRange(100, 1000)
        self.eeg_fs_spinbox.setSuffix(" Hz")
        self.eeg_fs_spinbox.setEnabled(False)
        settings_layout.addWidget(self.eeg_fs_spinbox, 0, 1)
        
        settings_layout.addWidget(QLabel("Audio Sampling Rate:"), 1, 0)
        self.audio_fs_spinbox = QSpinBox()
        self.audio_fs_spinbox.setValue(16000)
        self.audio_fs_spinbox.setRange(8000, 48000)
        self.audio_fs_spinbox.setSuffix(" Hz")
        settings_layout.addWidget(self.audio_fs_spinbox, 1, 1)
        
        settings_layout.addWidget(QLabel("Gain:"), 2, 0)
        self.gain_combo = QComboBox()
        self.gain_combo.addItems([f"{1 << i}x" for i in range(5)])  # 1x, 2x, 4x, 8x, 16x
        settings_layout.addWidget(self.gain_combo, 2, 1)
        
        settings_layout.addWidget(QLabel("Apply Bandpass Filter (4-30Hz):"), 3, 0)
        self.filter_checkbox = QCheckBox("Enabled")
        self.filter_checkbox.setChecked(True)
        settings_layout.addWidget(self.filter_checkbox, 3, 1)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Export settings
        export_group = QGroupBox("Export Formats")
        export_layout = QVBoxLayout()
        
        self.export_csv_checkbox = QCheckBox("CSV (separate files)")
        self.export_csv_checkbox.setChecked(True)
        export_layout.addWidget(self.export_csv_checkbox)
        
        self.export_hdf5_checkbox = QCheckBox("HDF5 (for long recordings)")
        self.export_hdf5_checkbox.setChecked(True)
        export_layout.addWidget(self.export_hdf5_checkbox)
        
        self.export_wav_checkbox = QCheckBox("WAV (audio file)")
        self.export_wav_checkbox.setChecked(True)
        export_layout.addWidget(self.export_wav_checkbox)
        
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _create_log_tab(self):
        """Create logging/debug tab."""
        widget = QWidget()
        layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        layout.addWidget(self.log_text)
        
        button_clear = QPushButton("Clear Log")
        button_clear.clicked.connect(lambda: self.log_text.clear())
        layout.addWidget(button_clear)
        
        widget.setLayout(layout)
        return widget
    
    def _setup_callbacks(self):
        """Set up manager callbacks."""
        self.device_manager.on_connection_changed = self._on_device_connection_changed
        self.calibration_manager.on_calibration_progress = self._on_calibration_progress
        self.calibration_manager.on_calibration_complete = self._on_calibration_complete
    
    def _scan_devices(self):
        """Scan for available devices."""
        scan_duration = self.scan_duration_spinbox.value()
        self._log(f"Scanning for devices ({scan_duration} seconds)...")
        self._log("Scanning for: LEHeadphones2, LEHeadband, LEBrainBit, LEBrainBitBlack,")
        self._log("             LECallibri, LEKolibri, LEBrainBit2, LEBrainBitPro, LEBrainBitFlex")
        
        devices = self.device_manager.scan_devices(scan_duration=float(scan_duration))
        
        self.device_list.clear()
        
        if not devices:
            self._log("✗ No devices found during scan")
            self._log("  - Ensure device is powered ON")
            self._log("  - Check if device is already paired via Bluetooth")
            self._log("  - Try increasing scan duration (top of Connection tab)")
            self._log("  - Try scanning again")
            return
        
        for device in devices:
            device_name = f"{device['name']} ({device['family']}) - SN: {device['serial']}"
            item = QListWidgetItem(device_name)
            item.setData(Qt.UserRole, device)
            self.device_list.addItem(item)
            self._log(f"  ✓ Found: {device_name}")
        
        self._log(f"✓ Scan complete: {len(devices)} device(s) found")
    
    def _scan_com_ports(self):
        """Scan for EEG devices on COM ports (Bluetooth serial fallback)."""
        self._log("Scanning COM ports (Bluetooth serial devices)...")
        self._log("This is an alternative scan if regular device scan fails")
        
        devices = self.device_manager.scan_com_ports()
        
        self.device_list.clear()
        
        if not devices:
            self._log("✗ No COM ports found")
            self._log("  - Device Bluetooth driver may not be installed")
            self._log("  - Try installing/reinstalling: USB-BT500 Realtek driver")
            self._log("  - Check Windows Device Manager for device with errors")
            return
        
        # Show all ports, but highlight likely EEG devices
        eeg_count = 0
        for device in devices:
            if device['is_eeg_likely']:
                device_name = f"[EEG] {device['name']} ({device['port']})"
                eeg_count += 1
            else:
                device_name = f"{device['name']} ({device['port']})"
            
            item = QListWidgetItem(device_name)
            item.setData(Qt.UserRole, device)
            self.device_list.addItem(item)
            
            marker = "✓" if device['is_eeg_likely'] else " "
            self._log(f"  {marker} Found: {device['name']}")
        
        self._log(f"✓ COM port scan complete: {len(devices)} port(s) found, {eeg_count} likely EEG device(s)")
    
    def _connect_device(self):
        """Connect to selected device."""
        current_item = self.device_list.currentItem()
        if not current_item:
            self._log("Please select a device")
            return
        
        device_info = current_item.data(Qt.UserRole)
        self._log(f"Connecting to {device_info['name']}...")
        
        if self.device_manager.connect_device(device_info):
            self._log("Device connected successfully")
        else:
            self._log("Failed to connect device")
    
    def _disconnect_device(self):
        """Disconnect from device."""
        self._log("Disconnecting device...")
        self.device_manager.disconnect_device()
        self._log("Device disconnected")
    
    def _on_device_connection_changed(self, connected, device_info):
        """Handle device connection state change."""
        self.is_connected = connected
        
        if connected:
            self._log(f"✓ Connected to: {device_info['name']}")
            self.status_label.setText("Status: Connected")
            self.session_device_label.setText(device_info['name'])
        else:
            self._log("✗ Disconnected")
            self.status_label.setText("Status: Disconnected")
            self.session_device_label.setText("Not connected")
            self.is_calibrated = False
            self.button_start_recording.setEnabled(False)
    
    def _start_calibration(self):
        """Start electrode calibration."""
        if not self.is_connected:
            self._log("Error: Device not connected")
            return
        
        self._log("Starting calibration...")
        self.calibration_progress.setVisible(True)
        self.calibration_progress.setValue(0)
        
        # Start resistance measurement
        if not self.device_manager.start_resist_measurement():
            self._log("Error: Failed to start resistance measurement")
            return
        
        # Start calibration
        self.calibration_manager.start_calibration()
        
        # Set up resistance callback during calibration
        self.device_manager.on_resist_received = self.calibration_manager.add_resistance_data
    
    def _on_calibration_progress(self, progress, message):
        """Handle calibration progress update."""
        self.calibration_progress.setValue(progress)
        self._log(f"Calibration: {message}")
    
    def _on_calibration_complete(self, results):
        """Handle calibration completion."""
        self._log("Calibration complete!")
        self._log(f"Overall status: {results['status']}")
        
        # Update electrode indicators
        for channel, data in results['channels'].items():
            indicator = self.electrode_indicators[channel]
            indicator.set_quality(
                data['quality'],
                data['mean_impedance'],
                data['color']
            )
            self._log(f"{channel}: {data['quality']} - {data['mean_impedance']/1000:.2f}kΩ")
        
        self.calibration_progress.setVisible(False)
        self.calibration_status.setText(f"Status: {results['overall_quality']}")
        
        # Enable recording if ready
        if self.calibration_manager.is_ready_to_record():
            self.is_calibrated = True
            self.button_start_recording.setEnabled(True)
            self._log("✓ Ready to record!")
        else:
            self._log("✗ Electrodes need adjustment - check contact quality")
        
        # Stop resistance measurement
        self.device_manager.stop_resist_measurement()
        self.device_manager.on_resist_received = None
    
    def _start_recording(self):
        """Start recording session."""
        if not self.is_connected or not self.is_calibrated:
            self._log("Error: Device not connected or not calibrated")
            return
        
        # Create session directory
        session_name = self.session_name_input.text().strip()
        if not session_name:
            session_name = None
        
        self.session_dir = self.export_manager.create_session_directory(session_name)
        self.session_start_time = time.time()
        
        self._log(f"Starting recording to {self.session_dir}")
        
        # Create and start recording worker
        self.recording_worker = RecordingWorker(
            self.device_manager,
            self.eeg_fs_spinbox.value(),
            self.audio_fs_spinbox.value()
        )
        
        # Connect worker signals
        self.recording_worker.recording_status.connect(self._log)
        self.recording_worker.eeg_data_acquired.connect(self._on_eeg_data)
        self.recording_worker.error_occurred.connect(self._on_recording_error)
        self.recording_worker.recording_stopped.connect(self._on_recording_stopped)
        
        # Update UI
        self.is_recording = True
        self.button_start_recording.setEnabled(False)
        self.button_stop_recording.setEnabled(True)
        
        # Start worker thread
        self.recording_worker.start_recording()
    
    def _stop_recording(self):
        """Stop recording session."""
        if self.recording_worker:
            self._log("Stopping recording...")
            self.recording_worker.stop_recording()
            self.is_recording = False
            self.button_start_recording.setEnabled(True)
            self.button_stop_recording.setEnabled(False)
    
    def _on_eeg_data(self, data):
        """Handle EEG data received during recording."""
        self.eeg_samples_label.setText(str(data['count']))
    
    def _on_recording_error(self, error_msg):
        """Handle recording error."""
        self._log(f"❌ Error: {error_msg}")
        self.is_recording = False
        self.button_start_recording.setEnabled(True)
        self.button_stop_recording.setEnabled(False)
    
    def _on_recording_stopped(self, stats):
        """Handle recording stopped."""
        self._log("Recording stopped")
        self._log(f"Duration: {stats['elapsed_time']:.1f}s")
        self._log(f"EEG samples: {stats['eeg_samples']}")
        self._log(f"Audio samples: {stats['audio_samples']}")
        self._log(f"Resistance samples: {stats['resist_samples']}")
        
        # Export data
        self._export_recorded_data()
    
    def _export_recorded_data(self):
        """Export recorded data to files."""
        if not self.recording_worker or not self.session_dir:
            return
        
        self._log("Exporting recorded data...")
        
        try:
            # Gather export formats
            export_formats = []
            if self.export_csv_checkbox.isChecked():
                export_formats.append('csv')
            if self.export_hdf5_checkbox.isChecked():
                export_formats.append('hdf5')
            if self.export_wav_checkbox.isChecked():
                export_formats.append('wav')
            
            # Prepare recording data
            recording_data = {
                'eeg': self.recording_worker.get_eeg_data(),
                'audio': self.recording_worker.get_audio_data(),
                'resist': self.recording_worker.get_resist_data()
            }
            
            # Prepare metadata
            metadata = {
                'device': self.device_manager.device_info['name'] if self.device_manager.device_info else 'Unknown',
                'calibration_results': self.calibration_manager.get_calibration_results(),
                'start_time': self.session_start_time,
                'export_time': time.time()
            }
            
            # Export
            self.export_manager.export_session(
                self.session_dir,
                recording_data,
                metadata,
                self.eeg_fs_spinbox.value(),
                self.audio_fs_spinbox.value(),
                export_formats
            )
            
            self._log(f"✓ Data exported to {self.session_dir}")
            
        except Exception as e:
            self._log(f"❌ Export error: {e}")
    
    def _update_status_display(self):
        """Update status display regularly."""
        if self.is_recording and self.recording_worker:
            elapsed = self.recording_worker.get_recording_duration()
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            self.recording_time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    
    def _log(self, message: str):
        """Add message to log."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        # Auto-scroll to bottom
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def closeEvent(self, event):
        """handle window close."""
        if self.is_recording:
            self._log("Stopping recording before exit...")
            self._stop_recording()
        
        self.update_timer.stop()
        self.device_manager.disconnect_device()
        super().closeEvent(event)
