/* SPDX-License-Identifier: GPL-3.0-only
 * Font atlas dimensions for the NFSU1 PC 1.4 drawing paths. */
#ifndef NFSU1_FONTS_H
#define NFSU1_FONTS_H
#include <stdint.h>

uint32_t nfsu1_font_dimension(uint32_t texture, unsigned axis);
uint32_t nfsu1_font_mip_reduction(uint32_t texture);

#endif
