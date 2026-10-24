#!/usr/bin/env python3
"""Prepare a private stock car-table overlay for PC 1.4 Online races.

The game validates all 35 car records at race start. Some installs contain
modified records in GlobalB.lzc alongside a stock GLOBALB.BUN. Restore only
that table in a copied container; original game inputs are never rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_hd_fonts import chunks, game_path, jdlz_decode


TABLE_SIZE = 35 * 0xC90
STOCK_CRC = 0x238562C5


def car_crc(data):
    """PC 1.4 CRC-32/MPEG polynomial, followed by low-first length bytes."""
    table = []
    for byte in range(256):
        value = byte << 24
        for _ in range(8):
            value = ((value << 1) ^ (0x04C11DB7 if value & 0x80000000 else 0)) & 0xFFFFFFFF
        table.append(value)
    value = 0xFFFFFFFF
    length = len(data)
    suffix = bytearray()
    while length:
        suffix.append(length & 255)
        length >>= 8
    for byte in data + suffix:
        value = ((value << 8) & 0xFFFFFFFF) ^ table[(value >> 24) ^ byte]
    return value ^ 0xFFFFFFFF


def unpack(data):
    return jdlz_decode(data) if data.startswith(b"JDLZ") else data


def table_span(data):
    matches = [(offset, size) for kind, offset, size in chunks(data) if kind == 0x34600]
    if len(matches) != 1:
        raise ValueError(f"Expected one car table chunk; found {len(matches)}")
    offset, size = matches[0]
    start = (offset + 8 + 15) & ~15
    if start + TABLE_SIZE != offset + 8 + size:
        raise ValueError("Car table does not contain the PC 1.4 set of 35 records")
    return start, start + TABLE_SIZE


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(data_root, output):
    # Missing LZC means this particular overlay is unnecessary. Ambiguous paths
    # and symlinks still fail through the shared Windows-name resolver.
    globals_dir = [p for p in data_root.iterdir() if p.name.casefold() == "global"]
    if len(globals_dir) > 1:
        raise ValueError("Ambiguous GLOBAL directory")
    if globals_dir and (globals_dir[0].is_symlink() or not globals_dir[0].is_dir()):
        raise ValueError("GLOBAL must be a regular directory")
    has_lzc = (len(globals_dir) == 1 and globals_dir[0].is_dir()
               and any(p.name.casefold() == "globalb.lzc" for p in globals_dir[0].iterdir()))
    report = {"kind": "nfsu1-online-data", "version": 1, "files": [],
              "expected_car_crc": f"{STOCK_CRC:08x}", "status": "no-active-lzc"}
    replacement = None
    if has_lzc:
        source = game_path(data_root, "GLOBAL/GlobalB.lzc")
        original = source.read_bytes()
        container = unpack(original)
        start, end = table_span(container)
        before = car_crc(container[start:end])
        report.update(source_car_crc=f"{before:08x}", status="already-stock")
        if before != STOCK_CRC:
            reference = game_path(data_root, "GLOBAL/GLOBALB.BUN")
            stock = unpack(reference.read_bytes())
            lo, hi = table_span(stock)
            table = stock[lo:hi]
            if car_crc(table) != STOCK_CRC:
                raise ValueError("GLOBALB.BUN is not the stock PC 1.4 car table; cannot restore Online data")
            replacement = container[:start] + table + container[end:]
            assert replacement[:start] == container[:start] and replacement[end:] == container[end:]
            assert car_crc(replacement[start:end]) == STOCK_CRC
            relative = source.relative_to(data_root).as_posix()
            report.update(status="restored", reference=reference.relative_to(data_root).as_posix(),
                          changed_bytes=sum(a != b for a, b in zip(container[start:end], table)),
                          table_offset=start, table_bytes=TABLE_SIZE,
                          source_compression="JDLZ" if original.startswith(b"JDLZ") else "none")
            report["files"] = [{"path": relative, "source_sha256": digest(original),
                                "sha256": digest(replacement), "size": len(replacement)}]
    # Finish validation before writing. A no-op manifest deselects any stale
    # previously prepared replacement without deleting private artifacts.
    output.mkdir(parents=True, exist_ok=True)
    if replacement is not None:
        path = output / "data" / report["files"][0]["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(replacement)
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("work/data"))
    parser.add_argument("--output", type=Path, default=Path("work/mods/online-data"))
    parser.add_argument("--report", type=Path, default=Path("out/online-data.json"))
    args = parser.parse_args()
    data, output = args.data.resolve(), args.output.resolve()
    if output == data or data in output.parents or output in data.parents:
        parser.error("Output must be separate from the original game data tree")
    try:
        report = prepare(data, output)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Online car data: {report['status']} (expected CRC {STOCK_CRC:08x})")
    if report["files"]:
        print(f"  Restored {report['changed_bytes']} bytes in a local overlay; original inputs unchanged.")


if __name__ == "__main__":
    main()
