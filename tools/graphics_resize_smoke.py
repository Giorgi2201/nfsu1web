#!/usr/bin/env python3
"""Exercise actual resolution selection and canvas resize tracking natively.

This focused host check uses handwritten runtime functions and synthetic canvas
sizes. It reads no game data and does not establish browser/game compatibility.
"""
import argparse
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include "cpu.h"
#include "nfsu1_widescreen.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

uint8_t *g_mem;
void __real_sub_0041c680(CPU *c){ (void)c; }
void __real_sub_00410e50(CPU *c){ (void)c; }
int nfsu1_graphics_size(uint32_t, uint32_t, uint32_t *, uint32_t *);

#define ENVC getenv
#define GW_ATTACHED 1
#define ald(p) (*(p))
static struct { unsigned view_w, view_h, attached; } control;
static typeof(control) *g_ctl = &control;
static unsigned g_view_used_w, g_view_used_h;
static double clock_ms;
static unsigned reset_requests;
static void gw_init(void){}
static double now_ms(void){ return clock_ms; }
void com_request_reset(void){ reset_requests++; }
/* ACTUAL_VIEW_WH */
/* ACTUAL_METAL_VIEW_SIZE */
/* ACTUAL_VIEW_FOLLOW */

static uint32_t g_req_w, g_req_h;
static float g_aspfix = 1.f, mapping = 1.f;
static int g_cur_row;
static uint32_t g_modes[16][2];
static int tbl_row(uint32_t w, uint32_t h){ (void)w; (void)h; return 0; }
static int modemap_on(void){ return 0; }
static void modes_refresh(void){}
static void ws_set_mapping(float scale){ mapping = scale; }
static float ws_ui_x(void){ return 1.f; }
static float ws_ui_y(void){ return 1.f; }
void metal_set_game_size(unsigned w, unsigned h){ (void)w; (void)h; }
void metal_set_ui_aspect(float x, float y){ (void)x; (void)y; }
void metal_native_size(unsigned w, unsigned h, unsigned *ow, unsigned *oh){
    (void)w; (void)h; (void)ow; (void)oh;
    assert(!"dynamic resolution entered legacy native-size path");
}
/* ACTUAL_RES_PICK */

static void pick(unsigned gw, unsigned gh, unsigned vw, unsigned vh,
                 unsigned expected_w, unsigned expected_h){
    control.view_w = vw; control.view_h = vh;
    uint32_t dw = 0, dh = 0;
    res_pick(gw, gh, &dw, &dh);
    assert(dw == expected_w && dh == expected_h);
    if (!nfsu1_widescreen_active())
        assert((uint64_t)dw * gh == (uint64_t)dh * gw);
    assert(g_aspfix == 1.f && mapping == 1.f);
    assert(g_view_used_w == (vw & ~1u) && g_view_used_h == (vh & ~1u));
}

