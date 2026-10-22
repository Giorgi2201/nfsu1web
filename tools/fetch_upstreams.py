#!/usr/bin/env python3
"""Fetch or validate the public source files pinned in profiles/upstreams.json.

The fetcher downloads only listed files into ignored work/upstream/. Each file
is checked against its Git blob SHA-1 before it can be written. Existing files
are never replaced. Runtime and browser overlay files may be verified through
their canonical copies under the overlay backup directories.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "profiles/upstreams.json"
DEFAULT_DESTINATION = ROOT / "work/upstream"
SHA1 = re.compile(r"^[0-9a-f]{40}$")


def git_blob_sha1(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def safe_relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe inventory path: {value!r}")
    return Path(*path.parts)


def load_inventory(path):
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or not isinstance(data.get("sources"), list):
        raise ValueError("unsupported upstream inventory schema")
    files = []
    destinations = set()
    for source in data["sources"]:
        repo = source["repository"]
        commit = source["commit"]
        expected_base = f"https://raw.githubusercontent.com/{repo}/{commit}"
        if not SHA1.fullmatch(commit) or source["raw_base"] != expected_base:
            raise ValueError(f"invalid pinned source URL or commit for {repo}")
        destination = safe_relative(source["destination"])
        for item in source["files"]:
            relative = safe_relative(item["path"])
            digest = item["git_blob_sha1"]
            if not SHA1.fullmatch(digest):
                raise ValueError(f"invalid Git blob hash for {repo}/{relative}")
            target = destination / relative
            if target in destinations:
                raise ValueError(f"duplicate upstream destination: {target}")
            destinations.add(target)
            files.append({"repo": repo, "base": source["raw_base"],
                          "commit": commit,
                          "source_path": relative.as_posix(),
                          "target": target, "hash": digest})
    return files


def canonical_backup(destination_root, item, target):
    """Return a pristine copy only when overlay state authenticates the target."""
    if item["repo"] != "th0mk/nfsu2-web":
        return None
    relative = item["target"].relative_to("nfsu2-web")
    if relative.parts[0] == "runtime":
        overlay = destination_root / "nfsu2-web/.nfsu1-profile"
    elif relative.parts[0] == "web":
        overlay = destination_root / "nfsu2-web/.nfsu1-browser-profile"
    else:
        return None
    state_path = overlay / "state.json"
    try:
        state = json.loads(state_path.read_text())
        applied = state["files"][relative.as_posix()]["applied_sha256"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None
    if (state.get("upstream_commit") != item["commit"] or
            hashlib.sha256(target.read_bytes()).hexdigest() != applied):
        return None
    return overlay / relative


def valid_file(path, expected):
    return path.is_file() and git_blob_sha1(path.read_bytes()) == expected


def local_status(destination_root, item):
    path = destination_root / item["target"]
    if not path.exists():
        if path.is_symlink():
            return "mismatch", path
        return "missing", path
    if not path.is_file():
        return "mismatch", path
    if valid_file(path, item["hash"]):
        return "present", path
    backup = canonical_backup(destination_root, item, path)
    if backup is not None and valid_file(backup, item["hash"]):
        return "backup", backup
    if backup is not None and backup.exists():
        return "mismatch", backup
    return "mismatch", path


def fetch_file(item):
    url = f"{item['base']}/{item['source_path']}"
    request = Request(url, headers={"User-Agent": "nfsu1web-pinned-source-bootstrap/1"})
    with urlopen(request, timeout=30) as response:
        data = response.read()
    actual = git_blob_sha1(data)
    if actual != item["hash"]:
        raise ValueError(f"download hash mismatch for {item['repo']}:{item['target']}: {actual}")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="validate local pinned sources without network access")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    args = parser.parse_args()

    try:
        files = load_inventory(args.inventory)
        destination = DEFAULT_DESTINATION.resolve()
        states = [(item, *local_status(destination, item)) for item in files]
        mismatches = [(item, path) for item, status, path in states if status == "mismatch"]
        if mismatches:
            details = "\n".join(f"  {path}: does not match {item['hash']}" for item, path in mismatches)
            raise ValueError("existing upstream files differ from their pinned blobs; no files changed:\n" + details)
        if args.check:
            missing = [(item, path) for item, status, path in states if status == "missing"]
            if missing:
                print(f"{len(missing)} pinned upstream files are missing:")
                for item, path in missing:
                    print(f"  {path} [{item['hash']}]")
                return 1
            backups = sum(status == "backup" for _, status, _ in states)
            print(f"Pinned upstream check passed: {len(files)} files verified ({backups} via canonical overlay backups).")
            return 0

        pending = [(item, path) for item, status, path in states if status == "missing"]
        downloads = []
        for item, path in pending:
            print(f"Fetching {item['repo']}:{item['target']}")
            downloads.append((path, fetch_file(item)))

        # All existing files and all downloaded payloads have been checked
        # before the first write. Exclusive creation prevents accidental replace.
        for path, payload in downloads:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("xb") as stream:
                    stream.write(payload)
            except FileExistsError:
                if not valid_file(path, git_blob_sha1(payload)):
                    raise ValueError(f"destination appeared with different contents; left unchanged: {path}")
        print(f"Pinned upstream sources ready: {len(files)} files ({len(downloads)} fetched).")
        return 0
    except (OSError, ValueError, KeyError, URLError) as error:
        print(f"fetch_upstreams: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
