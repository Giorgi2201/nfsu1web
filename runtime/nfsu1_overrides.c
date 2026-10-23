/* Original CPU* implementations of PC NFSU1 override contracts.
 * Sites/contracts: codepdbh/nfsu1-recompiled, src/runtime/overrides.c.
 * Integration/runtime: th0mk/nfsu2-web. See docs/source-permissions.md.
 * No translated game instructions are included. */
#include "cpu.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void dispatch_patch(uint32_t, guest_fn_t);
extern uint64_t g_hook_hits, g_gs_fail;

static void move_guest(CPU *c){
    uint32_t dst = MR32(c->esp + 4u), src = MR32(c->esp + 8u);
    uint32_t n = MR32(c->esp + 12u);
    /* Limit arithmetic before forming host/linear-memory pointers. Page
     * commitment faults remain the memory subsystem's responsibility. */
    if ((uint64_t)dst + n > NFSU1_GUEST_LIMIT ||
        (uint64_t)src + n > NFSU1_GUEST_LIMIT){
        fprintf(stderr, "NFSU1 memmove outside guest memory\n"); abort();
    }
    if (n) memmove(g_mem + dst, g_mem + src, n);
    c->eax = dst;
    POP32(c->eip); /* cdecl: caller owns the three arguments. */
}
void sub_00643a39(CPU *c){ c->eax = 0; POP32(c->eip); }
void sub_00672630(CPU *c){ move_guest(c); }
void sub_00678d30(CPU *c){ move_guest(c); }
void overrides_install(void){
    extern void nfsu1_intro_install(void);
    nfsu1_intro_install();
    dispatch_patch(0x00643a39u, sub_00643a39);
    dispatch_patch(0x00672630u, sub_00672630);
    dispatch_patch(0x00678d30u, sub_00678d30);
}
void overrides_report(void){ /* Only verified NFSU1 hooks are installed. */ }
