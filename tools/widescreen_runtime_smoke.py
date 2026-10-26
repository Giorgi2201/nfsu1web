#!/usr/bin/env python3
"""Native host-hook smoke with FE/cache layouts observed in the local PC build.

The real context wrapper executes around a stubbed guest renderer. This checks
group classification and wrapper state; it does not execute game drawing.
"""
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
#define MR16(a) (*(uint16_t *)(g_mem + (uint32_t)(a)))
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

/* The wrapper receives the game's FE instance in edi. Simulate the renderer's
 * register changes only after entering it, as the real cached-quad loop does. */
static void (*render_callback)(CPU *);
void __real_sub_004f2cb0(CPU *c){
    assert(render_callback);
    render_callback(c);
}

static float expected_canvas;
static int nested_draw;
static uint32_t nested_instance, nested_element;

static void inspect_draw(CPU *c){
    uint32_t origin = c->eax;
    /* These registers now describe cached geometry, not the origin passed to
     * the FE dispatcher. Glyph and quad origins may straddle the screen. */
    c->eax = 0xDEADBEEFu;
    c->edi = 0xBAADF00Du;
    c->eip = 0x0040C2D6u;
    c->ebp = 0x1000u;
    c->ebx = 0x2000u;
    MR32(c->ebp + 4u) = 0x00514BC7u;
    float canvas = nfsu1_widescreen_ui_canvas(c);
    if (canvas != expected_canvas)
        fprintf(stderr, "origin=%08x hash=%08x id=%08x flow=%u canvas=%g expected=%g\n",
                origin, MR32(origin + 0xCu), MR32(origin + 0x10u),
                MR32(0x0077A920u), (double)canvas, (double)expected_canvas);
    assert(canvas == expected_canvas);
    if (nested_draw){
        CPU outer_cpu = *c;
        float outer_canvas = expected_canvas;
        nested_draw = 0;
        expected_canvas = 1.f;
        c->edi = nested_instance;
        c->eax = nested_element;
        __wrap_sub_004f2cb0(c);
        *c = outer_cpu;
        expected_canvas = outer_canvas;
        assert(nfsu1_widescreen_ui_canvas(c) == outer_canvas);
    }
}

static void element(uint32_t address, uint32_t hash, uint16_t parent){
    MR32(address + 0x0Cu) = hash;
    MR32(address + 0x18u) = 1u;
    MR16(address + 0x20u) = parent;
}

