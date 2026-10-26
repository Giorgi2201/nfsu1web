#!/usr/bin/env python3
"""Native synthetic check of the overlaid lifecycle; no game/browser execution."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "work/upstream/nfsu2-web/runtime"
HARNESS = r'''
#include "cpu.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

uint8_t *g_mem;
uint8_t g_cbits[1u << 15];
static int activation = 1;
void win32_post_message(uint32_t m, uint32_t wp, uint32_t lp) {
    (void)lp;
    if (m == 0x1cu) activation = (int)wp;
}
void metal_request_quit(void) {}
int fileio_open_writers(void) { return 0; }
double audio_time(void) { return 0; }
void audio_set_muted(int on) { (void)on; }
void discord_lifecycle_changed(void) {}
void roam_game_parked(int on) { (void)on; }
/* Reproduce the important NFSU1 condition: Winsock is initialized even
 * outside multiplayer. That must not exempt single-player from pausing. */
int winsock_session_active(void) { return 1; }
void lifecycle_set_active(int, const char *);
void lifecycle_pump(void);
int lifecycle_may_park(void);
int lifecycle_game_parked(void);

int main(int argc, char **argv) {
    assert(argc == 2);
    int run = !strcmp(argv[1], "run");
    g_mem = calloc(1, 0x800000u);
    assert(g_mem);
    memset(g_cbits, 255, sizeof g_cbits);
    lifecycle_set_active(0, "single-player blur");
    lifecycle_pump();
    assert(activation == run);
    assert(lifecycle_may_park() == !run);
    assert(lifecycle_game_parked() == !run);
    /* The game's own background polling flag exempts its network flow. */
    MR8(0x735e78u) = 1;
    assert(!lifecycle_may_park());
    assert(!lifecycle_game_parked());
    MR8(0x735e78u) = 0;
    assert(lifecycle_may_park() == !run);
    lifecycle_set_active(1, "focus restored");
    lifecycle_pump();
    assert(activation == 1);
    assert(!lifecycle_may_park());
    assert(!lifecycle_game_parked());
    free(g_mem);
}
'''


def main():
    compiler = shutil.which("cc")
    if not compiler:
        raise SystemExit("A native C compiler is required.")
    with tempfile.TemporaryDirectory(prefix="nfsu1-lifecycle-") as temp:
        folder = Path(temp)
        source = folder / "smoke.c"
        source.write_text(HARNESS)
        binary = folder / "smoke"
        subprocess.run([compiler, "-std=c11", "-D_DEFAULT_SOURCE", "-I", str(RUNTIME),
                        str(RUNTIME / "lifecycle.c"), str(source), "-o", str(binary)],
                       check=True)
        for mode in ("pause", "run"):
            env = {**os.environ, "NFSU2_BACKGROUND": mode, "NOFOCUS": "0"}
            subprocess.run([str(binary), mode], env=env, check=True)
    print("Synthetic lifecycle smoke passed: blur/resume, initialized Winsock, "
          "network polling flag and Keep running. No game/browser execution.")


if __name__ == "__main__":
    main()
