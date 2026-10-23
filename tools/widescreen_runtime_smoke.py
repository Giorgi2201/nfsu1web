#!/usr/bin/env python3
"""Focused native smoke for nfsu1_widescreen hooks (no game emission)."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "runtime/nfsu1_widescreen.c"
HUD = ROOT / "runtime/widescreen_hud.inc"


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

''' + impl + r'''

int main(void){
    CPU cpu_storage = {0};
    CPU *c = &cpu_storage;
    assert(nfsu1_ws_hook(c, 0x12345678u) == 0);

    nfsu1_widescreen_set_display_aspect(16.0f / 9.0f);
    nfsu1_widescreen_set_resolution(1920, 1080);
    assert(nfsu1_widescreen_active());

    MRF32(0x006CC910u) = 320.0f;
    MRF32(0x006CC914u) = 1.0f / 320.0f;
    MR32(0x0071A96Cu) = 800;
    MR32(0x0071A970u) = 600;
    MR32(0x00701034u) = 800;
    assert(nfsu1_ws_hook(c, 0x0040875Au) == 1);
    assert(MR32(0x0071A96Cu) == 1066u);
    assert(fabsf(nfsu1_widescreen_hud_pos_x() - 320.0f) > 1.0f);

    assert(MRF32(0x006CC910u) == 320.0f);
    assert(MRF32(0x006CC914u) == 1.0f / 320.0f);
    assert(fabsf(nfsu1_widescreen_hud_scale_x() - 2.0f / 1066.0f * 600.0f / 480.0f) < 1e-7f);
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
    assert(c->eax != before);

    nfsu1_widescreen_set_display_aspect(4.0f / 3.0f);
    assert(!nfsu1_widescreen_active());
    assert(nfsu1_widescreen_hud_pos_x() == 320.0f);
    assert(nfsu1_widescreen_hud_scale_x() == 1.0f / 320.0f);
    c->eax = before;
    assert(nfsu1_ws_hook(c, 0x004B8CF0u) == 1);
    assert(c->eax == before);

    printf("widescreen_runtime_smoke ok\n");
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "widescreen_hud.inc").write_text(HUD.read_text())
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
