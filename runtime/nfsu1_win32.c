/* Original NFSU1 USER32/KERNEL32 HLE for imports the NFSU2 runtime omits.
 * Date/time formatting uses the runtime's English (United States) locale;
 * it is a focused implementation, not a full Windows globalization layer. */
#include "cpu.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

extern void win32_set_last_error(CPU *, uint32_t);

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

static uint32_t datetime_error(CPU *c, uint32_t error){
    win32_set_last_error(c, error);
    return 0;
}

static int datetime_range(uint32_t p, uint32_t size){
    if (!p || (uint64_t)p + size > GSZ) return 0;
    for (uint32_t i = 0; i < size; i++)
        if (!mem_is_committed(p + i)) return 0;
    return 1;
}

static int datetime_fields(uint32_t p, int is_time, int fields[8]){
    if (p){
        if (!datetime_range(p, 16)) return 0;
        for (unsigned i = 0; i < 8; i++) fields[i] = MR16(p + 2u * i);
    } else {
        time_t now = time(NULL);
        struct tm local;
        if (!localtime_r(&now, &local)) return 0;
        fields[0] = local.tm_year + 1900; fields[1] = local.tm_mon + 1;
        fields[2] = local.tm_wday; fields[3] = local.tm_mday;
        fields[4] = local.tm_hour; fields[5] = local.tm_min;
        fields[6] = local.tm_sec; fields[7] = 0;
    }
    if (is_time)
        return fields[4] < 24 && fields[5] < 60 && fields[6] < 60 && fields[7] < 1000;
    int y = fields[0], m = fields[1], d = fields[3];
    static const int days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    if (y < 1601 || y > 30827 || m < 1 || m > 12) return 0;
    int leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0);
    if (d < 1 || d > days[m - 1] + (m == 2 && leap)) return 0;
    /* SYSTEMTIME.wDayOfWeek is advisory; derive it from the actual date. */
    static const int offsets[] = {0,3,2,5,0,3,5,1,4,6,2,4};
    y -= m < 3;
    fields[2] = (y + y/4 - y/100 + y/400 + offsets[m - 1] + d) % 7;
    return 1;
}

/* Win32 pictures use different tokens from strftime, including quoted text.
 * Suppression flags with custom pictures are limited to pictures which already
 * omit the suppressed fields (the game's HH':'mm picture is one such case). */
static int datetime_picture(const char *format, int is_time, uint32_t flags,
                            const int f[8], char *out, size_t size){
    static const char *months[] = {"January","February","March","April","May","June",
        "July","August","September","October","November","December"};
    static const char *weekdays[] = {"Sunday","Monday","Tuesday","Wednesday",
        "Thursday","Friday","Saturday"};
    size_t used = 0;
    int quoted = 0;
    for (size_t i = 0; format[i];){
        char token = format[i++], part[64];
        unsigned run = 1;
        if (token == '\''){
            if (format[i] == '\''){ i++; part[0] = '\''; part[1] = 0; }
            else { quoted = !quoted; continue; }
        } else if (quoted){ part[0] = token; part[1] = 0; }
        else {
            while (format[i] == token){ run++; i++; }
            if (!is_time && token == 'd'){
                if (run >= 3) snprintf(part, sizeof part, run == 3 ? "%.3s" : "%s", weekdays[f[2]]);
                else snprintf(part, sizeof part, run == 2 ? "%02d" : "%d", f[3]);
            } else if (!is_time && token == 'M'){
                if (run >= 3) snprintf(part, sizeof part, run == 3 ? "%.3s" : "%s", months[f[1] - 1]);
                else snprintf(part, sizeof part, run == 2 ? "%02d" : "%d", f[1]);
            } else if (!is_time && token == 'y'){
                snprintf(part, sizeof part, run >= 3 ? "%04d" : run == 2 ? "%02d" : "%d",
                         run >= 3 ? f[0] : f[0] % 100);
            } else if (is_time && (token == 'H' || token == 'h')){
                int hour = token == 'H' || (flags & 8u) ? f[4] : (f[4] % 12 ? f[4] % 12 : 12);
                snprintf(part, sizeof part, run >= 2 ? "%02d" : "%d", hour);
            } else if (is_time && (token == 'm' || token == 's')){
                if ((flags & 1u) || (token == 's' && (flags & 2u))) return 0;
                snprintf(part, sizeof part, run >= 2 ? "%02d" : "%d", f[token == 'm' ? 5 : 6]);
            } else if (is_time && token == 't'){
                if (flags & 4u) return 0;
                snprintf(part, sizeof part, run == 1 ? "%.1s" : "%s", f[4] < 12 ? "AM" : "PM");
            } else {
                if (run >= sizeof part) return 0;
                memset(part, token, run); part[run] = 0;
            }
        }
        size_t n = strlen(part);
        if (used + n >= size) return 0;
        memcpy(out + used, part, n); used += n;
    }
    out[used] = 0;
    return 1;
}

