#ifndef NFS_ABK_H
#define NFS_ABK_H

#include "cpu.h"

typedef struct {
    uint32_t va;
    const uint8_t *code;
    uint32_t len;
    const uint16_t *rel;
    uint32_t nrel;
} nfs_abk_block_t;

extern const nfs_abk_block_t nfs_abk_blocks[];
extern const unsigned nfs_abk_block_count;

typedef struct {
    uint32_t va;
    guest_fn_t fn;
} Nfsu1AbkFunction;

extern const Nfsu1AbkFunction nfsu1_abk_functions[];
extern const unsigned nfsu1_abk_function_count;
extern const uint32_t nfsu1_abk_call_targets[];
extern const unsigned nfsu1_abk_call_target_count;

/* Match a loaded-bank callback by its full containing block. */
int nfsu1_abk_dispatch(CPU *c, uint32_t target);

/* Translate a canonical ABK return address while a matched routine is active. */
uint32_t nfsu1_abk_return_address(uint32_t canonical);

#endif
