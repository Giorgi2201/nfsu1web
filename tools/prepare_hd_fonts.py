#!/usr/bin/env python3
"""Prepare a private fonts-only data overlay from Raze's extracted HD Fonts.

Only two copied PC v4 TPK containers are rewritten. Original game inputs and
the DDS archive are never changed. No ASI, gauge or TexWizard files are used.
TPK layout reference: xan1242/xnfstpktool, MIT, revision
bfd46d4e71df7a23db4f4e43c51aa37db2839fee (OldTextureInfo and v2 pixel format).
The independently written JDLZ reader implements the format documented at
https://github.com/MWisBest/OpenNFSTools/blob/master/LibNFS/Compression/JDLZ.cs
and validates every source span. Language packs retain their compressed stream
table: the game's language loader requests individual textures through it.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct


FONTS = {
    "GLOBAL/GLOBALA.BUN": {
        "CONDUITMDITC_TT21I": ("GlobalMessageTextures", 0x5B9D88B9, 256),
    },
    "LANGUAGES/LANGUAGETEXTURES.BIN": {
        "CONDUITMDITC_TT14I": ("LanguageTextures", 0x5B9D84DB, 256),
        "LCD_LET48": ("LanguageTextures", 0xBBBA71C2, 128),
        "FONT_CONDUITMDITCTT38BI": ("LanguageTextures", 0x9583AA1A, 512),
    },
}
RECORD_SIZE = 124
MAX_TEXTURE_BYTES = 32 * 1024 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def game_path(root, relative):
    """Resolve the game's Windows names without relying on host case folding."""
    current = root
    for part in Path(relative).parts:
        matches = [entry for entry in current.iterdir() if entry.name.casefold() == part.casefold()]
        if len(matches) != 1:
            raise ValueError(f"Missing or ambiguous game path: {relative}")
        current = matches[0]
        if current.is_symlink():
            raise ValueError(f"Symlink in game path: {relative}")
    if not current.is_file():
        raise ValueError(f"Game input is not a regular file: {relative}")
    return current


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def chunks(data, start=0, end=None):
    end = len(data) if end is None else end
    while start < end:
        if start + 8 > end:
            raise ValueError("Truncated chunk header")
        kind, size = struct.unpack_from("<II", data, start)
        if start + 8 + size > end:
            raise ValueError(f"Chunk at {start:#x} exceeds its parent")
        yield kind, start, size
        start += 8 + size


def child(data, parent, kind, required=True):
    matches = [c for c in chunks(data, parent[1] + 8, parent[1] + 8 + parent[2])
               if c[0] == kind]
    if len(matches) == 1:
        return matches[0]
    if matches or required:
        raise ValueError(f"Expected one {kind:#x} chunk; found {len(matches)}")
    return None


def jdlz_decode(data):
    if len(data) < 16 or data[:8] != b"JDLZ\x02\x10\x00\x00":
        raise ValueError("Unsupported texture compression header")
    expected, stored = struct.unpack_from("<II", data, 8)
    if expected > MAX_TEXTURE_BYTES or stored != len(data):
        raise ValueError("Invalid JDLZ lengths")
    output = bytearray()
    cursor = 16
    control = mode = 1

    def take():
        nonlocal cursor
        if cursor >= len(data):
            raise ValueError("Truncated JDLZ stream")
        value = data[cursor]
        cursor += 1
        return value

    while len(output) < expected:
        if control == 1:
            control = take() | 256
        if mode == 1:
            mode = take() | 256
        if control & 1:
            first, second = take(), take()
            if mode & 1:
                distance = (first & 15) + 1
                count = ((first & 240) << 4) + second + 3
            else:
                distance = ((first & 224) << 3) + second + 17
                count = (first & 31) + 3
            if distance > len(output) or len(output) + count > expected:
                raise ValueError("Invalid JDLZ back-reference")
            for _ in range(count):
                output.append(output[-distance])
            mode >>= 1
        else:
            output.append(take())
        control >>= 1
    # The PC game's compressor emits up to two unused lookahead bytes after
    # the last output symbol (present in every stock language texture here).
    if len(data) - cursor > 2:
        raise ValueError("JDLZ stream has excessive trailing bytes")
    return bytes(output)


def jdlz_literals(data):
    """Encode valid JDLZ without back-references, retaining streaming support."""
    payload = bytearray()
    for offset in range(0, len(data), 8):
        payload.append(0)  # Eight literal tokens in the first flag stream.
        if offset == 0:
            payload.append(0)  # Second flag stream is loaded once, never used.
        payload.extend(data[offset:offset + 8])
    # PC 1.4's decoder refills the first flag stream immediately after each
    # group, before checking whether the compressed byte count reached zero.
    # Supply that terminal lookahead byte when the final group is complete.
    if data and len(data) % 8 == 0:
        payload.append(0)
    result = b"JDLZ\x02\x10\0\0" + struct.pack("<II", len(data), len(payload) + 16) + payload
    if jdlz_decode(result) != data:
        raise ValueError("JDLZ literal encoding failed round-trip verification")
    return result


