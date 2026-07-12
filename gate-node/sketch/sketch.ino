/*
 * gate-node/sketch/sketch.ino — UNO Q MCU (STM32U585): deterministic actuator.
 * OWNER: Beta.  Runs NO model. Provides Bridge RPCs to python/main.py (MPU):
 *
 *   gate_set_state(state)  -> matrix arrows/stop + RGB gate colour
 *   gate_chirp()           -> steward chirp (Buzzer Modulino, if present)
 *   gate_read_knob()       -> int  (-1 = no Knob Modulino)
 *   gate_read_thermo()     -> float (NAN = no Thermo Modulino)
 *
 * FAIL-SAFE (§4D): the MCU only changes state on RPC — so on broker/Linux loss
 * it inherently HOLDS LAST_SAFE. A watchdog (no Bridge traffic > 15 s) adds a
 * dim "link lost" pulse on the status LED without touching the gate state.
 *
 * ── COLOUR-PER-PULSE FIX ────────────────────────────────────────────────────
 * All state colours live in ONE table below (STATE_TABLE). If colours come out
 * wrong per pulse (red/green swapped is the classic GRB-vs-RGB wiring issue),
 * flip SWAP_RG to true — every state is corrected in one place. Brightness is
 * COLOR_SCALE (0.0-1.0) so pulses don't wash out.
 *
 * ── HARDWARE SEAMS ──────────────────────────────────────────────────────────
 * The shims rgbShow()/matrixShow()/buzzerChirp()/knobRead()/thermoRead() are
 * the ONLY places that touch pins. Board API names vary by App Lab version
 * (dev-guide rule: pin from the built-in examples, never invent) — paste the
 * working calls from the on-board sketch into those shims; everything else
 * here is board-agnostic.
 */
#include <Arduino.h>
#include "Bridge.h"
// #include <Modulino.h>          // optional Knob/Buzzer/Thermo — auto-detected

// ---------------------------------------------------------------------------
// Colour config — THE place to fix per-pulse colours.
// ---------------------------------------------------------------------------
static const bool  SWAP_RG     = false;  // true if red/green are swapped (GRB LEDs)
static const float COLOR_SCALE = 0.6f;   // global brightness 0.0-1.0

struct Rgb { uint8_t r, g, b; };

// 8x13 matrix patterns, one uint16_t per row (bit 12 = leftmost column).
typedef uint16_t Pattern[8];

static const Pattern PAT_CLEAR = {0, 0, 0, 0, 0, 0, 0, 0};

static const Pattern PAT_ARROW_LEFT = {   //  <—
  0b0000000000000,
  0b0001000000000,
  0b0011000000000,
  0b0111111111110,
  0b0111111111110,
  0b0011000000000,
  0b0001000000000,
  0b0000000000000,
};

static const Pattern PAT_ARROW_RIGHT = {  //  —>
  0b0000000000000,
  0b0000000001000,
  0b0000000001100,
  0b0111111111110,
  0b0111111111110,
  0b0000000001100,
  0b0000000001000,
  0b0000000000000,
};

static const Pattern PAT_STOP_X = {       //  X
  0b1100000000011,
  0b0110000000110,
  0b0011000001100,
  0b0001101011000,
  0b0001101011000,
  0b0011000001100,
  0b0110000000110,
  0b1100000000011,
};

static const Pattern PAT_SAFE = {         //  calm bar (used while flashing)
  0b0000000000000,
  0b0000000000000,
  0b0111111111110,
  0b0111111111110,
  0b0111111111110,
  0b0111111111110,
  0b0000000000000,
  0b0000000000000,
};

struct StateDef { const char *name; Rgb colour; const Pattern *pattern; bool flash; };

// state -> colour + matrix pattern. Colours: OPEN green, CLOSE red, diverts
// amber (open-but-rerouted) or red (closed + reroute), SAFE_FLASH cyan blink.
static const StateDef STATE_TABLE[] = {
  {"OPEN",               {  0, 255,   0}, &PAT_CLEAR,       false},
  {"CLOSE",              {255,   0,   0}, &PAT_STOP_X,      false},
  {"DIVERT_LEFT",        {255, 120,   0}, &PAT_ARROW_LEFT,  false},
  {"DIVERT_RIGHT",       {255, 120,   0}, &PAT_ARROW_RIGHT, false},
  {"CLOSE_DIVERT_LEFT",  {255,   0,   0}, &PAT_ARROW_LEFT,  false},
  {"CLOSE_DIVERT_RIGHT", {255,   0,   0}, &PAT_ARROW_RIGHT, false},
  {"SAFE_FLASH",         {  0, 200, 255}, &PAT_SAFE,        true },
};
static const int N_STATES = sizeof(STATE_TABLE) / sizeof(STATE_TABLE[0]);

