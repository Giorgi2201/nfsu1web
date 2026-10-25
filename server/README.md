# nfsu1-server

HTTP front end for the NFSU1 browser host: page, `/game.wasm`, `/game.json`,
`/data-manifest`, range-readable `/data/*`, COOP/COEP isolation headers, and a
minimal virtual-LAN switch on `/lan` (plus `/players`).

```sh
cargo build --release
./target/release/nfsu1-server --check
./target/release/nfsu1-server
# optional: node ../tools/lan_switch_smoke.mjs
```

The page attaches to `/lan` when `NFSU2_NET` is on (default in the NFSU1
overlay). `NFSU2_ONLINE` and `NFSU2_ROAM` stay off — no SPEED2 lobby/roam host.

`--online-data DIR` selects the prepared Online car-data overlay.
`start.sh` selects `work/mods/online-data/` automatically after a build.
Source game files remain unchanged.

## Online lobby

The local lobby implements login, rooms, private messages, challenge invites,
created games, and keepalives. News, statistics, and rankings are placeholders;
there is no database. Lobby details are in the
[protocol reference](../docs/online-protocol.md). A lobby connection does not
provide race peer networking, and actual multiplayer race behavior is not
established.

For non-loopback access, use `--public --host 0.0.0.0` (or `NFSU1_PUBLIC=1`).

The relay defaults to 512 players (`--max-players N`, up to 2045) on a /21
virtual network. It supports upstream kind-32 packet bundles and legacy
unbundled clients. Queued race packets flush immediately, without a batching
timer. Each client has a bounded 256-message outgoing queue; full queues,
blocked writes and excessive traffic disconnect that client instead of losing
reliable TCP frames. Pending handshakes and message sizes are bounded too.
Online sockets, rooms and games are cleaned up when browsers disconnect.
Lobby state remains in memory; automatic address/session resume is not implemented.

Focused command-line validation (no browser or game compatibility claim):

```sh
cargo test --manifest-path server/Cargo.toml
cargo build --release --manifest-path server/Cargo.toml
NFSU1_LAN_SMOKE_PEERS=300 node tools/lan_switch_smoke.mjs
```

Run those commands from the repository root. The smoke requires the local game
build, checks connections across the old /24 boundary and bundle ordering,
and does not simulate hundreds of races. The player limit is a configurable
admission cap, not a measured gameplay capacity.
