/* Original NFSU1 USER32/KERNEL32 HLE for imports the NFSU2 runtime omits.
 * Bring-up only: visible no-ops where full semantics are not needed yet. */
#include "cpu.h"
#include <ctype.h>
#include <string.h>

static uint32_t A(CPU *c, int i){ return MR32(c->esp + 4u * (uint32_t)i); }

static const char *guest_cstr(uint32_t p){
    if (!p || !mem_is_committed(p)) return "";
    return (const char *)(g_mem + p);
}

static uint32_t char_upper_a(uint32_t p){
    if ((p >> 16) == 0){
        return (uint32_t)(uint8_t)toupper((unsigned char)(p & 0xffu));
    }
    if (!p || !mem_is_committed(p)) return p;
    uint8_t *s = g_mem + p;
    for (uint32_t i = 0; i < 4096u && mem_is_committed(p + i) && s[i]; i++)
        s[i] = (uint8_t)toupper(s[i]);
    return p;
}

static int lstrcmpi_a(uint32_t a, uint32_t b){
    const unsigned char *x = (const unsigned char *)guest_cstr(a);
    const unsigned char *y = (const unsigned char *)guest_cstr(b);
    for (;;){
        int d = tolower(*x) - tolower(*y);
        if (d || !*x || !*y) return d < 0 ? -1 : d > 0 ? 1 : 0;
        x++; y++;
    }
}

static int set_rect(uint32_t rect, int left, int top, int right, int bottom){
    if (!rect) return 0;
    mem_commit(rect, 16);
    MR32(rect) = (uint32_t)left;
    MR32(rect + 4u) = (uint32_t)top;
    MR32(rect + 8u) = (uint32_t)right;
    MR32(rect + 12u) = (uint32_t)bottom;
    return 1;
}

int nfsu1_win32_call(CPU *c, const char *n, uint32_t *out){
    uint32_t r = 0;
    if (!strcmp(n, "CharUpperA")) r = char_upper_a(A(c, 0));
    else if (!strcmp(n, "lstrcmpiA") || !strcmp(n, "lstrcmpi"))
        r = (uint32_t)lstrcmpi_a(A(c, 0), A(c, 1));
    else if (!strcmp(n, "lstrcmpA") || !strcmp(n, "lstrcmp")){
        const char *x = guest_cstr(A(c, 0)), *y = guest_cstr(A(c, 1));
        int d = strcmp(x, y);
        r = (uint32_t)(d < 0 ? -1 : d > 0 ? 1 : 0);
    }
    else if (!strcmp(n, "GetKeyState")) r = 0;
    else if (!strcmp(n, "keybd_event")) r = 0;
    else if (!strcmp(n, "AdjustWindowRectEx")) r = 1;
    else if (!strcmp(n, "ClientToScreen")) r = 1;
    else if (!strcmp(n, "SetRect"))
        r = (uint32_t)set_rect(A(c, 0), (int)A(c, 1), (int)A(c, 2),
                               (int)A(c, 3), (int)A(c, 4));
    else if (!strcmp(n, "SetActiveWindow"))
        r = A(c, 0) ? A(c, 0) : 0x00B00001u;
    else if (!strcmp(n, "SetWindowsHookExA")) r = 0x00B20001u;
    else if (!strcmp(n, "UnhookWindowsHookEx")) r = 1;
    else if (!strcmp(n, "CallNextHookEx")) r = 0;
    else if (!strcmp(n, "PostThreadMessageA") || !strcmp(n, "SendNotifyMessageA")) r = 1;
    else if (!strcmp(n, "SystemParametersInfoA")) r = 1;
    else return 0;
    *out = r;
    return 1;
}
