#!/usr/bin/env python3
"""Compile the patched FE draw classifier against representative matrices.

This checks host draw selection only; it does not validate game rendering.
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--com", type=Path,
                        default=ROOT / "work/upstream/nfsu2-web/runtime/com.c")
    args = parser.parse_args()
    source = args.com.read_text()
    start = source.index("static float nfsu1_fe_canvas(")
    end = source.index("\nstatic int draw_up(", start)
    classifier = source[start:end]
    harness = r'''
#include <assert.h>
#include <math.h>
#include <stdint.h>
typedef struct { float f[256][4]; } VSConst;
typedef struct { int cx, cy, cw; } VSProg;
static uint32_t g_bb_w = 1920, g_bb_h = 1080, state = 3;
typedef struct { uint32_t esp, eip; } CPU;
static CPU cpu = {0x2000u, 0x0040C2D6u}, *g_com_cpu = &cpu;
static int active = 1;
uint32_t read_word(uint32_t address){ return address == 0x0077A920u ? state : 0x12345678u; }
#define MR32(address) read_word(address)
int mem_is_committed(uint32_t address){ return address < 0x100000u; }
int nfsu1_widescreen_active(void){ return active; }
int vs_pos_creg(const VSProg *p, int *w){ *w = p->cw; return p->cx; }
int vs_pos_creg_y(const VSProg *p){ return p->cy; }
''' + classifier + r'''
int main(void){
    VSConst k = {0};
    VSProg p = {0, 1, 3};
    k.f[0][0] = k.f[1][1] = k.f[2][2] = k.f[3][3] = 1.f;
    assert(fabsf(nfsu1_fe_canvas(&k, &p) - 1.f) < 1e-6f);
    /* A world camera must never inherit the preceding menu's clip. */
    k.f[3][2] = 1.f;
    assert(nfsu1_fe_canvas(&k, &p) == 0.f);
    k.f[3][2] = 0.f;
    state = 6;
    assert(nfsu1_fe_canvas(&k, &p) == 0.f);
    state = 3;
    assert(fabsf(nfsu1_fe_canvas(&k, 0) - 1.f) < 1e-6f);
    cpu.eip = 0x0040C4A8u;
    assert(fabsf(nfsu1_fe_canvas(&k, 0) - 1.f) < 1e-6f);
    cpu.eip = 0x0040D9A5u;
    assert(nfsu1_fe_canvas(&k, &p) == 0.f);
    assert(nfsu1_fe_canvas(&k, 0) == 0.f);
    cpu.eip = 0x0040C2D6u;
    g_com_cpu = 0;
    assert(nfsu1_fe_canvas(&k, &p) == 0.f);
    g_com_cpu = &cpu;
    active = 0;
    assert(nfsu1_fe_canvas(&k, &p) == 0.f);
    active = 1;
    g_bb_w = 800; g_bb_h = 600;
    assert(nfsu1_fe_canvas(&k, &p) == 1.f);
    g_bb_w = 600; g_bb_h = 800;
    assert(nfsu1_fe_canvas(&k, &p) == 1.f);
    state = 6;
    assert(nfsu1_fe_canvas(&k, &p) == 1.f);
    return 0;
}
'''
    with tempfile.TemporaryDirectory(prefix="nfsu1-fe-clip-") as temp:
        temp = Path(temp)
        c_file, executable = temp / "clip.c", temp / "clip"
        c_file.write_text(harness)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        str(c_file), "-lm", "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
    print("PASS: logical UI canvas selects menu and narrow HUD draws while excluding world/composites")


if __name__ == "__main__":
    main()
