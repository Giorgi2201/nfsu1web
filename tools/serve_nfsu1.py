#!/usr/bin/env python3
"""Serve the private NFSU1 browser build and game data on localhost."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import threading
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / "work/upstream/nfsu2-web/web/dist"
DEFAULT_WASM = ROOT / "work/upstream/nfsu2-web/out/web/nfsu1.wasm"
DEFAULT_METADATA = ROOT / "work/upstream/nfsu2-web/out/web/nfsu1.json"
DEFAULT_DATA = ROOT / "work/data"
ALLOWED_DATA_LINK = DEFAULT_DATA / "Speed.exe"
ALLOWED_DATA_TARGET = ROOT / "work/analysis/Speed.analysis.exe"
class RequestError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_under(root: Path, parts: tuple[str, ...], *, data: bool = False) -> Path:
    """Resolve a URL path while rejecting traversal and unexpected symlinks."""
    root = root.resolve(strict=True)
    current = root
    for i, part in enumerate(parts):
        if part in ("", ".", "..") or "/" in part or "\\" in part or "\x00" in part:
            raise RequestError(400, "invalid path")
        candidate = current / part
        if candidate.is_symlink():
            if data and candidate == ALLOWED_DATA_LINK and i == len(parts) - 1:
                try:
                    resolved = candidate.resolve(strict=True)
                except OSError:
                    raise RequestError(404, "not found") from None
                if resolved == ALLOWED_DATA_TARGET.resolve(strict=True):
                    current = resolved
                    continue
            raise RequestError(404, "not found")
        current = candidate
        # Check each existing component to catch a symlink introduced between
        # requests, and resolve it before the next segment is joined.
        try:
            resolved = current.resolve(strict=True)
        except FileNotFoundError:
            if i != len(parts) - 1:
                raise RequestError(404, "not found") from None
            return current
        except OSError:
            raise RequestError(404, "not found") from None
        if not within(resolved, root):
            raise RequestError(404, "not found")
        current = resolved
    return current


def decoded_parts(raw_path: str) -> tuple[str, ...]:
    if not raw_path.startswith("/"):
        raise RequestError(400, "invalid path")
    raw_parts = raw_path.split("/")[1:]
    if raw_parts and raw_parts[-1] == "":
        raw_parts.pop()
    result = []
    for raw in raw_parts:
        # Decode per segment so encoded separators can never change the route.
        if re.search(r"%(?![0-9A-Fa-f]{2})", raw):
            raise RequestError(400, "malformed percent escape")
        part = unquote(raw, errors="strict")
        if part in (".", "..") or "/" in part or "\\" in part or "\x00" in part:
            raise RequestError(400, "invalid path")
        result.append(part)
    return tuple(result)


def build_manifest(data: Path) -> dict:
    """Build the web runtime's files[] manifest from the private install tree."""
    root = data.resolve(strict=True)
    files: list[dict] = []
    for current, dirs, names in os.walk(root, followlinks=False):
        here = Path(current)
        dirs.sort(key=str.casefold)
        names.sort(key=str.casefold)
        # Symlinked directories are never followed or exposed.
        dirs[:] = [d for d in dirs if not (here / d).is_symlink()]
        rel_dir = here.relative_to(root).as_posix()
        if rel_dir != ".":
            files.append({"p": rel_dir, "d": True})
        for name in names:
            path = here / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                if path != ALLOWED_DATA_LINK:
                    continue
                try:
                    resolved = path.resolve(strict=True)
                except OSError:
                    continue
                if resolved != ALLOWED_DATA_TARGET.resolve(strict=True):
                    continue
                path = resolved
            try:
                st = path.stat()
            except OSError:
                continue
            if not path.is_file():
                continue
            files.append({"p": rel, "s": st.st_size, "m": int(st.st_mtime)})
    return {"files": files}