static void draw(CPU *c, uint32_t instance, uint32_t origin, float canvas){
    c->edi = instance;
    c->eax = origin;
    expected_canvas = canvas;
    render_callback = inspect_draw;
    __wrap_sub_004f2cb0(c);
    assert(c->eax == 0xDEADBEEFu && c->edi == 0xBAADF00Du);
    /* Context must end with the FE call, even though draw registers remain. */
    assert(nfsu1_widescreen_ui_canvas(c) == 1.f);
}

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
    /* PC_Loading's actual parent/child names and positions. Disk parent IDs
     * become FE-instance slot indices at runtime; slot +50 holds the group.
     * Both children must remain centered after flow switches to racing. */
    const uint32_t instance = 0x9000u;
    const uint32_t loading = 0x12000u, chrome = 0x12100u, fill = 0x12200u;
    element(loading, 0x64E0AE85u, 0u); /* Generic_Loading_Group */
    MR32(loading + 0x18u) = 5u;
    element(chrome, 0x20AFCB2Cu, 1u); /* ChromeGeneric_LoadingBar */
    element(fill, 0x71DEBBCDu, 1u); /* generic_loading_bar */
    MR32(loading + 0x10u) = 849618u;
    MR32(chrome + 0x10u) = 849619u;
    MR32(fill + 0x10u) = 849620u;
    MR32(instance + 0x20u + 0xD0u + 0x50u) = loading;
    MR32(chrome + 0x2Cu) = 0x4000u;
    MR32(fill + 0x2Cu) = 0x4100u;
    MRF32(0x401Cu) = 20.f; MRF32(0x4020u) = -75.f;
    MRF32(0x411Cu) = -37.f; MRF32(0x4120u) = -75.f;
    const unsigned sizes[][2] = {{1920,1080}, {2560,1080}, {1984,1278}, {1920,1080}};
    const unsigned loading_flows[] = {4u, 6u, 6u, 7u, 3u};
    for (unsigned i = 0; i < sizeof sizes / sizeof sizes[0]; i++){
        nfsu1_widescreen_set_resolution(sizes[i][0], sizes[i][1]);
        for (unsigned j = 0; j < sizeof loading_flows / sizeof loading_flows[0]; j++){
            MR32(0x0077A920u) = loading_flows[j];
            MRF32(0x2050u) = 327.f;
            draw(c, instance, chrome, 1.f);
            MRF32(0x2050u) = 270.f;
            draw(c, instance, fill, 1.f);
        }
    }

    /* Unknown UI does not become a HUD solely through flow, coordinates,
     * cached-origin register contents or a common cache draw caller. */
    MR32(0x0077A920u) = 6u;
    MR32(chrome + 0x2Cu) = 0x4000u;
    MR32(0x401Cu) = 0xC3960000u; MR32(0x4020u) = 0xC1980000u;
    MR32(0x2008u) = chrome;
    draw(c, instance, chrome, 1.f);

    /* The actual ChyronGroup owns all EA TRAX artwork and text, including a
     * nested tab. The same semantic origin must reach each glyph submission
     * while the animation moves both local and composed coordinates. */
    const uint32_t music_instance = 0xA000u, music = 0x13000u;
    const uint32_t music_hashes[] = {
        0x82009C1Fu, 0xF5387816u, 0x11DB9E17u, 0x48097852u,
        0x90192DFDu, 0x9A04E142u, 0x0000E196u,
        5193456u, 3802514982u, 2328181105u, 1537050809u,
    };
    /* logo texture, backing texture, nested-tab texture and nested-tab text */
    const uint16_t music_parents[] = {0u, 1u, 1u, 1u, 1u, 1u, 2u, 3u, 2u, 4u, 4u};
    const uint32_t music_types[] = {5u, 2u, 2u, 2u, 5u, 5u, 5u, 1u, 1u, 1u, 2u};
    const uint32_t music_ids[] = {0x53F4u, 0x5202u, 0x5205u, 0x5207u,
        0x5724u, 0x57F3u, 0x57F6u, 22131u, 22188u, 22282u, 22289u};
    for (unsigned i = 0; i < sizeof music_hashes / sizeof music_hashes[0]; i++){
        uint32_t origin = music + i * 0x100u;
        element(origin, music_hashes[i], music_parents[i]);
        MR32(origin + 0x18u) = music_types[i];
        MR32(origin + 0x10u) = music_ids[i];
        MR32(origin + 0x2Cu) = 0x5000u + i * 0x100u;
    }
    MR32(music_instance + 0x20u + 0xD0u + 0x50u) = music;
    MR32(music_instance + 0x20u + 2u * 0xD0u + 0x50u) = music + 0x500u;
    MR32(music_instance + 0x20u + 3u * 0xD0u + 0x50u) = music + 0x400u;
    MR32(music_instance + 0x20u + 4u * 0xD0u + 0x50u) = music + 0x600u;
    const float animated_x[] = {-600.f, 270.f, 320.f, 327.f, 900.f};
    const unsigned music_flows[] = {3u, 6u};
    for (unsigned size = 0; size < sizeof sizes / sizeof sizes[0]; size++){
        nfsu1_widescreen_set_resolution(sizes[size][0], sizes[size][1]);
        for (unsigned flow = 0; flow < sizeof music_flows / sizeof music_flows[0]; flow++){
            MR32(0x0077A920u) = music_flows[flow];
            for (unsigned frame = 0; frame < sizeof animated_x / sizeof animated_x[0]; frame++){
                for (unsigned i = 0; i < sizeof music_hashes / sizeof music_hashes[0]; i++){
                    MRF32(0x501Cu + i * 0x100u) = animated_x[frame];
                    MRF32(0x2050u) = animated_x[(frame + i) % 5u];
                    draw(c, music_instance, music + i * 0x100u, 2.f);
                }
            }
        }
    }
    nested_instance = instance;
    nested_element = fill;
    nested_draw = 1;
    draw(c, music_instance, music + 0x100u, 2.f);

    /* Real nested race graphs: drag GaugeCluster -> Group(31) -> NOS_4 ->
     * bar, and single-race GaugeCluster -> Turbo_Group -> fill/text. The
     * root name repeats across variants, so its original identity matters. */
    const uint32_t drag_instance = 0xB000u, drag = 0x14000u;
    element(drag, 0x5164D4EAu, 0u);
    MR32(drag + 0x10u) = 35798u;
    MR32(drag + 0x2Cu) = 0x6000u;
    MRF32(0x601Cu) = -109.20833587646484f;
    MRF32(0x6020u) = -25.815975189208984f;
    element(drag + 0x100u, 2228005409u, 1u); /* Group(31) */
    element(drag + 0x200u, 56299042u, 2u); /* NOS_4 */
    element(drag + 0x300u, 2541297158u, 3u); /* NOS_bar_4_1 */
    MR32(drag + 0x110u) = 17590u;
    MR32(drag + 0x210u) = 17408u;
    MR32(drag + 0x310u) = 17336u;
    for (unsigned i = 0; i < 3; i++){
        MR32(drag + i * 0x100u + 0x18u) = 5u;
        MR32(drag_instance + 0x20u + (i + 1u) * 0xD0u + 0x50u) = drag + i * 0x100u;
    }
    const uint32_t single_instance = 0xC000u, single = 0x15000u;
    element(single, 0x5164D4EAu, 0u);
    MR32(single + 0x10u) = 35713u;
    MR32(single + 0x2Cu) = 0x6100u;
    MRF32(0x611Cu) = 142.f; MRF32(0x6120u) = 196.f;
    element(single + 0x100u, 3319091639u, 1u); /* Turbo_Group */
    element(single + 0x200u, 1835001969u, 2u); /* 3rdperson_Turbofill */
    element(single + 0x300u, 1683069687u, 2u); /* TurboPSI */
    MR32(single + 0x110u) = 19866u;
    MR32(single + 0x210u) = 18988u;
    MR32(single + 0x310u) = 19042u;
    MR32(single + 0x300u + 0x18u) = 2u;
    for (unsigned i = 0; i < 2; i++){
        MR32(single + i * 0x100u + 0x18u) = 5u;
        MR32(single_instance + 0x20u + (i + 1u) * 0xD0u + 0x50u) = single + i * 0x100u;
    }
    for (unsigned i = 0; i < 4; i++){
        MRF32(0x2050u) = i % 2 ? 543.f : 210.79167f;
        draw(c, drag_instance, drag + i * 0x100u, 2.f);
        draw(c, single_instance, single + i * 0x100u, 3.f);
    }
    /* The static map backing and immediate map geometry share the same
     * viewport. Both real single-race/drift identities must align. */
    const uint32_t map = 0x16000u, map_ids[] = {0x1DF4u, 0x51F2u};
    element(map, 0x24D28793u, 0u); /* track_map_placeholder */
    for (unsigned i = 0; i < sizeof map_ids / sizeof map_ids[0]; i++){
        MR32(map + 0x10u) = map_ids[i];
        draw(c, single_instance, map, 2.f);
        MR32(c->ebp + 4u) = 0x0058FAFBu;
        assert(nfsu1_widescreen_ui_canvas(c) == 2.f);
        MR32(c->ebp + 4u) = 0x00590AB4u;
        assert(nfsu1_widescreen_ui_canvas(c) == 2.f);
        c->eip = 0x0040C4A8u;
        MR32(c->esp + 0x80u) = 0x00589907u;
        assert(nfsu1_widescreen_ui_canvas(c) == 2.f);
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
