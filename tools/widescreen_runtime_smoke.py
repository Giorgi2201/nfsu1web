#!/usr/bin/env python3
"""Focused native smoke for nfsu1_widescreen hooks (no game emission)."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "runtime/nfsu1_widescreen.c"


def main():
    impl = SRC.read_text()
    if '#include "nfsu1_widescreen.h"' not in impl:
        raise SystemExit("expected nfsu1_widescreen.h include")
    impl = impl.replace('#include "nfsu1_widescreen.h"\n', "")

    harness = r'''
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

uint8_t g_mem[0x01000000];
typedef struct CPU {
    uint32_t eax, ecx, edx, ebx, esp, ebp, esi, edi;
    uint32_t eip;
    int top;
    double st[8];
} CPU;
#define MR32(a) (*(uint32_t *)(g_mem + (uint32_t)(a)))
#define MRF32(a) (*(float *)(g_mem + (uint32_t)(a)))
#define ST(n) (c->st[(c->top + (n)) & 7])
#define HOOK_SITE(va) (va##u)

void nfsu1_widescreen_set_display_aspect(float aspect);
void nfsu1_widescreen_set_resolution(unsigned width, unsigned height);
int nfsu1_widescreen_active(void);
float nfsu1_widescreen_hud_pos_x(void);
int nfsu1_ws_hook(CPU *c, uint32_t ip);
void metal_set_game_size(unsigned w, unsigned h){ (void)w; (void)h; }
int mem_is_committed(uint32_t a){ return a < sizeof g_mem; }
void metal_get_cursor(int *x, int *y){ if (x) *x = 320; if (y) *y = 240; }

''' + impl + r'''

int main(void){
    CPU cpu_storage = {0};
    CPU *c = &cpu_storage;
    assert(nfsu1_ws_hook(c, 0x12345678u) == 0);

    nfsu1_widescreen_set_display_aspect(16.0f / 9.0f);
    nfsu1_widescreen_set_resolution(1920, 1080);
    assert(nfsu1_widescreen_active());
    /* UI projection remains logical across host resolution changes. */
    assert(nfsu1_widescreen_hud_pos_x() == 320.f);
    assert(nfsu1_widescreen_hud_scale_x() == 1.f / 320.f);

    MRF32(0x006CC910u) = 320.0f;
    MRF32(0x006CC914u) = 1.0f / 320.0f;
    MR32(0x0071A96Cu) = 800;
    MR32(0x0071A970u) = 600;
    MR32(0x00701034u) = 800;
    assert(nfsu1_ws_hook(c, 0x0040875Au) == 1);
    assert(MR32(0x0071A96Cu) == 1066u);
    assert(nfsu1_widescreen_hud_pos_x() == 320.f);

    assert(MRF32(0x006CC910u) == 320.0f);
    assert(MRF32(0x006CC914u) == 1.0f / 320.0f);
    assert(nfsu1_widescreen_hud_scale_x() == 1.f / 320.f);
    c->esp = 0x2000;
    const uint32_t quads[] = {0x004F1FD7u, 0x004F225Cu, 0x004F25D1u};
    for (unsigned i = 0; i < 3; i++) {
        float extents[] = {-0.5f, -0.5f, 0.5f, 0.5f};
        memcpy(g_mem + c->esp, extents, sizeof extents);
        assert(nfsu1_ws_hook(c, quads[i]) == 1);
        assert(memcmp(g_mem + c->esp, extents, sizeof extents) == 0);
    }
    ST(0) = 320.0;
    nfsu1_ws_hook(c, 0x0058E5C3u);
    assert(ST(0) == 320.0);

    c->ebp = 0x1000;
    c->esp = 0x2000;
    MR32(c->ebp + 4) = 0;
    c->top = 0;
    ST(0) = 0.75;
    assert(nfsu1_ws_hook(c, 0x0040DDE0u) == 1);
    assert(ST(0) == 1.0);
    assert(MR32(c->esp + 0x20) == 0x3F800000u);

    uint32_t before = 100;
    c->eax = before;
    assert(nfsu1_ws_hook(c, 0x004B8CF0u) == 1);
    assert(c->eax == before);

    /* FE uses one unmodified logical frame. The host fits that frame once;
     * text, quad centres and hit tests must share the same original units. */
    MR32(0x0077A920u) = 3u;
    assert(nfsu1_widescreen_hud_pos_x() == 320.f);
    assert(nfsu1_widescreen_hud_scale_x() == 1.f / 320.f);
    MRF32(c->esp + 0x80u) = 320.f;
    nfsu1_ws_hook(c, 0x004F20A7u);
    assert(MRF32(c->esp + 0x80u) == 320.f);
    c->eax = before;
    nfsu1_ws_hook(c, 0x004B8CF0u);
    assert(c->eax == before);
    MR32(0x0077A920u) = 6u;
    nfsu1_widescreen_set_resolution(2560, 1080);
    assert(nfsu1_widescreen_hud_pos_x() == 320.f);
    nfsu1_widescreen_set_display_aspect(.75f);
    assert(nfsu1_widescreen_active());
    assert(nfsu1_widescreen_hud_pos_x() == 320.f);
    assert(nfsu1_widescreen_hud_scale_x() == 1.f / 320.f);

    nfsu1_widescreen_set_display_aspect(4.0f / 3.0f);
    assert(nfsu1_widescreen_active());
    assert(nfsu1_widescreen_hud_pos_x() == 320.0f);
    assert(nfsu1_widescreen_hud_scale_x() == 1.0f / 320.0f);
    c->eax = before;
    assert(nfsu1_ws_hook(c, 0x004B8CF0u) == 1);
    assert(c->eax == before);
    /* Cached drag/minimap/lap transforms must never capture host aspect.
     * Repeated draws/resizes preserve their bits and live quad centres. */
    const float aspects[] = {16.f/9.f, 1984.f/1278.f, 21.f/9.f, .75f, 16.f/9.f};
    const uint32_t states[] = {3u, 6u, 7u};
    c->ecx = 0x3000u; c->eax = 0x4000u; c->ebx = 0x5000u;
    MR32(c->ecx + 0x68u) = 0x42AC0000u;
    MR32(c->ecx + 0x6Cu) = 0x43700000u;
    MR32(c->eax + 0x1Cu) = 0xC3960000u;
    MR32(c->eax + 0x20u) = 0xC1980000u;
    MR32(c->ebx + 0x1Cu) = 0xC35D0000u;
    MR32(c->ebx + 0x20u) = 0xC31F0000u;
    for (unsigned i = 0; i < sizeof aspects / sizeof aspects[0]; i++){
        nfsu1_widescreen_set_display_aspect(aspects[i]);
        for (unsigned j = 0; j < sizeof states / sizeof states[0]; j++){
            MR32(0x0077A920u) = states[j];
            CPU before_cpu = *c;
            uint8_t before_mem[0x4000];
            memcpy(before_mem, g_mem + 0x2000, sizeof before_mem);
            nfsu1_ws_hook(c, 0x00590DDFu);
            nfsu1_ws_hook(c, 0x0058E5B2u);
            nfsu1_ws_hook(c, 0x004F6DABu);
            nfsu1_ws_hook(c, 0x004F18D1u);
            nfsu1_ws_hook(c, 0x004F20A7u);
            assert(!memcmp(before_mem, g_mem + 0x2000, sizeof before_mem));
            assert(!memcmp(&before_cpu, c, sizeof before_cpu));
            assert(nfsu1_widescreen_hud_pos_x() == 320.f);
            assert(nfsu1_widescreen_hud_scale_x() == 1.f / 320.f);
        }
    }
    /* Cached FE element identity, rather than glyph position, chooses its
     * edge. Text/backing and animated pieces therefore move together. */
    c->eip = 0x0040C2D6u;
    c->ebp = 0x1000u; c->ebx = 0x2000u;
    MR32(c->ebp + 4u) = 0x00514BC7u;
    MR32(c->ebx + 8u) = 0x3000u;
    MR32(0x302Cu) = 0x4000u;
    const unsigned sizes[][2] = {{1920,1080}, {2560,1080}, {1984,1278}, {1920,1080}};
    for (unsigned i = 0; i < sizeof sizes / sizeof sizes[0]; i++){
        nfsu1_widescreen_set_resolution(sizes[i][0], sizes[i][1]);
        MR32(0x0077A920u) = 6;
        MR32(0x401Cu) = 0xC3960000u; MR32(0x4020u) = 0xC1980000u; /* Drag tach */
        assert(nfsu1_widescreen_ui_canvas(c) == 2.f);
        MR32(0x401Cu) = 0x43AB9AABu; MR32(0x4020u) = 0x43512639u; /* Turbo */
        assert(nfsu1_widescreen_ui_canvas(c) == 3.f);
        MR32(0x401Cu) = 0xC2EA0000u; MR32(0x4020u) = 0x43460000u; /* Results left column belongs on right */
        assert(nfsu1_widescreen_ui_canvas(c) == 3.f);
        /* Child local transforms do not match a root table entry. The
         * composed cached matrix places every glyph/quad on the same side. */
        MR32(0x401Cu) = 0; MR32(0x4020u) = 0;
        MRF32(c->ebx + 0x50u) = 210.79167f; /* Drag GaugeCluster origin */
        assert(nfsu1_widescreen_ui_canvas(c) == 2.f);
        MRF32(c->ebx + 0x50u) = 543.f; /* Drag speed group origin */
        assert(nfsu1_widescreen_ui_canvas(c) == 3.f);
        MRF32(c->ebx + 0x50u) = 320.f; /* Centered messages */
        assert(nfsu1_widescreen_ui_canvas(c) == 1.f);
        MR32(0x0077A920u) = 3;
        assert(nfsu1_widescreen_ui_canvas(c) == 1.f);
    }
    nfsu1_widescreen_set_display_aspect(0.f);
    assert(!nfsu1_widescreen_active());

    printf("widescreen_runtime_smoke ok\n");
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "widescreen_hud.inc").write_text((ROOT / "runtime/widescreen_hud.inc").read_text())
        (tmp / "smoke.c").write_text(harness)
        exe = tmp / "smoke"
        subprocess.check_call([
            "cc", "-O0", "-std=c11", "-I", str(tmp), "-o", str(exe), str(tmp / "smoke.c"), "-lm",
        ])
        out = subprocess.check_output([str(exe)], text=True)
        if "widescreen_runtime_smoke ok" not in out:
            raise SystemExit(out)


if __name__ == "__main__":
    main()