def validate_config(dist: Path, wasm: Path, metadata: Path, data: Path) -> list[str]:
    errors = []
    for label, path in (("dist", dist), ("wasm", wasm), ("metadata", metadata), ("data", data)):
        if not path.exists():
            errors.append(f"{label} path does not exist: {path}")
    if dist.exists() and (not dist.is_dir() or not (dist / "index.html").is_file() or not (dist / "main.js").is_file()):
        errors.append(f"dist must contain index.html and main.js: {dist}")
    if wasm.exists() and not wasm.is_file():
        errors.append(f"wasm is not a file: {wasm}")
    if metadata.exists():
        try:
            info = json.loads(metadata.read_text(encoding="utf-8"))
            if not isinstance(info, dict):
                raise ValueError("expected a JSON object")
            for key in ("pages", "maxPages", "guestEnd", "size"):
                if not isinstance(info.get(key), int) or info[key] < 0:
                    raise ValueError(f"missing or invalid {key}")
            if wasm.is_file() and info["size"] != wasm.stat().st_size:
                raise ValueError(f"size is {info['size']}, but wasm is {wasm.stat().st_size} bytes")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"invalid metadata {metadata}: {exc}")
    if data.exists() and not data.is_dir():
        errors.append(f"data is not a directory: {data}")
    if data.exists() and data.is_dir():
        for current, dirs, names in os.walk(data, followlinks=False):
            here = Path(current)
            for name in dirs + names:
                path = here / name
                if path.is_symlink() and path != ALLOWED_DATA_LINK:
                    errors.append(f"unexpected symlink in private data: {path}")
                elif path == ALLOWED_DATA_LINK:
                    try:
                        if path.resolve(strict=True) != ALLOWED_DATA_TARGET.resolve(strict=True):
                            errors.append(f"unexpected Speed.exe target: {path}")
                    except OSError:
                        errors.append(f"broken allowed Speed.exe link: {path}")
    return errors


