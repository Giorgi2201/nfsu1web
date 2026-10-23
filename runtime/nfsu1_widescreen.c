/* NFSU1 widescreen: port of codepdbh/nfsu1-recompiled src/runtime/widescreen.c
 * to the web CPU* ABI. Patch semantics from ThirteenAG
 * NFSUnderground.WidescreenFix (WidescreenFixesPack, MIT): FixFOV, FixHUD,
 * render-size widening and scoped HUD projection operands. Sites are config/hooks.txt
 * VAs emitted as guest_hook(c, va) before the marked instruction.
 * No translated game instructions are included. */
#include "nfsu1_widescreen.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static float s_display_aspect;
static float s_aspect = 4.0f / 3.0f;
static double s_fov_scale[3] = {1.0, 0.5, 1.0};
static float s_hud_pos_x = 320.0f;
static float s_hud_scale_x = 1.0f / 320.0f;

static const struct { uint32_t va; uint8_t reg; } k_hit[] = {
    { 0x00415358u, 2 },
    { 0x00415CADu, 2 },
    { 0x004B7E14u, 2 },
    { 0x004B8C71u, 2 },
    { 0x004C1A39u, 2 },
    { 0x004D1DF9u, 2 },
    { 0x004D516Au, 2 },
    { 0x004D66D1u, 2 },
    { 0x004DC438u, 2 },
    { 0x004E39A8u, 2 },
    { 0x004EAA5Au, 2 },
    { 0x004F7EDFu, 2 },
    { 0x004F7F36u, 2 },
    { 0x0054F09Au, 2 },
    { 0x0054F363u, 2 },
    { 0x005518D8u, 2 },
    { 0x00557EDCu, 2 },
    { 0x00559BAAu, 2 },
    { 0x0055BAEAu, 2 },
    { 0x0055CD90u, 2 },
    { 0x0055D7F8u, 2 },
    { 0x0055F0DAu, 2 },
    { 0x00561C98u, 2 },
    { 0x00562128u, 2 },
    { 0x0056391Au, 2 },
    { 0x00563CFAu, 2 },
    { 0x004B8CF0u, 0 },
    { 0x004D6750u, 0 },
    { 0x004F7D65u, 0 },
    { 0x004F608Bu, 1 },
};

typedef struct { uint32_t x, y; float off_x, off_y; } hud_entry;
static const hud_entry k_hud[] = {
#include "widescreen_hud.inc"
};

static float rdf(uint32_t va) { return MRF32(va); }
static void wrf(uint32_t va, float f) { MRF32(va) = f; }

static void widescreen_hud(uint32_t *bx, uint32_t *by, int minimap) {
    const float base_offset = (480.0f * (16.0f / 9.0f) - 640.0f) / 2.0f;
    const float hud_offset = s_hud_pos_x - 320.0f;
    if (MR32(0x0077A920u) == 3u) return;
    for (unsigned i = 0; i < sizeof k_hud / sizeof k_hud[0]; i++) {
        float x, y;
        if (k_hud[i].x != *bx || k_hud[i].y != *by) continue;
        memcpy(&x, bx, 4); memcpy(&y, by, 4);
        if (k_hud[i].off_x >= 0.0f) x += hud_offset + (k_hud[i].off_x - base_offset);
        else x -= hud_offset - (k_hud[i].off_x + base_offset);
        y += k_hud[i].off_y;
        if (minimap) x += s_hud_pos_x - 320.0f;
        memcpy(bx, &x, 4); memcpy(by, &y, 4);
        return;
    }
}

static void hud_mem_pair(uint32_t va_x, uint32_t va_y, int minimap) {
    uint32_t x = MR32(va_x), y = MR32(va_y);
    widescreen_hud(&x, &y, minimap);
    MR32(va_x) = x;
    MR32(va_y) = y;
}

void nfsu1_widescreen_set_display_aspect(float aspect) {
    s_display_aspect = aspect > 1.34f ? aspect : 0.0f;
}

void nfsu1_widescreen_set_resolution(unsigned width, unsigned height) {
    if (width && height) s_aspect = (float)width / (float)height;
}

int nfsu1_widescreen_active(void) {
    return s_display_aspect > 0.0f;
}

float nfsu1_widescreen_hud_pos_x(void) {
    return s_display_aspect > 0.0f ? s_hud_pos_x : 320.0f;
}

float nfsu1_widescreen_hud_scale_x(void) {
    return s_display_aspect > 0.0f ? s_hud_scale_x : 1.0f / 320.0f;
}

static int known_site(uint32_t va) {
    if (va == 0x00409EB8u || va == 0x00401832u || va == 0x004131B5u) return 1;
    for (unsigned i = 0; i < sizeof k_hit / sizeof k_hit[0]; i++)
        if (k_hit[i].va == va) return 1;
    switch (va) {
    case HOOK_SITE(0x0040875A):
    case HOOK_SITE(0x004F20A7):
    case HOOK_SITE(0x004F2333):
    case HOOK_SITE(0x004F28B3):
    case HOOK_SITE(0x004F1E31):
    case HOOK_SITE(0x004F26E9):
    case HOOK_SITE(0x004F314B):
    case HOOK_SITE(0x0058E5C3):
    case HOOK_SITE(0x00409F75):
    case HOOK_SITE(0x004F18D1):
    case HOOK_SITE(0x00590DDF):
    case HOOK_SITE(0x0058FB1C):
    case HOOK_SITE(0x0058E5B2):
    case HOOK_SITE(0x004F6DAB):
    case HOOK_SITE(0x004F1FD7):
    case HOOK_SITE(0x004F225C):
    case HOOK_SITE(0x004F25D1):
    case HOOK_SITE(0x0040DDE0):
    case HOOK_SITE(0x0040DE49):
    case HOOK_SITE(0x0040DEC1):
    case HOOK_SITE(0x0040DEF2):
        return 1;
    default:
        return 0;
    }
}

