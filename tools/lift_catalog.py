#!/usr/bin/env python3
"""Emit private web-ABI C from a cached NFSU1 catalog, without new discovery.

Outputs are game-derived: keep them under ignored gen/ or work/. Failed lifts
are recorded, never replaced by successful-looking no-op functions unless
--link-stubs is set (visible abort stubs for bring-up linking only).
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import time

from catalog_bridge import attach_catalog, load_web_lifter


def verify_emitter(upstream):
    expected = {"tools/lift.py": "abc0d23c368d5a66da97fe86804e5289222ab356",
                "tools/argcount.py": "08b642d29b52f7ccd6df9858b88df037f139ff4b"}
    for path, digest in expected.items():
        data = (upstream / path).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != digest:
            raise ValueError(f"upstream emitter file differs from pinned revision: {path}")


def known_import_counts(upstream):
    # Read only the upstream literal table, not its NFSU2 discovery script.
    tree = ast.parse((upstream / "tools/argcount.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "KNOWN" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("upstream KNOWN import signature table not found")


def validate_extension(catalog, catalog_hash, baseline_path, metadata_path,
                       expected_hash, image_hash):
    """Accept a provenance-recorded extension without replacing saved ranges."""
    baseline_bytes = baseline_path.read_bytes()
    baseline_hash = hashlib.sha256(baseline_bytes).hexdigest()
    if not expected_hash or baseline_hash != expected_hash:
        raise ValueError("base catalog SHA-256 does not match the profile")
    baseline = json.loads(baseline_bytes)
    if ({k: v for k, v in baseline.items() if k != "functions"} !=
            {k: v for k, v in catalog.items() if k != "functions"}):
        raise ValueError("callback repair changed baseline catalog metadata")
    originals = {f["address"]: f for f in baseline["functions"]}
    augmented = {f["address"]: f for f in catalog["functions"]}
    if any(augmented.get(a) != f for a, f in originals.items()):
        raise ValueError("callback repair changed or removed a saved function")
    metadata = json.loads(metadata_path.read_text())
    added = set(augmented) - set(originals)
    if (metadata.get("parent_catalog_sha256") != baseline_hash or
            metadata.get("catalog_sha256") != catalog_hash or
            metadata.get("image_sha256") != image_hash or
            metadata.get("unresolved") != [] or
            set(metadata.get("added_entries", [])) != added):
        raise ValueError("callback repair provenance does not match the catalog")
    return sorted(originals), sorted(added), baseline_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--base-catalog", type=Path,
                        help="profile-pinned parent of a callback-repaired catalog; "
                             "retain parent emission order and append new entries")
    parser.add_argument("--repair-metadata", type=Path,
                        help="repair provenance (default: metadata.json beside catalog)")
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--profile", type=Path, default=Path("profiles/nfsu1-pc.json"))
    parser.add_argument("--import-supplement", type=Path,
                        default=Path("profiles/nfsu1-imports.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("gen/nfsu1"))
    parser.add_argument("--limit", type=int, help="diagnostic partial lift, not build-ready")
    parser.add_argument("--shard-size", type=int, default=200)
    parser.add_argument("--cooperative-yield-entry", type=lambda value: int(value, 16),
                        action="append", default=[],
                        help="opt-in runtime scheduler yield before a catalog entry's first instruction (hex VA)")
    parser.add_argument("--hooks-file", type=Path,
                        help="VA list (hooks.txt): emit guest_hook(c, va) before each site")
    parser.add_argument("--link-stubs", action="store_true",
                        help="emit abort stubs + fntab for failed/unresolved "
                             "addresses so a Wasm module can link (not clean)")
    args = parser.parse_args()
    if args.shard_size <= 0 or args.limit is not None and args.limit <= 0:
        parser.error("limits must be positive")
    if args.limit is not None and args.link_stubs:
        parser.error("--link-stubs requires a full catalog selection (no --limit)")
    if args.repair_metadata and not args.base_catalog:
        parser.error("--repair-metadata requires --base-catalog")
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    if not any(output.is_relative_to(root / folder) for folder in ("gen", "work", "out")):
        parser.error("game-derived output must be inside this project's gen/, work/ or out/")
    if output.exists() and any(output.iterdir()):
        parser.error("output directory is not empty; choose a fresh directory")
    profile = json.loads(args.profile.read_text())
    image = args.image.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    if digest != profile["identity"]["sha256"]:
        raise ValueError("image SHA-256 does not match the selected profile")
    catalog_bytes = args.catalog.read_bytes()
    catalog_hash = hashlib.sha256(catalog_bytes).hexdigest()
    expected_catalog_hash = profile["identity"].get("catalog_sha256")
    if expected_catalog_hash and catalog_hash != expected_catalog_hash and not args.base_catalog:
        raise ValueError("catalog SHA-256 does not match the profile")
    catalog = json.loads(catalog_bytes)
    extension = None
    if args.base_catalog:
        extension = validate_extension(
            catalog, catalog_hash, args.base_catalog,
            args.repair_metadata or args.catalog.parent / "metadata.json",
            expected_catalog_hash, digest)
    verify_emitter(args.upstream.resolve())
    # Upstream's flag optimization is not yet validated against NFSU1's CFG.
    # JTSWITCH keeps switch case arms as in-function labels instead of
    # DISPATCH_TAIL into mid-function VAs that are absent from fntab.
    os.environ["FLAGOPT"] = "0"
    os.environ["X87PC"] = "1"
    module = load_web_lifter(args.upstream.resolve())
    os.environ["JTSWITCH"] = "1"
    hook_vas = []
    if args.hooks_file:
        for line in args.hooks_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            token = line.split()[0]
            if not token.lower().startswith("0x"):
                raise ValueError(f"hooks file expects hex VAs: {line!r}")
            hook_vas.append(int(token, 16))
        if len(hook_vas) != len(set(hook_vas)):
            raise ValueError("hooks file contains duplicate VAs")
    lifter = module.Lifter(str(args.image.resolve()), comments=False, hooks=hook_vas)
    from widescreen_operands import attach as attach_widescreen_operands, SITES
    hud_operands = attach_widescreen_operands(lifter) if hook_vas else set()
    from font_operands import attach as attach_font_operands, SITES as FONT_SITES, MIP_SITES
    font_operands = attach_font_operands(lifter)
    structural = profile["identity"]["structural_values"]
    import pefile
    pe = pefile.PE(data=image)
    actual = (pe.OPTIONAL_HEADER.ImageBase, pe.OPTIONAL_HEADER.SizeOfImage,
              pe.OPTIONAL_HEADER.AddressOfEntryPoint)
    expected = tuple(int(structural[k], 16) for k in
                     ("image_base", "size_of_image", "entry_rva"))
    if actual != expected or catalog["image_base"] != actual[0]:
        raise ValueError("PE/catalog structure does not match the profile")
    cooperative_yield_entries = set(args.cooperative_yield_entry)
    plan = attach_catalog(lifter, catalog, route_catalog_tails=True,
                          cooperative_yield_entries=cooperative_yield_entries)
    expected_text = (int(profile["lifting"]["dispatch_text_base"], 16),
                     int(profile["lifting"]["dispatch_text_size"], 16))
    if (lifter.TVA, lifter.TSZ) != expected_text:
        raise ValueError("PE text extent differs from the profile")
    addresses = [f["address"] for f in plan["functions"]]
    if extension:
        # Appending analyzed callbacks keeps existing shards stable. Dispatch
        # tables remain sorted independently; no generated body is patched.
        addresses = extension[0] + extension[1]
    overrides = {int(e["va"], 16) for e in profile["overrides"]["entries"]}
    if cooperative_yield_entries & overrides:
        parser.error("cooperative yield entry is replaced by a runtime override")
    if args.limit and cooperative_yield_entries - set(addresses[:args.limit]):
        parser.error("cooperative yield entry is outside the diagnostic selection")
    available = set(addresses) | overrides
    entry = int(structural["entry_va"], 16)
    if entry not in available:
        raise ValueError("catalog omits the selected game's entry point")
    counts = known_import_counts(args.upstream.resolve())
    supplement = json.loads(args.import_supplement.read_text())
    for item in supplement["entries"]:
        counts[item["name"]] = item["nargs"]
    imports, unknown_imports = [], []
    for dll in pe.DIRECTORY_ENTRY_IMPORT:
        for imp in dll.imports:
            name = imp.name.decode("latin1") if imp.name else f"#{imp.ordinal}"
            if name not in counts or name.startswith('#') and (
                    dll.dll.decode('latin1').lower(), name) != ('dsound.dll', '#1'):
                unknown_imports.append(f"{dll.dll.decode('latin1')}!{name}")
            imports.append((imp.address, dll.dll.decode("latin1"), name, counts.get(name)))
    if unknown_imports:
        raise ValueError(f"unreviewed import argument counts: {unknown_imports}")
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    selected = addresses[:args.limit] if args.limit else addresses
    report = {"image_sha256": digest, "catalog_sha256": catalog_hash,
              "status": "incomplete", "catalog_functions": len(addresses),
              "selected_functions": len(selected), "overrides": len(overrides),
              "imports": len(imports), "emitted_functions": 0, "failures": [],
              "stubbed_functions": 0, "unresolved_direct_targets": [],
              "ready_for_runtime_build": False, "link_stubs": args.link_stubs}
    report["cooperative_yield_entries"] = sorted(cooperative_yield_entries)
    report["widescreen_operands_version"] = 1 if hook_vas else 0
    report["font_operands_version"] = 2
    report["hooks"] = [f"0x{va:08x}" for va in sorted(hook_vas)]
    if extension:
        report["parent_catalog_sha256"] = extension[2]
        report["callback_entries_appended"] = len(extension[1])
    bodies, shard_index, unresolved, emitted = [], 0, set(), set()

    def flush():
        nonlocal bodies, shard_index
        if not bodies:
            return
        path = output / f"shard_{shard_index:04d}.c"
        font_header = '#include "nfsu1_fonts.h"\n' if any(
            "nfsu1_font_dimension(" in body or "nfsu1_font_mip_reduction(" in body
            for body in bodies) else ""
        path.write_text('/* GAME-DERIVED: local output, DO NOT DISTRIBUTE. */\n'
                        '#include "cpu.h"\n#include "decls.h"\n#include <math.h>\n'
                        + font_header
                        + "\n\n".join(bodies) + "\n")
        bodies = []
        shard_index += 1

    for index, address in enumerate(selected):
        if address in overrides:
            continue
        lifter.traps = 0
        lifter.truncated = 0
        before_calls = getattr(lifter, "oob_calls", 0)
        before_branches = getattr(lifter, "oob_branch", 0)
        try:
            # The upstream C emitter sorts blocks by address. Missing sequential
            # edges must not silently fall into an unrelated next C label.
            decoded, _ = lifter.discover(address)
            for instructions in decoded.values():
                last = instructions[-1]
                if last.mnemonic not in ('ret', 'retf', 'jmp', 'int3', 'hlt',
                                         'ud2', 'iret', 'iretd'):
                    fallthrough = last.address + last.size
                    if fallthrough not in decoded:
                        raise ValueError(f"missing fallthrough block 0x{fallthrough:08x}")
            code, targets = lifter.lift(address)
            if (address in cooperative_yield_entries and
                    code.count("{ void guest_fair_yield(void); guest_fair_yield(); }") != 1):
                # Some upstream branch paths bypass insn(). Never turn an
                # explicitly requested scheduling site into an unhooked body
                # or a link-stub fallback: this configuration must fail closed.
                parser.error(f"cooperative yield hook was not emitted exactly once at 0x{address:08x}; "
                             "choose an entry whose first instruction uses semantic emission")
            if lifter.traps or lifter.truncated:
                raise ValueError(f"traps={lifter.traps}, truncated={lifter.truncated}")
            if 'unsupported_insn(' in code:
                raise ValueError("emitted unsupported instruction/branch site")
            if (getattr(lifter, "oob_calls", 0) != before_calls or
                    getattr(lifter, "oob_branch", 0) != before_branches):
                raise ValueError("out-of-text direct transfer needs reviewed routing")
            unresolved.update(t for t in targets if lifter.in_text(t) and t not in available)
            bodies.append(code)
            emitted.add(address)
            report["emitted_functions"] += 1
            if len(bodies) >= args.shard_size:
                flush()
        except Exception as error:
            report["failures"].append({"address": f"0x{address:08x}", "error": str(error)})
        if (index + 1) % 1000 == 0:
            print(f"{index + 1}/{len(selected)} functions; "
                  f"{len(report['failures'])} failed", flush=True)
    if cooperative_yield_entries - emitted:
        parser.error("a cooperative yield entry failed emission; refusing an unhooked stub")
    flush()
    if not args.limit and font_operands != set(FONT_SITES) | MIP_SITES:
        raise SystemExit("missing scoped HD font dimension operands")
    report["font_operand_sites"] = [f"0x{va:08x}" for va in sorted(font_operands)]
    if hook_vas:
        # Mid-block sites must appear as guest_hook calls in emitted bodies.
        # Fail closed: a missing site means the runtime cannot apply the patch.
        emitted_text = []
        for path in sorted(output.glob("shard_*.c")):
            emitted_text.append(path.read_text())
        joined = "\n".join(emitted_text)
        missing = [va for va in hook_vas
                   if f"guest_hook(c, 0x{va:x}u)" not in joined]
        if missing:
            report["missing_hooks"] = [f"0x{va:08x}" for va in missing]
            (output / "lift-report.json").write_text(json.dumps(report, indent=2) + "\n")
            raise SystemExit(
                "hooks were not emitted at: " +
                ", ".join(f"0x{va:08x}" for va in missing))
        if hud_operands != set(SITES):
            raise SystemExit("missing scoped widescreen HUD operands")
        report["widescreen_operand_sites"] = [f"0x{va:08x}" for va in sorted(hud_operands)]
        report["hooks_emitted"] = len(hook_vas)
    report["unresolved_direct_targets"] = [f"0x{a:08x}" for a in sorted(unresolved)]
    complete = not args.limit and not report["failures"] and not unresolved
    if args.link_stubs and not complete:
        # Bring-up only: declare/stub every catalogued entry plus unresolved
        # in-text targets so shards compile and the module links. Stubs abort.
        available |= unresolved
        stub_addrs = sorted((available - emitted) - overrides)
        stub_lines = [
            '/* GAME-DERIVED bring-up stubs: abort on call. DO NOT DISTRIBUTE. */',
            '#include "cpu.h"', '#include "decls.h"',
        ]
        for address in stub_addrs:
            stub_lines.append(
                f'void sub_{address:08x}(CPU *c){{'
                f' unsupported_insn(c, 0x{address:08x}u, "lift-failed"); }}'
            )
        (output / "stubs.c").write_text("\n".join(stub_lines) + "\n")
        report["stubbed_functions"] = len(stub_addrs)
        report["status"] = "linkable_with_stubs"
    else:
        report["status"] = "emission_complete" if complete else "partial_or_failed"
    report["seconds"] = round(time.monotonic() - started, 2)
    # Always declare the full catalog so direct references compile in partial diagnostics.
    declarations = ['#ifndef NFSU1_DECLS_H', '#define NFSU1_DECLS_H', '#include "cpu.h"',
                    'void unsupported_insn(CPU *, uint32_t, const char *);',
                    'void cpuid_shim(CPU *);', 'uint64_t rdtsc_shim(void);']
    declarations += [f"void sub_{a:08x}(CPU *);" for a in sorted(available)]
    if hook_vas:
        declarations += ['float nfsu1_widescreen_hud_scale_x(void);',
                         'float nfsu1_widescreen_hud_pos_x(void);']
    declarations.append('#endif')
    (output / "decls.h").write_text("\n".join(declarations) + "\n")
    # Clean lifts always publish tables. --link-stubs publishes for bring-up link.
    if complete or args.link_stubs:
        table = ['#include "decls.h"', f'const uint32_t g_fn_count = {len(available)};',
                 'const uint32_t g_fn_addr[] = {']
        table += [f'0x{a:08x}u,' for a in sorted(available)]
        table += ['};', 'const guest_fn_t g_fn_ptr[] = {']
        table += [f'sub_{a:08x},' for a in sorted(available)]
        table.append('};')
        (output / "fntab.c").write_text("\n".join(table) + "\n")
        lines = ['#include <stdint.h>',
                 'typedef struct { uint32_t iat; const char *dll, *name; int nargs; } ImpEnt;',
                 f'const uint32_t g_imp_count = {len(imports)};', 'const ImpEnt g_imp[] = {']
        lines += [f'{{0x{va:08x}u,{json.dumps(dll)},{json.dumps(name)},{n}}},'
                  for va, dll, name, n in imports]
        lines.append('};')
        (output / "impargs.c").write_text("\n".join(lines) + "\n")
        if complete:
            report["ready_for_runtime_build"] = True
    (output / "lift-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in
                      ("failures", "unresolved_direct_targets")}, indent=2))
    if not complete and not args.link_stubs:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
