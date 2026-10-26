#!/usr/bin/env python3
"""Check the patched UI pointer mapping natively, without a browser/game."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    upstream = ROOT / "work/upstream/nfsu2-web"
    relative = Path("runtime/web/input_web.c")
    backup = upstream / ".nfsu1-profile" / relative
    original = backup if backup.exists() else upstream / relative
    with tempfile.TemporaryDirectory(prefix="nfsu1-mouse-canvas-") as directory:
        temporary = Path(directory)
        source = temporary / relative
        source.parent.mkdir(parents=True)
        source.write_text(original.read_text())
        subprocess.run(["patch", "-p1", "-d", str(temporary), "-i",
                        str(ROOT / "patches/nfsu2-web/runtime/web/input_web.c.patch")], check=True)
        implementation = source.read_text()
        start = implementation.index("static double g_last_nx")
        end = implementation.index('\n/* autotest "click', start)
        harness = r'''
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdatomic.h>
typedef struct { int a, b, flags; } InEv;
static unsigned cw = 1920, ch = 1080, state = 3;
static _Atomic int g_ui_asp = 10000, g_ui_asp_y = 10000;
static _Atomic int g_mouse_x, g_mouse_y, g_mouse_dx, g_mouse_dy;
static _Atomic unsigned mailbox[64];
#define MH(i) mailbox[i]
#define IM_MOUSE_X 23
#define IM_MOUSE_Y 24
#define MR32(address) state
int nfsu1_widescreen_active(void){ return 1; }
void nfsu1_widescreen_device_size(unsigned *w, unsigned *h){ *w = cw; *h = ch; }
void metal_game_size(unsigned *w, unsigned *h){ *w = 1280; *h = 720; }
static unsigned mouse_mk(int flags){ return (unsigned)flags; }
static unsigned mouse_lp(void){ return 0; }
void kbd_post_mousemove(unsigned a, unsigned b){ (void)a; (void)b; }
''' + implementation[start:end] + r'''
static void move(double x, double y){
    InEv e = { (int)lround(x * 65536.), (int)lround(y * 65536.), 0 };
    mouse_move(&e);
}
static void expect(int x, int y){
    assert(abs(atomic_load(&g_mouse_x) - x) <= 1);
    assert(abs(atomic_load(&g_mouse_y) - y) <= 1);
}
int main(void){
    move(.5, .5); expect(320, 240);
    move(.125, .5); expect(0, 240);
    move(.3125, .25); expect(160, 120);
    atomic_store(&g_mouse_dx, 0); atomic_store(&g_mouse_dy, 0);
    cw = 600; ch = 1000;
    move(.5, .5); expect(320, 240);
    assert(atomic_load(&g_mouse_dx) == 0 && atomic_load(&g_mouse_dy) == 0);
    move(.25, .275); expect(160, 0);
    move(.75, .725); expect(480, 479);
    /* Interactive overlays use the centered canvas even during a race. */
    state = 6;
    move(.5, .5); expect(320, 240);
    atomic_store(&g_mouse_dx, 0); atomic_store(&g_mouse_dy, 0);
    cw = 1920; ch = 1080;
    move(.5, .5); expect(320, 240);
    assert(atomic_load(&g_mouse_dx) == 0 && atomic_load(&g_mouse_dy) == 0);
    move(.125, .5); expect(0, 240);
    move(.875, .5); expect(639, 240);
    atomic_store(&g_mouse_dx, 0); atomic_store(&g_mouse_dy, 0);
    /* Loading can overlap flow 6. State changes never change pointer units. */
    const unsigned centered_states[] = {1, 2, 3, 4, 5, 6, 7, 8};
    for (unsigned i = 0; i < sizeof centered_states / sizeof centered_states[0]; i++){
        state = 6;
        move(.125, .5); expect(0, 240);
        atomic_store(&g_mouse_dx, 0); atomic_store(&g_mouse_dy, 0);
        state = centered_states[i];
        move(.125, .5); expect(0, 240);
        assert(atomic_load(&g_mouse_dx) == 0 && atomic_load(&g_mouse_dy) == 0);
        move(.875, .5); expect(639, 240);
    }
    return 0;
}
'''
        c_file = temporary / "mouse.c"
        c_file.write_text("#include <stdlib.h>\n" + harness)
        executable = temporary / "mouse"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(c_file), "-lm", "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
    print("PASS: UI pointer mapping fits wide/narrow canvases and rebases on layout changes")


if __name__ == "__main__":
    main()