int nfsu1_ws_hook(CPU *c, uint32_t va) {
    if (!known_site(va)) return 0;

    /* Inert arrow sites: touch/FE cursor path superseded on this host. */
    if (va == 0x00409EB8u || va == 0x00401832u) return 1;

    /* ClientRect clamp for FE-unit cursors; browser mouse stays in pixels. */
    if (va == 0x004131B5u) return 1;

    if (s_display_aspect <= 0.0f) return 1;

    for (unsigned i = 0; i < sizeof k_hit / sizeof k_hit[0]; i++) {
        if (k_hit[i].va != va) continue;
        uint32_t *r = k_hit[i].reg == 0 ? &c->eax : k_hit[i].reg == 1 ? &c->ecx : &c->edx;
        *r += (uint32_t)(int32_t)lroundf(320.0f - s_hud_pos_x);
        return 1;
    }

    switch (va) {
    case HOOK_SITE(0x0040875A): {
        uint32_t height = MR32(0x0071A970u);
        uint32_t width = (uint32_t)lroundf((float)height * s_display_aspect) & ~1u;
        if (height && width > MR32(0x0071A96Cu)) {
            MR32(0x0071A96Cu) = width;
            MR32(0x00701034u) = width;
            s_aspect = (float)width / (float)height;
            { extern void metal_set_game_size(unsigned, unsigned);
              metal_set_game_size(width, height); }
        }
        if (height) {
            float w = (float)MR32(0x0071A96Cu), h = (float)height;
            float scale = (1.0f / w * (h / 480.0f)) * 2.0f;
            s_hud_pos_x = 640.0f / (640.0f * scale);
            s_hud_scale_x = scale;
            /* Keep the shared guest float pool intact: FE layout uses it too. */
        }
        break;
    }
    case HOOK_SITE(0x004F20A7): wrf(c->esp + 0x80u, s_hud_pos_x); break;
    case HOOK_SITE(0x004F2333): wrf(c->esp + 0x90u, s_hud_pos_x); break;
    case HOOK_SITE(0x004F28B3): wrf(c->esp + 0xA0u, s_hud_pos_x); break;
    case HOOK_SITE(0x004F1E31): wrf(c->esp + 0x60u, s_hud_pos_x); break;
    case HOOK_SITE(0x004F26E9): wrf(c->esp + 0x50u, s_hud_pos_x); break;
    case HOOK_SITE(0x004F314B): wrf(c->esp + 0x19Cu, s_hud_pos_x); break;
    case HOOK_SITE(0x0058E5C3): break; /* Minimap still reads the original 320. */
    case HOOK_SITE(0x00409F75): {
        const uint32_t xs[4] = { 0x6Cu, 0x7Cu, 0x8Cu, 0x9Cu };
        for (int i = 0; i < 4; i++)
            wrf(c->esp + xs[i], rdf(c->esp + xs[i]) + (s_hud_pos_x - 320.0f));
        break;
    }
    case HOOK_SITE(0x004F18D1): widescreen_hud(&c->eax, &c->ecx, 0); break;
    case HOOK_SITE(0x00590DDF): hud_mem_pair(c->ecx + 0x68u, c->ecx + 0x6Cu, 1); break;
    case HOOK_SITE(0x0058FB1C): hud_mem_pair(c->eax + 0x68u, c->eax + 0x6Cu, 1); break;
    case HOOK_SITE(0x0058E5B2): hud_mem_pair(c->eax + 0x1Cu, c->eax + 0x20u, 1); break;
    case HOOK_SITE(0x004F6DAB): hud_mem_pair(c->ebx + 0x1Cu, c->ebx + 0x20u, 0); break;
    case HOOK_SITE(0x004F1FD7):
    case HOOK_SITE(0x004F225C):
    case HOOK_SITE(0x004F25D1):
        /* Shared FE quad helpers also draw menus and loading artwork.
         * Preserve their extents; a crop here enlarges every rectangle. */
        break;
    case HOOK_SITE(0x0040DDE0): {
        uint32_t view = MR32(c->ebp + 4u);
        if (view == 1u || view == 4u) {
            s_fov_scale[0] = 1.0 / (s_aspect / (4.0 / 3.0));
            s_fov_scale[1] = 0.4525;
            s_fov_scale[2] = 1.28;
        } else {
            s_fov_scale[0] = 1.0;
            s_fov_scale[1] = 0.5;
            s_fov_scale[2] = 1.0;
        }
        ST(0) = view == 3u ? 0.45 : 1.0;
        MR32(c->esp + 0x20u) = 0x3F800000u;
        break;
    }
    case HOOK_SITE(0x0040DE49): ST(0) *= s_fov_scale[1] / 0.5; break;
    case HOOK_SITE(0x0040DEC1): ST(0) *= s_fov_scale[0]; break;
    case HOOK_SITE(0x0040DEF2): ST(0) *= s_fov_scale[2]; break;
    default:
        fprintf(stderr, "NFSU1 widescreen hook at 0x%08x has no handler\n", va);
        abort();
    }
    return 1;
}
