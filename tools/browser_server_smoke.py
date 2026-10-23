#!/usr/bin/env python3
"""Focused HTTP smoke check for tools/serve_nfsu1.py (no browser involved)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from serve_nfsu1 import Config, Handler, LocalServer


def request(url: str, method: str = "GET", headers: dict | None = None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        return urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as response:
        return response


class MemorySocket:
    """Small socket-shaped adapter for exercising BaseHTTPRequestHandler."""

    def __init__(self, request_bytes: bytes):
        self.input = io.BytesIO(request_bytes)
        self.output = OutputBuffer()

    def makefile(self, mode: str, *args, **kwargs):
        return self.input if "r" in mode else self.output

    def sendall(self, data: bytes):
        self.output.write(data)


class OutputBuffer(io.BytesIO):
    def close(self):
        # StreamRequestHandler closes its response stream after dispatch.
        pass


class MemoryServer:
    server_name = "localhost"
    server_port = 8765

    def __init__(self, config):
        self.config = config


class QuietHandler(Handler):
    def log_message(self, fmt, *args):
        pass


class MemoryResponse:
    def __init__(self, status: int, headers: dict[str, str], body: bytes):
        self.status = status
        self.headers = headers
        self.body = body

    def read(self):
        return self.body


def disconnected_client_smoke(config):
    class ResetInput(io.BytesIO):
        def readline(self, *args):
            raise ConnectionResetError("client closed keep-alive connection")

    class ClosedSocket(MemorySocket):
        def sendall(self, data):
            raise BrokenPipeError("client closed response connection")

    wire = MemorySocket(b"")
    wire.input = ResetInput()
    QuietHandler(wire, ("127.0.0.1", 54321), MemoryServer(config))
    wire = ClosedSocket(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
    QuietHandler(wire, ("127.0.0.1", 54321), MemoryServer(config))


def in_process_request(config, path: str, method="GET", headers=None):
    headers = headers or {}
    lines = [f"{method} {path} HTTP/1.1", "Host: localhost"]
    lines.extend(f"{key}: {value}" for key, value in headers.items())
    wire = MemorySocket(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
    QuietHandler(wire, ("127.0.0.1", 54321), MemoryServer(config))
    raw = wire.output.getvalue()
    head, _, body = raw.partition(b"\r\n\r\n")
    response_lines = head.decode("iso-8859-1").split("\r\n")
    status = int(response_lines[0].split()[1])
    response_headers = {}
    for line in response_lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            response_headers[key.strip()] = value.strip()
    return MemoryResponse(status, response_headers, body)


def exercise(request_fn, config, root):
    info_response = request_fn(config, "/game.json")
    info = json.loads(info_response.read())
    assert info["rev"] == f"nfsu1-local-{hashlib.sha256((root / 'game.wasm').read_bytes()).hexdigest()[:12]}"
    assert info["module"] == hashlib.sha256((root / "game.wasm").read_bytes()).hexdigest()
    assert info_response.headers["Cache-Control"] == "no-store"

    page = request_fn(config, "/")
    assert page.status == 200 and b"local" in page.read()
    assert page.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert page.headers["Cross-Origin-Embedder-Policy"] == "require-corp"

    module = request_fn(config, "/game.wasm", headers={"Range": "bytes=1-4"})
    assert module.status == 206 and module.read() == b"asm-"
    assert module.headers["Content-Type"] == "application/wasm"
    assert module.headers["Content-Range"].startswith("bytes 1-4/")
    bare_module = request_fn(config, "/game.wasm")
    assert bare_module.status == 200 and bare_module.headers["Cache-Control"] == "no-store"
    good_hash = request_fn(config, f"/game.wasm?v={config.module_hash}")
    assert good_hash.status == 200 and good_hash.read() == (root / "game.wasm").read_bytes()
    assert good_hash.headers["Cache-Control"] == "private, max-age=31536000, immutable"
    stale_hash = request_fn(config, "/game.wasm?v=stale-module-hash")
    assert stale_hash.status == 409
    (root / "game.wasm").write_bytes(b"rebuilt-module")
    changed_hash = request_fn(config, f"/game.wasm?v={config.module_hash}")
    assert changed_hash.status == 409
    head = request_fn(config, "/game.wasm", method="HEAD")
    assert head.status == 200 and int(head.headers["Content-Length"]) == (root / "game.wasm").stat().st_size

    manifest_response = request_fn(config, "/data-manifest")
    manifest = json.loads(manifest_response.read())
    assert {entry["p"] for entry in manifest["files"]} == {"Cars", "Cars/car.bin"}
    data_range = request_fn(config, "/data/Cars/car.bin", headers={"Range": "bytes=3-6"})
    assert data_range.status == 206 and data_range.read() == b"3456"

    invalid_range = request_fn(config, "/data/Cars/car.bin", headers={"Range": "bytes=999-"})
    assert invalid_range.status == 416 and invalid_range.headers["Content-Range"] == "bytes */10"
    escaped = request_fn(config, "/data/%2e%2e%2Fgame.wasm")
    assert escaped.status == 400
    malformed_escape = request_fn(config, "/data/%2e%2e%2")
    assert malformed_escape.status == 400
    symlink_escape = request_fn(config, "/data/escape.bin")
    assert symlink_escape.status == 404
    missing = request_fn(config, "/missing.js")
    assert missing.status == 404


def font_overlay_smoke(root):
    data, overlay = root / "font-data", root / "fonts"
    files = []
    for name in ("GLOBAL/GLOBALA.BUN", "LANGUAGES/LANGUAGETEXTURES.BIN"):
        source, replacement = data / name, overlay / "data" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        replacement.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"original")
        replacement.write_bytes(b"HD fonts")
        files.append({"path": name, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                      "sha256": hashlib.sha256(replacement.read_bytes()).hexdigest()})
    (overlay / "manifest.json").write_text(json.dumps({"kind": "nfsu1-hd-fonts", "files": files}))
    config = Config(root / "dist", root / "game.wasm", root / "game.json", data, overlay)
    response = in_process_request(config, "/data/Global/GLOBALA.BUN", headers={"Range": "bytes=0-1"})
    assert response.status == 206 and response.read() == b"HD"
    entry = next(e for e in config.get_manifest()["files"] if e["p"] == files[0]["path"])
    assert entry["s"] == 8 and entry["m"] != int((data / files[0]["path"]).stat().st_mtime)
    assert (data / files[0]["path"]).read_bytes() == b"original"
    plain = Config(root / "dist", root / "game.wasm", root / "game.json", data)
    assert in_process_request(plain, "/data/GLOBAL/GLOBALA.BUN").read() == b"original"
    (overlay / "data" / files[0]["path"]).write_bytes(b"tampered after server startup")
    assert in_process_request(config, "/data/GLOBAL/GLOBALA.BUN").status == 409
    try:
        Config(root / "dist", root / "game.wasm", root / "game.json", data, overlay)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered font overlay accepted")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--network", dest="mode", action="store_const", const="network", help="use a localhost socket (may be blocked by the sandbox)")
    mode.add_argument("--in-process", dest="mode", action="store_const", const="in-process", help="exercise the HTTP handler without binding a socket (default)")
    parser.set_defaults(mode="in-process")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="nfsu1-http-smoke-") as temporary:
        root = Path(temporary)
        dist = root / "dist"
        data = root / "data"
        dist.mkdir()
        data.mkdir()
        (dist / "index.html").write_text("<h1>local</h1>", encoding="utf-8")
        (dist / "app.js").write_text("ok", encoding="utf-8")
        (data / "Cars").mkdir()
        (data / "Cars" / "car.bin").write_bytes(b"0123456789")
        outside = root / "outside.bin"
        outside.write_bytes(b"private")
        (data / "escape.bin").symlink_to(outside)
        wasm = root / "game.wasm"
        wasm.write_bytes(b"\0asm-test-module")
        metadata = root / "game.json"
        metadata.write_text(json.dumps({"pages": 1, "maxPages": 2, "guestEnd": 65536, "size": wasm.stat().st_size,
                                        "hdFonts": 1}), encoding="utf-8")

        config = Config(dist, wasm, metadata, data)
        font_overlay_smoke(root)
        if args.mode == "in-process":
            exercise(in_process_request, config, root)
            disconnected_client_smoke(config)
            print("In-process HTTP smoke passed: routes, ranges, headers, and path protections. No socket was bound.")
            return 0

        try:
            server = LocalServer(("127.0.0.1", 0), config)
        except OSError as exc:
            print(f"Network smoke could not bind localhost: {exc}")
            return 2
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            exercise(lambda _config, path, method="GET", headers=None: request(base + path, method, headers), config, root)
            print("Network HTTP smoke passed through a localhost socket.")
            return 0
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
