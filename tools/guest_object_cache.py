#!/usr/bin/env python3
"""Compute guest object cache keys, ignoring only unused generated prototypes."""

import hashlib
from pathlib import Path
import re
import sys


PROTOTYPE = re.compile(rb"void (sub_[0-9a-f]{8})\(CPU \*\);")
TOKEN = re.compile(rb"[A-Za-z_][A-Za-z_0-9]*")


def cache_keys(source: bytes, declarations: bytes, header_sum: str) -> tuple[str, str]:
    tokens = set(TOKEN.findall(source))
    retained = []
    for line in re.findall(rb"[^\n]*\n|[^\n]+$", declarations):
        # Preserve everything except exact, unreferenced generated prototypes.
        # In particular, unfamiliar signatures and CRLF lines remain hashed.
        prototype = PROTOTYPE.fullmatch(line.removesuffix(b"\n"))
        if prototype is None or prototype.group(1) in tokens:
            retained.append(line)
    suffix = header_sum.encode("ascii") + b"\n"
    current = hashlib.sha1(
        b"guest-object-cache-v1\0" + source + b"\0" + b"".join(retained) + b"\0" + suffix
    ).hexdigest()
    # Exact historical shell formula: (cat source decls; echo "$HDRSUM") | shasum.
    legacy = hashlib.sha1(source + declarations + suffix).hexdigest()
    return current, legacy


if __name__ == "__main__":
    source_path, declarations_path, header_sum = sys.argv[1:]
    print(*cache_keys(Path(source_path).read_bytes(), Path(declarations_path).read_bytes(), header_sum))
