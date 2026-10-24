/* Bounded diagnostics for Speed.exe 1.4's Online race teardown callbacks.
 * These wrappers observe the CPU * ABI without changing the game's decisions.
 * Guest bodies and packet contents stay in the local generated build.
 */
#include "cpu.h"
#include <stdio.h>
#include <string.h>

void guest_backtrace(CPU *, int);

static uint32_t online_word(uint32_t address){
    if (address > GSZ - 4u || !mem_is_committed(address) ||
        !mem_is_committed(address + 3u)) return 0;
    return MR32(address);
}

static void online_racers(uint32_t manager){
    uint32_t cars = online_word(0x007361f8u);
    uint32_t count = cars ? online_word(cars + 0x18u) : 0;
    if (count > 16) count = 16;
    fprintf(stderr, "[nfsu1 online] coordinator=%08x state=%u local=%08x\n",
            manager, online_word(manager), online_word(manager + 4u));
    for (unsigned i = 0; i < 4; i++){
        uint32_t player = online_word(manager + 8u + i * 4u);
        if (!player) continue;
        int index = (int8_t)(online_word(player + 4u) & 0xffu);
        uint32_t car = 0;
        for (unsigned j = 0; j < count; j++){
            uint32_t candidate = online_word(cars + 0x28u + j * 4u);
            if (candidate && (int16_t)(online_word(candidate + 8u) >> 16) == index){
                car = candidate;
                break;
            }
        }
        uint32_t physics = car ? online_word(car + 0x830u) : 0;
        uint32_t encoded = 0, key = 0, offset = 0;
        float decoded = 0;
        if (physics && physics <= GSZ - 0x2a0u){
            encoded = online_word(physics + 0x254u);
            key = online_word(online_word(physics + 0x298u));
            offset = online_word(physics + 0x29cu);
            uint32_t bits = encoded ^ key;
            memcpy(&decoded, &bits, sizeof decoded);
            decoded = (float)((double)decoded - (int32_t)offset);
        }
        fprintf(stderr, "[nfsu1 online] slot=%u player=%08x status=%u index=%d"
                " car=%08x physics=%08x guard-raw=%08x guard-key=%08x"
                " guard-offset=%d guard-decoded=%.9g\n",
                i, player, online_word(player), index, car, physics,
                encoded, key, (int32_t)offset, (double)decoded);
    }
}

static void online_teardown(CPU *c, const char *reason, int failure){
    /* Cleanup also runs on an ordinary menu exit. Bound both logs and traces. */
    static unsigned reports, traces;
    if (reports >= 32) return;
    reports++;
    uint32_t link = online_word(0x00734f7cu);
    uint32_t now = 0, received = 0;
    uint32_t comm = 0, comm_state = 0xffffffffu, protocol_state = 0xffffffffu;
    uint32_t link_flags = 0;
    uint32_t sim_tick = online_word(0x0073ad3cu);
    uint32_t heartbeat = online_word(0x0074029cu);
    uint32_t host_sent = online_word(0x007402a0u);
    /* NetGameLink's stats accessor (0x664100) returns link + 0x24.
     * 0x54e020 compares stats[0] - stats[0x20] with the client limit. */
    if (link && link <= GSZ - 0x6cu){
        now = online_word(link + 0x24u);
        received = online_word(link + 0x44u);
        link_flags = online_word(link + 0x68u) & 0xffffu;
        comm = online_word(link);
        /* CommUDP identifies its constructor at +0; its ProtoUDP is +0x68.
         * Other Comm transports have different layouts. */
        if (comm && comm <= GSZ - 0x84u && online_word(comm) == 0x0066a3e0u){
            comm_state = online_word(comm + 0x80u);
            uint32_t protocol = online_word(comm + 0x68u);
            if (protocol && protocol <= GSZ - 0xc0u)
                protocol_state = online_word(protocol + 0xbcu);
        }
    }
    fprintf(stderr, "[nfsu1 online] %s caller=%08x arg=%08x"
            " lobby-state=%u client-state=%u host-state=%u peers=%u"
            " sim-tick=%u link=%08x link-clock=%u last-recv=%u age=%u"
            " game-heartbeat=%u game-age-ms=%u"
            " host-last-send=%u host-send-age-ms=%u host-heartbeat-gate=%u"
            " client-limit=%u host-limit=%u link-flags=%04x"
            " comm=%08x comm-state=%u protocol-state=%u\n",
            reason, online_word(c->esp), online_word(c->esp + 4u),
            online_word(0x0073dda0u), online_word(0x007354e0u),
            online_word(0x00735500u), online_word(0x006f1e08u),
            sim_tick, link, now, received, now - received,
            heartbeat, (sim_tick - heartbeat) / 4u,
            host_sent, (sim_tick - host_sent) / 4u,
            online_word(0x006f3da4u) & 0xffu,
            online_word(0x00730150u), online_word(0x00730174u),
            link_flags, comm, comm_state, protocol_state);
    if (failure && traces < 8){
        traces++;
        CPU snapshot = *c;
        guest_backtrace(&snapshot, 6);
    }
}

