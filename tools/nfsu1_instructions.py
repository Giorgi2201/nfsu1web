"""Original value-semantics additions for the web runtime's x86 lifter.

Reference: Intel SDM, Volume 2B (PADDQ, PSUBQ, UNPCKLPD, UNPCKHPD) and
Volume 1 chapter 8 (FSAVE/FRSTOR 32-bit protected-mode image):
https://www.intel.com/content/dam/www/public/us/en/documents/manuals/64-ia-32-architectures-software-developer-vol-2b-manual.pdf
https://www.intel.com/content/dam/www/public/us/en/documents/manuals/64-ia-32-architectures-software-developer-vol-1-manual.pdf

Only legacy 32-bit guest forms are supported. PADDQ and PSUBQ wrap each
unsigned 64-bit lane; the unpack instructions copy bits without floating-point
conversion. FNSAVE/FRSTOR use the 108-byte protected-mode image with stack-order
ST(0)..ST(7) via f80_store/f80_load; the tag word is written as 0 (all valid)
and ignored on restore, matching the upstream Unicorn bridge. FIP/FDP/opcode
slots are zeroed on save. None of these instructions change EFLAGS. Memory
accesses and MMX/x87 separation follow the existing runtime (CPU.mm is separate
from CPU.st); architectural alignment, SIMD exception delivery and full
MMX/x87 tag aliasing are not introduced here. No upstream source or game
instructions are copied into this module.
"""
from capstone.x86 import X86_OP_MEM, X86_OP_REG

_LANE_ARITH = {"paddq": "+", "psubq": "-"}
_UNPACK = frozenset(("unpcklpd", "unpckhpd"))
_X87_IMAGE = frozenset(("fnsave", "fsave", "frstor"))
_SUPPORTED = frozenset(_LANE_ARITH) | _UNPACK | _X87_IMAGE
_REGISTER_INDICES = tuple(str(index) for index in range(8))


def _register(lifter, operand):
    if operand.type != X86_OP_REG:
        return None
    name = lifter.md.reg_name(operand.reg)
    for kind in ("xmm", "mm"):
        suffix = name[len(kind):] if name.startswith(kind) else ""
        if suffix in _REGISTER_INDICES:
            return kind, int(suffix)
    return None


def _operand_size_override(ins):
    prefix = getattr(ins, "prefix", None) or ()
    return len(prefix) > 2 and prefix[2] == 0x66


def _emit_x87_image(lifter, ins):
    if len(ins.operands) != 1:
        raise ValueError(f"unexpected {ins.mnemonic} operand count")
    operand = ins.operands[0]
    if operand.type != X86_OP_MEM:
        raise ValueError(f"{ins.mnemonic} requires a memory operand")
    if _operand_size_override(ins):
        raise ValueError(f"16-bit {ins.mnemonic} image is not supported")
    ea = f"(uint32_t){lifter.ea(operand.mem)}"
    lines = ["{", f"uint8_t *_nfsu1_p = g_mem + {ea};"]
    if ins.mnemonic in ("fnsave", "fsave"):
        lines.extend([
            "uint16_t _nfsu1_cw = c->fcw;",
            "uint16_t _nfsu1_sw = fsw_get(c);",
            "uint16_t _nfsu1_tw = 0;",
            "memset(_nfsu1_p, 0, 28);",
            "memcpy(_nfsu1_p + 0, &_nfsu1_cw, 2);",
            "memcpy(_nfsu1_p + 4, &_nfsu1_sw, 2);",
            "memcpy(_nfsu1_p + 8, &_nfsu1_tw, 2);",
            "for (int _nfsu1_i = 0; _nfsu1_i < 8; _nfsu1_i++)",
            "  f80_store(_nfsu1_p + 28 + 10 * _nfsu1_i,"
            "            c->st[(c->top + _nfsu1_i) & 7]);",
            "memset(c->st, 0, sizeof c->st);",
            "c->top = 0; c->fcw = 0x037f; c->fsw = 0;",
        ])
    else:
        lines.extend([
            "uint16_t _nfsu1_cw, _nfsu1_sw;",
            "memcpy(&_nfsu1_cw, _nfsu1_p + 0, 2);",
            "memcpy(&_nfsu1_sw, _nfsu1_p + 4, 2);",
            "c->fcw = _nfsu1_cw;",
            "c->top = (int)((_nfsu1_sw >> 11) & 7);",
            "c->fsw = (uint16_t)(_nfsu1_sw & ~0x3800u);",
            "for (int _nfsu1_i = 0; _nfsu1_i < 8; _nfsu1_i++)",
            "  c->st[(c->top + _nfsu1_i) & 7] ="
            "      f80_load(_nfsu1_p + 28 + 10 * _nfsu1_i);",
        ])
    return lines + ["}"]


def _emit_simd(lifter, ins):
    if len(ins.operands) != 2:
        raise ValueError(f"unexpected {ins.mnemonic} operand count")
    dst, src = ins.operands
    destination = _register(lifter, dst)
    if destination is None:
        raise ValueError(f"{ins.mnemonic} requires an XMM/MMX destination")
    kind, index = destination
    if ins.mnemonic in _UNPACK and kind != "xmm":
        raise ValueError(f"{ins.mnemonic} requires an XMM destination")
    source = _register(lifter, src)
    width = 16 if kind == "xmm" else 8
    if source is not None and source[0] != kind:
        raise ValueError(f"mixed register classes for {ins.mnemonic}")
    if source is None and (src.type != X86_OP_MEM or src.size != width):
        raise ValueError(f"unexpected {ins.mnemonic} source operand")

    def dst_lane(lane):
        return f"c->xmm[{index}].u64[{lane}]" if kind == "xmm" else f"c->mm[{index}]"

    def src_lane(lane):
        if source is None:
            return f"MR64((uint32_t)(_nfsu1_ea + {8 * lane}u))"
        source_kind, source_index = source
        if source_kind == "xmm":
            return f"c->xmm[{source_index}].u64[{lane}]"
        return f"c->mm[{source_index}]"

    lines = ["{"]
    if source is None:
        lines.append(f"uint32_t _nfsu1_ea = (uint32_t){lifter.ea(src.mem)};")
    if ins.mnemonic in _UNPACK:
        selected_lane = 1 if ins.mnemonic == "unpckhpd" else 0
        lines.extend([
            f"uint64_t _nfsu1_a0 = {dst_lane(selected_lane)};",
            f"uint64_t _nfsu1_b0 = {src_lane(selected_lane)};",
            f"{dst_lane(0)} = _nfsu1_a0;",
            f"{dst_lane(1)} = _nfsu1_b0;",
        ])
    else:
        op = _LANE_ARITH[ins.mnemonic]
        lanes = range(2 if kind == "xmm" else 1)
        for lane in lanes:
            lines.extend([
                f"uint64_t _nfsu1_a{lane} = {dst_lane(lane)};",
                f"uint64_t _nfsu1_b{lane} = {src_lane(lane)};",
            ])
        for lane in lanes:
            lines.append(f"{dst_lane(lane)} = _nfsu1_a{lane} {op} _nfsu1_b{lane};")
    return lines + ["}"]


def emit_instruction(lifter, ins):
    """Return scoped C statements, or None to use the upstream emitter.

    Both inputs are captured before destination writes, including self-aliasing
    register operands. Recognized mnemonics with unexpected operand forms fail
    explicitly rather than manufacturing successful-looking code.
    """
    if ins.mnemonic not in _SUPPORTED:
        return None
    if ins.mnemonic in _X87_IMAGE:
        return _emit_x87_image(lifter, ins)
    return _emit_simd(lifter, ins)
