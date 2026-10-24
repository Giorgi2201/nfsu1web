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

`--online-data DIR` selects the prepared stock car-table overlay from
`tools/prepare_online_data.py`. `start.sh` automatically selects the default
`work/mods/online-data/` after a build. Input/output hashes are validated, and
the data-manifest stamp invalidates cached modified data. Source game files
remain unchanged.

For non-loopback access, use `--public --host 0.0.0.0` (or `NFSU1_PUBLIC=1`).