def read_dds(path, nominal):
    data = path.read_bytes()
    if (len(data) < 128 or data[:4] != b"DDS " or u32(data, 4) != 124
            or u32(data, 76) != 32 or data[84:88] != b"DXT5"):
        raise ValueError(f"Expected legacy DXT5 DDS: {path}")
    height, width = struct.unpack_from("<II", data, 12)
    levels = max(1, u32(data, 28))
    if width != nominal * 4 or height != nominal * 4 or not 1 <= levels <= 13:
        raise ValueError(f"Unexpected font dimensions/mips: {path}")
    expected = sum(max(1, (width >> i) // 4) * max(1, (height >> i) // 4) * 16
                   for i in range(levels))
    if len(data) != expected + 128 or u32(data, 20) != width * height:
        raise ValueError(f"DDS pixel length does not match dimensions: {path}")
    return data, width, height, levels


def parse_pack(data):
    top = list(chunks(data))
    capsules = [c for c in top if c[0] == 0xB3300000]
    if len(capsules) != 1:
        raise ValueError("Expected exactly one texture pack")
    capsule = capsules[0]
    header = child(data, capsule, 0xB3310000)
    pixels = child(data, capsule, 0xB3320000)
    info = child(data, header, 0x33310001)
    records = child(data, header, 0x33310004)
    formats = child(data, header, 0x33310005)
    streams = child(data, header, 0x33310003, required=False)
    image_chunk = child(data, pixels, 0x33320002)
    if info[2] != 124 or u32(data, info[1] + 8) != 4:
        raise ValueError("Expected PC TPK version 4")
    if records[2] % RECORD_SIZE or formats[2] != records[2] // RECORD_SIZE * 32:
        raise ValueError("Invalid PC texture metadata table lengths")
    # The loader rounds the image chunk payload up to the next 128-byte boundary.
    origin = (image_chunk[1] + 8 + 127) & ~127
    if data[image_chunk[1] + 8:origin] != b"\x11" * (origin - image_chunk[1] - 8):
        raise ValueError("Unexpected image alignment padding")
    stream_map = {}
    if streams:
        if streams[2] % 20:
            raise ValueError("Invalid v4 texture stream table")
        for off in range(streams[1] + 8, streams[1] + 8 + streams[2], 20):
            key, location, size, flags, unused = struct.unpack_from("<5I", data, off)
            if key in stream_map or flags != 256 or unused != 0:
                raise ValueError("Unsupported or duplicate compressed texture entry")
            if location < origin or location + size > image_chunk[1] + 8 + image_chunk[2]:
                raise ValueError("Texture stream exceeds image chunk")
            stream_map[key] = jdlz_decode(data[location:location + size])
    textures = []
    for index, off in enumerate(range(records[1] + 8, records[1] + 8 + records[2], RECORD_SIZE)):
        raw = bytearray(data[off:off + RECORD_SIZE])
        key = u32(raw, 36)
        name = raw[12:36].split(b"\0", 1)[0].decode("ascii")
        placement, palette, size, palette_size = struct.unpack_from("<4I", raw, 48)
        if palette_size or not 0 < size <= MAX_TEXTURE_BYTES:
            raise ValueError("Palette textures or invalid image lengths are unsupported")
        if streams:
            if key not in stream_map:
                raise ValueError("Texture is missing its compressed stream")
            image = stream_map.pop(key)
        else:
            start = origin + placement
            if start < origin or start + size > image_chunk[1] + 8 + image_chunk[2]:
                raise ValueError("Texture image exceeds image chunk")
            image = data[start:start + size]
        if len(image) != size:
            raise ValueError("Decompressed texture length differs from metadata")
        fmt_off = formats[1] + 8 + index * 32
        textures.append({"name": name, "hash": key, "raw": raw, "offset": off,
                         "image": image, "format_offset": fmt_off})
    if stream_map:
        raise ValueError("Unreferenced compressed textures")
    return capsule, pixels, image_chunk, origin, streams, textures


def prepare_container(original, selection, textures_root):
    capsule, pixels, image_chunk, origin, streams, textures = parse_pack(original)
    updated = bytearray(original)
    manifest_fonts = []
    seen = set()
    images = bytearray()
    logical_offset = 0
    stream_entries = {}
    if streams:
        for offset in range(streams[1] + 8, streams[1] + 8 + streams[2], 20):
            key, location, size = struct.unpack_from("<III", original, offset)
            stream_entries[key] = (offset, original[location:location + size])
    for texture in textures:
        raw = texture["raw"]
        image = texture["image"]
        name = texture["name"]
        if name in selection:
            folder, key, nominal = selection[name]
            if name in seen or texture["hash"] != key or struct.unpack_from("<HH", raw, 68) != (nominal, nominal):
                raise ValueError(f"Unexpected original font identity: {name}")
            seen.add(name)
            path = textures_root / folder / (name + ".dds")
            dds, width, height, levels = read_dds(path, nominal)
            image = dds[128:]
            struct.pack_into("<III", raw, 56, len(image), 0, width * height)
            struct.pack_into("<HHBBBB", raw, 68, width, height,
                             width.bit_length() - 1, height.bit_length() - 1, 0x26, raw[75])
            raw[78] = levels
            updated[texture["format_offset"] + 20:texture["format_offset"] + 24] = b"DXT5"
            manifest_fonts.append({"name": name, "hash": f"0x{key:08x}",
                                   "width": width, "height": height, "nominal_size": nominal,
                                   "mip_levels": levels, "dds_sha256": sha256(dds)})
        logical_offset = (logical_offset + 127) & ~127
        # Zero-length palettes are unused, but retain their end-of-image convention.
        struct.pack_into("<I", raw, 48, logical_offset)
        if u32(raw, 52) != 0xFFFFFFFF:
            struct.pack_into("<I", raw, 52, logical_offset + len(image))
        logical_offset += len(image)
        if streams:
            stream_offset, original_stream = stream_entries[texture["hash"]]
            stored = jdlz_literals(image) if name in selection else original_stream
            struct.pack_into("<II", updated, stream_offset + 4, origin + len(images), len(stored))
            images.extend(stored)
        else:
            images.extend(b"\0" * (-len(images) % 128))
            images.extend(image)
        updated[texture["offset"]:texture["offset"] + RECORD_SIZE] = raw
    if seen != set(selection):
        raise ValueError("One or more selected fonts were not found")
    old_end = image_chunk[1] + 8 + image_chunk[2]
    images.extend(b"\0" * ((old_end - origin - len(images)) % 128))
    difference = origin + len(images) - old_end
    for chunk in (capsule, pixels, image_chunk):
        struct.pack_into("<I", updated, chunk[1] + 4, chunk[2] + difference)
    result = bytes(updated[:origin]) + images + bytes(updated[old_end:])
    # Re-read the output through its original loading path and verify every pixel payload,
    # including untouched fonts and artwork from the original compressed pack.
    output_textures = parse_pack(result)[-1]
    for source, dest in zip(textures, output_textures):
        if source["name"] not in selection and source["image"] != dest["image"]:
            raise ValueError("Repacking altered an unrelated texture")
        if source["name"] in selection:
            folder = selection[source["name"]][0]
            if dest["image"] != (textures_root / folder / (source["name"] + ".dds")).read_bytes()[128:]:
                raise ValueError("Repacked font differs from DDS")
    return result, manifest_fonts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("work/data"))
    parser.add_argument("--mod", type=Path, required=True, help="Extracted HD Fonts archive directory")
    parser.add_argument("--output", type=Path, default=Path("work/mods/hd-fonts"))
    args = parser.parse_args()
    data_root = args.data.resolve()
    output = args.output.resolve()
    if output == data_root or data_root in output.parents or output in data_root.parents:
        parser.error("Output must be separate from the original game data tree")
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory must be empty; use a fresh --output directory")
    textures_root = args.mod.resolve() / "Textures"
    files = []
    prepared = []
    try:
        for relative, selection in FONTS.items():
            source = game_path(data_root, relative)
            actual_relative = source.relative_to(data_root).as_posix()
            original = source.read_bytes()
            result, fonts = prepare_container(original, selection, textures_root)
            files.append({"path": actual_relative, "sha256": sha256(result),
                          "source_sha256": sha256(original), "size": len(result), "fonts": fonts})
            prepared.append((actual_relative, result))
    except (ValueError, OSError, struct.error) as error:
        parser.error(str(error))
    # Finish parsing and validating all files before creating any output.
    output.mkdir(parents=True, exist_ok=True)
    for relative, result in prepared:
        destination = output / "data" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(result)
    manifest = {"kind": "nfsu1-hd-fonts", "version": 1, "files": files,
                "language_texture_loading": "original compressed stream table; literal JDLZ for replaced fonts",
                "provenance": {"mod": "NFSU-HD FONTS by Raze", "url": "https://nfsmods.xyz/mod/6370",
                               "scope": "Four font textures only; no gauges or ASI binaries",
                               "distribution": "Private local preparation; artwork redistribution unverified",
                               "tool_sha256": sha256(Path(__file__).read_bytes())}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared four HD fonts in {output}")
    for item in files:
        print(f"  {item['path']}: {item['size']:,} bytes, {len(item['fonts'])} font(s)")


if __name__ == "__main__":
    main()
