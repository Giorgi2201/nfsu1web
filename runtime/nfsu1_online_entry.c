/* PC 1.4: use the loaded profile for the browser server's accountless Online.
 * The original SelectPersona success path closes the temporary account lobby
 * (0x55cc97 -> 0x54d590), then opens MU_QuickRaceCarSelect.fng. Its auth/pers
 * results are discarded by that cleanup; only the identity strings survive.
 * Follow that same car-selection/game-lobby path directly from the main menu.
 * Profile-name and CPU-save orchestration follows nfsu2-web/runtime/online.c
 * (MIT; see NOTICE.md); addresses and the transition are specific to NFSU1.
 */
#include "cpu.h"
#include <stdio.h>
#include <string.h>

int winsock_online(void);
void __real_sub_004f6360(CPU *);

static void profile_field(uint32_t address, unsigned capacity, const char *name){
    memset(g_mem + address, 0, capacity);
    memcpy(g_mem + address, name, strlen(name));
}

void __wrap_sub_004f6360(CPU *c){
    /* Only the main menu's Online selection. Other transitions, including
     * LAN and Back, retain their existing package and calling convention. */
    if (MR32(c->esp) != 0x004b3454u || c->edi != 0x006c2614u ||
        MR32(0x00777b4cu) != 8u || !winsock_online()){
        __real_sub_004f6360(c);
        return;
    }
    char name[17];
    unsigned length = 0;
    /* The active profile's first 13 bytes hold its name (setter 0x4aa4d0).
     * 0x777b74 is shared keyboard-entry scratch and is cleared between menus. */
    for (unsigned i = 0; i < 13; i++){
        unsigned char ch = MR8(0x007588c4u + i);
        if (!ch) break;
        /* Dirtysock fields are line-delimited and its persona list uses ','. */
        if (ch >= 32 && ch != 127 && ch != '=' && ch != ',')
            name[length++] = (char)ch;
    }
    name[length] = 0;
    if (!length) strcpy(name, "Player");

    /* Close stale account state, using a private guest stack and restoring
     * all registers before invoking the original frontend switch. */
    CPU saved = *c;
    c->esp = (c->esp - 256u) & ~15u;
    PUSH32(0x0055cc9cu);
    dispatch_indirect(c, 0x0054d590u);
    *c = saved;

    profile_field(0x00734dc4u, 17, name);  /* account UI buffer */
    profile_field(0x00734dd8u, 17, name);  /* password UI buffer */
    profile_field(0x007346d8u, 32, name);  /* reconnect account */
    profile_field(0x007346f8u, 32, name);  /* reconnect password */
    profile_field(0x00734718u, 33, name);  /* selected persona */
    profile_field(0x00730188u, 64, name);  /* lobby player name */
    profile_field(0x00777c90u, 32, name);  /* frontend display name */
    MR8(0x007354ccu) = 1;                 /* login identity is initialized */
    fprintf(stderr, "[nfsu1 online] profile %s: skipping legacy EA screens\n", name);
    c->edi = 0x006c27e0u;  /* MU_QuickRaceCarSelect.fng */
    __real_sub_004f6360(c);
}