int main(void){
    unsetenv("NFSRES"); unsetenv("ASPFIX"); unsetenv("NFSNATIVE");
    unsetenv("NFSU1_DYNAMIC_RESOLUTION");
    uint32_t dw = 123, dh = 456;
    assert(nfsu1_graphics_size(640, 480, &dw, &dh) == 0);
    assert(dw == 123 && dh == 456 && g_view_used_w == 0);
    setenv("NFSU1_DYNAMIC_RESOLUTION", "1", 1);
    setenv("NFSU1_WIDESCREEN", "0", 1);
    control.attached = GW_ATTACHED;
    pick(640, 480, 1920, 1080, 1440, 1080);

    /* Live resize arms one reset only after the existing 250 ms debounce. */
    control.view_w = 2560; control.view_h = 1440;
    clock_ms = 1000; view_follow(); assert(reset_requests == 0);
    clock_ms = 1249; view_follow(); assert(reset_requests == 0);
    clock_ms = 1251; view_follow(); assert(reset_requests == 1);
    pick(640, 480, 2560, 1440, 1920, 1440);
    clock_ms = 4000; view_follow(); assert(reset_requests == 1);

    control.view_w = 640; control.view_h = 360;
    clock_ms = 5000; view_follow(); assert(reset_requests == 1);
    clock_ms = 5251; view_follow(); assert(reset_requests == 2);
    pick(640, 480, 640, 360, 480, 360);
    pick(1280, 1024, 1920, 1080, 1350, 1080);
    pick(1280, 1024, 640, 360, 450, 360);
    pick(640, 480, 320, 240, 320, 240);
    pick(640, 480, 8192, 8192, 8192, 6144);
    pick(640, 480, 1601, 901, 1200, 900);
    /* Oversized displays use the same bounded view for selection and follow,
     * so consuming a resize does not immediately request another reset. */
    control.view_w = 16384; control.view_h = 8192;
    clock_ms = 8000; view_follow(); assert(reset_requests == 2);
    clock_ms = 8251; view_follow(); assert(reset_requests == 3);
    res_pick(640, 480, &dw, &dh);
    assert(dw == 5460 && dh == 4095);
    assert(g_view_used_w == 8192 && g_view_used_h == 4096);
    clock_ms = 11000; view_follow(); assert(reset_requests == 3);

    /* Default widescreen fills the canvas and keeps host mapping at identity.
     * Use the real widescreen adapter to exercise its active-state handshake. */
    unsetenv("NFSU1_WIDESCREEN");
    pick(640, 480, 1920, 1080, 1920, 1080);
    assert(nfsu1_widescreen_active());
    pick(1280, 1024, 1601, 901, 1600, 900);
    assert(nfsu1_widescreen_active());
    pick(640, 480, 800, 600, 800, 600);
    assert(nfsu1_widescreen_active());
    /* The scene uses the whole canvas through wide/portrait transitions;
     * the menu's logical canvas is fitted separately by the encoder. */
    pick(640, 480, 1500, 1650, 1500, 1650);
    assert(nfsu1_widescreen_active());
    pick(640, 480, 600, 1000, 600, 1000);
    pick(640, 480, 1338, 1000, 1338, 1000);
    pick(640, 480, 1920, 1080, 1920, 1080);
    assert(nfsu1_widescreen_active());
    setenv("NFSU1_WIDESCREEN", "0", 1);
    pick(640, 480, 1920, 1080, 1440, 1080);
    assert(!nfsu1_widescreen_active());
    puts("PASS: actual res_pick follows canvas up/down, preserves legacy aspects, fills widescreen views, and arms the GPU host's debounced reset tracking");
    return 0;
}
'''


def function(source, signature, boundary):
    start = source.index(signature)
    end = source.index(boundary, start)
    result = source[start:end].strip()
    if not result.endswith("}"):
        raise ValueError(f"unexpected extraction boundary for {signature}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path,
                        default=ROOT / "work/upstream/nfsu2-web")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "out/graphics-resize-smoke")
    parser.add_argument("--cc", default="clang")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    com = (upstream / "runtime/com.c").read_text()
    gpu = (upstream / "runtime/web/gpu_web.c").read_text()
    res_pick = function(com, "static void res_pick(", "\n/* Copy ONLY")
    if "nfsu1_graphics_size" not in res_pick:
        raise ValueError("runtime/com.c does not integrate nfsu1_graphics_size")
    harness = HARNESS.replace("/* ACTUAL_RES_PICK */", res_pick)
    for marker, signature, boundary in (
        ("VIEW_WH", "static void view_wh(", "\n/* the view size"),
        ("METAL_VIEW_SIZE", "void metal_view_size(", "\n/* The canvas changed"),
        ("VIEW_FOLLOW", "static void view_follow(", "\n/* a size with"),
    ):
        harness = harness.replace(f"/* ACTUAL_{marker} */",
                                  function(gpu, signature, boundary))
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / "graphics-resize.c"
    executable = output / "graphics-resize"
    source.write_text(harness)
    subprocess.run([args.cc, "-std=gnu11", "-O1", "-Wall", "-Wextra",
                    "-I", str(upstream / "runtime"),
                    "-I", str(ROOT / "runtime"), str(source),
                    str(ROOT / "runtime/nfsu1_graphics.c"),
                    str(ROOT / "runtime/nfsu1_widescreen.c"), "-lm",
                    "-o", str(executable)], check=True)
    return subprocess.run([str(executable)], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