/* Both imports take six stdcall arguments; win32_call owns stack cleanup.
 * Success counts the terminating NUL, including a cch == 0 size query.
 * https://learn.microsoft.com/en-us/windows/win32/api/datetimeapi/nf-datetimeapi-getdateformata
 * https://learn.microsoft.com/en-us/windows/win32/api/datetimeapi/nf-datetimeapi-gettimeformata
 */
static uint32_t datetime_format_a(CPU *c, int is_time){
    uint32_t locale = A(c, 0), flags = A(c, 1), p = A(c, 2);
    uint32_t picture = A(c, 3), output = A(c, 4);
    int32_t capacity = (int32_t)A(c, 5);
    if (locale != 0x0409u && locale != 0x0400u && locale != 0x0800u && locale != 0x007fu)
        return datetime_error(c, 87); /* ERROR_INVALID_PARAMETER */
    flags &= ~0xc0000000u; /* English CP_ACP / NOUSEROVERRIDE do not change these pictures. */
    if (is_time ? (flags & ~15u) != 0 :
        ((flags & ~11u) != 0 || (flags && (flags & (flags - 1u))) || (picture && flags)))
        return datetime_error(c, 1004); /* ERROR_INVALID_FLAGS */
    if (capacity < 0) return datetime_error(c, 87);
    int fields[8];
    if (!datetime_fields(p, is_time, fields)) return datetime_error(c, 87);
    char custom[256], text[512];
    const char *format;
    if (picture){
        unsigned i;
        for (i = 0; i < sizeof custom; i++){
            if ((uint64_t)picture + i >= GSZ || !datetime_range(picture + i, 1))
                return datetime_error(c, 87);
            custom[i] = (char)MR8(picture + i);
            if (!custom[i]) break;
        }
        if (i == sizeof custom) return datetime_error(c, 87);
        format = custom;
    } else if (is_time){
        if (flags & 8u)
            format = flags & 1u ? "H" : flags & 2u ? "H:mm" : "H:mm:ss";
        else if (flags & 4u)
            format = flags & 1u ? "h" : flags & 2u ? "h:mm" : "h:mm:ss";
        else format = flags & 1u ? "h tt" : flags & 2u ? "h:mm tt" : "h:mm:ss tt";
    } else format = flags & 2u ? "dddd, MMMM d, yyyy" : flags & 8u ? "MMMM yyyy" : "M/d/yyyy";
    if (!datetime_picture(format, is_time, flags, fields, text, sizeof text))
        return datetime_error(c, 87);
    uint32_t count = (uint32_t)strlen(text) + 1u;
    if (!capacity) return count;
    if (!output || (uint32_t)capacity < count) return datetime_error(c, 122);
    if (!datetime_range(output, count)) return datetime_error(c, 87);
    memcpy(g_mem + output, text, count);
    return count;
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
    else if (!strcmp(n, "GetDateFormatA")) r = datetime_format_a(c, 0);
    else if (!strcmp(n, "GetTimeFormatA")) r = datetime_format_a(c, 1);
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
