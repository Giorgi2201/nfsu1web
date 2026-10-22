#!/usr/bin/env python3
"""Cache focused additions for runtime-observed missing callbacks.

Uses the pinned original pcrecomp recursive-descent Disassembler, attributed in
docs/source-permissions.md and docs/source-manifest.json. No full discovery or
baseline code-immediate sweep is run. Optional immediate following visits only
newly recovered bodies. Game-derived output stays under ignored work/.
"""
import argparse
from bisect import bisect_left
import hashlib
import json
from pathlib import Path
import sys

from prepare_game_catalog import (GAME_SHA256, PC_REV, PINNED_BLOBS, ROOT,
                                  digest, toolchain_versions)


def serialize(function):
    return {
        "address": function.address, "end": function.end, "size": function.size,
        "entry_kind": function.entry_kind, "is_thunk": function.is_thunk,
        "jump_targets": sorted(function.jump_targets),
        "calls_to": sorted(function.calls_to),
        "blocks": [[b.start, b.end, sorted(set(b.successors)), int(b.is_exit)]
                   for b in sorted(function.blocks.values(), key=lambda b: b.start)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--entry", type=lambda value: int(value, 16), action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, default=ROOT / "work/upstream")
    parser.add_argument("--max-additions", type=int, default=64)
    parser.add_argument("--follow-code-immediates", action="store_true",
                        help="Apply original code_seeds mov/push probe only to newly added bodies")
    args = parser.parse_args()
    image, baseline = args.image.resolve(), args.catalog.resolve()
    out, upstream = args.output_dir.resolve(), args.upstream.resolve()
    if not out.is_relative_to(ROOT / "work"):
        parser.error("Output must be inside this repository's ignored work/ directory")
    if not 1 <= args.max_additions <= 256:
        parser.error("--max-additions must be between 1 and 256")
    if digest(image) != GAME_SHA256:
        parser.error("Image does not match the selected PC NFSU1 1.4 fingerprint")
    sources = {}
    for relative, expected in PINNED_BLOBS.items():
        if relative.startswith("pcrecomp/") or (args.follow_code_immediates and relative.endswith("/code_seeds.py")):
            path = upstream / relative
            data = path.read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if actual != expected:
                parser.error(f"Upstream source differs from pinned blob: {path}")
            sources[relative] = expected
    for sub in ("pe", "disasm"):
        sys.path.insert(0, str(upstream / "pcrecomp/tools" / sub))
    from pe_analyze import analyze_pe, build_iat_map
    from disasm32 import Disassembler, NOT_COMPILED
    from capstone.x86 import X86_OP_IMM

    roots = sorted(set(args.entry))
    inputs = {"image_sha256": digest(image), "parent_catalog_sha256": digest(baseline),
              "tool_sha256": digest(Path(__file__)),
              "prepare_tool_sha256": digest(Path(__file__).with_name("prepare_game_catalog.py")),
              "source_blobs": sources, "toolchain": toolchain_versions(),
              "observed_roots": roots, "max_additions": args.max_additions,
              "follow_code_immediates": args.follow_code_immediates}
    catalog_path, metadata_path = out / "catalog.json", out / "metadata.json"
    if baseline == catalog_path:
        parser.error("Output catalog must not overwrite its baseline")
    if catalog_path.exists() and metadata_path.exists():
        previous = json.loads(metadata_path.read_text())
        if (previous.get("inputs") == inputs and not previous.get("unresolved")
                and previous.get("catalog_sha256") == digest(catalog_path)):
            print(f"Reusing {catalog_path}")
            return
    info = analyze_pe(str(image))
    dis = Disassembler(image.read_bytes(), info.image_base, info.sections)
    iat = build_iat_map(info)
    document = json.loads(baseline.read_text())
    existing = {f["address"]: f for f in document["functions"]}
    # Decode only known blocks overlapping candidate instructions. This rejects
    # interior-byte entries without walking or rediscovering the full image.
    ranges = sorted(set((b[0], b[1]) for f in existing.values() for b in f["blocks"]))
    starts = [s for s, _ in ranges]
    maximum_end = []
    for _, end in ranges:
        maximum_end.append(max(end, maximum_end[-1] if maximum_end else 0))
    decoded = {}
    claimed = {}

    def validate(function):
        if not function or not function.blocks:
            raise ValueError("decode produced no blocks")
        new_instructions = {}
        for block in function.blocks.values():
            cursor = block.start
            for instruction in block.instructions:
                if instruction.address != cursor or instruction.mnemonic in NOT_COMPILED:
                    raise ValueError(f"invalid decode at 0x{cursor:08x}")
                cursor = instruction.end_address
                prior = new_instructions.setdefault(instruction.address, cursor)
                if prior != cursor:
                    raise ValueError(f"conflicting new instruction at 0x{instruction.address:08x}")
            if cursor != block.end or not block.instructions:
                raise ValueError(f"incomplete block at 0x{block.start:08x}")
            last = block.instructions[-1]
            if not (last.is_terminator or last.mnemonic == "int3" or cursor in function.blocks):
                raise ValueError(f"unterminated block at 0x{block.start:08x}")
            for successor in block.successors:
                if successor not in function.blocks and successor not in existing:
                    raise ValueError(f"missing block successor 0x{successor:08x}")
        for start, end in sorted(new_instructions.items()):
            # Each new instruction must agree with every overlapping known block.
            index = bisect_left(starts, end) - 1
            while index >= 0 and maximum_end[index] > start:
                low, high = ranges[index]
                if high > start:
                    key = (low, high)
                    if key not in decoded:
                        raw = dis.read_bytes(low, high - low)
                        decoded[key] = {ins.address: ins.end_address
                                        for ins in dis.disassemble_at(low, max_bytes=high - low)} if raw else {}
                    known = decoded[key]
                    if low <= start < high and known.get(start) != end:
                        raise ValueError(f"conflict with known block at 0x{start:08x}")
                    if start < low < end:
                        raise ValueError(f"instruction crosses known block at 0x{low:08x}")
                index -= 1
        for start, end in new_instructions.items():
            if start in claimed and claimed[start] != end:
                raise ValueError(f"conflict with repaired instruction at 0x{start:08x}")
        ordered = sorted({**claimed, **new_instructions}.items())
        for (_, end), (start, _) in zip(ordered, ordered[1:]):
            if end > start:
                raise ValueError(f"overlapping new instructions at 0x{start:08x}")
        claimed.update(new_instructions)

    added, unresolved, pending = {}, [], list(reversed(roots))
    introductions, rejected_probes = [], []
    attempted_probes = {}
    while pending:
        address = pending.pop()
        if address in existing or address in added:
            continue
        try:
            if not dis.is_code_address(address):
                raise ValueError("entry outside executable text")
            if len(added) >= args.max_additions:
                raise ValueError("direct-call closure exceeded addition cap")
            function = dis.disassemble_function(address, iat)
            validate(function)
            added[address] = serialize(function)
            pending.extend(sorted(function.calls_to - existing.keys() - added.keys(), reverse=True))
            for block in function.blocks.values():
                for instruction in block.instructions:
                    target = instruction.get_branch_target() if instruction.is_call else None
                    if target in function.calls_to and target not in existing:
                        introductions.append({"address": target, "parent_entry": address,
                                              "instruction": instruction.address, "kind": "direct_call"})
                    if not args.follow_code_immediates:
                        continue
                    if (instruction.mnemonic not in ("mov", "push") or instruction.size < 5
                            or not instruction.operands or instruction.operands[-1].type != X86_OP_IMM):
                        continue
                    target = instruction.operands[-1].imm & 0xffffffff
                    if not info.code_start <= target < info.code_end or target in existing or target in added:
                        continue
                    source = {"address": target, "parent_entry": address,
                              "instruction": instruction.address, "kind": "code_immediate"}
                    if target not in attempted_probes:
                        attempted_probes[target] = dis.probes_as_function_body(target)
                    if attempted_probes[target]:
                        introductions.append(source)
                        pending.append(target)
                    else:
                        rejected_probes.append({**source, "reason": "original function-body probe rejected"})
        except ValueError as error:
            unresolved.append({"address": address, "reason": str(error)})
            break
    out.mkdir(parents=True, exist_ok=True)
    metadata = {**inputs, "inputs": inputs, "pcrecomp_revision": PC_REV,
                "added_entries": sorted(added), "unresolved": unresolved,
                "introductions": introductions, "rejected_immediate_probes": rejected_probes,
                "analysis": "pinned recursive descent; observed roots and missing direct calls; optional mov/push probes only in newly added bodies"}
    if unresolved:
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
        # A failed new analysis must not leave an old output looking current.
        catalog_path.unlink(missing_ok=True)
        parser.exit(1, f"Callback repair unresolved; see {metadata_path}\n")
    document["functions"] = [*document["functions"], *[added[a] for a in sorted(added)]]
    temporary = catalog_path.with_suffix(".json.partial")
    temporary.write_text(json.dumps(document, separators=(",", ":")) + "\n")
    temporary.replace(catalog_path)
    metadata["catalog_sha256"] = digest(catalog_path)
    metadata["functions"] = len(document["functions"])
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Catalog ready: {catalog_path} ({len(added)} additions)")


if __name__ == "__main__":
    main()
