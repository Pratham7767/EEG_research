"""
Device management: Scanner, connection, and sensor communication.
"""

import sys
import os
import platform

# Add pyneurosdk2 to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'pyneurosdk2-1.0.15'))

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily, SensorCommand
from typing import Callable, Optional, List
import threading
import time

# For COM port detection (optional)
try:
    from serial.tools.list_ports import comports
except ImportError:
    comports = None

# For serial communication
from .serial_communication import SerialEEGDevice


class DeviceManager:
    """Manages EEG device connection and communication."""
    
    # Supported device types (in order of preference)
    SUPPORTED_DEVICES = [
        SensorFamily.LEHeadPhones2,
        SensorFamily.LEHeadband,
        SensorFamily.LEBrainBit,
        SensorFamily.LEBrainBitBlack,
        SensorFamily.LECallibri,
        SensorFamily.LEKolibri,
        SensorFamily.LEBrainBit2,
        SensorFamily.LEBrainBitPro,
        SensorFamily.LEBrainBitFlex,
        SensorFamily.SensorLEHeadPhones,
    ]
    
    def __init__(self):
        """Initialize device manager."""
        self.scanner = None
        self.sensor = None
        self.connected = False
        self.device_info = None
        self.is_scanning = False
        
        # Callbacks
        self.on_signal_received: Optional[Callable] = None
        self.on_resist_received: Optional[Callable] = None
        self.on_battery_received: Optional[Callable] = None
        self.on_connection_changed: Optional[Callable] = None
    
    def scan_devices(self, scan_duration: float = 10.0) -> List[dict]:
        """
        Scan for available EEG devices.
        
        Args:
            scan_duration: How long to scan in seconds (default 10 seconds)
        
        Returns:
            List of device info dicts
        """
        try:
            if self.is_scanning:
                print("Already scanning, please wait...")
                return []
            
            self.is_scanning = True
            device_list = []
            found_devices = {}
            
            print(f"Scanning for {len(self.SUPPORTED_DEVICES)} device types for {scan_duration}s...")
            
            # Create scanner for all supported devices
            self.scanner = Scanner(self.SUPPORTED_DEVICES)
            
            # Start scanning
            self.scanner.start()
            
            # Scan for specified duration
            start_time = time.time()
            while (time.time() - start_time) < scan_duration:
                sensors = self.scanner.sensors()
                
                for device in sensors:
                    device_key = device.SerialNumber
                    if device_key not in found_devices:
                        found_devices[device_key] = {
                            'name': device.Name,
                            'address': device.Address,
                            'serial': device.SerialNumber,
                            'family': str(device.Family),
                            'info': device
                        }
                        print(f"  Found: {device.Name} (SN: {device.SerialNumber})")
                
                time.sleep(0.5)  # Check every 500ms
            
            # Stop scanning
            self.scanner.stop()
            
            device_list = list(found_devices.values())
            print(f"Scan complete: {len(device_list)} device(s) found\n")
            
            self.is_scanning = False
            return device_list
            
        except Exception as e:
            print(f"Error scanning devices: {e}")
            self.is_scanning = False
            try:
                if self.scanner:
                    self.scanner.stop()
            except:
                pass
            return []
    
    def scan_com_ports(self) -> List[dict]:
        """
        Scan for EEG devices on COM ports (Bluetooth serial devices).
        This is a fallback when USB scanner doesn't find Bluetooth-paired devices.
        
        Returns:
            List of COM port device info dicts
        """
        com_devices = []
        
        try:
            if comports is None:
                print("pyserial not installed - COM port scanning unavailable")
                print("Install with: pip install pyserial --user")
                return []
            
            print("Scanning for COM ports (Bluetooth serial devices)...")
            
            # Get all available COM ports
            ports = list(comports())
            
            if not ports:
                print("  No COM ports found")
                return []
            
            for port in ports:
                # Extract info
                port_name = port.device  # e.g., "COM3"
                description = port.description if hasattr(port, 'description') else "Unknown"
                
                # Look for EEG-related keywords in description
                is_eeg_device = any(keyword in description for keyword in [
                    'Bluetooth', 'COM', 'NeuroSky', 'BrainBit', 'Callibri',
                    'HeadPhones', 'Headband', 'Serial'
                ])
                
                device_info = {
                    'name': f"COM Port: {description}",
                    'address': port_name,
                    'serial': f"COM-{port_name}",
                    'family': 'COM_PORT',
                    'port': port_name,
                    'description': description,
                    'is_eeg_likely': is_eeg_device,
                    'info': None  # No pyneurosdk info for COM ports
                }
                
                com_devices.append(device_info)
                
                symbol = ">" if is_eeg_device else " "
                print(f"  {symbol} {port_name}: {description}")
            
            print(f"Found {len(com_devices)} COM port(s) - {len([d for d in com_devices if d['is_eeg_likely']])} likely EEG\n")
            return com_devices
            
        except Exception as e:
            print(f"Error scanning COM ports: {e}")
            return []
    
    def connect_device(self, device_info) -> bool:
        """
        Connect to selected device.
        
        Args:
            device_info: Device info dict from scan_devices() or scan_com_ports()
            
        Returns:
            True if connected, False otherwise
        """
        try:
            # Handle COM port devices (Bluetooth via serial)
            if device_info.get('family') == 'COM_PORT':
                port = device_info['port']
                print(f"Attempting to connect to COM port device: {port}")
                
                # Create serial device wrapper
                self.sensor = SerialEEGDevice(port)
                
                # Try to connect
                if not self.sensor.connect():
                    print(f"Failed to open serial port {port}")
                    self.sensor = None
                    return False
                
                self.device_info = device_info
                self.connected = True
                if self.on_connection_changed:
                    self.on_connection_changed(True, device_info)
                print(f"Serial device registered and connected on {port}")
                return True
            
            # Handle USB devices via scanner
            if self.scanner is None:
                return False
            
            # Create sensor from device info
            self.sensor = self.scanner.create_sensor(device_info['info'])
            
            if self.sensor is None:
                return False
            
            # Register callbacks
            self.sensor.signalDataReceived = self._on_signal_received
            self.sensor.resistDataReceived = self._on_resist_received
            self.sensor.batteryDataReceived = self._on_battery_received
            self.sensor.infoReceived = self._on_info_received
            
            self.device_info = device_info
            self.connected = True
            
            # Notify connection change
            if self.on_connection_changed:
                self.on_connection_changed(True, device_info)
            
            return True
            
        except Exception as e:
            print(f"Error connecting device: {e}")
            self.connected = False
            if self.on_connection_changed:
                self.on_connection_changed(False, None)
            return False
    
    def disconnect_device(self):
        """Disconnect from device."""
        try:
            if self.sensor:
                self.sensor.signalDataReceived = None
                self.sensor.resistDataReceived = None
                self.sensor.batteryDataReceived = None
                self.sensor.infoReceived = None
                
                # For serial devices, call disconnect explicitly
                if isinstance(self.sensor, SerialEEGDevice):
                    self.sensor.disconnect()
            
            self.sensor = None
            self.connected = False
            
            if self.on_connection_changed:
                self.on_connection_changed(False, None)
                
        except Exception as e:
            print(f"Error disconnecting device: {e}")
    
    def start_signal_acquisition(self) -> bool:
        """Start EEG signal acquisition."""
        if not self.connected or not self.sensor:
            return False
        
        try:
            command = SensorCommand.StartSignal
            self.sensor.exec_command(command)
            return True
        except Exception as e:
            print(f"Error starting signal acquisition: {e}")
            return False
    
    def stop_signal_acquisition(self) -> bool:
        """Stop EEG signal acquisition."""
        if not self.connected or not self.sensor:
            return False
        
        try:
            command = SensorCommand.StopSignal
            self.sensor.exec_command(command)
            return True
        except Exception as e:
            print(f"Error stopping signal acquisition: {e}")
            return False
    
    def start_resist_measurement(self) -> bool:
        """Start electrode resistance measurement."""
        if not self.connected or not self.sensor:
            return False
        
        try:
            command = SensorCommand.StartResist
            self.sensor.exec_command(command)
            return True
        except Exception as e:
            print(f"Error starting resistance measurement: {e}")
            return False
    
    def stop_resist_measurement(self) -> bool:
        """Stop electrode resistance measurement."""
        if not self.connected or not self.sensor:
            return False
        
        try:
            command = SensorCommand.StopResist
            self.sensor.exec_command(command)
            return True
        except Exception as e:
            print(f"Error stopping resistance measurement: {e}")
            return False
    
    def _on_signal_received(self, data):
        """Internal callback for signal data."""
        if self.on_signal_received:
            self.on_signal_received(data)
    
    def _on_resist_received(self, data):
        """Internal callback for resistance data."""
        if self.on_resist_received:
            self.on_resist_received(data)
    
    def _on_battery_received(self, battery_percent):
        """Internal callback for battery data."""
        if self.on_battery_received:
            self.on_battery_received(battery_percent)
    
    def _on_info_received(self, info):
        """Internal callback for device info."""
        pass
    
    def is_connected(self) -> bool:
        """Check if device is connected."""
        return self.connected and self.sensor is not None
