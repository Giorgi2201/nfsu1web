#!/usr/bin/env python3
"""Emit private CPU* ABI sound-bank routines from the cached original analysis.

No discovery or main-image emission is repeated. Original bank bytes stay in
ignored output; the input banks and executable are never modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
from types import MethodType

from catalog_bridge import attach_catalog, load_web_lifter
from lift_catalog import verify_emitter
from prepare_abk_catalog import bank_inputs, load_pinned_sources


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=ROOT / "work/analysis/abk")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=ROOT / "work/data")
    parser.add_argument("--upstream", type=Path, default=ROOT / "work/upstream/nfsu2-web")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "gen/nfsu1-abk")
    args = parser.parse_args()
    output, analysis = args.output_dir.resolve(), args.analysis.resolve()
    if not any(output.is_relative_to(ROOT / folder) for folder in ("gen", "work", "out")):
        parser.error("game-derived output must remain in ignored gen/, work/ or out/")
    if output.exists() and any(output.iterdir()):
        parser.error("choose an empty output directory")
    metadata = json.loads((analysis / "metadata.json").read_text())
    if metadata.get("schema") != "nfsu1-abk-catalog-cache-v1":
        parser.error("unsupported ABK analysis metadata")
    if (metadata["inputs"]["sources"] != load_pinned_sources(args.upstream.resolve().parent)
            or metadata["inputs"].get("catalog_bridge_sha256") != digest(ROOT / "tools/catalog_bridge.py")
            or metadata["inputs"]["wrapper_sha256"] != digest(ROOT / "tools/prepare_abk_catalog.py")):
        parser.error("ABK analysis source/tool provenance changed; rerun cached preparation")
    if digest(args.image) != metadata["inputs"]["image_sha256"]:
        parser.error("main image does not match the ABK analysis")
    profile = json.loads((ROOT / "profiles/nfsu1-pc.json").read_text())
    if digest(args.image) != profile["identity"]["sha256"]:
        parser.error("main image does not match the PC profile")
    for name in ("analysis.dll", "catalog.json", "seeds.json", "blocks.c"):
        if digest(analysis / name) != metadata["outputs"].get(name):
            parser.error(f"cached ABK output hash mismatch: {name}")
    for bank in metadata["inputs"]["banks"]:
        path = (args.data / bank["path"]).resolve()
        if not path.is_relative_to(args.data.resolve()) or digest(path) != bank["sha256"]:
            parser.error("bank input differs from cached ABK analysis")
    if bank_inputs(args.data.resolve())[1] != metadata["inputs"]["banks"]:
        parser.error("bank inventory differs from cached ABK analysis; rerun preparation")
    verify_emitter(args.upstream)
    os.environ["FLAGOPT"] = "0"
    os.environ["X87PC"] = "1"
    module = load_web_lifter(args.upstream)
    os.environ["JTSWITCH"] = "1"
    lifter = module.Lifter(str(analysis / "analysis.dll"), comments=False)
    catalog = json.loads((analysis / "catalog.json").read_text())
    plan = attach_catalog(lifter, catalog, route_catalog_tails=True)
    addresses = {f["address"] for f in plan["functions"]}
    external = set(catalog["unresolved_calls"])
    import pefile
    image = pefile.PE(str(args.image)).get_memory_mapped_image()
    # Recover original call-index operands from the verified bank inputs.
    max_index = -1
    for bank in metadata["inputs"]["banks"]:
        data = (args.data / bank["path"]).read_bytes()
        rel_table = struct.unpack_from("<I", data, 0x30)[0]
        count = struct.unpack_from("<I", data, rel_table)[0]
        for offset in struct.unpack_from(f"<{count}I", data, rel_table + 4):
            max_index = max(max_index, struct.unpack_from("<I", data, offset)[0])
    if not 0 <= max_index <= 1023:
        parser.error("invalid ABK main-image call table extent")
    call_targets = list(struct.unpack_from(f"<{max_index + 1}I", image, 0x6e9ae8 - 0x400000))
    if external - set(call_targets):
        parser.error("analysis contains calls outside the original ABK function table")
    semantic_instruction = lifter.insn
    translated_calls = 0

    def instruction(self, ins, targets):
        nonlocal translated_calls
        lines = semantic_instruction(ins, targets)
        if ins.mnemonic == "call":
            # This is part of instruction emission: preserve the loaded bank's
            # real guest return address instead of exposing analysis-module VAs.
            token = f"PUSH32(0x{ins.address + ins.size:x}u);"
            replacement = f"PUSH32(nfsu1_abk_return_address(0x{ins.address + ins.size:x}u));"
            if sum(line.count(token) for line in lines) != 1:
                raise ValueError("ABK call lacks a unique guest return-slot push")
            lines = [line.replace(token, replacement) for line in lines]
            translated_calls += 1
        return lines

    lifter.insn = MethodType(instruction, lifter)
    bodies = []
    for address in sorted(addresses):
        lifter.traps = lifter.truncated = 0
        decoded, _ = lifter.discover(address)
        for instructions in decoded.values():
            last = instructions[-1]
            if last.mnemonic not in ("ret", "retf", "jmp", "int3", "hlt", "ud2", "iret", "iretd"):
                if last.address + last.size not in decoded:
                    raise ValueError("ABK catalog omits a fallthrough block")
            for ins in instructions:
                if ins.mnemonic == "call" and ins.operands[0].type == 2:
                    target = ins.operands[0].imm & 0xffffffff
                    if target not in addresses and target not in external:
                        raise ValueError(f"unreviewed ABK direct call {target:08x}")
        code, targets = lifter.lift(address)
        if (lifter.traps or lifter.truncated or "unsupported_insn(" in code
                or set(targets) - addresses - external):
            raise ValueError(f"incomplete ABK emission at {address:08x}")
        bodies.append(code)
    output.mkdir(parents=True, exist_ok=True)
    notice = "/* GAME-DERIVED: local output, DO NOT DISTRIBUTE. */\n"
    header = ["#ifndef NFSU1_ABK_DECLS_H", "#define NFSU1_ABK_DECLS_H", '#include "nfs_abk.h"']
    header += [f"void sub_{a:08x}(CPU *);" for a in sorted(addresses)]
    header += ["#endif", ""]
    (output / "abk_decls.h").write_text("\n".join(header))
    (output / "abk_functions.c").write_text(
        notice + '#include "abk_decls.h"\n#include <math.h>\n' + "\n\n".join(bodies) + "\n")
    tables = [notice, '#include "abk_decls.h"',
              "const Nfsu1AbkFunction nfsu1_abk_functions[] = {"]
    tables += [f"  {{0x{a:08x}u, sub_{a:08x}}}," for a in sorted(addresses)]
    tables += ["};", f"const unsigned nfsu1_abk_function_count = {len(addresses)};",
               "const uint32_t nfsu1_abk_call_targets[] = {"]
    tables += [f"  0x{a:08x}u," for a in call_targets]
    tables += ["};", f"const unsigned nfsu1_abk_call_target_count = {len(call_targets)};", ""]
    (output / "abk_tables.c").write_text("\n".join(tables))
    shutil.copyfile(analysis / "blocks.c", output / "blocks.c")
    report = {"status": "emission_complete", "functions": len(addresses),
              "main_image_targets": len(external), "translated_call_sites": translated_calls,
              "analysis_cache_key": metadata["cache_key"],
              "catalog_sha256": digest(analysis / "catalog.json"),
              "emitter_sha256": digest(Path(__file__)),
              "outputs": {name: digest(output / name) for name in (
                  "abk_decls.h", "abk_functions.c", "abk_tables.c", "blocks.c")}}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
