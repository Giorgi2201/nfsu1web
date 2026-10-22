/* NFSU1 bring-up diagnostics, independent of Present and game-flow globals.
 * Uses the pinned th0mk/nfsu2-web thread registry and guest_backtrace interface;
 * see docs/source-permissions.md and patches/nfsu2-web.LICENSE.
 * NFSU1_DIAGNOSTICS=<seconds> enables repeated best-effort thread reports.
 *
 * The upstream thread registry and CPU fields are not synchronized with this
 * observer. Volatile reads and slot rechecks only reduce stale observations;
 * they do not provide an atomic snapshot or protect an exiting CPU's lifetime.
 * Treat register/state combinations and stack candidates as diagnostic hints,
 * not a coherent debugger stop. In particular, lifted code does not update EIP
 * at every instruction, and register values may remain in compiled locals.
 * The stack scan is the upstream guest_backtrace heuristic, not an unwind.
 */
#include "cpu.h"
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#define MAXCPUS 32 /* Registry layout in upstream win32_ext.c. */
enum { TS_RUN = 0, TS_GIL, TS_WAIT, TS_WAITM, TS_CS, TS_SLEEP, TS_IDLE };
typedef struct {
    volatile int what;
    volatile uint32_t obj;
    volatile uint64_t since_us;
} TState;
extern TState g_tstate[MAXCPUS];
extern CPU *g_all_cpus[MAXCPUS];
extern uint32_t g_all_tids[MAXCPUS];
extern int g_all_n;
extern CPU *g_cur_cpu;
void guest_backtrace(CPU *, int);
long metal_frames(void);

static pthread_once_t diagnostics_once = PTHREAD_ONCE_INIT;
static struct timespec report_interval;
static uint32_t watched_words[16];
static int watched_count;

void nfsu1_diagnostics_dispatch(CPU *c, uint32_t target){
    if (!getenv("NFSU1_DIAGNOSTICS")) return;
    fprintf(stderr, "[nfsu1 diagnostics] dispatch registers eax=%08x ebx=%08x ecx=%08x edx=%08x esi=%08x edi=%08x ebp=%08x\n",
            c->eax, c->ebx, c->ecx, c->edx, c->esi, c->edi, c->ebp);
    /* A bounded fingerprint of an observed target, never a bulk memory dump.
     * Keep diagnostics local: these may be game-derived instruction bytes. */
    if (target <= GSZ - 64u && mem_is_committed(target) && mem_is_committed(target + 63u)){
        fprintf(stderr, "[nfsu1 diagnostics] target bytes at %08x:", target);
        for (unsigned i = 0; i < 64; i++)
            fprintf(stderr, "%02x", (unsigned)*(volatile uint8_t *)(g_mem + target + i));
        fputc('\n', stderr);
    } else {
        fprintf(stderr, "[nfsu1 diagnostics] target bytes unavailable\n");
    }
}

void nfsu1_diagnostics_words(void){
    for (int i = 0; i < watched_count; i++){
        uint32_t address = watched_words[i];
        if (mem_is_committed(address) && mem_is_committed(address + 3u))
            fprintf(stderr, "  word[0x%08x]=0x%08x\n", address,
                    *(volatile uint32_t *)(g_mem + address));
        else
            fprintf(stderr, "  word[0x%08x]=uncommitted\n", address);
    }
}

