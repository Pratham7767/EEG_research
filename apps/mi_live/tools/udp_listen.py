"""Prints the commands MI Live sends by UDP. Run it, then tick 'Send to bot by UDP' (127.0.0.1:5005).
Use the same code on a Raspberry Pi bot: replace print() with your motor calls.
    C:\\Python313\\python.exe tools\\udp_listen.py [port]"""
import json
import socket
import sys

port = int(sys.argv[1]) if len(sys.argv) > 1 else 5005
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", port))
s.settimeout(1.0)
print(f"listening on UDP {port} ... (Ctrl+C to stop)")
last = None
while True:
    try:
        data, addr = s.recvfrom(1024)
    except socket.timeout:
        if last != "SILENT":
            print("no messages for 1 s -> a bot should STOP here")
            last = "SILENT"
        continue
    m = json.loads(data)
    if m["cmd"] != last:
        print(f"{m['cmd']:8s} v={m['v']:+.2f} d={m['d']:+.2f}")
        last = m["cmd"]