class Config:
    def __init__(self, dist: Path, wasm: Path, metadata: Path, data: Path):
        self.dist = dist.resolve(strict=True)
        self.wasm = wasm.resolve(strict=True)
        self.metadata = metadata.resolve(strict=True)
        self.data = data.resolve(strict=True)
        # Pin the module and its browser metadata for this server lifetime.
        # Restart after rebuilding the wasm or changing the game data.
        self.lock = threading.Lock()
        self.manifest = None
        self.module_hash = self._hash_file(self.wasm)
        self.module_stamp = self._file_stamp(self.wasm)
        self.game_info = json.loads(self.metadata.read_text(encoding="utf-8"))
        self.game_info["rev"] = f"nfsu1-local-{self.module_hash[:12]}"
        self.game_info["module"] = self.module_hash
        self.game_json = json.dumps(self.game_info, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _file_stamp(path: Path) -> tuple[int, int, int, int]:
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    def get_manifest(self):
        # This private install manifest is fixed for one server run; restart
        # after changing the data tree so file metadata and URLs stay aligned.
        with self.lock:
            if self.manifest is None:
                self.manifest = build_manifest(self.data)
            return self.manifest


class Handler(BaseHTTPRequestHandler):
    server_version = "nfsu1-private/1.0"
    protocol_version = "HTTP/1.1"

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # Closing/reloading a tab can interrupt a keep-alive read or a
            # streamed response. It is a disconnected client, not a server fault.
            pass

    @property
    def config(self) -> Config:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def do_HEAD(self):
        self.handle_request(send_body=False)

    def do_GET(self):
        self.handle_request(send_body=True)

    def handle_request(self, send_body: bool):
        try:
            parsed = urlsplit(self.path)
            path = parsed.path
            if path == "/game.json":
                self._send_bytes(self.config.game_json, "application/json", send_body)
                return
            if path == "/game.wasm":
                requested_hash = parse_qs(parsed.query, keep_blank_values=True).get("v", [""])[0]
                if requested_hash and requested_hash != self.config.module_hash:
                    self._error(409, "module changed; reload game.json")
                    return
                if requested_hash:
                    if self.config._file_stamp(self.config.wasm) != self.config.module_stamp:
                        self._error(409, "module changed; restart the local server")
                        return
                    self._send_file(self.config.wasm, "application/wasm", send_body, ranges=True,
                                    cache_control="private, max-age=31536000, immutable",
                                    expected_stamp=self.config.module_stamp)
                else:
                    self._send_file(self.config.wasm, "application/wasm", send_body, ranges=True)
                return
            if path == "/data-manifest":
                body = json.dumps(self.config.get_manifest(), separators=(",", ":")).encode()
                self._send_bytes(body, "application/json", send_body)
                return
            if path == "/data" or path.startswith("/data/"):
                suffix = path[len("/data/"):] if path.startswith("/data/") else ""
                parts = decoded_parts("/" + suffix) if suffix else ()
                target = resolve_under(self.config.data, parts, data=True)
                self._send_file(target, self._mime(target), send_body, ranges=True)
                return
            parts = decoded_parts(path)
            target = resolve_under(self.config.dist, parts, data=False)
            if target.is_dir():
                target = resolve_under(self.config.dist, parts + ("index.html",), data=False)
            self._send_file(target, self._mime(target), send_body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # Do not attempt a second HTTP response on a closed connection.
            return
        except RequestError as exc:
            self._error(exc.status, str(exc))
        except (OSError, ValueError, UnicodeError):
            self._error(404, "not found")

    @staticmethod
    def _mime(path: Path) -> str:
        return mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    def _send_file(self, path: Path, content_type: str, send_body: bool, ranges: bool = False,
                   cache_control: str = "no-store", expected_stamp: tuple[int, int, int, int] | None = None):
        try:
            if not path.is_file():
                raise RequestError(404, "not found")
            stat = path.stat()
            if expected_stamp is not None and (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != expected_stamp:
                self._error(409, "module changed; restart the local server")
                return
            size = stat.st_size
        except OSError:
            raise RequestError(404, "not found") from None
        start, end = 0, size - 1
        status = 200
        range_header = self.headers.get("Range") if ranges else None
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or size == 0:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            a, b = match.groups()
            if a:
                start = int(a)
                end = min(int(b), size - 1) if b else size - 1
            elif b:
                length = int(b)
                start = max(0, size - length)
            else:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if start >= size or end < start:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes" if ranges else "none")
        self.send_header("Content-Length", str(length))
        self.send_header("Last-Modified", formatdate(stat.st_mtime, usegmt=True))
        self.send_header("Cache-Control", cache_control)
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if send_body:
            with path.open("rb") as stream:
                stream.seek(start)
                remaining = length
                while remaining:
                    chunk = stream.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    def _send_bytes(self, body: bytes, content_type: str, send_body: bool):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _error(self, status: int, message: str):
        body = (message + "\n").encode("utf-8", "replace")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, config):
        super().__init__(address, Handler)
        self.config = config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST, help="built web dist directory")
    parser.add_argument("--wasm", type=Path, default=DEFAULT_WASM, help="private NFSU1 wasm module")
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA, help="NFSU1 module metadata JSON")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="private game data directory")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (localhost only by default)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port")
    parser.add_argument("--check", action="store_true", help="validate required local inputs without binding a port")
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "::1", "localhost"):
        parser.error("only loopback hosts are allowed")
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    return args


def main(argv=None):
    args = parse_args(argv)
    errors = validate_config(args.dist, args.wasm, args.metadata, args.data)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    if args.check:
        print("Local server inputs are ready.")
        return 0
    config = Config(args.dist, args.wasm, args.metadata, args.data)
    server = LocalServer((args.host, args.port), config)
    address = server.server_address
    print(f"Serving private NFSU1 build at http://{address[0]}:{address[1]}/ (Ctrl-C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
