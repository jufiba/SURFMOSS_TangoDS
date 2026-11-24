// MotorApertura -- stepper driving the LEEM aperture, on an Arduino Mega 2560
// with a DRV8825 step/dir driver.
//
// Talks to the MotorApertura Tango device server. This sketch and
// ../README.md are the specification of the protocol; keep all three in
// step.
//
// Protocol: ASCII, '\n'-terminated, 8N1 at 9600. One line of reply per
// command, and for a move that line comes out when the move has FINISHED --
// which is what lets the device server know it is done. The previous sketch
// (Motor-original.ino, kept beside this one) answered before moving and said
// nothing afterwards, so nothing downstream could tell a finished move from
// one that never happened.
//
//   I       -> MotorApertura 1        identity and protocol version
//   ?       -> POS <position>
//   +<n>    -> OK <moved> <position>  move n steps forward, reply when done
//   -<n>    -> OK <moved> <position>  (moved is negative here)
//   Z       -> OK 0 0                 call this spot zero
//   H       -> ERR nohome             reserved for a future limit switch
//   other   -> ERR formato
//
// BEWARE: the unit is STEPS, not revolutions. Motor-original.ino multiplied
// the number by 200, so its "+5" meant five turns; here "+5" is five steps.
//
// Opening the serial port resets the board, so the position cannot live in
// RAM: it is kept in EEPROM, and the identity line is printed on boot so the
// device server can check what it is talking to.

#define dirPin 31
#define stepPin 33

// Full step on this driver today. Informational only -- nothing here divides
// by it any more -- but worth keeping in step with the DRV8825's microstep
// jumpers if they are ever changed.
#define stepsPerRevolution 200

// Half-period of the step pulse. 1200 us each way is 2.4 ms per step, which
// is what the original sketch used; the mechanism is known to cope with it.
#define stepHalfPeriodUs 1200

// ---------------------------------------------------------------- EEPROM --
// The position must survive both a reset (every time the port is opened) and
// a power cut, so it goes in EEPROM. Written ONCE PER MOVE, never per step.
//
// Writing it always to the same cell would wear that cell out: the ATmega2560
// is rated 100,000 write cycles, which at 100 moves a day is about four
// years. So the records rotate through a ring of slots, and the live one is
// whichever carries the highest sequence number:
//
//   100,000 cycles x 512 slots = 51,200,000 moves
//
// which at the same rate is over a thousand years. A blank cell reads 0xFF,
// so seq == 0xFFFFFFFF means "never written" and must not win the scan.

#include <EEPROM.h>

#define SLOT_COUNT 512
#define SLOT_SIZE  8            // uint32 seq + int32 position = 4096 bytes
#define SEQ_EMPTY  0xFFFFFFFFUL

long position = 0;
unsigned long sequence = 0;
int slot = -1;                  // slot holding the live record

void positionLoad() {
  unsigned long best = 0;
  bool found = false;
  for (int i = 0; i < SLOT_COUNT; i++) {
    unsigned long seq;
    EEPROM.get(i * SLOT_SIZE, seq);
    if (seq == SEQ_EMPTY) continue;           // never written
    if (!found || seq > best) {
      long pos;
      EEPROM.get(i * SLOT_SIZE + 4, pos);
      best = seq;
      position = pos;
      slot = i;
      found = true;
    }
  }
  if (!found) {                 // first run on a blank board
    position = 0;
    sequence = 0;
    slot = -1;
  } else {
    sequence = best;
  }
}

void positionSave() {
  slot = (slot + 1) % SLOT_COUNT;
  sequence++;
  // EEPROM.put is update-based: bytes that do not change are not written.
  EEPROM.put(slot * SLOT_SIZE, sequence);
  EEPROM.put(slot * SLOT_SIZE + 4, position);
}

// ------------------------------------------------------------------ move --

void moveSteps(long steps) {
  if (steps == 0) return;
  digitalWrite(dirPin, steps > 0 ? LOW : HIGH);
  long n = steps > 0 ? steps : -steps;
  for (long i = 0; i < n; i++) {
    digitalWrite(stepPin, HIGH);
    delayMicroseconds(stepHalfPeriodUs);
    digitalWrite(stepPin, LOW);
    delayMicroseconds(stepHalfPeriodUs);
  }
  position += steps;
  positionSave();               // once per move, not per step
}

// ------------------------------------------------------------------ setup --

void setup() {
  pinMode(stepPin, OUTPUT);
  pinMode(dirPin, OUTPUT);
  digitalWrite(stepPin, LOW);
  positionLoad();
  Serial.begin(9600);
  Serial.println("MotorApertura 1");
}

void loop() {
  if (Serial.available() <= 0) return;

  String input = Serial.readStringUntil('\n');
  input.trim();
  if (input.length() == 0) return;

  char c = input.charAt(0);

  if (c == 'I') {
    Serial.println("MotorApertura 1");
    return;
  }
  if (c == '?') {
    Serial.print("POS ");
    Serial.println(position);
    return;
  }
  if (c == 'Z') {
    position = 0;
    positionSave();
    Serial.println("OK 0 0");
    return;
  }
  if (c == 'H') {
    // No limit switch is fitted. Answered explicitly rather than ignored, so
    // the day one is added the device server needs no new command, only this
    // branch filling in.
    Serial.println("ERR nohome");
    return;
  }

  if (c == '+' || c == '-') {
    String rest = input.substring(1);
    // toInt() returns 0 for anything it cannot parse, which would silently
    // turn a typo into a no-op. Check the digits ourselves instead.
    if (rest.length() == 0) { Serial.println("ERR formato"); return; }
    for (unsigned int i = 0; i < rest.length(); i++) {
      if (!isDigit(rest.charAt(i))) { Serial.println("ERR formato"); return; }
    }
    long steps = rest.toInt();
    if (c == '-') steps = -steps;
    moveSteps(steps);
    Serial.print("OK ");
    Serial.print(steps);
    Serial.print(" ");
    Serial.println(position);
    return;
  }

  Serial.println("ERR formato");
}
