#!/usr/bin/env python3
"""HTTP smoke for the Rust nfsu1-server (no browser)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "server/target/release/nfsu1-server"
DEBUG = ROOT / "server/target/debug/nfsu1-server"


def server_bin() -> Path:
    env = os.environ.get("NFSU1_SERVER_BIN")
    if env and Path(env).is_file():
        return Path(env)
    if RELEASE.is_file():
        return RELEASE
    if DEBUG.is_file():
        return DEBUG
    subprocess.run(
        ["cargo", "build", "--manifest-path", str(ROOT / "server/Cargo.toml")],
        check=True,
        cwd=ROOT,
    )
    if not DEBUG.is_file():
        raise SystemExit("nfsu1-server binary missing after cargo build")
    return DEBUG


def request(url: str, method: str = "GET", headers: dict | None = None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        return urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as response:
        return response


class Resp:
    def __init__(self, status: int, headers: dict[str, str], body: bytes):
        self.status = status
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.body = body

    def read(self):
        return self.body


def fetch(base: str, path: str, method="GET", headers=None):
    raw = request(base + path, method, headers)
    body = raw.read() if method != "HEAD" else b""
    status = getattr(raw, "status", None) or raw.getcode()
    headers_out = {k: v for k, v in raw.headers.items()}
    return Resp(status, headers_out, body)


def exercise(base: str, root: Path, module_hash: str):
    info_response = fetch(base, "/game.json")
    info = json.loads(info_response.read())
    digest = hashlib.sha256((root / "game.wasm").read_bytes()).hexdigest()
    assert info["rev"] == f"nfsu1-local-{digest[:12]}"
    assert info["module"] == digest
    assert info_response.headers["cache-control"] == "no-store"

    page = fetch(base, "/")
    assert page.status == 200 and b"local" in page.read()
    assert page.headers["cross-origin-opener-policy"] == "same-origin"
    assert page.headers["cross-origin-embedder-policy"] == "require-corp"

    module = fetch(base, "/game.wasm", headers={"Range": "bytes=1-4"})
    assert module.status == 206 and module.read() == b"asm-"
    assert module.headers["content-type"] == "application/wasm"
    assert module.headers["content-range"].startswith("bytes 1-4/")
    bare_module = fetch(base, "/game.wasm")
    assert bare_module.status == 200 and bare_module.headers["cache-control"] == "no-store"
    good_hash = fetch(base, f"/game.wasm?v={module_hash}")
    assert good_hash.status == 200 and good_hash.read() == (root / "game.wasm").read_bytes()
    assert good_hash.headers["cache-control"] == "private, max-age=31536000, immutable"
    stale_hash = fetch(base, "/game.wasm?v=stale-module-hash")
    assert stale_hash.status == 409

    (root / "game.wasm").write_bytes(b"rebuilt-module")
    changed_hash = fetch(base, f"/game.wasm?v={module_hash}")
    assert changed_hash.status == 409
    # Restore for later size checks against the running process stamp.
    (root / "game.wasm").write_bytes(b"\0asm-test-module")

    head = fetch(base, "/game.wasm", method="HEAD")
    assert head.status == 200 and int(head.headers["content-length"]) == (root / "game.wasm").stat().st_size

    health = fetch(base, "/healthz")
    assert health.status == 200 and health.read() == b"ok\n"

    manifest_response = fetch(base, "/data-manifest")
    manifest = json.loads(manifest_response.read())
    assert {entry["p"] for entry in manifest["files"]} == {"Cars", "Cars/car.bin"}
    data_range = fetch(base, "/data/Cars/car.bin", headers={"Range": "bytes=3-6"})
    assert data_range.status == 206 and data_range.read() == b"3456"

    invalid_range = fetch(base, "/data/Cars/car.bin", headers={"Range": "bytes=999-"})
    assert invalid_range.status == 416 and invalid_range.headers["content-range"] == "bytes */10"
    escaped = fetch(base, "/data/%2e%2e%2Fgame.wasm")
    assert escaped.status == 400
    malformed_escape = fetch(base, "/data/%2e%2e%2")
    assert malformed_escape.status == 400
    symlink_escape = fetch(base, "/data/escape.bin")
    assert symlink_escape.status == 404
    missing = fetch(base, "/missing.js")
    assert missing.status == 404


def font_overlay_smoke(binary: Path, root: Path):
    data, overlay = root / "font-data", root / "fonts"
    files = []
    for name in ("GLOBAL/GLOBALA.BUN", "LANGUAGES/LANGUAGETEXTURES.BIN"):
        source, replacement = data / name, overlay / "data" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        replacement.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"original")
        replacement.write_bytes(b"HD fonts")
        files.append({
            "path": name,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "sha256": hashlib.sha256(replacement.read_bytes()).hexdigest(),
        })
    (overlay / "manifest.json").write_text(json.dumps({"kind": "nfsu1-hd-fonts", "files": files}))
    wasm = root / "game.wasm"
    meta = root / "game.json"
    proc = subprocess.Popen(
        [
            str(binary),
            "--dist", str(root / "dist"),
            "--wasm", str(wasm),
            "--metadata", str(meta),
            "--data", str(data),
            "--hd-fonts", str(overlay),
            "--host", "127.0.0.1",
            "--port", "0",
            "--public",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base = wait_for_url(proc)
        response = fetch(base, "/data/Global/GLOBALA.BUN", headers={"Range": "bytes=0-1"})
        assert response.status == 206 and response.read() == b"HD"
        (overlay / "data" / files[0]["path"]).write_bytes(b"tampered after server startup")
        assert fetch(base, "/data/GLOBAL/GLOBALA.BUN").status == 409
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def wait_for_url(proc: subprocess.Popen, timeout=10.0) -> str:
    deadline = time.time() + timeout
    buf = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out = (proc.stdout.read() if proc.stdout else "") or buf
            raise SystemExit(f"server exited early:\n{out}")
        line = proc.stdout.readline() if proc.stdout else ""
        if line:
            buf += line
            if "http://" in line:
                # Serving NFSU1 build at http://127.0.0.1:PORT/
                start = line.index("http://")
                end = line.index("/", start + len("http://"))
                return line[start:end]
        time.sleep(0.05)
    raise SystemExit(f"server did not print listen URL:\n{buf}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-process", action="store_true", help="ignored; Rust smoke always uses a socket")
    parser.add_argument("--network", action="store_true", help="ignored; same as default")
    parser.parse_args()
    binary = server_bin()

    with tempfile.TemporaryDirectory(prefix="nfsu1-http-smoke-") as temporary:
        root = Path(temporary)
        dist = root / "dist"
        data = root / "data"
        dist.mkdir()
        data.mkdir()
        (dist / "index.html").write_text("<h1>local</h1>", encoding="utf-8")
        (dist / "main.js").write_text("ok", encoding="utf-8")
        (data / "Cars").mkdir()
        (data / "Cars" / "car.bin").write_bytes(b"0123456789")
        outside = root / "outside.bin"
        outside.write_bytes(b"private")
        (data / "escape.bin").symlink_to(outside)
        wasm = root / "game.wasm"
        wasm.write_bytes(b"\0asm-test-module")
        module_hash = hashlib.sha256(wasm.read_bytes()).hexdigest()
        metadata = root / "game.json"
        metadata.write_text(
            json.dumps({
                "pages": 1, "maxPages": 2, "guestEnd": 65536,
                "size": wasm.stat().st_size, "hdFonts": 1,
            }),
            encoding="utf-8",
        )

        # Port 0: ask the OS. The server prints the bound URL.
        # Use a high fixed port if binding 0 is awkward — prefer probing.
        port = pick_port()
        proc = subprocess.Popen(
            [
                str(binary),
                "--dist", str(dist),
                "--wasm", str(wasm),
                "--metadata", str(metadata),
                "--data", str(data),
                "--host", "127.0.0.1",
                "--port", str(port),
                "--public",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            base = wait_for_url(proc)
            exercise(base, root, module_hash)
            font_overlay_smoke(binary, root)
            print("Rust HTTP smoke passed: routes, ranges, headers, and path protections.")
            return 0
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def pick_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


if __name__ == "__main__":
    raise SystemExit(main())
