#!/usr/bin/env python3
"""Check the actual font dimension adapter with synthetic texture headers.

No game data or generated game functions are used. This validates logical
dimensions and unchanged upload metadata, not browser/game appearance.
"""
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CPU_HEADER = r'''
#include <stdint.h>
extern uint8_t *g_mem;
#define MR16(a) (*(uint16_t *)(g_mem + (uint32_t)(a)))
#define MR32(a) (*(uint32_t *)(g_mem + (uint32_t)(a)))
#define MR8(a) (*(uint8_t *)(g_mem + (uint32_t)(a)))
'''
HARNESS = r'''
#include "cpu.h"
#include "nfsu1_fonts.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint8_t storage[8 * 1024 * 1024];
uint8_t *g_mem = storage;

int main(void) {
    const uint32_t texture = 256u;
    const uint32_t hashes[] = {0x5b9d88b9u, 0x5b9d84dbu, 0xbbba71c2u, 0x9583aa1au};
    const unsigned nominal[] = {256u, 256u, 128u, 512u};
    MR32(0x7364f4u) = 2u;
    for (unsigned i = 0; i < 4; i++) {
        MR32(texture + 0x24u) = hashes[i];
        for (unsigned factor = 1; factor <= 4; factor += 3) {
            MR16(texture + 0x44u) = nominal[i] * factor;
            MR16(texture + 0x46u) = nominal[i] * factor;
            uint8_t before[80];
            memcpy(before, g_mem + texture, sizeof before);
            assert(nfsu1_font_dimension(texture, 0u) == nominal[i]);
            assert(nfsu1_font_dimension(texture, 1u) == nominal[i]);
            assert(nfsu1_font_mip_reduction(texture) == (factor == 4 ? 0u : 2u));
            assert(MR32(0x7364f4u) == 2u);
            assert(memcmp(before, g_mem + texture, sizeof before) == 0);
        }
    }
    /* Unknown artwork and non-imported fonts must retain their real size. */
    const uint32_t other_hashes[] = {0x12345678u, 0xa87927beu};
    for (unsigned i = 0; i < 2; i++) {
        MR32(texture + 0x24u) = other_hashes[i];
        MR16(texture + 0x44u) = 1024;
        MR16(texture + 0x46u) = 512;
        assert(nfsu1_font_dimension(texture, 0u) == 1024u);
        assert(nfsu1_font_dimension(texture, 1u) == 512u);
        assert(nfsu1_font_mip_reduction(texture) == 2u);
    }
    MR16(texture + 0x44u) = 0xffff;
    assert(nfsu1_font_dimension(texture, 0u) == 0xffffffffu);
    MR32(texture + 0x24u) = hashes[0];
    MR16(texture + 0x44u) = 128;
    MR16(texture + 0x46u) = 1024;
    assert(nfsu1_font_dimension(texture, 0u) == 128u);
    assert(nfsu1_font_dimension(texture, 1u) == 1024u);
    puts("font_runtime_smoke ok: HD/stock dimensions and mip policy, unchanged headers/settings, fallback reads");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        (directory / "cpu.h").write_text(CPU_HEADER)
        (directory / "smoke.c").write_text(HARNESS)
        executable = directory / "smoke"
        subprocess.check_call([
            "cc", "-O1", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I", str(directory), "-I", str(ROOT / "runtime"),
            str(directory / "smoke.c"), str(ROOT / "runtime/nfsu1_fonts.c"),
            "-o", str(executable),
        ])
        subprocess.check_call([str(executable)])


if __name__ == "__main__":
    main()