static void report_threads(unsigned long report){
    static const char *const states[] = {
        "running", "waiting for GIL", "waiting on object", "waiting on multiple objects",
        "contended critical section", "sleeping", "outside guest code"
    };
    int count = *(volatile int *)&g_all_n;
    if (count < 0) count = 0;
    if (count > MAXCPUS) count = MAXCPUS;
    CPU *holder = *(CPU *volatile *)&g_cur_cpu;
    fprintf(stderr, "\n[nfsu1 diagnostics] report %lu, frames=%ld; approximate guest snapshots:\n",
            report, metal_frames());
    nfsu1_diagnostics_words();
    int shown = 0;
    for (int i = 0; i < count; i++){
        CPU *source = *(CPU *volatile *)&g_all_cpus[i];
        if (!source) continue;
        uint32_t tid = *(volatile uint32_t *)&g_all_tids[i];
        int state = g_tstate[i].what;
        uint32_t object = g_tstate[i].obj;
        /* Only copy fields used below; avoid scanning an actively changing CPU. */
        CPU snapshot = {0};
        snapshot.eip = ((volatile CPU *)source)->eip;
        snapshot.esp = ((volatile CPU *)source)->esp;
        snapshot.ebp = ((volatile CPU *)source)->ebp;
        if (source != *(CPU *volatile *)&g_all_cpus[i] ||
            tid != *(volatile uint32_t *)&g_all_tids[i]){
            fprintf(stderr, "  slot %d changed during sampling; skipped\n", i);
            continue;
        }
        shown++;
        fprintf(stderr, "  slot=%d tid=%u%s state=%s(%d) wait_object=0x%08x"
                " eip=0x%08x esp=0x%08x ebp=0x%08x\n",
                i, tid, source == holder ? " (last observed GIL CPU)" : "",
                state >= TS_RUN && state <= TS_IDLE ? states[state] : "unknown",
                state, object, snapshot.eip, snapshot.esp, snapshot.ebp);
        if (snapshot.esp && snapshot.esp <= GSZ - 8192u)
            guest_backtrace(&snapshot, 12);
        else
            fprintf(stderr, "    stack pointer outside guest range; scan skipped\n");
    }
    if (!shown) fprintf(stderr, "  no registered guest CPU observed\n");
    fprintf(stderr, "[nfsu1 diagnostics] end of report\n");
    fflush(stderr);
}

static void *diagnostics_main(void *unused){
    (void)unused;
    unsigned long report = 0;
    for (;;){
        struct timespec remaining = report_interval;
        while (nanosleep(&remaining, &remaining) != 0){
            if (errno != EINTR){
                fprintf(stderr, "[nfsu1 diagnostics] interval wait failed; stopping\n");
                return NULL;
            }
        }
        report_threads(++report);
    }
    return NULL;
}

static void diagnostics_init(void){
    const char *value = getenv("NFSU1_DIAGNOSTICS");
    if (!value || !*value) return;
    char *end;
    errno = 0;
    double seconds = strtod(value, &end);
    /* Bound conversions and avoid an accidental high-frequency stack scanner. */
    if (errno || end == value || *end || !isfinite(seconds) ||
        seconds < 0.1 || seconds > 86400.0){
        fprintf(stderr, "[nfsu1 diagnostics] expected interval 0.1..86400 seconds; disabled\n");
        return;
    }
    report_interval.tv_sec = (time_t)seconds;
    report_interval.tv_nsec = (long)((seconds - (double)report_interval.tv_sec) * 1e9);
    const char *words = getenv("NFSU1_DIAGNOSTIC_WORDS");
    while (words && *words && watched_count < 16){
        char *word_end;
        errno = 0;
        unsigned long address = strtoul(words, &word_end, 0);
        if (errno || word_end == words || (*word_end && *word_end != ',') ||
            address > GSZ - 4u || (address & 3u)){
            fprintf(stderr, "[nfsu1 diagnostics] invalid aligned guest word address; remaining words ignored\n");
            break;
        }
        watched_words[watched_count++] = (uint32_t)address;
        words = *word_end ? word_end + 1 : word_end;
    }
    pthread_t thread;
    int error = pthread_create(&thread, NULL, diagnostics_main, NULL);
    if (error){
        fprintf(stderr, "[nfsu1 diagnostics] could not start reporting thread (%d)\n", error);
        return;
    }
    pthread_detach(thread);
    fprintf(stderr, "[nfsu1 diagnostics] thread snapshots every %.3g seconds (including before first Present)\n",
            seconds);
}

void nfsu1_diagnostics_start(void){
    pthread_once(&diagnostics_once, diagnostics_init);
}
