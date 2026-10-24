"""Synthetic ABI check for the scoped profile-based frontend shortcut."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class OnlineEntryTest(unittest.TestCase):
    def test_profile_shortcut_and_other_transitions(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("C compiler unavailable")
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "cpu.h").write_text(r"""
#include <stdint.h>
typedef struct { uint32_t eax, edi, esp, eip; } CPU;
extern uint8_t *g_mem;
#define MR8(a) (*(uint8_t *)(g_mem + (a)))
#define MR32(a) (*(uint32_t *)(g_mem + (a)))
#define PUSH32(v) do { c->esp -= 4; MR32(c->esp) = (v); } while (0)
void dispatch_indirect(CPU *, uint32_t);
""")
            (folder / "check.c").write_text(r"""
#include "cpu.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
uint8_t *g_mem;
static unsigned cleaned, switched, enabled = 1;
static CPU expected;
int winsock_online(void) { return enabled; }
void __wrap_sub_004f6360(CPU *);
void dispatch_indirect(CPU *c, uint32_t fn) {
    assert(fn == 0x54d590);
    assert(MR32(c->esp) == 0x55cc9c);
    c->eax = c->edi = 0xdeadbeef;
    cleaned++;
}
void __real_sub_004f6360(CPU *c) {
    assert(!memcmp(c, &expected, sizeof *c));
    switched++;
}
int main(void) {
    g_mem = calloc(1, 0x800000);
    CPU cpu = {123, 0x6c2614, 0x100000, 456};
    MR32(cpu.esp) = 0x4b3454;
    MR32(0x777b4c) = 8;
    strcpy((char *)g_mem + 0x7588c4, "ProfileName");
    /* Menu keyboard scratch can contain unrelated text or be empty. */
    strcpy((char *)g_mem + 0x777b74, "WrongName");
    expected = cpu; expected.edi = 0x6c27e0;
    __wrap_sub_004f6360(&cpu);
    assert(cleaned == 1 && switched == 1);
    assert(MR8(0x7354cc) == 1);
    const uint32_t fields[] = {0x734dc4, 0x734dd8, 0x7346d8,
        0x7346f8, 0x734718, 0x730188, 0x777c90};
    for (unsigned i = 0; i < sizeof fields / sizeof *fields; i++)
        assert(!strcmp((char *)g_mem + fields[i], "ProfileName"));
    strcpy((char *)g_mem + 0x7588c4, "OtherProfile");
    MR8(0x777b74) = 0;
    cpu.edi = 0x6c2614;
    __wrap_sub_004f6360(&cpu);
    assert(!strcmp((char *)g_mem + 0x7346d8, "OtherProfile"));
    cpu.edi = 0x6c2614;
    enabled = 0; expected = cpu;
    __wrap_sub_004f6360(&cpu);
    enabled = 1; MR32(cpu.esp) = 0x55b01f;
    __wrap_sub_004f6360(&cpu);
    MR32(cpu.esp) = 0x4b3454; MR32(0x777b4c) = 0x200;
    __wrap_sub_004f6360(&cpu);
    assert(cleaned == 2 && switched == 5);
    free(g_mem);
}
""")
            subprocess.run([
                compiler, "-std=c11", "-I", str(folder),
                str(root / "runtime/nfsu1_online_entry.c"),
                str(folder / "check.c"), "-o", str(folder / "check"),
            ], check=True)
            subprocess.run([str(folder / "check")], check=True)
