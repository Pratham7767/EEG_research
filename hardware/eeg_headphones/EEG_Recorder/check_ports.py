"""Check available COM ports."""
import serial
from serial.tools.list_ports import comports

ports = list(comports())
print(f"Found {len(ports)} port(s):\n")

for p in ports:
    print(f"Port: {p.device}")
    print(f"  Description: {p.description}")
    print(f"  HWID: {p.hwid if hasattr(p, 'hwid') else 'N/A'}")
    print(f"  VID: {p.vid if hasattr(p, 'vid') else 'N/A'}")
    print(f"  PID: {p.pid if hasattr(p, 'pid') else 'N/A'}")
    print()
