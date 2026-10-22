#!/usr/bin/env python3
"""Check saved split guards and aliases with the real lifter, using authored bytes.

No game input or discovery is used. This checks jump-table emission only, not
runtime/game compatibility.
"""
import argparse
import os
from pathlib import Path
import struct

from catalog_bridge import attach_catalog, load_web_lifter


def fixture(intervening=b""):
    base, table = 0x1000, 0x1040
    data = bytearray(b"\xcc" * 0x60)
    guard = bytes.fromhex("83fb05") + intervening  # cmp ebx,5
    branch = base + len(guard)
    jump = branch + 2
    data[:len(guard)] = guard
    data[branch - base:jump - base] = bytes((0x77, 0x1020 - jump))
    data[jump - base:jump - base + 7] = bytes.fromhex("ff249d") + struct.pack("<I", table)
    targets = list(range(0x1010, 0x1016))
    for target in targets + [0x1020]:
        data[target - base] = 0xc3
    data[table - base:table - base + 24] = struct.pack("<6I", *targets)
    common = [[branch, jump, [jump, 0x1020], 0], [jump, jump + 7, targets, 0]]
    common += [[target, target + 1, [], 1] for target in targets + [0x1020]]
    catalog = {"image_base": base, "code_start": base, "code_end": base + len(data),
               "functions": []}
    for entry, blocks in ((base, [[base, branch, [branch], 0]] + common),
                          (branch, common)):
        catalog["functions"].append({"address": entry, "blocks": blocks,
                                     "calls_to": [], "jump_targets": []})
    return bytes(data), catalog, branch, jump, targets


def stack_slot_fixture(case="positive"):
    base, table = 0x1000, 0x1040
    slot = -0x2c
    disp = slot & 0xff
    data = bytearray(b"\xcc" * 0x80)
    # cmp dword [ebp-0x2c],7
    guard = bytes((0x83, 0x7d, disp, 0x07))
    if case == "store between compare and branch":
        guard += bytes((0x89, 0x45, disp))  # mov [ebp-0x2c],eax
    branch = base + len(guard)
    jump = branch + 2
    data[:len(guard)] = guard
    data[branch - base:jump - base] = bytes((0x77, 0x1020 - jump))

    load_slot = slot if case != "different slot" else -0x28
    dispatch = b""
    if case == "EBP changed before load":
        dispatch += bytes.fromhex("8d6d04")  # lea ebp,[ebp+4]
    dispatch += bytes((0x8b, 0x45, load_slot & 0xff))  # mov eax,[ebp+disp8]
    if case == "loaded register clobbered":
        dispatch += bytes.fromhex("b801000000")  # mov eax,1
    dispatch += bytes.fromhex("ff2485") + struct.pack("<I", table)
    data[jump - base:jump - base + len(dispatch)] = dispatch
    jt_site = jump + len(dispatch) - 7

    targets = list(range(0x1028, 0x1030))
    for target in targets + [0x1020]:
        data[target - base] = 0xc3
    data[table - base:table - base + 32] = struct.pack("<8I", *targets)
    end = jump + len(dispatch)
    blocks = [[base, jump, [jump, 0x1020], 0],
              [jump, end, targets, 0]]
    blocks += [[target, target + 1, [], 1] for target in targets + [0x1020]]
    catalog = {"image_base": base, "code_start": base, "code_end": base + len(data),
               "functions": [{"address": base, "blocks": blocks,
                              "calls_to": [], "jump_targets": []}]}
    return bytes(data), catalog, jt_site, targets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    module = load_web_lifter(args.upstream)
    os.environ["JTSWITCH"] = "1"
    for name, intervening, expected in (("split guard", b"", True),
                                        ("flags overwritten", b"\x41", False),
                                        ("index overwritten", b"\x89\xc3", False),
                                        ("unrelated adjacent range", b"", False)):
        data, catalog, alias, jump, targets = fixture(intervening)
        if name == "unrelated adjacent range":
            catalog["functions"][0]["blocks"] = catalog["functions"][0]["blocks"][:1]
        lifter = module.RawLifter(data, base=0x1000)
        attach_catalog(lifter, catalog)
        # Alias first: recovery must not rely on prior canonical emission.
        for entry in (alias, 0x1000):
            blocks, _ = lifter.discover(entry)
            assert (jump in lifter.jtab) == expected, (name, hex(entry), lifter.jtab)
            if expected:
                assert lifter.jtab[jump][2] == targets
                assert all(target in blocks for target in targets)
                code, _ = lifter.lift(entry)
                assert "case 5u:" in code and "/* indirect tail call */" in code
                assert "MR32(0x1054u) == 0x1015u" in code
        print(f"PASS: {name}, canonical and alias")

    for case, expected in (("positive", True),
                           ("different slot", False),
                           ("EBP changed before load", False),
                           ("store between compare and branch", False),
                           ("loaded register clobbered", False)):
        data, catalog, jump, targets = stack_slot_fixture(case)
        lifter = module.RawLifter(data, base=0x1000)
        attach_catalog(lifter, catalog)
        blocks, _ = lifter.discover(0x1000)
        assert (jump in lifter.jtab) == expected, (case, lifter.jtab)
        if expected:
            assert lifter.jtab[jump][2] == targets
            assert all(target in blocks for target in targets)
            code, _ = lifter.lift(0x1000)
            assert "case 7u:" in code and "/* indirect tail call */" in code
        print(f"PASS: stack-slot {case}")


if __name__ == "__main__":
    main()