// ---------------------------------------------------------------------------
// Runtime state
// ---------------------------------------------------------------------------
static int           currentIdx   = 0;        // LAST_SAFE = whatever we hold
static unsigned long lastBridgeMs = 0;        // watchdog: MPU link liveness
static bool          linkLost     = false;
static bool          flashOn      = true;
static unsigned long lastFlashMs  = 0;
static bool          hasKnob = false, hasBuzzer = false, hasThermo = false;

// ---------------------------------------------------------------------------
// HARDWARE SEAMS — paste the verified on-board calls here (never invent APIs).
// ---------------------------------------------------------------------------
static void rgbShow(Rgb c, float scale) {
  uint8_t r = (uint8_t)(c.r * scale), g = (uint8_t)(c.g * scale),
          b = (uint8_t)(c.b * scale);
  if (SWAP_RG) { uint8_t t = r; r = g; g = t; }
  // TODO(board): replace with the working RGB call from the on-board sketch,
  // e.g. the App Lab LED example's API for MCU LEDs #3/#4:
  //   ledRgb.set(r, g, b);
  (void)r; (void)g; (void)b;
}

static void matrixShow(const Pattern &p) {
  // TODO(board): replace with the working matrix call from the on-board
  // sketch (App Lab matrix example), drawing 8 rows x 13 cols from p[row]
  // bit 12..0. Keep this the ONLY matrix-touching function.
  (void)p;
}

static void buzzerChirp() {
  if (!hasBuzzer) return;
  // TODO(board): Buzzer Modulino chirp (short, steward-facing — never alarm).
}

static int knobRead() {
  if (!hasKnob) return -1;
  // TODO(board): return Knob Modulino position (0..N). -1 = absent.
  return -1;
}

static float thermoRead() {
  if (!hasThermo) return NAN;
  // TODO(board): return Thermo Modulino degrees C.
  return NAN;
}

// ---------------------------------------------------------------------------
// State application
// ---------------------------------------------------------------------------
static void applyState(int idx, bool flashPhase) {
  const StateDef &s = STATE_TABLE[idx];
  float scale = COLOR_SCALE;
  if (s.flash && !flashPhase) scale = 0.0f;         // blink off-phase
  if (linkLost) scale *= 0.35f;                     // dim = link-lost hint
  rgbShow(s.colour, scale);
  matrixShow((s.flash && !flashPhase) ? PAT_CLEAR : *(s.pattern));
}

// ---------------------------------------------------------------------------
// Bridge RPCs (names pinned with python/main.py — change both or neither)
// ---------------------------------------------------------------------------
String gate_set_state(String state) {
  lastBridgeMs = millis();
  linkLost = false;
  for (int i = 0; i < N_STATES; i++) {
    if (state.equals(STATE_TABLE[i].name)) {
      currentIdx = i;
      flashOn = true;
      lastFlashMs = millis();
      applyState(currentIdx, flashOn);
      return String("ok:") + state;
    }
  }
  return String("err:unknown-state");                // hold LAST_SAFE
}

String gate_chirp() {
  lastBridgeMs = millis();
  buzzerChirp();
  return hasBuzzer ? "ok" : "absent";
}

int gate_read_knob() {
  lastBridgeMs = millis();
  return knobRead();
}

float gate_read_thermo() {
  lastBridgeMs = millis();
  return thermoRead();
}

// ---------------------------------------------------------------------------
void setup() {
  Bridge.begin();
  Bridge.provide("gate_set_state", gate_set_state);
  Bridge.provide("gate_chirp", gate_chirp);
  Bridge.provide("gate_read_knob", gate_read_knob);
  Bridge.provide("gate_read_thermo", gate_read_thermo);

  // TODO(board): matrix/LED init from the working on-board sketch, and
  // Modulino presence probes -> hasKnob / hasBuzzer / hasThermo.
  lastBridgeMs = millis();
  applyState(currentIdx, true);                     // boot = OPEN, green
}

void loop() {
  Bridge.update();

  unsigned long now = millis();

  // Watchdog: no Bridge traffic 15 s => LINK LOST. HOLD state, dim the LEDs.
  bool lost = (now - lastBridgeMs) > 15000UL;
  if (lost != linkLost) {
    linkLost = lost;
    applyState(currentIdx, flashOn);
  }

  // SAFE_FLASH blink (500 ms), driven off millis() — never blocks the Bridge.
  if (STATE_TABLE[currentIdx].flash && (now - lastFlashMs) > 500UL) {
    flashOn = !flashOn;
    lastFlashMs = now;
    applyState(currentIdx, flashOn);
  }
}
