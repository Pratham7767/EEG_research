"""A bot on the screen that does what the commands say (to try control before building a real one).
LEFT / RIGHT: turn 120 deg/s while creeping forward; FORWARD: drive; STOP: stand still."""
import math
from collections import deque

SPEED = {"FORWARD": 70.0, "LEFT": 30.0, "RIGHT": 30.0, "STOP": 0.0}     # pixels per second
TURN = {"LEFT": -120.0, "RIGHT": 120.0}                                 # degrees per second


class SimBot:
    def __init__(self, w=340, h=240):
        self.w, self.h = w, h
        self.reset()

    def reset(self):
        self.x, self.y, self.heading = self.w / 2, self.h / 2, -90.0
        self.trail = deque(maxlen=600)
        self.distance = 0.0
        self.turned = 0.0

    def step(self, cmd, dt):
        turn = TURN.get(cmd, 0.0) * dt
        self.heading = (self.heading + turn) % 360
        self.turned += abs(turn)
        v = SPEED.get(cmd, 0.0) * dt
        if v:
            a = math.radians(self.heading)
            self.x = (self.x + v * math.cos(a)) % self.w
            self.y = (self.y + v * math.sin(a)) % self.h
            self.trail.append((self.x, self.y))
            self.distance += v
