#!/usr/bin/env python3
"""Check physical text/frontend input separately from remapped race actions.

Compiles actual keyboard.c and dinput_kbd.c plus the actual web key handlers.
Memory, COM and registry are stubbed; no game data, browser or gameplay is used.
"""
import argparse
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include "cpu.h"
#include "kbd.h"
#include "input_proto.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
uint8_t *g_mem;
uint8_t g_cbits[1u << 15];
void mem_commit(uint32_t p, uint32_t n){ assert((uint64_t)p + n < 8u*1024u*1024u); }
uint32_t call_guest(CPU *c, uint32_t fn, int n, const uint32_t *a){
    (void)c; (void)fn; (void)n; (void)a; return 0;
}
uint32_t com_scratch(uint32_t n){ (void)n; return 0x10000; }
uint32_t com_devinst(int k){ (void)k; return 0x11000; }
int win32_reg_get_str(const char *n, char *out, unsigned cap){
    (void)n; (void)out; (void)cap; return 0;
}
void win32_reg_set_str(const char *n, const char *v){ (void)n; (void)v; }
void win32_reg_del(const char *n){ (void)n; }
void win32_reg_flush(void){}
const char *kbdmac_layout_name(unsigned dik){ (void)dik; return 0; }
uint32_t host_ms(void){ return 123; }
static struct { uint32_t m, w, l; } messages[128];
static unsigned nmessages;
void win32_post_message(uint32_t m, uint32_t w, uint32_t l){
    assert(nmessages < 128);
    messages[nmessages].m = m; messages[nmessages].w = w; messages[nmessages++].l = l;
}
int win32_msg_room(void){ return 1024; }
#define WM_KEYDOWN 0x0100u
#define WM_KEYUP 0x0101u
#define WM_CHAR 0x0102u
#define WM_DEADCHAR 0x0103u
#define WM_SYSKEYDOWN 0x0104u
#define WM_SYSKEYUP 0x0105u
#define WM_SYSCHAR 0x0106u
#define WM_SYSDEADCHAR 0x0107u
#define DIK_LMENU 0x38u
#define DIK_RMENU 0xb8u
/* ACTUAL_WEB_KEY_HANDLERS */
static void mouse_release_all(void){}
#include "dinput_kbd.c"

