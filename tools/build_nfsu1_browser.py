#!/usr/bin/env python3
"""Bundle the pinned browser host for private NFSU1 testing, without a browser."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ASSETS = (
    "index.html", "main.js", "main.css", "sw.js",
    "host/game-worker.js", "host/io-worker.js", "host/predownload-worker.js",
    "audio/worklet.js",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT / "work/upstream/nfsu2-web")
    parser.add_argument("--node-modules", type=Path,
                        default=ROOT / "work/toolchain/web-bundler/node_modules")
    parser.add_argument("--report", type=Path, default=ROOT / "out/browser-build.json")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    web = upstream / "web"
    modules = web / "node_modules"
    if not modules.exists():
        dependency = args.node_modules.resolve()
        if not (dependency / "esbuild/package.json").is_file():
            parser.error("esbuild is missing. Install the isolated bundler with: "
                         "npm install --prefix work/toolchain/web-bundler "
                         "--no-audit --no-fund --ignore-scripts esbuild@0.27.4")
        if modules.is_symlink():
            parser.error(f"broken browser node_modules symlink: {modules}")
        modules.symlink_to(dependency, target_is_directory=True)
    package = modules / "esbuild/package.json"
    if not package.is_file():
        parser.error(f"browser dependencies do not contain esbuild: {modules}")
    version = json.loads(package.read_text())["version"]
    subprocess.run(["bash", str(ROOT / "tools/apply_browser_profile.sh"),
                    "--upstream", str(upstream)], check=True)
    subprocess.run(["node", str(ROOT / "tools/browser_startup_smoke.mjs"), str(upstream)], check=True)
    subprocess.run(["node", str(ROOT / "tools/keyboard_smoke.mjs"), str(upstream)], check=True)
    subprocess.run(["node", "build.mjs"], cwd=web, check=True)
    dist = web / "dist"
    missing = [name for name in ASSETS if not (dist / name).is_file()]
    if missing:
        raise ValueError(f"browser build omitted required assets: {missing}")
    # Upstream keeps maps in dist-dev; this private server serves dist only.
    # Retain the local maps without advertising nonexistent public map URLs.
    for name in ASSETS:
        if not name.endswith((".js", ".css")):
            continue
        path = dist / name
        lines = path.read_bytes().splitlines(keepends=True)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and (lines[-1].strip().startswith(b"//# sourceMappingURL=")
                      or (lines[-1].strip().startswith(b"/*# sourceMappingURL=")
                          and lines[-1].strip().endswith(b"*/"))):
            path.write_bytes(b"".join(lines[:-1]))
    # Compile the actual bundles for syntax without entering their browser APIs.
    for name in ASSETS:
        if name.endswith(".js"):
            subprocess.run(["node", "--check", str(dist / name)], check=True)
    server = ROOT / "server/target/release/nfsu1-server"
    if not server.is_file():
        server = ROOT / "server/target/debug/nfsu1-server"
    if not server.is_file():
        subprocess.run(
            ["cargo", "build", "--release", "--manifest-path", str(ROOT / "server/Cargo.toml")],
            check=True,
            cwd=ROOT,
        )
        server = ROOT / "server/target/release/nfsu1-server"
    subprocess.run([
        str(server), "--check",
        "--dist", str(dist), "--wasm", str(upstream / "out/web/nfsu1.wasm"),
        "--metadata", str(upstream / "out/web/nfsu1.json"),
        "--data", str(ROOT / "work/data"),
    ], check=True, cwd=ROOT)
    sources = [web / "index.html", web / "build.mjs"] + sorted((web / "src").rglob("*"))
    state = json.loads((upstream / ".nfsu1-browser-profile/state.json").read_text())
    report = {
        "kind": "browser-host-bundle-and-local-input-check",
        "upstream_revision": state["upstream_commit"],
        "esbuild_version": version,
        "esbuild_package_sha256": digest(package),
        "source_maps": "retained in dist-dev without public map URL advertisements",
        "overlay_script_sha256": digest(ROOT / "tools/apply_browser_profile.sh"),
        "menu_sources": {str(p.relative_to(ROOT)): digest(p) for p in sorted((ROOT / "browser").glob("*")) if p.is_file()},
        "keyboard_smoke_sha256": digest(ROOT / "tools/keyboard_smoke.mjs"),
        "builder_sha256": digest(Path(__file__)),
        "startup_smoke_sha256": digest(ROOT / "tools/browser_startup_smoke.mjs"),
        "server_cargo_sha256": digest(ROOT / "server/Cargo.toml"),
        "wasm_sha256": digest(upstream / "out/web/nfsu1.wasm"),
        "sources": {str(p.relative_to(web)): digest(p) for p in sources if p.is_file()},
        "assets": {name: {"bytes": (dist / name).stat().st_size,
                           "sha256": digest(dist / name)} for name in ASSETS},
        "validation": "Stubbed startup execution, bundle generation, JavaScript syntax and local server input validation; no browser operation or rendered-game validation by this build.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Browser host bundled with esbuild {version}: {dist}")
    print(f"Build record: {args.report}")
    print("Start locally: ./server/target/release/nfsu1-server")
    print("User test URL: http://127.0.0.1:8765/")


if __name__ == "__main__":
    main()
