#!/usr/bin/env bash
# Build (if needed) and run the NFSU1 browser server — same role as upstream
# nfsu2-web's web/start.sh, without Python.
#
#   ./start.sh [--data DIR] [--port N] [--hd-fonts DIR] [--check] [--no-build]
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

DATA="${NFSU1_DATA:-$ROOT/work/data}"
DIST="$ROOT/work/upstream/nfsu2-web/web/dist"
WASM="$ROOT/work/upstream/nfsu2-web/out/web/nfsu1.wasm"
META="$ROOT/work/upstream/nfsu2-web/out/web/nfsu1.json"
PORT="${PORT:-8765}"
HD_FONTS=""
CHECK=0
NO_BUILD=0
EXTRA=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data) DATA="$2"; shift 2 ;;
    --dist) DIST="$2"; shift 2 ;;
    --wasm) WASM="$2"; shift 2 ;;
    --metadata) META="$2"; shift 2 ;;
    --port|--http-port) PORT="$2"; shift 2 ;;
    --hd-fonts) HD_FONTS="$2"; shift 2 ;;
    --check) CHECK=1; shift ;;
    --no-build) NO_BUILD=1; shift ;;
    --public) EXTRA+=(--public); shift ;;
    --host) EXTRA+=(--host "$2"); shift 2 ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

SERVER_BIN="$ROOT/server/target/release/nfsu1-server"
if [[ "$NO_BUILD" -eq 0 ]]; then
  if [[ ! -x "$SERVER_BIN" ]] || [[ server/src -nt "$SERVER_BIN" ]] || \
     [[ server/Cargo.toml -nt "$SERVER_BIN" ]]; then
    echo "Building nfsu1-server…"
    cargo build --release --manifest-path "$ROOT/server/Cargo.toml"
  fi
fi
[[ -x "$SERVER_BIN" ]] || { echo "error: missing $SERVER_BIN (run without --no-build)" >&2; exit 1; }

ARGS=(--dist "$DIST" --wasm "$WASM" --metadata "$META" --data "$DATA" --port "$PORT")
[[ -n "$HD_FONTS" ]] && ARGS+=(--hd-fonts "$HD_FONTS")
if ((${#EXTRA[@]})); then
  ARGS+=("${EXTRA[@]}")
fi

if [[ "$CHECK" -eq 1 ]]; then
  exec "$SERVER_BIN" "${ARGS[@]}" --check
fi

exec "$SERVER_BIN" "${ARGS[@]}"
