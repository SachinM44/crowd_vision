// gate-node/sketch/sketch.ino — UNO Q MCU: gate actuators over the Bridge.
// OWNER: Beta (TODO(beta)). Contract stub.
//
// Exposes RPC functions the MPU (python/main.py) calls over the Bridge:
//   gate_set_state(state)  -> 4x RGB gate LEDs + 8x13 matrix arrows / stop-X
//   gate_chirp()           -> Buzzer steward chirp (if Modulino secured)
//   gate_read_knob()       -> Knob override position (if Modulino secured)
//   gate_read_thermo()     -> Thermo temp_c (if Modulino secured; else default)
//
// Modulinos are OPTIONAL (feature flags / auto-detect over Qwiic). The MCU keeps
// signals deterministic even if Linux hiccups — this is the fail-safe half.
//
// Bridge pattern pinned from the App Lab built-in examples (NEVER invent):
//   #include "Bridge.h"
//   void setup(){ Bridge.begin(); Bridge.provide("gate_set_state", gate_set_state); }
//   void loop(){ Bridge.update(); }

#include <Arduino.h>
// #include "Bridge.h"   // TODO(beta): exact include from the UNO Q User Manual

// void gate_set_state(const char* state) { /* TODO(beta): RGB + matrix pattern */ }
// void gate_chirp() { /* TODO(beta): buzzer if present */ }

void setup() {
  // TODO(beta): Bridge.begin(); Bridge.provide("gate_set_state", gate_set_state); ...
}

void loop() {
  // TODO(beta): Bridge.update();
}
