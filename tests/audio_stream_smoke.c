/* Focused native check of the real patched browser mixer; no game inputs.
 * After applying the runtime overlay:
 * clang -std=c11 -pthread -Iwork/upstream/nfsu2-web/runtime \
 *   -Iwork/upstream/nfsu2-web/runtime/web tests/audio_stream_smoke.c \
 *   -lm -o /tmp/nfsu1-audio-smoke && /tmp/nfsu1-audio-smoke
 */
#include <assert.h>
#define __builtin_wasm_memory_atomic_wait32(a, b, c) (0)
#include "audio_web.c"

static uint8_t memory[4096];
uint8_t *g_mem = memory;
uint64_t host_us(void){ return 0; }
int nfsu2_register(int kind, void *ptr, uint32_t size){ return 0; }
void horn_mix(float *out, unsigned frames, unsigned rate){}
void carsfx_mix(float *out, unsigned frames, unsigned rate){}

static void check_level(unsigned frames, float level){
    float out[FRAMES * OUT_CH];
    mix_into(out, frames);
    for (unsigned i = 0; i < frames * OUT_CH; i++)
        assert(fabsf(out[i] - level) < 0.00001f);
}

int main(void){
    for (unsigned i = 16; i < sizeof memory; i += 2){
        int16_t value = 8192;
        memcpy(memory + i, &value, 2);
    }
    int id = audio_register(16, 64, OUT_RATE, 2, 16);
    audio_play(id, 1);
    audio_note_region(id, 0, 32); /* a partial write identifies a live stream */
    assert(g_snd[id].fresh);
    check_level(16, 0.25f);
    check_level(16, 0.f); /* old PCM must not repeat, cursors still wrap */
    audio_note_region(id, 48, 16);
    audio_note_region(id, 0, 16); /* two regions of a wrapped Unlock */
    check_level(4, 0.25f);
    check_level(8, 0.f);
    check_level(4, 0.25f);
    check_level(16, 0.f);
    /* Upsampling must reuse a fresh frame for both output samples. */
    audio_set_freq(id, OUT_RATE / 2);
    audio_note_region(id, 0, 16);
    check_level(8, 0.25f);
    check_level(24, 0.f);
    audio_stop(id);
    audio_note_region(id, 0, 64);
    audio_play(id, 1);
    check_level(32, 0.25f); /* a stopped stream can refill and restart */
    check_level(32, 0.f);
    /* Duplicates must not free or consume their source's validity map. */
    int duplicate = audio_duplicate(id);
    assert(!g_snd[duplicate].fresh);
    audio_unregister(duplicate);
    assert(g_snd[id].fresh);
    audio_unregister(id);

    id = audio_register(16, 64, OUT_RATE, 2, 16);
    audio_buffer_static(id, 1);
    audio_play(id, 1);
    audio_note_region(id, 0, 32);
    assert(!g_snd[id].fresh);
    check_level(48, 0.25f); /* intentional static loops keep playing */
    audio_unregister(id);
    puts("audio stream smoke passed");
}
