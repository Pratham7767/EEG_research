# DEVICE DETECTION TROUBLESHOOTING GUIDE

## Issue: "No devices found" during scan

If your EEG device is not being detected, follow these steps:

---

## Step 1: Verify Device is Paired

### Windows 10/11 Bluetooth Settings:
1. Go to **Settings** → **Devices** → **Bluetooth & other devices**
2. Look for your device in the list:
   - **LEHeadphones2**
   - **LEHeadband**
   - **LEBrainBit**
   - Or similar NeuroSky/MOOB Labs device
3. If device is NOT in the list:
   - **Power it ON** (check battery/charging)
   - **Enable Bluetooth** on the device (if it has a button)
   - **Pair manually** in Windows Bluetooth settings

---

## Step 2: Update Scan Settings

The device may need a longer scan time to be detected:

### In the GUI Application:
1. Go to **Connection & Calibration** tab
2. Look for **"Scan Duration"** field (top of Device Connection panel)
3. Increase from 10 seconds to **20-30 seconds** (or more)
4. Click **"Scan for Devices"** again

### Why longer scan helps:
- Some devices take time to advertise over Bluetooth
- Multiple device types are being scanned simultaneously
- The device may be in a low-power or distant state

---

## Step 3: Check Supported Device Types

The application now supports **9 device types**:

✓ LEHeadphones2 (primary)
✓ LEHeadband
✓ LEBrainBit
✓ LEBrainBitBlack
✓ LECallibri
✓ LEKolibri
✓ LEBrainBit2
✓ LEBrainBitPro
✓ LEBrainBitFlex

**Verify your device model matches one of these types.**

---

## Step 4: Troubleshooting Steps

### A) Device is powered on but not appearing:

```
1. Restart the application:
   - Close the GUI
   - Wait 10 seconds
   - Re-launch

2. Restart the device:
   - Turn OFF the device
   - Wait 30 seconds
   - Turn it back ON
   - Try scanning again

3. Unpair and re-pair in Bluetooth settings:
   - Settings → Devices → Bluetooth
   - Find device → "Remove device"
   - Turn device OFF, then ON
   - Manually pair device again
```

### B) Device appears but won't connect:

```
1. Close all other EEG/Bluetooth applications
   - CapsuleApp
   - MindWave Mobile
   - Other manufacturer apps
   
2. Check Windows driver:
   - Device Manager → Bluetooth
   - Look for driver errors (yellow triangle)
   - Update or reinstall driver if needed

3. Try a different Bluetooth USB adapter:
   - Some adapters have compatibility issues
   - Built-in laptop Bluetooth may work better
```

### C) Device keeps disconnecting:

```
1. Increase scan duration in GUI (20-30 seconds)
2. Check signal strength:
   - Move device closer to laptop
   - Remove obstacles/interference
   - Try in different location

3. Update your device firmware:
   - Check manufacturer's website
   - Follow firmware update instructions
```

---

## Step 5: Advanced - Manual Testing

If the GUI still doesn't find the device, test the SDK directly:

### Test 1: List Bluetooth devices
```powershell
cd d:\sit_secrets\EEG_Recorder
c:/python313/python.exe -c "
import sys
sys.path.insert(0, '..')
from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily

# Test all device types
devices_to_test = [
    ('LEHeadphones2', SensorFamily.LEHeadPhones2),
    ('LEHeadband', SensorFamily.LEHeadband),
    ('LEBrainBit', SensorFamily.LEBrainBit),
]

for name, family in devices_to_test:
    print(f'\nScanning for {name}...')
    scanner = Scanner([family])
    scanner.start()
    
    import time
    time.sleep(5)
    
    sensors = scanner.sensors()
    if sensors:
        for s in sensors:
            print(f'  Found: {s.Name} - {s.SerialNumber}')
    else:
        print(f'  No {name} devices found')
    
    scanner.stop()
"
```

### Test 2: Check pyneurosdk2 installation
```powershell
c:/python313/python.exe -c "
import sys
sys.path.insert(0, 'd:\sit_secrets\pyneurosdk2-1.0.15')
from neurosdk.scanner import Scanner
from neurosdk.cmn_types import SensorFamily
print('✓ pyneurosdk2 working correctly')
print(f'✓ Supported families: {len(SensorFamily)}')
"
```

---

## Step 6: Device-Specific Notes

### LEHeadphones2 / LEHeadband (most common):
- Usually appear as **"NeuroSky Headset"** in Bluetooth
- Battery indicator should show on device startup
- May need 10-15 second scan initially

### LEBrainBit / LECallibri:
- Often appear as **"BrainBit"** or **"Callibri"** in Bluetooth
- Check MOOB Labs software for firmware version
- May have different Bluetooth advertise behavior

### Legacy devices:
- Older MindWave devices may use different protocol
- Check manufacturer website for compatibility
- May need device-specific driver installation

---

## Step 7: Still Not Working?

If the device is paired in Windows Bluetooth but still not found:

### Gather diagnostic information:
```powershell
# Run these and share output with support
1. Device Manager Bluetooth info:
   - Open Device Manager
   - Expand "Bluetooth"
   - Screenshot all entries

2. Bluetooth device details:
   Settings → Devices → Bluetooth → [Your Device] → Device Properties
   - Screenshot device info

3. SDK scan log:
   Run the manual test from Step 5
   - Copy all output

4. Application log:
   - In GUI, go to Log tab
   - Copy all messages from last scan attempt
```

---

## Summary Checklist

- [ ] Device is powered ON
- [ ] Device is paired in Windows Bluetooth settings
- [ ] No other apps are using the device
- [ ] Tried scanning multiple times
- [ ] Increased scan duration to 20-30 seconds
- [ ] Restarted the application
- [ ] Restarted the device
- [ ] Checked if device is in the supported list (9 types)
- [ ] Tried in a different location (away from interference)
- [ ] Checked for Windows driver issues

---

## Contact/Support

For persistent issues, provide:
1. Device model name (from Bluetooth settings)
2. Serial number (if visible)
3. Application version
4. Last 20 lines from Log tab
5. Screenshot of Bluetooth settings showing your device

---

## Reference: Device Detection Flow

```
User clicks "Scan for Devices"
     ↓
Application creates Scanner for 9 device types
     ↓
Scanner broadcasts to all nearby devices
     ↓
Device responds with Bluetooth advertisement (if powered on & in range)
     ↓
Scanner collects responses over specified duration (10-60 seconds)
     ↓
Results displayed in GUI device list
     ↓
User selects device and clicks "Connect"
```

**If device is paired but not appearing: Usually a timing/advertisement issue**
- Solution: Increase scan duration
- Alternative: Restart device → rescan

**If device won't connect after appearing: Usually a driver/compatibility issue**
- Solution: Update Windows Bluetooth drivers
- Alternative: Use different Bluetooth adapter
