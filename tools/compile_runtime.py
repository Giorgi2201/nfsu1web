#!/usr/bin/env python3
"""Compile handwritten upstream browser runtime objects; do not link a game.

Uses the upstream build.sh runtime list and feature flags. Reports failures
without adding stubs or changing upstream code. Requires a full WASI SDK.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--wasi", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True,
                        help="directory containing actual generated decls.h")
    parser.add_argument("--output-dir", type=Path, default=Path("out/runtime-compile"))
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    root = args.upstream.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    generated = args.generated.resolve()
    if not (generated / "decls.h").is_file():
        parser.error("generated directory must contain decls.h")
    build = (root / "web/build.sh").read_text()

    def setting(name):
        match = re.search(r'^' + re.escape(name) + r'="([^"\n]*)"$', build, re.M)
        if not match:
            raise RuntimeError(f"cannot read upstream build setting: {name}")
        return shlex.split(match.group(1))

    compiler = args.wasi.resolve() / "bin/clang"
    target = ["--target=wasm32-wasip1-threads", "-pthread", "-O3"]
    features = setting("FEAT")
    common = target + features + setting("DEFS") + [
        "-fno-delete-null-pointer-checks", "-include",
        str(root / "runtime/web/compat/wasm_plat.h"),
        "-I", str(root / "runtime/web/compat"),
        "-I", str(root / "runtime"), "-I", str(generated)]
    jobs = []
    for name in setting("RT"):
        src = root / f"runtime/{name}.c"
        if not src.exists():
            src = root / f"runtime/web/{name}.c"
        jobs.append((name, src, common + (["-ffp-contract=off"]
                     if name in ("roam_core", "roam_game") else []) + ["-DNFS_ENHANCED=0"]))
    for src in sorted((root / "runtime/web").glob("*.c")):
        flags = target + features if src.stem == "thread_exit" else common + ["-DNFS_ENHANCED=0"]
        jobs.append(("web_" + src.stem, src, flags))

    def compile_one(job):
        name, src, flags = job
        obj = output / f"{name}.o"
        # A failed recompile must not leave an earlier success looking current.
        obj.unlink(missing_ok=True)
        command = [str(compiler)] + flags + ["-c", str(src), "-o", str(obj)]
        result = subprocess.run(command, text=True, capture_output=True, cwd=root)
        log = output / f"{name}.log"
        log.write_text(result.stdout + result.stderr)
        return {"source": str(src.relative_to(root)), "exit_code": result.returncode,
                "object": str(obj), "log": str(log), "command": command}

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(compile_one, jobs))
    failed = [x for x in results if x["exit_code"]]
    report = {"kind": "handwritten-runtime-object-compilation-only",
              "upstream": str(root), "wasi": str(args.wasi.resolve()),
              "generated_declarations": str(generated / "decls.h"),
              "compiled": len(results) - len(failed), "failed": len(failed),
              "limitations": "No generated shards compiled; no game link or browser/game validation.",
              "results": results}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Runtime objects: {report['compiled']} compiled, {len(failed)} failed")
    for result in failed:
        diagnostics = Path(result["log"]).read_text().splitlines()
        errors = [line for line in diagnostics if "error:" in line]
        print(result["source"] + ": " + (errors[0] if errors else "see log"))
    print(f"Report: {output / 'report.json'}")
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
