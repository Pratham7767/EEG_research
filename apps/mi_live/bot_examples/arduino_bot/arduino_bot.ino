// MI Live -> 2-wheel bot (Arduino Uno/Nano + L298N motor driver). Receives one letter per line over
// USB serial (or an HC-05 Bluetooth module on pins 0/1) at 115200 baud:
//   L = turn left, R = turn right, F = forward, S = stop.
// Safety: stops by itself if nothing arrives for 1 s (MI Live sends every 0.25 s).
// Wiring (change to yours): left motor IN1=5 IN2=6, right motor IN3=9 IN4=10 (PWM pins), ENA/ENB jumpered.

const int L1 = 5, L2 = 6, R1 = 9, R2 = 10;
const int SPEED = 160;        // 0-255
const int TURN = 140;
unsigned long lastMsg = 0;

void motors(int left, int right) {           // -255..255
  analogWrite(L1, left > 0 ? left : 0);  analogWrite(L2, left < 0 ? -left : 0);
  analogWrite(R1, right > 0 ? right : 0); analogWrite(R2, right < 0 ? -right : 0);
}

void setup() {
  pinMode(L1, OUTPUT); pinMode(L2, OUTPUT); pinMode(R1, OUTPUT); pinMode(R2, OUTPUT);
  Serial.begin(115200);
  motors(0, 0);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') continue;
    lastMsg = millis();
    if (c == 'L') motors(-TURN, TURN);         // spin left on the spot
    else if (c == 'R') motors(TURN, -TURN);    // spin right
    else if (c == 'F') motors(SPEED, SPEED);
    else motors(0, 0);                          // 'S' or anything else
  }
  if (millis() - lastMsg > 1000) motors(0, 0);
}
