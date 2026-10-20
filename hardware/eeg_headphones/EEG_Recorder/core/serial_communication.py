"""
Serial communication for NeuroSky ThinkGear protocol via COM port.
Handles reading EEG, resistance, and battery data from Bluetooth serial devices.
"""

import serial
import struct
import threading
import time
from typing import Callable, Optional, List
from collections import deque


class ThinkGearProtocol:
    """NeuroSky ThinkGear protocol parser for serial communication."""
    
    # Protocol constants
    SYNC_BYTE = 0xAA  # Packet sync byte
    EXCODE_THINKGEAR = 0x80  # Extended code for ThinkGear packets
    
    # Data codes
    CODE_POOR_SIGNAL = 0x02
    CODE_ATTENTION = 0x04
    CODE_MEDITATION = 0x05
    CODE_BLINK = 0x09
    CODE_8BIT_RAW = 0x80
    CODE_16BIT_RAW = 0x81
    CODE_RAW_MARKER = 0x03
    CODE_ASIC_EEG_POWER = 0x83
    CODE_ELECTRODE_CONTACT = 0x0F  # Impedance data
    CODE_BATTERY = 0x01
    
    def __init__(self, port: str, baudrate: int = 57600):
        """Initialize ThinkGear serial communication.
        
        Args:
            port: COM port name (e.g., 'COM3')
            baudrate: Serial port baudrate (default 57600 for NeuroSky)
        """
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.is_running = False
        self.read_thread = None
        
        # Callbacks
        self.on_raw_eeg = None
        self.on_signal_quality = None
        self.on_attention = None
        self.on_meditation = None
        self.on_electrode_contact = None
        self.on_battery = None
        
        # Data buffers
        self.rx_buffer = bytearray()
        self.packet_count = 0
        
    def connect(self) -> bool:
        """Open serial port and start reading thread."""
        try:
            print(f"Attempting to open {self.port} at {self.baudrate} baud...")
            
            # For Bluetooth devices, we may need to try different approaches
            for attempt in range(3):
                try:
                    # Try exclusive, non-blocking approach for Bluetooth
                    self.ser = serial.Serial(
                        port=self.port,
                        baudrate=self.baudrate,
                        bytesize=serial.EIGHTBITS,
                        stopbits=serial.STOPBITS_ONE,
                        parity=serial.PARITY_NONE,
                        timeout=2.0,
                        xonxoff=False,
                        rtscts=False,
                        dsrdtr=False,
                        inter_byte_timeout=0.1
                    )
                    print(f"Opened serial port {self.port} at {self.baudrate} baud (attempt {attempt+1})")
                    time.sleep(1.0)  # Give device time to respond
                    
                    # Start read thread
                    self.is_running = True
                    self.read_thread = threading.Thread(target=self._read_thread_worker, daemon=True)
                    self.read_thread.start()
                    
                    return True
                    
                except (OSError, serial.SerialException) as e:
                    print(f"  Attempt {attempt+1} failed: {e}")
                    if self.ser:
                        try:
                            self.ser.close()
                        except:
                            pass
                    if attempt < 2:
                        time.sleep(0.5)  # Wait before retry
            
            print(f"Failed to open {self.port} after 3 attempts")
            return False
            
        except Exception as e:
            print(f"Error opening serial port {self.port}: {e}")
            return False
    
    def disconnect(self):
        """Close serial port and stop reading thread."""
        self.is_running = False
        if self.read_thread:
            self.read_thread.join(timeout=2.0)
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"Closed serial port {self.port}")
    
    def _read_thread_worker(self):
        """Background thread for reading and parsing serial data."""
        while self.is_running:
            try:
                if self.ser.in_waiting > 0:
                    # Read available data
                    data = self.ser.read(self.ser.in_waiting)
                    self.rx_buffer.extend(data)
                    
                    # Process packets in buffer
                    self._process_buffer()
                else:
                    time.sleep(0.001)  # Avoid busy-waiting
                    
            except Exception as e:
                print(f"Error in serial read thread: {e}")
                time.sleep(0.1)
    
    def _process_buffer(self):
        """Parse ThinkGear packets from receive buffer."""
        while len(self.rx_buffer) >= 4:  # Minimum packet: SYNC + SYNC + PAYLOAD_LEN + 1 byte data
            # Look for sync bytes
            if self.rx_buffer[0] != self.SYNC_BYTE or self.rx_buffer[1] != self.SYNC_BYTE:
                # Resync: skip one byte
                del self.rx_buffer[0]
                continue
            
            # Get payload length
            payload_len = self.rx_buffer[2]
            
            # Check if we have complete packet
            total_len = 3 + payload_len + 1  # SYNC SYNC LEN + PAYLOAD + CHECKSUM
            if len(self.rx_buffer) < total_len:
                break  # Wait for more data
            
            # Extract packet
            packet = self.rx_buffer[:total_len]
            del self.rx_buffer[:total_len]
            
            # Verify checksum
            checksum = packet[-1]
            payload = packet[3:3 + payload_len]
            
            calculated_checksum = self._calculate_checksum(payload)
            if checksum != calculated_checksum:
                print(f"Checksum mismatch: {checksum:02x} != {calculated_checksum:02x}")
                continue
            
            # Parse payload
            self._parse_payload(payload)
    
    def _calculate_checksum(self, payload: bytes) -> int:
        """Calculate ThinkGear checksum (one's complement of sum)."""
        total = sum(payload) & 0xFF
        checksum = (~total) & 0xFF
        return checksum
    
    def _parse_payload(self, payload: bytes):
        """Parse ThinkGear data codes from payload."""
        i = 0
        while i < len(payload):
            code = payload[i]
            i += 1
            
            # Handle extended code
            if code == self.EXCODE_THINKGEAR:
                if i < len(payload):
                    code = payload[i] | 0x100  # Mark as extended
                    i += 1
            
            # Parse value length
            if i >= len(payload):
                break
            
            value_len = payload[i]
            i += 1
            
            # Extract value
            if i + value_len > len(payload):
                break
            
            value_data = payload[i:i + value_len]
            i += value_len
            
            # Process data code
            self._process_data_code(code, value_data)
    
    def _process_data_code(self, code: int, value_data: bytes):
        """Process individual ThinkGear data codes."""
        try:
            if code == self.CODE_POOR_SIGNAL:
                # Signal quality (0-255, 0=good)
                signal_quality = value_data[0]
                if self.on_signal_quality:
                    self.on_signal_quality(signal_quality)
            
            elif code == self.CODE_ATTENTION:
                # eSense Attention (0-100)
                attention = value_data[0]
                if self.on_attention:
                    self.on_attention(attention)
            
            elif code == self.CODE_MEDITATION:
                # eSense Meditation (0-100)
                meditation = value_data[0]
                if self.on_meditation:
                    self.on_meditation(meditation)
            
            elif code == 0x180:  # Extended code for raw EEG data
                # Raw EEG (3 bytes, big-endian, 2's complement)
                if len(value_data) >= 2:
                    raw_value = struct.unpack('>H', value_data[:2])[0]
                    
                    # Convert from unsigned to signed (assuming 16-bit)
                    if raw_value > 32767:
                        raw_value -= 65536
                    
                    if self.on_raw_eeg:
                        self.on_raw_eeg(raw_value)
                    
                    self.packet_count += 1
            
            elif code == self.CODE_ELECTRODE_CONTACT:
                # Electrode impedance contact quality (0-255 per electrode)
                # NeuroSky typically sends 2 bytes: contact quality on two sides
                if len(value_data) >= 2:
                    contact_left = value_data[0]
                    contact_right = value_data[1]
                    if self.on_electrode_contact:
                        self.on_electrode_contact([contact_left, contact_right, 0, 0])
            
            elif code == self.CODE_BATTERY:
                # Battery percentage (0-100)
                if len(value_data) >= 1:
                    battery_pct = value_data[0]
                    if self.on_battery:
                        self.on_battery(battery_pct)
        
        except Exception as e:
            print(f"Error processing data code {code:02x}: {e}")
    
    def write_command(self, command: bytes) -> bool:
        """Send command to device."""
        try:
            if self.ser and self.ser.is_open:
                self.ser.write(command)
                return True
        except Exception as e:
            print(f"Error writing command: {e}")
        return False


