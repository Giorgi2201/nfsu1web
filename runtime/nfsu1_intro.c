/* NFSU1 startup movie controls for the CPU* host ABI.
 * Adapted from th0mk/nfsu2-web runtime/intro.c at
 * 31da468582c3de14fd6f4233831f62816e2df83d (MIT).
 * See patches/nfsu2-web.LICENSE and docs/source-permissions.md.
 * Only handwritten host logic and verified interface addresses live here.
 * No translated game instructions are included. */
#include "cpu.h"
#include "kbd.h"
#include "gamepad.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#define MSG_ACCEPT 0x406415e3u
#define MSG_START  0xb5af2461u
#define MSG_BACK   0x911ab364u
#define MSG_END    0xc3960eb9u
#define MSG_TICK   0xc98356bau

enum { INTRO_SKIPPABLE, INTRO_ORIGINAL, INTRO_OFF };
static int mode, pad_enabled;
static struct {
  uint32_t self, package, vtable, sequence, buttons;
} baseline;

/* These are the original lifted functions. Only their indirect vtable
 * dispatch is patched; calls below retain the original guest stack ABI.
 * The saved catalog and emitted call sites contain no direct callers. */
void sub_004de9f0(CPU *);
void sub_004deb30(CPU *);
void sub_004dec50(CPU *);
void dispatch_patch(uint32_t, guest_fn_t);

static uint32_t pad_buttons(void) {
  PadState state;
  return pad_enabled && gamepad_read(&state) ? state.buttons : 0;
}

static void rebase(CPU *c) {
  baseline.self = c->ecx;
  baseline.package = MR32(c->ecx + 12u);
  baseline.vtable = MR32(c->ecx);
  baseline.sequence = kbd_ev_head();
  baseline.buttons = pad_buttons();
}

static const char *new_press(void) {
  const char *key = NULL;
  uint32_t head = kbd_ev_head();
  if (head - baseline.sequence > 256u) baseline.sequence = head - 256u;
  for (uint32_t sequence = baseline.sequence; sequence != head; sequence++) {
    KbdEv event;
    if (kbd_ev_get(sequence, &event) == 1 && event.down && !key) {
      switch (event.dik) {
      case 0x01: key = "Escape"; break;
      case 0x1c: case 0x9c: key = "Enter"; break;
      case 0x39: key = "Space"; break;
      }
    }
  }
  baseline.sequence = head;
  uint32_t buttons = pad_buttons();
  if (!key && (buttons & ~baseline.buttons &
      ((1u << PAD_A) | (1u << PAD_B) | (1u << PAD_START))))
    key = "controller";
  baseline.buttons = buttons;
  return key;
}

static void movie_message(CPU *c, guest_fn_t original, const char *name,
                          int native_skip) {
  uint32_t message = MR32(c->esp + 4u);
  if (mode == INTRO_ORIGINAL) {
    original(c);
    return;
  }
  if (baseline.self != c->ecx ||
      baseline.package != MR32(c->ecx + 12u) ||
      baseline.vtable != MR32(c->ecx))
    rebase(c);

  const char *by = NULL;
  uint32_t replacement = 0;
  if (mode == INTRO_OFF && message == MSG_TICK) {
    by = "off";
    replacement = MSG_END;
  } else if (mode == INTRO_SKIPPABLE) {
    if (message == MSG_TICK) by = new_press();
    /* Preserve the game's own Enter/click/A/Start route. The extra keys
     * are observed on ticks because boot packages may ignore PAD_BACK. */
    else if (message == MSG_ACCEPT || message == MSG_START || message == MSG_BACK)
      by = "front-end input";
    if (by) replacement = native_skip ? MSG_ACCEPT : MSG_END;
    if (by && native_skip && (message == MSG_ACCEPT || message == MSG_START))
      replacement = message;
  }

  if (replacement) {
    fprintf(stderr, "[nfsu1 intro] %s skipped by %s\n", name, by);
    MR32(c->esp + 4u) = replacement;
  }
  /* Baseline again on the next screen, even if the allocator reuses both
   * addresses. Buffered input from this movie must not skip its successor. */
  if (replacement || message == MSG_END) baseline.self = 0;
  original(c);
}

static void intro_message(CPU *c) {
  movie_message(c, sub_004de9f0, "intro", 1);
}
static void bumper_message(CPU *c) {
  movie_message(c, sub_004deb30, "EA/THX logo", 0);
}
static void psa_message(CPU *c) {
  movie_message(c, sub_004dec50, "PSA", 1);
}

void nfsu1_intro_install(void) {
  const char *setting = getenv("NFSU1_INTRO");
  mode = INTRO_SKIPPABLE;
  if (setting && *setting) {
    if (!strcasecmp(setting, "original")) mode = INTRO_ORIGINAL;
    else if (!strcasecmp(setting, "off") || !strcasecmp(setting, "no") ||
             !strcasecmp(setting, "false") || !strcmp(setting, "0"))
      mode = INTRO_OFF;
    else if (strcasecmp(setting, "skippable"))
      fprintf(stderr, "[nfsu1 intro] invalid NFSU1_INTRO=%s; using skippable\n", setting);
  }
  const char *pad = getenv("NFSU2_PAD");
  pad_enabled = (pad && !strcasecmp(pad, "hotplug")) ||
                gamepad_env_flag("NFSU2_PAD", 1);
  memset(&baseline, 0, sizeof baseline);
  dispatch_patch(0x004de9f0u, intro_message);
  dispatch_patch(0x004deb30u, bumper_message);
  dispatch_patch(0x004dec50u, psa_message);
  fprintf(stderr, "[nfsu1 intro] startup movies: %s\n",
          mode == INTRO_OFF ? "off" : mode == INTRO_ORIGINAL ? "original" : "skippable");
}
