#!/usr/bin/env bash
# Build the playable NFSU1 browser port.
#
# New machine (after copying your game — see below):
#   ./build.sh
#
# Already prepared tree:
#   ./build.sh
#   ./start.sh
#
# Optional: ./build.sh --serve
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

SERVE=0
for arg in "$@"; do
  case "$arg" in
    --serve) SERVE=1 ;;
    -h|--help)
      cat <<'EOF'
Build Wasm + browser page + Rust server.

  1. Copy your whole PC install into work/data/
     (Cars, FrontEnd, Global, Tracks, Sound, Movies, Speed.exe, …)
  2. ./build.sh
  3. ./start.sh   → http://127.0.0.1:8765/

Need once on the machine: Python 3.10+, Node 20+, Rust (rustup), curl, tar.
Everything else (WASI SDK, venv, upstream sources, catalog/lift) is handled
under work/ and gen/ when missing. Speed.exe must be the 1.4 build
(SHA-256 c0fad450912952f53809a54690d235aa8b4e25b9f46650693c7cbee1b4c074b7).
EOF
      exit 0
      ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

need() { command -v "$1" >/dev/null || { echo "error: install $1 first" >&2; exit 1; }; }
need python3
need node
need npm
need cargo
need curl
need tar
need shasum

# --- Game files (you copy the install once; we never download them) ---
[[ -d work/data/Cars ]] || {
  echo "error: copy your PC game install into work/data/" >&2
  echo "  need Cars/, FrontEnd/, … and Speed.exe in that folder" >&2
  exit 1
}
SPEED_EXE=""
for candidate in work/data/Speed.exe work/data/SPEED.exe; do
  if [[ -f "$candidate" && ! -L "$candidate" ]]; then
    SPEED_EXE="$candidate"
    break
  fi
done
[[ -n "$SPEED_EXE" ]] || {
  echo "error: no Speed.exe under work/data/ (copy the full install, including the exe)" >&2
  exit 1
}
echo "Using exe: $SPEED_EXE"

# --- Python venv (Capstone/pefile for catalog/lift only) ---
if [[ ! -x .venv/bin/python ]]; then
  echo "==> Creating .venv + analysis deps"
  python3 -m venv .venv
  .venv/bin/pip install -q capstone==5.0.7 pefile==2024.8.26
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# --- WASI SDK 34 (host-specific download under work/toolchain/) ---
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)
    WASI_ARCHIVE="wasi-sdk-34.0-arm64-macos.tar.gz"
    WASI_DIR="wasi-sdk-34.0-arm64-macos"
    WASI_SHA="9c59398106b417f8f14913380fdf0097a8cc0ff4af9eb3ce0065a859e88d49e9"
    ;;
  Darwin-x86_64)
    WASI_ARCHIVE="wasi-sdk-34.0-x86_64-macos.tar.gz"
    WASI_DIR="wasi-sdk-34.0-x86_64-macos"
    WASI_SHA="87d27fa8adc68dee59bfbf2e22a6d34ef717c34d6bf1d8af2a56fc929d9ce0eb"
    ;;
  Linux-x86_64)
    WASI_ARCHIVE="wasi-sdk-34.0-x86_64-linux.tar.gz"
    WASI_DIR="wasi-sdk-34.0-x86_64-linux"
    WASI_SHA="b761e3a0721dbae9c09a0059e5fdb2bf917d1b4a8a7b430fb3b5aafb0984b2c4"
    ;;
  Linux-aarch64)
    WASI_ARCHIVE="wasi-sdk-34.0-arm64-linux.tar.gz"
    WASI_DIR="wasi-sdk-34.0-arm64-linux"
    WASI_SHA="f7e243dff54d60bcc576e94d6166b69f410f2500ae4a9ceef34315be10e77971"
    ;;
  *)
    echo "error: unsupported host $(uname -s)-$(uname -m); unpack WASI SDK 34 into work/toolchain/ yourself" >&2
    exit 1
    ;;
esac
WASI_ROOT="work/toolchain/$WASI_DIR"
if [[ ! -x "$WASI_ROOT/bin/clang" ]]; then
  echo "==> Downloading WASI SDK 34 ($WASI_ARCHIVE)"
  mkdir -p work/toolchain
  TMP="work/toolchain/$WASI_ARCHIVE"
  URL="https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-34/$WASI_ARCHIVE"
  curl -fL --retry 3 -o "$TMP" "$URL"
  echo "$WASI_SHA  $TMP" | shasum -a 256 -c -
  tar -xzf "$TMP" -C work/toolchain
  rm -f "$TMP"
fi
export WASI="$ROOT/$WASI_ROOT"

# --- Upstream sources + NFSU1 overlays ---
if [[ ! -f work/upstream/nfsu2-web/runtime/cpu.h ]]; then
  echo "==> Fetching pinned upstream sources"
  python3 tools/fetch_upstreams.py
fi
bash tools/apply_runtime_profile.sh --upstream work/upstream/nfsu2-web
bash tools/apply_browser_profile.sh --upstream work/upstream/nfsu2-web

# --- esbuild for the page ---
if [[ ! -x work/toolchain/web-bundler/node_modules/.bin/esbuild ]]; then
  echo "==> Installing esbuild"
  npm install --prefix work/toolchain/web-bundler --no-audit --no-fund \
    --ignore-scripts esbuild@0.27.4
fi

# --- One-time catalog + lift (skipped when gen/ already exists) ---
if [[ ! -f gen/nfsu1-current/fntab.c ]]; then
  echo "==> Catalog + lift (first time on this machine; slow)"
  mkdir -p work/analysis gen
  python3 tools/prepare_game_catalog.py --image "$SPEED_EXE"
  python3 tools/prepare_abk_catalog.py \
    --image "$SPEED_EXE" --data work/data
  python3 tools/lift_abk_catalog.py \
    --image "$SPEED_EXE" --data work/data \
    --output-dir gen/nfsu1-abk
  python3 tools/repair_catalog_callbacks.py \
    --image "$SPEED_EXE" \
    --catalog work/analysis/catalog.json \
    --entry 0x00448a40 --follow-code-immediates \
    --output-dir work/analysis/callback-closure
  python3 tools/lift_catalog.py \
    --image "$SPEED_EXE" \
    --catalog work/analysis/callback-closure/catalog.json \
    --base-catalog work/analysis/catalog.json \
    --upstream work/upstream/nfsu2-web --output-dir gen/nfsu1-current \
    --cooperative-yield-entry 0x0063f0a0 \
    --hooks-file work/upstream/nfsu1-recompiled/config/hooks.txt --link-stubs
fi

# Restore stock car attributes for the game's Online integrity check in a
# sparse local overlay, preserving the user's original containers.
python3 tools/prepare_online_data.py --data work/data --output work/mods/online-data

# --- Compile ---
echo "==> Wasm"
J="${J:-4}" bash tools/build_nfsu1_wasm.sh

echo "==> Browser page"
python3 tools/build_nfsu1_browser.py

echo "==> Server"
cargo build --release --manifest-path server/Cargo.toml

echo
echo "Build OK."
echo "  Play:   ./start.sh"
echo "  Check:  ./start.sh --check"
if [[ "$SERVE" -eq 1 ]]; then
  exec ./start.sh
fi
