/* NFSU1: bounded evidence for traffic/world depth comparisons. This samples
 * the CPU reference; it does not change GPU draws or their constants. */
static void nfsu1_depth_draw(uint32_t vp, uint32_t stride, const VSConst *vsk,
                             const VSProg *prog, const DElem *el, int nel,
                             int position_offset, int position_type){
    enum { CAP = 192 };
    static int enabled = -1;
    static uint32_t seen[CAP][10];
    static unsigned count;
    if (enabled < 0){
        const char *setting = getenv("NFSU1_DEPTH_DIAGNOSTICS");
        enabled = !setting || strcmp(setting, "0");
    }
    if (!enabled || count == CAP) return;
    uint32_t caller = 0;
    if (g_com_cpu && mem_is_committed(g_com_cpu->esp + 3u))
        caller = MR32(g_com_cpu->esp);
    uint32_t key[10] = {g_cur_rt, g_cur_zid, g_cur_vs, (uint32_t)g_cur_ps_id,
                      g_rs[7], g_rs[14], g_rs[23], g_cur_fvf, g_rs[27], caller};
    for (unsigned i = 0; i < count; i++)
        if (!memcmp(seen[i], key, sizeof key)) return;
    memcpy(seen[count++], key, sizeof key);
    fprintf(stderr, "[nfsu1 depth] frame=%u caller=%08x rt=%u zid=%u vs=%u ps=%d z=%u write=%u cmp=%u blend=%u fvf=%08x stride=%u indexed=%u",
            g_present_no, caller, g_cur_rt, g_cur_zid, g_cur_vs, g_cur_ps_id,
            g_rs[7], g_rs[14], g_rs[23], g_rs[27], g_cur_fvf, stride, g_ix.n != 0);
    if (g_ix.n){
        /* The indexed caller has already validated the mirrored index span.
         * Recover the corresponding original guest vertex, without expanding
         * or modifying the actual geometry submitted to the GPU. */
        const uint8_t *metal_pool_cpu(void);
        const uint8_t *pool = metal_pool_cpu();
        if (pool && g_ss_vb && mem_is_committed(g_ss_vb + 11u)){
            uint32_t index = 0;
            memcpy(&index, pool + g_ix.ibo, g_ix.isz);
            int64_t vertex = (int64_t)index + g_ix.base;
            uint64_t offset = vertex >= 0 ? (uint64_t)g_ss_off +
                (uint64_t)vertex * stride : UINT64_MAX;
            if (offset <= MR32(g_ss_vb + 4u) &&
                stride <= (uint64_t)MR32(g_ss_vb + 4u) - offset)
                vp = MR32(g_ss_vb + 8u) + (uint32_t)offset;
        }
    }
    if (vp && stride && mem_is_committed(vp) && mem_is_committed(vp + stride - 1u)){
        float pos[4] = {0, 0, 0, 1};
        int sampled = 0;
        static const uint8_t type_bytes[] = {4,8,12,16,4,4,4,8,4,4,8,4,8,4,4,4,8,0};
        int safe = nel >= 0 && nel <= 16;
        for (int k = 0; safe && k < nel; k++)
            if (el[k].reg < 0 || el[k].reg >= 16 || el[k].type >= sizeof type_bytes ||
                !type_bytes[el[k].type] || el[k].off + type_bytes[el[k].type] > stride)
                safe = 0;
        if (prog && nel && safe){
            float inputs[16][4];
            for (unsigned i = 0; i < 16; i++){
                inputs[i][0] = inputs[i][1] = inputs[i][2] = 0.f;
                inputs[i][3] = 1.f;
            }
            for (int k = 0; k < nel; k++)
                decl_fetch(vp + el[k].off, el[k].type, inputs[el[k].reg]);
            VSOut output;
            if (vs_run(prog, vsk, (const float (*)[4])inputs, &output)){
                memcpy(pos, output.pos, sizeof pos);
                sampled = 1;
            }
        } else if (!prog && position_type >= 0 && position_type < (int)sizeof type_bytes &&
                   position_offset >= 0 && type_bytes[position_type] &&
                   (uint32_t)position_offset + type_bytes[position_type] <= stride){
            decl_fetch(vp + (unsigned)position_offset, (unsigned)position_type, pos);
            if (position_type != 3) pos[3] = 1.f;
            sampled = 1;
        }
        if (sampled)
            fprintf(stderr, " cpu-clip=(%.7g,%.7g,%.9g,%.9g) z/w=%.9g",
                    (double)pos[0], (double)pos[1], (double)pos[2], (double)pos[3],
                    pos[3] != 0.f ? (double)pos[2] / pos[3] : 0.0);
    }
    fputc('\n', stderr);
    if (count == CAP) fprintf(stderr, "[nfsu1 depth] unique-state log limit reached\n");
}
