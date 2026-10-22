#!/usr/bin/env python3
"""Build a private, cached function catalog for PC NFSU1 ABK code.

This wrapper invokes the pinned upstream ABK parser/relocator, then runs only
the pinned pcrecomp recursive-descent disassembler at the ABK routine starts
provided by that parser. It does not scan the main executable for functions.
All game-derived outputs must remain under this repository's ignored work/.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM = ROOT / "work/upstream"
DEFAULT_OUTPUT = ROOT / "work/analysis/abk"
PROFILE = ROOT / "profiles/nfsu1-pc.json"
MANIFEST = ROOT / "docs/source-manifest.json"
NFS_REV = "58d9d4f63d59c941031f91973ae48c2cdb1a42b1"
PC_REV = "8c92919a99aaf9e129af5787776bca84863468cc"
PINNED = {
    "nfsu1-recompiled/scripts/abk_module.py": "7e7ace3135472dca1a01a918f66d3ddf516c01ee",
    "nfsu1-recompiled/src/runtime/abk_code.c": "c596ed00c12c75ffbb80dd7f181dd0a03a58556e",
    "pcrecomp/tools/pe/pe_analyze.py": "65fb0dfd8bd5889230444f47c9bc29a256402ec4",
    "pcrecomp/tools/disasm/disasm32.py": "7084a0e0fdae6f93214c6babbcff001e8ac1e169",
}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_pinned_sources(upstream):
    manifest = json.loads(MANIFEST.read_text())
    repo = next((item for item in manifest["repositories"]
                 if item["repository"] == "codepdbh/nfsu1-recompiled"), None)
    pc_repo = next((item for item in manifest["repositories"]
                    if item["repository"] == "sp00nznet/pcrecomp"), None)
    if not repo or repo["commit"] != NFS_REV or not pc_repo or pc_repo["commit"] != PC_REV:
        raise ValueError("source manifest does not pin the expected PC NFSU1/pcrecomp revisions")
    manifest_blobs = {
        **{"nfsu1-recompiled/" + item["path"]: item["blob_sha"]
           for item in repo["inspected_files"]},
        **{"pcrecomp/" + item["path"]: item["blob_sha"]
           for item in pc_repo["inspected_files"]},
    }

    files = {}
    for relative, expected in PINNED.items():
        path = upstream / relative
        if not path.is_file():
            raise FileNotFoundError(f"missing pinned analysis source: {path}")
        data = path.read_bytes()
        actual = git_blob_sha1(data)
        if actual != expected or manifest_blobs.get(relative) != expected:
            raise ValueError(f"pinned source hash mismatch: {path}")
        files[relative] = {"path": str(path), "git_blob_sha1": actual,
                           "sha256": hashlib.sha256(data).hexdigest()}
    return files


def load_modules(upstream):
    pcrecomp = upstream / "pcrecomp"
    for component in ("pe", "disasm"):
        sys.path.insert(0, str(pcrecomp / "tools" / component))
    sys.path.insert(0, str(ROOT))

    abk_path = upstream / "nfsu1-recompiled/scripts/abk_module.py"
    spec = importlib.util.spec_from_file_location("pinned_abk_module", abk_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load pinned ABK module: {abk_path}")
    abk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(abk)

    from pe_analyze import analyze_pe
    from disasm32 import Disassembler
    from tools.catalog_bridge import normalize
    try:
        import capstone
        import pefile
        capstone_version = capstone.__version__
        pefile_version = pefile.__version__
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("pinned Capstone and pefile Python packages are required") from exc
    return abk, analyze_pe, Disassembler, normalize, {
        "python": sys.version.split()[0], "capstone": capstone_version,
        "pefile": pefile_version,
    }


def verify_image(image, profile):
    identity = profile.get("identity", {})
    expected_hash = identity.get("sha256")
    actual_hash = sha256(image)
    if not expected_hash or actual_hash != expected_hash:
        raise ValueError("PC image full SHA-256 does not match profiles/nfsu1-pc.json")
    import pefile
    pe = pefile.PE(str(image), fast_load=True)
    structural = identity.get("structural_values", {})
    expected = {
        "image_base": int(structural["image_base"], 0),
        "size_of_image": int(structural["size_of_image"], 0),
        "entry_rva": int(structural["entry_rva"], 0),
    }
    actual = {
        "image_base": pe.OPTIONAL_HEADER.ImageBase,
        "size_of_image": pe.OPTIONAL_HEADER.SizeOfImage,
        "entry_rva": pe.OPTIONAL_HEADER.AddressOfEntryPoint,
    }
    if actual != expected:
        raise ValueError(f"PC image PE identity mismatch: expected {expected}, got {actual}")
    return actual_hash, actual


def bank_inputs(data_root):
    banks = sorted((data_root / "Sound").rglob("*.abk"))
    if not banks:
        raise ValueError(f"no Sound/**/*.abk banks found under {data_root}")
    entries = []
    for path in banks:
        if not path.is_file():
            raise ValueError(f"ABK bank is not a regular file: {path}")
        entries.append({"path": path.relative_to(data_root).as_posix(),
                        "sha256": sha256(path), "bytes": path.stat().st_size})
    return banks, entries


def catalog_for_abk(image, analysis_dll, seeds_path, analyze_pe, Disassembler, normalize):
    import pefile
    info = analyze_pe(str(analysis_dll))
    pe = pefile.PE(str(analysis_dll), fast_load=True)
    image_bytes = analysis_dll.read_bytes()
    mapped = pe.get_memory_mapped_image()
    dis = Disassembler(image_bytes, pe.OPTIONAL_HEADER.ImageBase, info.sections)
    main = analyze_pe(str(image))
    seeds_doc = json.loads(seeds_path.read_text())
    seeds = sorted({int(item["address"], 0) if isinstance(item["address"], str)
                    else int(item["address"]) for item in seeds_doc})
    if not seeds:
        raise ValueError("upstream ABK analysis produced no routine starts")

    functions = []
    missing = []
    external_targets = set()
    external_sites = 0
    for seed in seeds:
        if not dis.is_code_address(seed):
            missing.append(seed)
            continue
        function = dis.disassemble_function(seed)
        if function is None or not function.blocks or seed not in function.blocks:
            missing.append(seed)
            continue

        calls = set(function.calls_to)
        for block in function.blocks.values():
            for ins in block.instructions:
                if not ins.is_call:
                    continue
                target = ins.get_branch_target()
                if target is None or dis.is_code_address(target):
                    continue
                if not main.code_start <= target < main.code_end:
                    raise ValueError(
                        f"ABK direct call at {ins.address:#x} targets neither ABK nor main code: {target:#x}")
                calls.add(target)
                external_targets.add(target)
                external_sites += 1

        blocks = [[block.start, block.end, sorted(set(block.successors)),
                   int(block.is_exit)]
                  for block in sorted(function.blocks.values(), key=lambda item: item.start)]
        functions.append({
            "address": function.address,
            "end": function.end,
            "size": function.size,
            "entry_kind": "start",
            "is_thunk": bool(function.is_thunk),
            "jump_targets": sorted(function.jump_targets),
            "calls_to": sorted(calls),
            "blocks": blocks,
        })
    if missing:
        sample = ", ".join(f"{value:#x}" for value in missing[:8])
        raise ValueError(f"ABK analysis failed to decode {len(missing)}/{len(seeds)} routine starts: {sample}")

    raw = {"exe": analysis_dll.name, "image_base": info.image_base,
           "code_start": info.code_start, "code_end": info.code_end,
           "functions": functions}
    normalized = normalize(raw)
    # Check every address against the private analysis image and verify all
    # external direct calls survived the schema adapter.
    entries = {item["address"] for item in normalized["functions"]}
    if len(entries) != len(seeds):
        raise ValueError(f"catalog retained {len(entries)} entries for {len(seeds)} routine starts")
    external = set(normalized["unresolved_calls"])
    if external != external_targets:
        other = sorted(external - external_targets)
        lost = sorted(external_targets - external)
        raise ValueError(f"ABK catalog external-call mismatch; unexpected targets={other[:8]}, lost main calls={lost[:8]}")
    return normalized, {
        "routine_starts": len(seeds), "functions": len(functions),
        "basic_blocks": sum(len(item["blocks"]) for item in functions),
        "unique_external_main_calls": len(external),
        "external_main_call_sites": external_sites,
        "external_call_targets": sorted(external),
        "analysis_image_bytes": len(mapped),
    }


def prepare(image, data_root, upstream, output_root):
    profile = json.loads(PROFILE.read_text())
    image_hash, image_identity = verify_image(image, profile)
    banks, bank_manifest = bank_inputs(data_root)
    source_files = load_pinned_sources(upstream)
    abk, analyze_pe, Disassembler, normalize, versions = load_modules(upstream)
    signature = {
        "image_sha256": image_hash,
        "profile_sha256": sha256(PROFILE),
        "image_identity": image_identity,
        "banks": bank_manifest,
        "sources": source_files,
        "toolchain": versions,
        "wrapper_sha256": sha256(Path(__file__)),
        "catalog_bridge_sha256": sha256(ROOT / "tools/catalog_bridge.py"),
    }
    key = hashlib.sha256(json.dumps(signature, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    output_root = output_root.resolve()
    if not output_root.is_relative_to(ROOT / "work"):
        raise ValueError("ABK analysis outputs must remain inside this repository's ignored work/ directory")
    output_root.mkdir(parents=True, exist_ok=True)
    cache = output_root
    names = ("analysis.dll", "seeds.json", "blocks.c", "catalog.json")
    stamp_path = cache / "metadata.json"
    if cache.is_dir() and stamp_path.is_file():
        try:
            saved = json.loads(stamp_path.read_text())
            valid = saved.get("inputs") == signature and all(
                (cache / name).is_file() and saved["outputs"].get(name) == sha256(cache / name)
                for name in names)
            if valid:
                print(f"Reusing cached ABK catalog: {cache}")
                print_summary(saved["summary"], cache)
                return cache
        except (OSError, KeyError, json.JSONDecodeError):
            pass

    stage = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-{key[:12]}-", suffix=".partial",
                                  dir=output_root.parent))
    input_root = Path(tempfile.mkdtemp(prefix="abk-input-", dir=output_root.parent))
    try:
        (input_root / "Speed.exe").symlink_to(image)
        (input_root / "Sound").symlink_to(data_root / "Sound", target_is_directory=True)
        unique_blocks = abk.banks(str(input_root))
        dll, seeds, blocks = (stage / names[0], stage / names[1], stage / names[2])
        abk.main(str(input_root), str(dll), str(seeds), str(blocks))
        catalog, stats = catalog_for_abk(image, dll, seeds, analyze_pe, Disassembler, normalize)
        catalog_path = stage / "catalog.json"
        catalog_path.write_text(json.dumps(catalog, separators=(",", ":")) + "\n")
        outputs = {name: sha256(stage / name) for name in names}
        summary = {
            **stats,
            "banks": len(banks), "unique_abk_bytes": sum(entry["bytes"] for entry in bank_manifest),
            "unique_code_blocks": len(unique_blocks),
            "unique_code_bytes": sum(len(block["code"]) for block in unique_blocks),
            "analysis_dll_bytes": dll.stat().st_size,
            "seeds_json_bytes": seeds.stat().st_size,
            "blocks_c_bytes": blocks.stat().st_size,
            "catalog_bytes": catalog_path.stat().st_size,
        }
        metadata = {"schema": "nfsu1-abk-catalog-cache-v1", "cache_key": key,
                    "inputs": signature, "outputs": outputs, "summary": summary,
                    "notes": [
                        "ABK functions were seeded only from upstream routine_starts; no main-image discovery was run.",
                        "Direct calls into the verified PC main code range are retained in calls_to and exposed as unresolved_calls.",
                        "analysis.dll, seeds.json, blocks.c, and catalog.json contain local game-derived analysis and must remain private under work/.",
                    ]}
        (stage / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        if cache.exists():
            shutil.rmtree(cache)
        stage.replace(cache)
        print_summary(summary, cache)
        return cache
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if input_root.exists():
            shutil.rmtree(input_root)


def print_summary(summary, cache):
    print(f"ABK catalog ready: {cache}")
    print("  banks: {banks}; unique ABK input: {unique_abk_bytes:,} bytes".format(**summary))
    print("  unique code blocks: {unique_code_blocks}; routine starts/functions: {routine_starts}".format(**summary))
    print("  basic blocks: {basic_blocks}; unique external main-image calls: {unique_external_main_calls}".format(**summary))
    print("  outputs: analysis.dll {analysis_dll_bytes:,} B, seeds.json {seeds_json_bytes:,} B, "
          "blocks.c {blocks_c_bytes:,} B, catalog.json {catalog_bytes:,} B".format(**summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True,
                        help="matching, unmodified PC NFSU1 1.4 Speed.exe")
    parser.add_argument("--data", type=Path, default=ROOT / "work/data",
                        help="game data root containing Sound/**/*.abk")
    parser.add_argument("--upstream", type=Path, default=DEFAULT_UPSTREAM,
                        help="pinned nfsu1-recompiled and pcrecomp source snapshots")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT,
                        help="cache directory inside ignored work/")
    args = parser.parse_args()
    try:
        prepare(args.image.resolve(), args.data.resolve(), args.upstream.resolve(),
                args.output_dir)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