class SerialEEGDevice:
    """Wrapper for NeuroSky EEG device via serial port."""
    
    def __init__(self, port: str):
        """Initialize serial EEG device."""
        self.port = port
        self.protocol = ThinkGearProtocol(port)
        
        # Data buffers (similar to pyneurosdk2 device)
        self.signal_data_buffer = deque(maxlen=1000)
        self.resist_data_buffer = deque(maxlen=100)
        self.battery_buffer = deque(maxlen=10)
        
        # Device info
        self.connected = False
        self.device_name = f"NeuroSky COM Port ({port})"
        self.battery_level = 0
        self.signal_quality = 0
        
        # Setup callbacks
        self.protocol.on_raw_eeg = self._on_raw_eeg
        self.protocol.on_electrode_contact = self._on_electrode_contact
        self.protocol.on_battery = self._on_battery
        self.protocol.on_signal_quality = self._on_signal_quality
        
        # External callbacks (like pyneurosdk2 device)
        self.signalDataReceived = None
        self.resistDataReceived = None
        self.batteryDataReceived = None
        self.infoReceived = None
    
    def connect(self) -> bool:
        """Connect to device."""
        if self.protocol.connect():
            self.connected = True
            print(f"Connected to serial device on {self.port}")
            return True
        return False
    
    def disconnect(self):
        """Disconnect from device."""
        self.protocol.disconnect()
        self.connected = False
    
    def _on_raw_eeg(self, value: int):
        """Called when raw EEG data received."""
        # For now, we buffer single-channel EEG
        # In a real implementation, we'd accumulate 4 channels
        self.signal_data_buffer.append(value)
        
        # Create dummy signal data compatible with pyneurosdk2
        if self.signalDataReceived:
            # Dummy data: package 4 channels with same value for now
            class DummySignalData:
                def __init__(self, channels):
                    self.Channels = channels
            
            data = DummySignalData([value, value, value, value])
            self.signalDataReceived(data)
    
    def _on_electrode_contact(self, contact_quality: List[int]):
        """Called when electrode contact quality received."""
        # Convert to resistance format (0-255 quality -> approximate kOhms)
        # This is a rough approximation: quality 50 = ~10kΩ
        contact_quality = contact_quality[:4]  # Ensure 4 channels
        
        # Map quality (0-255) to impedance (0-100kΩ roughly)
        # 0-50 quality = good (<5kΩ)
        # 50-150 quality = acceptable (5-20kΩ)
        # 150-255 quality = bad (>20kΩ)
        resistance = [(q / 255.0) * 100.0 for q in contact_quality]
        
        self.resist_data_buffer.append(resistance)
        
        if self.resistDataReceived:
            # Create dummy resistance data
            class DummyResistData:
                def __init__(self, ohms):
                    self.Ohms = [o * 1000 for o in ohms]  # Convert to Ohms
            
            data = DummyResistData(resistance)
            self.resistDataReceived(data)
    
    def _on_battery(self, battery_pct: int):
        """Called when battery info received."""
        self.battery_level = battery_pct
        self.battery_buffer.append(battery_pct)
        
        if self.batteryDataReceived:
            class DummyBatteryData:
                def __init__(self, charge_pct):
                    self.ChargePercent = charge_pct
            
            data = DummyBatteryData(battery_pct)
            self.batteryDataReceived(data)
    
    def _on_signal_quality(self, quality: int):
        """Called when signal quality received."""
        self.signal_quality = quality
