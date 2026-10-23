"""Scope host HUD constants to verified projection operands, not shared data.

The original float pool is also read by FE layout and animation routines.
Only these PC 1.4 instruction sites consume the widescreen replacements.
No game bytes or translated instructions are stored here.
"""
from types import MethodType

SITES = {
    0x0040BF07: ("fmul", 0x6CC914, "nfsu1_widescreen_hud_scale_x"),
    0x0040BF98: ("fmul", 0x6CC914, "nfsu1_widescreen_hud_scale_x"),
    0x0040BFFD: ("fmul", 0x6CC914, "nfsu1_widescreen_hud_scale_x"),
    0x0040C051: ("fmul", 0x6CC914, "nfsu1_widescreen_hud_scale_x"),
    0x0041E58F: ("fcomp", 0x6CC910, "nfsu1_widescreen_hud_pos_x"),
}


def attach(lifter):
    original = lifter.insn
    seen = set()

    def instruction(self, ins, targets):
        lines = original(ins, targets)
        if ins.address not in SITES:
            return lines
        mnemonic, address, accessor = SITES[ins.address]
        token = f"MRF32(0x{address:x}u)"
        if ins.mnemonic != mnemonic or sum(line.count(token) for line in lines) != 1:
            raise ValueError(f"unexpected HUD operand at 0x{ins.address:08x}")
        seen.add(ins.address)
        return [line.replace(token, f"{accessor}()") for line in lines]

    lifter.insn = MethodType(instruction, lifter)
    return seen
