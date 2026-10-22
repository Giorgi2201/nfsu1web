#!/usr/bin/env python3
"""Cache a local NFSU1 catalog using the maintainer's original analysis passes.

Requires the pinned upstream scripts and pcrecomp modules under work/upstream.
No game bytes or game-derived analysis should leave the ignored work directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
GAME_SHA256 = "c0fad450912952f53809a54690d235aa8b4e25b9f46650693c7cbee1b4c074b7"
NFS_REV = "58d9d4f63d59c941031f91973ae48c2cdb1a42b1"
PC_REV = "8c92919a99aaf9e129af5787776bca84863468cc"
PINNED_BLOBS = {
    "nfsu1-recompiled/scripts/data_seeds.py": "11d03560e84360910750232f00351b777f318b5c",
    "nfsu1-recompiled/scripts/code_seeds.py": "45f0b6e3eb6c46f1e39f7ec51c2a24f2cd2c95a1",
    "nfsu1-recompiled/scripts/run_lift.py": "54406db323ac24602ef24b0a348fcacefaf71f34",
    "pcrecomp/tools/pe/pe_analyze.py": "65fb0dfd8bd5889230444f47c9bc29a256402ec4",
    "pcrecomp/tools/disasm/disasm32.py": "7084a0e0fdae6f93214c6babbcff001e8ac1e169",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def toolchain_versions():
    return {"python": sys.version.split()[0],
            "capstone": __import__("capstone").__version__,
            "pefile": __import__("pefile").__version__}


def run_stage(script, args, output, inputs, env, trailing=()):
    """Reuse a completed pass only when both its inputs and output still match."""
    stamp = output.with_suffix(output.suffix + ".provenance.json")
    signature = {str(path): digest(path) for path in inputs}
    signature["toolchain"] = toolchain_versions()
    if output.exists() and stamp.exists():
        saved = json.loads(stamp.read_text())
        if saved.get("inputs") == signature and saved.get("output_sha256") == digest(output):
            print(f"Reusing {output.name}", flush=True)
            return
    temporary = output.with_suffix(output.suffix + ".partial")
    command = [sys.executable, "-u", str(script), *map(str, args), str(temporary), *map(str, trailing)]
    log = output.with_suffix(".log")
    print(f"Running {script.name} -> {output.name}; progress: {log}", flush=True)
    with log.open("w") as stream:
        subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    json.loads(temporary.read_text())
    temporary.replace(output)
    stamp.write_text(json.dumps({"inputs": signature, "output_sha256": digest(output)}, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True, help="Unmodified matching Speed.exe (read only)")
    parser.add_argument("--upstream", type=Path, default=ROOT / "work/upstream")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "work/analysis")
    args = parser.parse_args()
    image, upstream, out = args.image.resolve(), args.upstream.resolve(), args.output_dir.resolve()
    if digest(image) != GAME_SHA256:
        parser.error("Speed.exe does not match the selected PC NFSU1 1.4 fingerprint")
    # Keep actual catalogs out of distributable source trees, including custom destinations.
    if not out.is_relative_to(ROOT / "work"):
        parser.error("Catalog output must be inside this repository's ignored work/ directory")
    sources = []
    for relative, expected in PINNED_BLOBS.items():
        path = upstream / relative
        if not path.is_file():
            parser.error(f"Missing upstream source: {path}; provision pinned upstream files first")
        data = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != expected:
            parser.error(f"Upstream source differs from pinned blob: {path}")
        sources.append(path)
    env = os.environ.copy()
    env["PCRECOMP"] = str(upstream / "pcrecomp")
    out.mkdir(parents=True, exist_ok=True)
    scripts = upstream / "nfsu1-recompiled/scripts"
    seeds, initial = out / "seeds-data.json", out / "catalog-initial.json"
    merged, catalog = out / "seeds-all.json", out / "catalog.json"
    common = [image, *sources]
    run_stage(scripts / "data_seeds.py", [image], seeds, common, env)
    run_stage(scripts / "run_lift.py", ["catalog", image, seeds], initial, [*common, seeds], env)
    run_stage(scripts / "code_seeds.py", [image, initial], merged,
              [*common, initial, seeds], env, trailing=["--merge", seeds])
    run_stage(scripts / "run_lift.py", ["catalog", image, merged], catalog, [*common, merged], env)
    document = json.loads(catalog.read_text())
    provenance = {
        "image_sha256": digest(image), "catalog_sha256": digest(catalog),
        "functions": len(document["functions"]), "nfsu1_revision": NFS_REV,
        "pcrecomp_revision": PC_REV, "source_blobs": PINNED_BLOBS,
        "toolchain": toolchain_versions(),
        "pipeline": ["data_seeds", "catalog", "code_seeds", "merge seeds", "catalog with restore_seeds"],
        "note": "Regenerated locally with upstream algorithms; not the maintainer's historical catalog. Cache and reuse.",
    }
    (out / "catalog.metadata.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Catalog ready: {catalog} ({provenance['functions']} entries)")


if __name__ == "__main__":
    main()
