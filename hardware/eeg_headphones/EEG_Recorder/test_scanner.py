"""Test pyneurosdk2 scanner for Bluetooth devices."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pyneurosdk2-1.0.15'))

from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily
import time

def test_scanner():
    """Test device scanning with various timeouts."""
    print("Testing pyneurosdk2 scanner for Bluetooth devices...\n")
    
    device_families = [
        SensorFamily.LEHeadPhones2,
        SensorFamily.LEHeadband,
        SensorFamily.LEBrainBit,
    ]
    
    found_devices = []
    
    def on_sensors_changed(scanner_self, sensors_list):
        print(f"  Devices detected: {len(sensors_list)}")
        for s in sensors_list:
            print(f"    - {s.Name} (Address: {s.Address}, RSSI: {s.RSSI})")
            found_devices.append(s)
    
    for family in device_families:
        print(f"Scanning for {family.name}...")
        scanner = Scanner([family])
        scanner.sensorsChanged = on_sensors_changed
        
        try:
            # Start scanning
            scanner.start()
            
            # Wait 20 seconds for devices
            for i in range(20):
                current_devices = scanner.sensors()
                if current_devices:
                    print(f"  Found {len(current_devices)} sensor(s):")
                    for s in current_devices:
                        print(f"    - {s.Name} (Address: {s.Address})")
                    break
                time.sleep(1)
                print(f"  Scanning... {i+1}/20", end='\r')
            else:
                current_devices = scanner.sensors()
                if current_devices:
                    print(f"  Found {len(current_devices)} sensor(s):")
                    for s in current_devices:
                        print(f"    - {s.Name} (Address: {s.Address})")
                else:
                    print(f"  No sensors found after 20 seconds")
            
            scanner.stop()
            
        except Exception as e:
            print(f"  Error: {e}")
        
        print()

if __name__ == '__main__':
    test_scanner()

