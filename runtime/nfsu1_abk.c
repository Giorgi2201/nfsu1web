/* Content-matched dispatch for relocated EA sound-bank routines.
 * The source block/relocation format follows the user's authorized
 * codepdbh/nfsu1-recompiled reuse; see docs/source-permissions.md.
 */
#include "nfs_abk.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define ABK_PAGE_SIZE 0x4000u

typedef struct {
    int active;
    unsigned block_index;
    uint32_t loaded_base;
} abk_active_t;

static _Thread_local abk_active_t active_abk;
static _Thread_local unsigned diagnostic_matches;
static int metadata_state;

static int block_bounds_valid(const nfs_abk_block_t *block) {
    uint64_t end;
    if (!block || !block->code || !block->len ||
        (block->nrel && !block->rel)) return 0;
    end = (uint64_t)block->va + block->len;
    if (end > 0x100000000ull) return 0;
    for (uint32_t i = 0; i < block->nrel; ++i) {
        uint32_t rel = block->rel[i];
        uint32_t call_index;
        if (rel == 0 || (uint64_t)rel + 4u > block->len ||
            block->code[rel - 1u] != 0xe8u) return 0;
        if (i && (uint32_t)block->rel[i - 1u] + 4u > rel) return 0;
        call_index = (uint32_t)block->code[rel] |
                     ((uint32_t)block->code[rel + 1u] << 8) |
                     ((uint32_t)block->code[rel + 2u] << 16) |
                     ((uint32_t)block->code[rel + 3u] << 24);
        if (call_index >= nfsu1_abk_call_target_count ||
            nfsu1_abk_call_targets[call_index] < DISPATCH_TEXT_BASE ||
            (uint64_t)nfsu1_abk_call_targets[call_index] >=
                (uint64_t)DISPATCH_TEXT_BASE + DISPATCH_TEXT_SIZE) return 0;
    }
    return 1;
}

static int metadata_validate(void) {
    if (!nfs_abk_block_count || !nfsu1_abk_function_count ||
        !nfsu1_abk_call_target_count || nfs_abk_block_count > 4096u ||
        nfsu1_abk_function_count > 65536u ||
        nfsu1_abk_call_target_count > 65536u) return 0;
    for (unsigned i = 0; i < nfs_abk_block_count; ++i) {
        uint64_t a0, a1;
        if (!block_bounds_valid(&nfs_abk_blocks[i])) return 0;
        a0 = nfs_abk_blocks[i].va;
        a1 = a0 + nfs_abk_blocks[i].len;
        for (unsigned j = 0; j < i; ++j) {
            uint64_t b0 = nfs_abk_blocks[j].va;
            uint64_t b1 = b0 + nfs_abk_blocks[j].len;
            if (a0 < b1 && b0 < a1) return 0;
        }
    }
    for (unsigned i = 0; i < nfsu1_abk_function_count; ++i) {
        unsigned containing = 0;
        if (!nfsu1_abk_functions[i].fn) return 0;
        for (unsigned b = 0; b < nfs_abk_block_count; ++b) {
            uint64_t end = (uint64_t)nfs_abk_blocks[b].va + nfs_abk_blocks[b].len;
            if (nfsu1_abk_functions[i].va >= nfs_abk_blocks[b].va &&
                (uint64_t)nfsu1_abk_functions[i].va < end) containing++;
        }
        if (containing != 1) return 0;
        for (unsigned j = 0; j < i; ++j)
            if (nfsu1_abk_functions[i].va == nfsu1_abk_functions[j].va)
                return 0;
    }
    return 1;
}

static int metadata_valid(void) {
    if (!metadata_state) metadata_state = metadata_validate() ? 1 : -1;
    return metadata_state > 0;
}

static int loaded_range_committed(uint32_t base, uint32_t len) {
    uint64_t end = (uint64_t)base + len;
    uint64_t page, last_page;
    if (!len || end > GSZ || end > 0x100000000ull) return 0;
    page = (uint64_t)base & ~(uint64_t)(ABK_PAGE_SIZE - 1u);
    last_page = (end - 1u) & ~(uint64_t)(ABK_PAGE_SIZE - 1u);
    for (;;) {
        if (!mem_is_committed((uint32_t)page)) return 0;
        if (page == last_page) break;
        page += ABK_PAGE_SIZE;
    }
    return 1;
}

static int is_relocation(const nfs_abk_block_t *block, uint32_t offset,
                         uint32_t *rel_index) {
    for (uint32_t i = 0; i < block->nrel; ++i) {
        uint32_t rel = block->rel[i];
        if (offset >= rel && offset - rel < 4u) {
            *rel_index = i;
            return 1;
        }
        if (rel > offset) break;
    }
    return 0;
}

