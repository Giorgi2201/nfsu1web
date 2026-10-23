#!/usr/bin/env python3
"""Check relative bone-matrix rows in the actual CPU/WGSL shader translator.

Uses authored shader tokens and two synthetic matrix palettes, no game data.
WGSL source checks establish row selection, not execution on a browser GPU.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include "vsemu.h"
#include "web/wgsl.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void check_matrix(unsigned opcode, unsigned rows, unsigned columns) {
    /* vs_1_1: mov a0.x, v1.x; m?x? oPos, v0, c[a0.x + 8]; end. */
    uint32_t tokens[] = {
        0xfffe0101u, 1u, 0xb0010000u, 0x90000001u,
        opcode, 0xc0000000u | (((1u << rows) - 1u) << 16),
        0x90e40000u, 0xa0e42008u, 0x0000ffffu,
    };
    VSProg *shader = vs_compile(tokens, sizeof tokens / sizeof tokens[0]);
    assert(shader && vs_ninstr(shader) == 2 && vs_unknown(shader) == 0);
    VSConst constants = {0};
    const float palette[4][4] = {
        {1, 0, 0, 10}, {0, 2, 0, 20}, {0, 0, 3, 30}, {0, 0, 0, 1},
    };
    memcpy(constants.f[8], palette, sizeof palette);
    for (unsigned row = 0; row < 4; row++)
        for (unsigned col = 0; col < 4; col++)
            constants.f[12 + row][col] = palette[row][col] * 10;
    float inputs[16][4] = {{2, 3, 4, 1}};
    const float expected4[] = {12, 26, 42, 1};
    const float expected3[] = {2, 6, 12, 0};
    const float *expected = columns == 4 ? expected4 : expected3;
    for (unsigned bone = 0; bone < 2; bone++) {
        inputs[1][0] = (float)(4 * bone);
        VSOut result = {0};
        assert(vs_run(shader, &constants, (const float (*)[4])inputs, &result));
        for (unsigned row = 0; row < rows; row++)
            assert(result.pos[row] == expected[row] * (bone ? 10 : 1));
    }
    int declaration[16][2];
    for (unsigned i = 0; i < 16; i++) {
        declaration[i][0] = -1;
        declaration[i][1] = 0;
    }
    declaration[0][0] = 0; declaration[0][1] = 3; /* FLOAT4 position */
    declaration[1][0] = 16; declaration[1][1] = 0; /* FLOAT1 bone offset */
    char wgsl[128 * 1024];
    assert(vs_to_wgsl(shader, 1, (const int (*)[2])declaration, wgsl, sizeof wgsl) > 0);
    for (unsigned row = 0; row < rows; row++) {
        char relative_row[96];
        snprintf(relative_row, sizeof relative_row,
                 "K.c[kb + 1u + u32(clamp(a0.x + %u, 0, 255))]", 8 + row);
        assert(strstr(wgsl, relative_row));
    }
    vs_free(shader);
}

int main(void) {
    check_matrix(20, 4, 4); /* m4x4 */
    check_matrix(21, 3, 4); /* m4x3 */
    check_matrix(22, 4, 3); /* m3x4 */
    check_matrix(23, 3, 3); /* m3x3 */
    check_matrix(24, 2, 3); /* m3x2 */
    puts("PASS: CPU selects both bone palettes; WGSL resolves every matrix row relative to a0");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT / "work/upstream/nfsu2-web")
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()
    runtime = args.upstream.resolve() / "runtime"
    with tempfile.TemporaryDirectory(prefix="nfsu1-skinning-") as directory:
        temporary = Path(directory)
        source = temporary / "smoke.c"
        executable = temporary / "smoke"
        source.write_text(HARNESS)
        subprocess.run([
            args.cc, "-std=c11", "-O0", "-DVSEMU_WGSL", "-DNFS_ENHANCED=0",
            "-I", str(runtime), str(source), str(runtime / "vsemu.c"),
            "-o", str(executable), "-lm",
        ], check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    main()