static void make_map(unsigned dev, unsigned af, unsigned rg,
                     const unsigned *keys, const unsigned *ids, unsigned n){
    MR32(af) = 328; MR32(af+4) = 40; MR32(af+8) = 4*n;
    MR32(af+12) = n; MR32(af+16) = rg; MR32(af+40) = 16;
    for (unsigned i = 0; i < n; i++){
        MR32(rg+i*40) = ids[i]; MR32(rg+i*40+4) = 0x81000400u | keys[i];
    }
    unsigned a[] = {dev, af, 0, 2, 0};
    assert(dikbd_call(0, dev, "BuildActionMap", 4, a) == 0);
    assert(dikbd_call(0, dev, "SetActionMap", 4, a) == 0);
    assert(dikbd_call(0, dev, "Acquire", 1, a) == 0);
}
static unsigned read_events(unsigned dev){
    MR32(0x5000) = 16;
    unsigned a[] = {dev, 20, 0x4000, 0x5000, 0};
    assert(dikbd_call(0, dev, "GetDeviceData", 5, a) == 0);
    return MR32(0x5000);
}
static void expect_event(unsigned dev, unsigned id, int down){
    assert(read_events(dev) == 1);
    assert(MR32(0x4010) == id);
    assert(MR32(0x4004) == (down ? 0x80u : 0u));
}
static void event(unsigned dik, unsigned race, unsigned vk, unsigned ch, int down){
    InEv e = {0}; e.dik = dik; e.vk = vk; e.a = race;
    if (ch){ e.nch = 1; e.ch[0] = ch; }
    if (down) key_down(&e); else key_up(&e);
}
int main(void){
    g_mem = calloc(1, 8u*1024u*1024u); assert(g_mem);
    memset(g_cbits, 255, sizeof g_cbits);
    const unsigned race = 0x100, frontend = 0x200, raw = 0x300;
    const unsigned keys[] = {0xc8, 0x36, 0x39, 0xd2, 0xd3};
    const unsigned ids[] = {1, 5, 6, 7, 8};
    make_map(race, 0x719798, 0x2000, keys, ids, 5);
    const unsigned fe_keys[] = {0xc8, 0x11, 0x23};
    const unsigned fe_ids[] = {16, 40, 41};
    make_map(frontend, 0x7198e0, 0x3000, fe_keys, fe_ids, 3);

    /* Real raw data-format installation, with W, Up and H objects. */
    MR32(0x6004) = 16; MR32(0x600c) = 256; MR32(0x6010) = 3; MR32(0x6014) = 0x7000;
    for (unsigned i = 0; i < 3; i++){
        MR32(0x7004+i*16) = fe_keys[i]; MR32(0x7008+i*16) = 4 | fe_keys[i] << 8;
    }
    unsigned a[] = {raw, 0x6000, 0, 0, 0};
    assert(dikbd_call(0, raw, "SetDataFormat", 2, a) == 0);
    assert(dikbd_call(0, raw, "Acquire", 1, a) == 0);

    event(0x11, 0xc8, 'W', 'w', 1);
    expect_event(race, 1, 1); expect_event(frontend, 40, 1);
    assert(read_events(raw) == 1 && MR32(0x4000) == 0x11);
    kbd_pump();
    assert(nmessages == 2 && messages[0].m == WM_KEYDOWN && messages[0].w == 'W');
    assert(messages[1].m == WM_CHAR && messages[1].w == 'w');
    assert(((messages[0].l >> 16) & 0xffu) == 0x11);
    uint8_t physical[256], driving[256];
    kbd_state(physical, 256); kbd_race_state(driving, 256);
    assert(physical[0x11] == 0x80 && physical[0xc8] == 0);
    assert(driving[0x11] == 0 && driving[0xc8] == 0x80);

    /* Up and W independently type/send messages but share one race hold. */
    event(0xc8, 0, 0x26, 0, 1);
    assert(read_events(race) == 0); expect_event(frontend, 16, 1);
    event(0x11, 0, 'W', 0, 0); /* release uses cached target, not changed metadata */
    assert(read_events(race) == 0); expect_event(frontend, 40, 0);
    event(0xc8, 0, 0x26, 0, 0);
    expect_event(race, 1, 0); expect_event(frontend, 16, 0);
    kbd_pump(); nmessages = 0;
    (void)read_events(raw);

    /* A letter mapped to a modifier must still produce its original WM_CHAR. */
    event(0x23, 0x36, 'H', 'h', 1);
    expect_event(race, 5, 1); expect_event(frontend, 41, 1);
    assert(read_events(raw) == 1 && MR32(0x4000) == 0x23);
    event(0x23, 0, 'H', 0, 0);
    expect_event(race, 5, 0); expect_event(frontend, 41, 0);
    kbd_pump();
    assert(nmessages == 3 && messages[0].m == WM_KEYDOWN && messages[0].w == 'H');
    assert(messages[1].m == WM_CHAR && messages[1].w == 'h');
    assert(messages[2].m == WM_KEYUP && messages[2].w == 'H');

    /* A focus loss releases both channels; duplicate releases cannot underflow. */
    event(0x11, 0xc8, 'W', 'w', 1); expect_event(race, 1, 1);
    release_all("smoke focus loss", 0); expect_event(race, 1, 0);
    event(0x11, 0, 'W', 0, 0); assert(read_events(race) == 0);
    kbd_state(physical, 256); kbd_race_state(driving, 256);
    for (unsigned i = 0; i < 256; i++) assert(!physical[i] && !driving[i]);

    /* Switching the same device between frontend and race selects the right ring. */
    a[0] = race; a[1] = 0x7198e0; a[2] = 0; a[3] = 0;
    assert(dikbd_call(0, race, "SetActionMap", 4, a) == 0);
    event(0x11, 0xc8, 'W', 'w', 1); expect_event(race, 40, 1);
    a[1] = 0x719798; assert(dikbd_call(0, race, "SetActionMap", 4, a) == 0);
    assert(read_events(race) == 0); /* old events are not replayed across maps */
    a[1] = 20; a[2] = 0x8000;
    assert(dikbd_call(0, race, "GetDeviceState", 3, a) == 0 && MR32(0x8000) == 0x80);
    event(0x11, 0, 'W', 0, 0); expect_event(race, 1, 0);
    puts("PASS: original WM text, frontend/raw keys, race-only remaps, shared holds, map switches and focus release.");
    free(g_mem); return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT / "work/upstream/nfsu2-web")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "out/keyboard-runtime-smoke")
    args = parser.parse_args()
    runtime = args.upstream.resolve() / "runtime"
    web = (runtime / "web/input_web.c").read_text()
    start = web.index("/* alttext:")
    end = web.index("/* ---- mouse (", start)
    handlers = web[start:end]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / "keyboard-runtime.c"
    source.write_text(HARNESS.replace("/* ACTUAL_WEB_KEY_HANDLERS */", handlers))
    executable = output / "keyboard-runtime"
    subprocess.run(["clang", "-std=c11", "-O1", "-Wall", "-Wextra", "-pthread",
                    "-I", str(runtime), "-I", str(runtime / "web"), str(source),
                    str(runtime / "keyboard.c"), str(runtime / "dikeys.c"),
                    "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    main()
