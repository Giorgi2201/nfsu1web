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

For non-loopback access, use `--public --host 0.0.0.0` (or `NFSU1_PUBLIC=1`).
