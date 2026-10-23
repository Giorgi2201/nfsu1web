/* NFSU1 widescreen host hooks: CPU* port of the pinned PC recomp sites.
 * Semantics from ThirteenAG NFSUnderground.WidescreenFix (MIT) via
 * codepdbh/nfsu1-recompiled. See docs/settings.md. */
#ifndef NFSU1_WIDESCREEN_H
#define NFSU1_WIDESCREEN_H
#include "cpu.h"

#ifndef HOOK_SITE
#define HOOK_SITE(va) (va##u)
#endif

void nfsu1_widescreen_set_display_aspect(float aspect);
void nfsu1_widescreen_set_resolution(unsigned width, unsigned height);
int nfsu1_widescreen_active(void);
float nfsu1_widescreen_hud_pos_x(void);
float nfsu1_widescreen_hud_scale_x(void);
int nfsu1_ws_hook(CPU *c, uint32_t ip);

#endif
