# SPDX-License-Identifier: GPL-3.0-only
"""Keep imported HD font atlases at their original logical drawing scale.

These four PC 1.4 movsx sites are the dimension reads replaced by the two
NFSHDContentSupport font hooks. Texture header dimensions stay untouched.
Adapted 2026-10-23 from Aero_'s GPL-3.0 NFSHDContentSupport; see NOTICE.md
and patches/NFSHDContentSupport.LICENSE. Distributed without warranty.
"""
from types import MethodType

SITES = {
    0x0040C0E8: ("ecx", 0),
    0x0040C0F0: ("ecx", 1),
    0x004F479B: ("edx", 0),
    0x004F47A6: ("edx", 1),
}
MIP_SITES = {0x00407EB5, 0x00407F3D}


def attach(lifter):
    original = lifter.insn
    seen = set()

    def instruction(self, ins, targets):
        lines = original(ins, targets)
        if ins.address in MIP_SITES:
            token = "MR32(0x7364f4u)"
            if ins.mnemonic != "mov" or sum(line.count(token) for line in lines) != 1:
                raise ValueError(f"unexpected font mip operand at 0x{ins.address:08x}")
            seen.add(ins.address)
            return [line.replace(token, "nfsu1_font_mip_reduction(c->esi)") for line in lines]
        if ins.address not in SITES:
            return lines
        register, axis = SITES[ins.address]
        offset = 0x46 if axis else 0x44
        token = f"MR16(c->{register}+0x{offset:x}u)"
        if ins.mnemonic != "movsx" or sum(line.count(token) for line in lines) != 1:
            raise ValueError(f"unexpected font dimension operand at 0x{ins.address:08x}")
        seen.add(ins.address)
        return [line.replace(token, f"nfsu1_font_dimension(c->{register}, {axis}u)")
                for line in lines]

    lifter.insn = MethodType(instruction, lifter)
    return seen
