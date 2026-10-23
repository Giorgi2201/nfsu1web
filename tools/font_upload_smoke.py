#!/usr/bin/env python3
"""Execute the private emitted texture uploader with synthetic COM resources.

Checks actual CreateTexture dimensions and every copied mip payload. Requires
a local emission; extracted game code is written only under ignored out/.
No GPU or browser is used. This is not rendered-game validation.
"""
import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include "cpu.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
uint8_t *g_mem;
guest_fn_t g_dtab[DISPATCH_TEXT_SIZE];
static unsigned width, height, levels, locks;
void sub_00407db0(CPU *);
void sub_00408010(CPU *c) { (void)c; abort(); }
void sub_0067121a(CPU *c) { (void)c; abort(); }
void sub_00671102(CPU *c) { (void)c; abort(); }
#define ARG(i) MR32(c->esp + 4u + 4u * (i))
void dispatch_indirect(CPU *c, uint32_t target) {
    unsigned nargs;
    if (target == 0x10000u) {
        width = ARG(1); height = ARG(2); levels = ARG(3);
        MR32(ARG(7)) = 0x3000u;
        MR32(0x3000u) = 0x4000u;
        MR32(0x404cu) = 0x10010u; MR32(0x4050u) = 0x10020u;
        nargs = 9;
    } else if (target == 0x10010u) {
        unsigned level = ARG(1); assert(level < 4u);
        uint32_t locked = ARG(2);
        MR32(locked) = width >> level;
        MR32(locked + 4u) = 0x2000000u + level * 0x400000u;
        locks++; nargs = 5;
    } else if (target == 0x10020u) { nargs = 2;
    } else { fprintf(stderr, "unexpected dispatch %x\n", target); abort(); }
    POP32(c->eip); c->esp += nargs * 4u; c->eax = 0;
}
static void check(uint32_t hash, unsigned atlas, unsigned mip_count, unsigned drop, int hd) {
    memset(g_mem, 0, 64u * 1024u * 1024u);
    uint32_t texture = 0x1000u, resource = 0x2000u, data = 0x1000000u;
    MR32(texture) = resource;
    MR32(texture + 0x24u) = hash;
    MR16(texture + 0x44u) = MR16(texture + 0x46u) = atlas;
    MR8(texture + 0x4eu) = mip_count;
    MR32(texture + 0x40u) = atlas * atlas;
    MR32(texture + 0x70u) = data;
    MR32(resource + 0x14u) = 0x35545844u; /* DXT5 */
    MR32(0x73636cu) = 0x5000u; MR32(0x5000u) = 0x6000u;
    MR32(0x605cu) = 0x10000u;
    MR32(0x78daa4u) = 0x78daa0u;
    MR32(0x7364f4u) = drop;
    unsigned size = atlas * atlas;
    for (unsigned i = 0; i < mip_count; i++) {
        memset(g_mem + data, 0x31u + i, size); data += size; size /= 4u;
    }
    CPU cpu = {0}; cpu.esp = 0x800000u; cpu.eax = texture;
    MR32(cpu.esp) = 0xdeadbeefu; locks = 0;
    sub_00407db0(&cpu);
    assert(cpu.eip == 0xdeadbeefu && cpu.esp == 0x800004u);
    unsigned skipped = hd || drop >= mip_count ? 0u : drop;
    assert(width == (atlas >> skipped) && height == width);
    assert(levels == mip_count - skipped && locks == levels);
    size = width * height;
    for (unsigned i = 0; i < levels; i++) {
        uint8_t *bytes = g_mem + 0x2000000u + i * 0x400000u;
        for (unsigned j = 0; j < size; j++) assert(bytes[j] == 0x31u + i + skipped);
        size /= 4u;
    }
    assert(MR32(0x7364f4u) == drop);
}
int main(void) {
    g_mem = calloc(1, 64u * 1024u * 1024u); assert(g_mem);
    const uint32_t hashes[] = {0x5b9d88b9u, 0x5b9d84dbu, 0x9583aa1au, 0xbbba71c2u};
    const unsigned sizes[] = {1024, 1024, 2048, 512};
    for (unsigned i = 0; i < 4; i++) check(hashes[i], sizes[i], i == 2 ? 4 : 3, 2, 1);
    check(0x12345678u, 1024, 3, 2, 0);
    check(hashes[0], 256, 1, 2, 0);
    check(hashes[0], 1024, 3, 0, 1);
    free(g_mem);
    puts("PASS: actual emitted uploader preserves all HD font mips/pixels and stock texture reduction");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gen", type=Path, default=ROOT / "gen/nfsu1-current")
    args = parser.parse_args()
    body = None
    for source in sorted(args.gen.glob("shard_*.c")):
        match = re.search(r"void sub_00407db0\(CPU \*restrict c\) \{.*?\n\}",
                          source.read_text(), re.S)
        if match:
            body = match.group(); break
    if body is None:
        parser.error("selected emission has no texture upload routine")
    out = ROOT / "out/font-upload-smoke"
    out.mkdir(parents=True, exist_ok=True)
    (out / "upload.c").write_text('/* PRIVATE GAME-DERIVED OUTPUT. DO NOT DISTRIBUTE. */\n'
                                  '#include "cpu.h"\n#include "nfsu1_fonts.h"\n'
                                  'void sub_00408010(CPU *); void sub_0067121a(CPU *); '
                                  'void sub_00671102(CPU *);\n' + body)
    (out / "check.c").write_text(HARNESS)
    executable = out / "check"
    subprocess.run(["cc", "-O1", "-fno-strict-aliasing", "-Wno-unused-label",
                    "-I", str(ROOT / "runtime"), "-I", str(ROOT / "work/upstream/nfsu2-web/runtime"),
                    str(out / "upload.c"), str(out / "check.c"), str(ROOT / "runtime/nfsu1_fonts.c"),
                    "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    main()