static int same_loaded_block(const nfs_abk_block_t *block, uint32_t base) {
    if (!block_bounds_valid(block) ||
        !loaded_range_committed(base, block->len)) return 0;

    for (uint32_t i = 0; i < block->len; ++i) {
        uint32_t rel_index = 0;
        uint8_t actual = g_mem[base + i];
        if (is_relocation(block, i, &rel_index)) {
            uint32_t rel = block->rel[rel_index];
            uint32_t call_index = (uint32_t)block->code[rel] |
                                  ((uint32_t)block->code[rel + 1u] << 8) |
                                  ((uint32_t)block->code[rel + 2u] << 16) |
                                  ((uint32_t)block->code[rel + 3u] << 24);
            uint32_t disp_bits = (uint32_t)g_mem[base + rel] |
                                 ((uint32_t)g_mem[base + rel + 1u] << 8) |
                                 ((uint32_t)g_mem[base + rel + 2u] << 16) |
                                 ((uint32_t)g_mem[base + rel + 3u] << 24);
            int32_t disp = (int32_t)disp_bits;
            int64_t actual_target = (int64_t)(uint64_t)base + rel + 4 + disp;
            if (call_index >= nfsu1_abk_call_target_count ||
                actual_target != (int64_t)nfsu1_abk_call_targets[call_index])
                return 0;
            i = rel + 3u;
        } else if (actual != block->code[i]) {
            return 0;
        }
    }
    return 1;
}

static int routine_in_block(const Nfsu1AbkFunction *function,
                            const nfs_abk_block_t *block,
                            uint32_t *offset_out) {
    uint64_t end = (uint64_t)block->va + block->len;
    if (function->va < block->va || (uint64_t)function->va >= end) return 0;
    *offset_out = function->va - block->va;
    return 1;
}

static int try_block(CPU *c, uint32_t target, unsigned block_index) {
    const nfs_abk_block_t *block = &nfs_abk_blocks[block_index];
    if (!block_bounds_valid(block)) return 0;
    for (unsigned i = 0; i < nfsu1_abk_function_count; ++i) {
        const Nfsu1AbkFunction *function = &nfsu1_abk_functions[i];
        uint32_t offset;
        uint32_t base;
        abk_active_t previous;
        if (!function->fn || !routine_in_block(function, block, &offset) ||
            target < offset) continue;
        base = target - offset;
        if (!same_loaded_block(block, base)) continue;
        if (diagnostic_matches < 8u && getenv("NFSU1_DIAGNOSTICS")) {
            fprintf(stderr, "[abk] matched loaded=0x%08x canonical=0x%08x block=%u\n",
                    target, function->va, block->len);
            diagnostic_matches++;
        }
        previous = active_abk;
        active_abk.active = 1;
        active_abk.block_index = block_index;
        active_abk.loaded_base = base;
        function->fn(c);
        active_abk = previous;
        return 1;
    }
    return 0;
}

static int dispatch_canonical_in_active_block(CPU *c, uint32_t target) {
    const nfs_abk_block_t *block = &nfs_abk_blocks[active_abk.block_index];
    for (unsigned i = 0; i < nfsu1_abk_function_count; ++i) {
        const Nfsu1AbkFunction *function = &nfsu1_abk_functions[i];
        uint32_t offset;
        if (function->va != target ||
            !routine_in_block(function, block, &offset)) continue;
        if (!same_loaded_block(block, active_abk.loaded_base)) return 0;
        function->fn(c);
        return 1;
    }
    return 0;
}

static int is_canonical_routine(uint32_t target) {
    for (unsigned i = 0; i < nfsu1_abk_function_count; ++i)
        if (nfsu1_abk_functions[i].va == target) return 1;
    return 0;
}

int nfsu1_abk_dispatch(CPU *c, uint32_t target) {
    if (!c || !metadata_valid()) return 0;

    if (active_abk.active) {
        if (active_abk.block_index >= nfs_abk_block_count) return 0;
        if (dispatch_canonical_in_active_block(c, target)) return 1;
        if (is_canonical_routine(target)) return 0;
    }
    for (unsigned i = 0; i < nfs_abk_block_count; ++i)
        if (try_block(c, target, i)) return 1;
    return 0;
}

uint32_t nfsu1_abk_return_address(uint32_t canonical) {
    const nfs_abk_block_t *block;
    uint64_t end, translated;
    if (!active_abk.active || active_abk.block_index >= nfs_abk_block_count)
        return canonical;
    block = &nfs_abk_blocks[active_abk.block_index];
    end = (uint64_t)block->va + block->len;
    if (canonical < block->va || (uint64_t)canonical > end) return canonical;
    translated = (uint64_t)active_abk.loaded_base + (canonical - block->va);
    if (translated >= GSZ || translated > UINT32_MAX) return canonical;
    return (uint32_t)translated;
}