/* Installed by the client's initializer at 0x547a9c..0x547aba. */
void __real_sub_00547db0(CPU *);
void __wrap_sub_00547db0(CPU *c){
    online_teardown(c, "client connect timeout", 1);
    __real_sub_00547db0(c);
}

void __real_sub_00547dc0(CPU *);
void __wrap_sub_00547dc0(CPU *c){
    online_teardown(c, "client receive timeout", 1);
    __real_sub_00547dc0(c);
}

/* Packet kind 10 in 0x547e00's receive dispatch ends the client session. */
void __real_sub_00548610(CPU *);
void __wrap_sub_00548610(CPU *c){
    online_teardown(c, "received server quit", 1);
    __real_sub_00548610(c);
}

/* Installed by the host initializer at 0x5468ed and 0x5468f7. */
void __real_sub_00546d70(CPU *);
void __wrap_sub_00546d70(CPU *c){
    online_teardown(c, "host peer receive timeout", 1);
    __real_sub_00546d70(c);
}

void __real_sub_00546e00(CPU *);
void __wrap_sub_00546e00(CPU *c){
    online_teardown(c, "host accept timeout", 1);
    __real_sub_00546e00(c);
}

void __real_sub_00547ae0(CPU *);
void __wrap_sub_00547ae0(CPU *c){
    online_teardown(c, "client cleanup", 0);
    __real_sub_00547ae0(c);
}

void __real_sub_0054e2f0(CPU *);
void __wrap_sub_0054e2f0(CPU *c){
    online_teardown(c, "host transport cleanup", 0);
    __real_sub_0054e2f0(c);
}

void __real_sub_0043a220(CPU *);
void __wrap_sub_0043a220(CPU *c){
    static unsigned reports;
    if (reports++ < 8){
        online_teardown(c, "coordinator session stop", 1);
        online_racers(c->ecx);
    }
    __real_sub_0043a220(c);
}

void __real_sub_0043a830(CPU *);
void __wrap_sub_0043a830(CPU *c){
    static unsigned reports;
    if (reports++ < 8){
        online_teardown(c, "coordinator abort", 1);
        online_racers(c->ecx);
    }
    __real_sub_0043a830(c);
}

void __real_sub_004390d0(CPU *);
void __wrap_sub_004390d0(CPU *c){
    static unsigned reports;
    uint32_t next = online_word(c->esp + 4u), previous = online_word(c->ecx);
    int relevant = c->ecx == 0x0077b240u;
    for (unsigned i = 0; i < 4; i++)
        if (c->ecx && c->ecx == online_word(0x0077b248u + i * 4u)) relevant = 1;
    if (relevant && next != previous && reports++ < 64)
        fprintf(stderr, "[nfsu1 online] race state object=%08x %u->%u caller=%08x sim-tick=%u\n",
                c->ecx, previous, next, online_word(c->esp), online_word(0x0073ad3cu));
    __real_sub_004390d0(c);
}

void __real_sub_005647d0(CPU *);
void __wrap_sub_005647d0(CPU *c){
    uint32_t caller = online_word(c->esp), base = c->edx, length = c->ecx;
    __real_sub_005647d0(c);
    /* Observe the game's own car-table check at race start. Other checksums
     * retain their original path and do not produce diagnostic output. */
    static unsigned reports;
    if (caller == 0x0043b057u && reports++ < 4)
        fprintf(stderr, "[nfsu1 online] race car-table checksum base=%08x bytes=%u actual=%08x expected=238562c5\n",
                base, length, c->eax);
}
