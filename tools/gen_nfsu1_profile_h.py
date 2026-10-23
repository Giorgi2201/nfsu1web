#!/usr/bin/env python3
"""Emit runtime/nfsu1_profile.h from profiles/nfsu1-pc.json (no source rewriting)."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=ROOT / "profiles/nfsu1-pc.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    ident = profile["identity"]["structural_values"]
    lifting = profile["lifting"]
    guest = int(profile["runtime"]["guest_end"], 16)
    lines = [
        "/* Generated from profiles/nfsu1-pc.json; see docs/source-permissions.md. */",
        "#ifndef NFSU1_PROFILE_H",
        "#define NFSU1_PROFILE_H",
        f"#define NFSU1_IMAGE_BASE 0x{int(ident['image_base'], 16):08x}u",
        f"#define NFSU1_IMAGE_SIZE 0x{int(ident['size_of_image'], 16):08x}u",
        f"#define NFSU1_ENTRY_VA 0x{int(ident['entry_va'], 16):08x}u",
        f"#define DISPATCH_TEXT_BASE 0x{int(lifting['dispatch_text_base'], 16):08x}u",
        f"#define DISPATCH_TEXT_SIZE 0x{int(lifting['dispatch_text_size'], 16):08x}u",
        f"#define NFSU1_ENTRY_POINT {profile['runtime']['entry_symbol']}",
        f'#define NFSU1_EXE_SHA256 "{profile["identity"]["sha256"]}"',
        '#define NFSU1_EXE_PATH "/data/Speed.exe"',
        '#define NFSU1_EXE_NAME "Speed.exe"',
        f"#define NFSU1_GUEST_LIMIT {guest}ull",
        "#endif",
        "",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
