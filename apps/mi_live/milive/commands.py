"""Sends the bot command out of the laptop. Two ways, both optional:

  UDP     one JSON line per message to host:port, e.g. {"cmd": "LEFT", "v": -0.72, "d": -1.31, "t": 1730000000.12}
          (any program, a Raspberry Pi bot, an ESP32 on Wi-Fi). See tools/udp_listen.py.
  Serial  one letter + newline: L = left, R = right, S = stop, F = forward (Arduino over USB or a Bluetooth
          serial module such as HC-05). See bot_examples/arduino_bot/arduino_bot.ino.

A message is sent when the command changes and again every 0.25 s (heartbeat), so a bot can stop by itself
if messages stop arriving (the Arduino example stops after 1 s of silence).
"""
import json
import socket
import time

LETTER = {"LEFT": "L", "RIGHT": "R", "STOP": "S", "FORWARD": "F"}


class CommandSender:
    def __init__(self, heartbeat_s=0.25):
        self.heartbeat_s = heartbeat_s
        self.sock = self.addr = self.ser = None
        self.last, self.t_last = None, 0.0
        self.n_sent = 0
        self.error = None

    @property
    def active(self):
        return self.sock is not None or self.ser is not None

    def set_udp(self, addr_text):
        """'host:port' to start, '' or None to stop."""
        if self.sock is not None:
            self.sock.close()
        self.sock = self.addr = None
        if addr_text:
            host, port = addr_text.strip().rsplit(":", 1)
            self.addr = (host, int(port))
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def open_serial(self, port, baud=115200):
        import serial                      # pyserial
        self.close_serial()
        self.ser = serial.Serial(port, baud, timeout=0, write_timeout=0)

    def close_serial(self):
        if self.ser is not None:
            try:
                self.ser.write(b"S\n")
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def send(self, cmd, v=0.0, d=0.0, force=False):
        now = time.time()
        if not self.active or (not force and cmd == self.last and now - self.t_last < self.heartbeat_s):
            return False
        self.last, self.t_last = cmd, now
        if self.sock is not None:
            try:
                msg = json.dumps(dict(cmd=cmd, v=round(float(v), 3), d=round(float(d), 3), t=round(now, 3)))
                self.sock.sendto(msg.encode(), self.addr)
            except OSError as e:
                self.error = f"UDP: {e}"
        if self.ser is not None:
            try:
                self.ser.write((LETTER.get(cmd, "S") + "\n").encode())
            except Exception as e:
                self.error = f"Serial: {e}"
                self.ser = None
        self.n_sent += 1
        return True

    def close(self):
        self.send("STOP", force=True)
        self.set_udp(None)
        self.close_serial()
