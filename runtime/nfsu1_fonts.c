/* SPDX-License-Identifier: GPL-3.0-only
 * HD font scaling semantics adapted from Aero_'s NFSHDContentSupport,
 * SOURCE/NFSU/dllmain.cpp (GPL-3.0). See docs/source-permissions.md.
 * Only the four fonts imported by the fonts-only asset profile are handled.
 * The renderer retains the actual texture dimensions; these accessors supply
 * the original atlas dimensions only to the two font drawing paths. No game
 * instructions or artwork are included here. Modified 2026-10-23 for the
 * CPU-pointer browser runtime and a four-font allowlist. Distributed under
 * GPL version 3, without warranty; see patches/NFSHDContentSupport.LICENSE. */
#include "cpu.h"
#include "nfsu1_fonts.h"
#include <stdio.h>

static uint32_t nominal_size(uint32_t texture) {
    switch (MR32(texture + 0x24u)) {
    case 0x5B9D88B9u: /* CONDUITMDITC_TT21I */
    case 0x5B9D84DBu: /* CONDUITMDITC_TT14I */
        return 256u;
    case 0x9583AA1Au: /* FONT_CONDUITMDITCTT38BI */
        return 512u;
    case 0xBBBA71C2u: /* LCD_LET48 */
        return 128u;
    default:
        return 0;
    }
}

static int hd_font(uint32_t texture, uint32_t nominal) {
    return nominal && MR16(texture + 0x44u) == nominal * 4u &&
        MR16(texture + 0x46u) == nominal * 4u;
}

uint32_t nfsu1_font_mip_reduction(uint32_t texture) {
    uint32_t nominal = nominal_size(texture);
    uint32_t drop = MR32(0x7364f4u);
    if (!nominal) return drop;
    uint32_t hash = MR32(texture + 0x24u);
    unsigned bit = hash == 0x5b9d88b9u ? 1u : hash == 0x5b9d84dbu ? 2u :
        hash == 0x9583aa1au ? 4u : 8u;
    int hd = hd_font(texture, nominal);
    static unsigned reported;
    unsigned key = hd ? bit << 4 : bit;
    if (!(reported & key)) {
        reported |= key;
        fprintf(stderr, "[nfsu1 fonts] %s hash=%08x atlas=%ux%u mips=%u mip-drop=%u->%u\n",
                hd ? "HD" : "stock", hash, (unsigned)MR16(texture + 0x44u),
                (unsigned)MR16(texture + 0x46u), (unsigned)MR8(texture + 0x4eu),
                drop, hd ? 0u : drop);
    }
    /* The game's WorldLOD setting drops the leading mips of every texture.
     * Keep the imported font's full atlas, without changing other artwork or
     * the shared setting. Both creation and upload use this same accessor. */
    return hd ? 0u : drop;
}

uint32_t nfsu1_font_dimension(uint32_t texture, unsigned axis) {
    const uint32_t dimension = (uint32_t)(int32_t)(int16_t)
        MR16(texture + (axis ? 0x46u : 0x44u));
    uint32_t nominal = nominal_size(texture);
    /* Stock atlases, unrelated textures and smaller variants keep the exact
     * original signed read. Do not write the shared texture header: uploads
     * and sampling must continue to see the high-resolution atlas size. */
    if (hd_font(texture, nominal))
        return nominal;
    return dimension;
}
