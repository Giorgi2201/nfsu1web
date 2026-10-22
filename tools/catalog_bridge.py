#!/usr/bin/env python3
"""Consume saved PC function/CFG metadata without discovering functions.

Original adapter; no upstream implementation or game instructions included.
The optional smoke test uses only the synthetic bytes declared below.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
from types import MethodType, SimpleNamespace


def address(value):
    if isinstance(value, bool):
        raise ValueError("boolean address")
    value = int(value, 0) if isinstance(value, str) else value
    if not isinstance(value, int) or not 0 <= value < 2**32:
        raise ValueError("address outside uint32")
    return value


def normalize(catalog):
    """Retain catalog block extents, successors, calls and entry distinctions."""
    base, lo, hi = (address(catalog[k]) for k in
                    ("image_base", "code_start", "code_end"))
    if not base <= lo < hi:
        raise ValueError("invalid image/code bounds")
    functions, seen = [], set()
    for item in catalog["functions"]:
        entry = address(item["address"])
        if entry in seen or not lo <= entry < hi:
            raise ValueError("duplicate or out-of-range function")
        seen.add(entry)
        blocks, starts = [], set()
        for raw in item["blocks"]:
            if len(raw) != 4:
                raise ValueError("expected [start, end, successors, is_exit]")
            start, end = address(raw[0]), address(raw[1])
            if not lo <= start < end <= hi or start in starts:
                raise ValueError("invalid or duplicate block")
            if raw[3] not in (0, 1):
                raise ValueError("invalid exit marker")
            starts.add(start)
            blocks.append([start, end, sorted({address(a) for a in raw[2]}),
                           int(raw[3])])
        if entry not in starts:
            raise ValueError("function has no entry block")
        blocks.sort()
        # x86 may enter the same bytes at different instruction offsets. Keep
        # overlapping decode contexts separate; each range is decoded exactly
        # in attach_catalog rather than merged or split into guessed blocks.
        functions.append({"address": entry, "blocks": blocks,
                          "entry_kind": item.get("entry_kind", "start"),
                          "is_thunk": bool(item.get("is_thunk", False)),
                          "calls_to": sorted({address(a) for a in item["calls_to"]}),
                          "jump_targets": sorted({address(a) for a in item["jump_targets"]})})
    functions.sort(key=lambda f: f["address"])
    external_calls = sorted({a for f in functions for a in f["calls_to"]
                             if a not in seen})
    return {"schema": "nfsu-catalog-bridge-v1", "image_base": base,
            "code_start": lo, "code_end": hi, "functions": functions,
            "unresolved_calls": external_calls,
            "binary_identity": "unverified: original catalog contains no digest"}


def attach_catalog(lifter, catalog, route_catalog_tails=False,
                   cooperative_yield_entries=None):
    """Replace web Lifter.discover with exact-range decoding of saved blocks.

    Lifter supplies Capstone in md and VA-addressed sections in secs. It still
    supplies instruction semantics and C emission. No search for new entries.
    Successors/exit kinds/jump targets remain metadata; jump-table merging
    state is cleared. Optional tail routing adds termination nodes only for
    already catalogued entry addresses, without decoding or discovering more.
    Optional cooperative yields apply only to the first real instruction of
    explicitly selected functions, using the runtime's existing scheduler.
    """
    plan = normalize(catalog)
    entries = {f["address"]: f for f in plan["functions"]}
    cooperative_yield_entries = set(cooperative_yield_entries or ())
    if cooperative_yield_entries and not route_catalog_tails:
        raise ValueError("cooperative yield entries require catalog-tail instruction routing")
    if cooperative_yield_entries - entries.keys():
        raise ValueError("cooperative yield entry is absent from the catalog")
    original_insn = lifter.insn if route_catalog_tails else None
    # A saved alias may start at a conditional branch, with its cmp in an
    # adjacent block retained only by the canonical owner. Index only pairs
    # actually saved together; equal addresses alone do not establish context.
    guard_predecessors = {}
    for function in plan["functions"]:
        ending = {}
        for start, end, *_ in function["blocks"]:
            ending.setdefault(end, set()).add((start, end))
        for start, end, *_ in function["blocks"]:
            guard_predecessors.setdefault((start, end), set()).update(
                ending.get(start, ()))
    guard_decodes = {}

    def decode_range(self, start, end):
        section = next((s for s in self.secs
                        if s[1] <= start and end <= s[1] + len(s[3])), None)
        if section is None:
            raise ValueError("catalog block outside available section bytes")
        data = section[3][start - section[1]:end - section[1]]
        instructions = list(self.md.disasm(data, start))
        cursor = start
        for ins in instructions:
            if ins.address != cursor or ins.size <= 0:
                raise ValueError("non-contiguous decode")
            cursor += ins.size
        if cursor != end:
            raise ValueError("catalog block does not decode exactly")
        return instructions

    if route_catalog_tails:
        if __package__:
            from .nfsu1_instructions import emit_instruction
        else:
            from nfsu1_instructions import emit_instruction

        def instruction(self, ins, targets):
            if getattr(ins, "catalog_tail", False):
                targets.add(ins.address)
                return [f"DISPATCH_TAIL(c, 0x{ins.address:08x}u);"]
            extension = emit_instruction(self, ins)
            lines = extension if extension is not None else original_insn(ins, targets)
            if ins.address == getattr(self, "_catalog_cooperative_yield_entry", None):
                return ["{ void guest_fair_yield(void); guest_fair_yield(); }", *lines]
            return lines
        lifter.insn = MethodType(instruction, lifter)

    def discover(self, entry):
        function = entries[entry]  # missing entry is an error, never discovery
        self._catalog_cooperative_yield_entry = (
            entry if entry in cooperative_yield_entries else None)
        blocks = {}
        self.jtab = {}
        for start, end, successors, is_exit in function["blocks"]:
            blocks[start] = decode_range(self, start, end)
        # Recover MSVC jump tables from the saved blocks. Upstream discover
        # builds self.jtab while walking the CFG; the catalog path must rebuild
        # it or switch sites emit DISPATCH_TAIL to mid-function case VAs that
        # are absent from fntab. Only keep a table when every target is already
        # a block of this function (so the C switch has labels). Targets that
        # are other catalog entries stay as DISPATCH_TAIL, which can resolve.
        if os.environ.get("JTSWITCH", "") == "1":
            from capstone.x86 import X86_OP_IMM, X86_OP_REG, X86_OP_MEM
            try:
                from capstone.x86 import (X86_REG_EAX, X86_REG_ECX, X86_REG_EDX,
                                         X86_REG_EBX, X86_REG_ESP, X86_REG_EBP,
                                         X86_REG_ESI, X86_REG_EDI)
            except ImportError:
                from capstone.x86_const import (X86_REG_EAX, X86_REG_ECX, X86_REG_EDX,
                                               X86_REG_EBX, X86_REG_ESP, X86_REG_EBP,
                                               X86_REG_ESI, X86_REG_EDI)
            r32_names = {
                X86_REG_EAX: "eax", X86_REG_ECX: "ecx", X86_REG_EDX: "edx",
                X86_REG_EBX: "ebx", X86_REG_ESP: "esp", X86_REG_EBP: "ebp",
                X86_REG_ESI: "esi", X86_REG_EDI: "edi",
            }

            def block_end(insns):
                last = insns[-1]
                return last.address + last.size

            # Layout fallthrough: block whose end VA equals this block's start.
            pred_by_start = {}
            for start, instructions in blocks.items():
                if instructions:
                    pred_by_start[block_end(instructions)] = start

            def exit_consts(insns):
                """r32 id -> imm for registers with a definite constant at block end."""
                consts = {}
                i = 0
                while i < len(insns):
                    ins = insns[i]
                    ops = ins.operands
                    if (ins.mnemonic == "mov" and len(ops) == 2
                            and ops[0].type == X86_OP_REG and ops[0].reg in r32_names
                            and ops[1].type == X86_OP_IMM):
                        consts[ops[0].reg] = ops[1].imm & 0xffffffff
                    elif (ins.mnemonic == "push" and len(ops) == 1
                          and ops[0].type == X86_OP_IMM):
                        # MSVC often inserts dec/inc on the index between
                        # `push imm` and `pop limitreg` before cmp/ja.
                        j = i + 1
                        while j < len(insns):
                            mid = insns[j]
                            if (mid.mnemonic == "pop" and mid.operands
                                    and mid.operands[0].type == X86_OP_REG
                                    and mid.operands[0].reg in r32_names):
                                consts[mid.operands[0].reg] = ops[0].imm & 0xffffffff
                                i = j + 1
                                break
                            if mid.mnemonic in ("push", "call", "jmp", "ret", "retf",
                                                "cmp", "test") or mid.mnemonic.startswith("j"):
                                i += 1
                                break
                            if self._jt_writes(mid, "esp"):
                                i += 1
                                break
                            j += 1
                        else:
                            i += 1
                        continue
                    elif (ins.mnemonic == "xor" and len(ops) == 2
                          and ops[0].type == X86_OP_REG and ops[1].type == X86_OP_REG
                          and ops[0].reg == ops[1].reg and ops[0].reg in r32_names):
                        consts[ops[0].reg] = 0
                    else:
                        for reg, name in r32_names.items():
                            if self._jt_writes(ins, name):
                                consts.pop(reg, None)
                    i += 1
                return consts

            def jt_bound_reg(insns, incoming):
                """cmp index, limitreg; ja/jbe when limitreg holds a known immediate."""
                if not insns:
                    return None
                j = insns[-1]
                if j.mnemonic not in ("ja", "jbe") or j.operands[0].type != X86_OP_IMM:
                    return None
                between = []
                for k in reversed(insns[:-1]):
                    if k.mnemonic == "cmp":
                        o = k.operands
                        if (len(o) != 2 or o[0].type != X86_OP_REG
                                or o[0].reg not in r32_names
                                or o[1].type != X86_OP_REG
                                or o[1].reg not in r32_names):
                            return None
                        idx = o[0].reg
                        if any(self._jt_writes(x, r32_names[idx]) for x in between):
                            return None
                        if o[1].reg not in incoming:
                            return None
                        held = (j.address + j.size if j.mnemonic == "ja"
                                else j.operands[0].imm & 0xffffffff)
                        return idx, incoming[o[1].reg], held
                    if k.mnemonic not in self._JT_PASS:
                        return None
                    between.append(k)
                return None

            def stack_slot(operand):
                # Narrow MSVC spill form: a dword at a fixed frame offset.
                # ESP-relative slots and indexed/segmented addresses need
                # additional alias and register-lifetime analysis.
                if operand.type != X86_OP_MEM or operand.size != 4:
                    return None
                mem = operand.mem
                if mem.segment or mem.base != X86_REG_EBP or mem.index:
                    return None
                return mem.disp

            def jt_bound_stack(insns):
                if len(insns) < 2:
                    return None
                branch = insns[-1]
                compare = insns[-2]
                if (branch.mnemonic not in ("ja", "jbe")
                        or branch.operands[0].type != X86_OP_IMM
                        or compare.mnemonic != "cmp" or len(compare.operands) != 2):
                    return None
                slot = stack_slot(compare.operands[0])
                limit = compare.operands[1]
                if slot is None or limit.type != X86_OP_IMM:
                    return None
                held = (branch.address + branch.size if branch.mnemonic == "ja"
                        else branch.operands[0].imm & 0xffffffff)
                return slot, limit.imm & 0xffffffff, held

            bounds = {}
            stack_bounds = {}
            for start, instructions in blocks.items():
                if not instructions:
                    continue
                bound = self._jt_bound(instructions)
                stack_bound = jt_bound_stack(instructions)
                if (not bound and instructions[-1].mnemonic in ("ja", "jbe")):
                    predecessors = guard_predecessors.get(
                        (start, block_end(instructions)), ())
                    if len(predecessors) == 1:
                        extent = next(iter(predecessors))
                        if extent not in guard_decodes:
                            guard_decodes[extent] = decode_range(self, *extent)
                        # Upstream requires a cmp followed only by flag-neutral
                        # instructions that preserve the index. A branch/call or
                        # flag write in this predecessor therefore rejects it.
                        bound = self._jt_bound(guard_decodes[extent] + instructions)
                        if not stack_bound:
                            stack_bound = jt_bound_stack(guard_decodes[extent] + instructions)
                if not bound:
                    incoming = {}
                    pred = pred_by_start.get(start)
                    if pred is not None:
                        incoming = exit_consts(blocks[pred])
                    incoming = {**incoming, **exit_consts(instructions)}
                    bound = jt_bound_reg(instructions, incoming)
                if bound:
                    bounds[bound[2]] = bound[:2]
                if stack_bound:
                    stack_bounds[stack_bound[2]] = stack_bound[:2]
            for start, instructions in list(blocks.items()):
                if not instructions:
                    continue
                if instructions[-1].address in self.jtab:
                    continue
                table = None
                if start in bounds:
                    table = self._jt_table(instructions, bounds[start])
                if table is None and start in stack_bounds:
                    slot, limit = stack_bounds[start]
                    load = instructions[0]
                    ops = load.operands
                    if (load.mnemonic == "mov" and len(ops) == 2
                            and ops[0].type == X86_OP_REG and ops[0].reg in r32_names
                            and ops[0].size == 4 and stack_slot(ops[1]) == slot):
                        table = self._jt_table(instructions[1:], (ops[0].reg, limit))
                if table is None:
                    continue
                # Keep the table when every arm is either a block of this
                # function (goto label) or another catalog entry (synthetic
                # catalog_tail block -> DISPATCH_TAIL into fntab). Rejecting
                # the whole table for a few external arms left mid-function
                # cases as DISPATCH_TAIL targets absent from fntab.
                if not all(t in blocks or t in entries for t in table[2]):
                    continue
                for target in table[2]:
                    if target not in blocks and target in entries:
                        blocks[target] = [SimpleNamespace(
                            address=target, size=0, mnemonic="ret",
                            operands=[], catalog_tail=True)]
                self.jtab[instructions[-1].address] = table
        if route_catalog_tails:
            tails = set()
            for instructions in blocks.values():
                for ins in instructions:
                    # Capstone's architecture-independent IMM operand kind is 2.
                    if (ins.mnemonic.startswith('j') or ins.mnemonic.startswith('loop')):
                        if ins.operands and ins.operands[0].type == 2:
                            target = ins.operands[0].imm & 0xffffffff
                            if target in entries and target not in blocks:
                                tails.add(target)
                last = instructions[-1]
                if last.mnemonic not in ('ret', 'retf', 'jmp', 'int3', 'hlt',
                                         'ud2', 'iret', 'iretd'):
                    target = last.address + last.size
                    if target in entries and target not in blocks:
                        tails.add(target)
            for target in tails:
                # A synthetic ret-shaped terminator lets the existing C emitter
                # use its normal label logic; instruction() emits typed tail
                # dispatch, never a guest ret or guessed instruction bytes.
                blocks[target] = [SimpleNamespace(address=target, size=0,
                                  mnemonic='ret', operands=[], catalog_tail=True)]
            self.catalog_tail_targets = tails
        return blocks, set(function["calls_to"])

    lifter.discover = MethodType(discover, lifter)
    return plan


def synthetic_catalog():
    # Authored fixture, unrelated to any game's addresses or bytes:
    # mov eax,[esp+4]; add eax,[esp+8]; ret
    return {"image_base": 0x1000, "code_start": 0x1000, "code_end": 0x1009,
            "functions": [{"address": 0x1000, "entry_kind": "start",
                           "is_thunk": False, "calls_to": [], "jump_targets": [],
                           "blocks": [[0x1000, 0x1009, [], 1]]}]}


def load_web_lifter(checkout):
    """Load upstream, mutating this CLI process's environment to smoke defaults."""
    import os
    for key in ("FLAGABI", "LREGS", "X87OPT", "JTSWITCH", "FTOL2INL", "INLINE_LIST"):
        os.environ.pop(key, None)
    os.environ["RETEIP"] = "1"  # the smoke verifies guest return-slot contents
    path = Path(checkout) / "tools" / "lift.py"
    spec = importlib.util.spec_from_file_location("nfsu_web_lift", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upstream_smoke(checkout):
    """Exercise the actual MIT web lifter if its dependencies are installed."""
    module = load_web_lifter(checkout)
    lifter = module.RawLifter(bytes.fromhex("8b44240403442408c3"), base=0x1000)
    attach_catalog(lifter, synthetic_catalog())
    code, targets = lifter.lift(0x1000)
    if lifter.traps or getattr(lifter, "truncated", 0) or targets:
        raise RuntimeError("synthetic lift produced traps or unresolved edges")
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--upstream-smoke", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.catalog) == bool(args.upstream_smoke):
        parser.error("choose --catalog or --upstream-smoke")
    if args.catalog:
        result = json.dumps(normalize(json.loads(args.catalog.read_text())), indent=2)
    else:
        result = upstream_smoke(args.upstream_smoke)
    # Refuse to overwrite an existing artifact.
    with args.output.open("x") as output:
        output.write(result + "\n")


if __name__ == "__main__":
    main()
