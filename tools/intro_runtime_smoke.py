#!/usr/bin/env python3
"""Synthetic native smoke of the actual startup adapter; no game or browser."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work/upstream/nfsu2-web/runtime"

HARNESS = r'''
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "cpu.h"
#include "kbd.h"
#include "gamepad.h"

uint8_t *g_mem;
static guest_fn_t hooks[3];
static uint32_t seen, head, buttons;
static int called;
static KbdEv events[256];

void dispatch_patch(uint32_t address, guest_fn_t fn) {
  int i = address == 0x4de9f0u ? 0 : address == 0x4deb30u ? 1 :
          address == 0x4dec50u ? 2 : -1;
  assert(i >= 0 && !hooks[i]);
  hooks[i] = fn;
}
uint32_t kbd_ev_head(void) { return head; }
int kbd_ev_get(uint32_t seq, KbdEv *ev) {
  *ev = events[seq & 255u];
  return 1;
}
int gamepad_env_flag(const char *name, int fallback) {
  const char *value = getenv(name);
  return value ? strcmp(value, "off") != 0 : fallback;
}
int gamepad_read(PadState *state) {
  memset(state, 0, sizeof *state);
  state->buttons = buttons;
  return 1;
}
static void original(CPU *c, int which) {
  seen = MR32(c->esp + 4u);
  called = which;
  assert(MR32(c->esp + 8u) == 0x12345678u);
  assert(MR32(c->esp + 12u) == 0x23456789u);
  assert(MR32(c->esp + 16u) == 0x3456789au);
  POP32(c->eip);
  c->esp += 16u;
  c->ecx = 0xdeadbeefu; /* The handler can destroy its object. */
}
void sub_004de9f0(CPU *c) { original(c, 0); }
void sub_004deb30(CPU *c) { original(c, 1); }
void sub_004dec50(CPU *c) { original(c, 2); }
void nfsu1_intro_install(void);

static void press(unsigned dik) {
  events[head & 255u] = (KbdEv){.dik = dik, .down = 1, .seq = head};
  head++;
}
static uint32_t message(int which, uint32_t self, uint32_t value) {
  CPU cpu = {0};
  cpu.ecx = self;
  cpu.esp = 0x1000u;
  MR32(cpu.esp) = 0x11223344u;
  MR32(cpu.esp + 4u) = value;
  MR32(cpu.esp + 8u) = 0x12345678u;
  MR32(cpu.esp + 12u) = 0x23456789u;
  MR32(cpu.esp + 16u) = 0x3456789au;
  hooks[which](&cpu);
  assert(cpu.esp == 0x1014u && cpu.eip == 0x11223344u && called == which);
  return seen;
}
int main(int argc, char **argv) {
  assert(argc == 2);
  const uint32_t tick = 0xc98356bau, end = 0xc3960eb9u, accept = 0x406415e3u;
  g_mem = calloc(1, 0x10000u);
  assert(g_mem);
  nfsu1_intro_install();
  assert(hooks[0] && hooks[1] && hooks[2]);
  for (int i = 0; i < 3; i++) {
    uint32_t self = 0x2000u + (uint32_t)i * 0x100u;
    MR32(self) = 0x6000u + (uint32_t)i;
    MR32(self + 12u) = 0x7000u + (uint32_t)i;
    if (!strcmp(argv[1], "off")) {
      assert(message(i, self, tick) == end);
    } else {
      press(0x39); /* A press made before the screen starts is ignored. */
      assert(message(i, self, tick) == tick);
      const unsigned keys[] = {0x01, 0x39, 0x1c};
      for (unsigned k = 0; k < 3; k++) {
        press(keys[k]);
        assert(message(i, self, tick) ==
               (!strcmp(argv[1], "original") ? tick : i == 1 ? end : accept));
        /* Same allocation may serve the next movie. A held key has no
         * new down event and cannot skip that movie's first or next tick. */
        assert(message(i, self, tick) == tick);
        assert(message(i, self, tick) == tick);
      }
      buttons = 1u << PAD_B;
      uint32_t expected = !strcmp(argv[1], "original") ||
                          !strcmp(getenv("NFSU2_PAD") ? getenv("NFSU2_PAD") : "", "off")
                          ? tick : i == 1 ? end : accept;
      assert(message(i, self, tick) == expected);
      assert(message(i, self, tick) == tick);
      assert(message(i, self, tick) == tick);
      buttons = 0;
      message(i, self, tick);
      /* Native accept/start stay native; logos gain a completion message. */
      assert(message(i, self, accept) ==
             (!strcmp(argv[1], "original") || i != 1 ? accept : end));
    }
    assert(message(i, self, end) == end);
  }
  free(g_mem);
  return 0;
}
'''


def main():
    compiler = shutil.which("cc")
    if not compiler:
        raise SystemExit("A native C compiler is required.")
    with tempfile.TemporaryDirectory(prefix="nfsu1-intro-") as temp:
        folder = Path(temp)
        source = folder / "smoke.c"
        source.write_text(HARNESS)
        binary = folder / "smoke"
        subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-I", str(RUNTIME), str(ROOT / "runtime/nfsu1_intro.c"),
                        str(source), "-o", str(binary)], check=True)
        for mode, pad in [("skippable", "on"), ("skippable", "off"),
                          ("original", "on"), ("off", "on")]:
            subprocess.run([str(binary), mode],
                           env={**os.environ, "NFSU1_INTRO": mode, "NFSU2_PAD": pad},
                           check=True)
    print("Synthetic startup adapter smoke passed (native; no game/browser execution).")


if __name__ == "__main__":
    main()
