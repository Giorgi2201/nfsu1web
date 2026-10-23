# nfsu1-server

HTTP front end for the NFSU1 browser host: page, `/game.wasm`, `/game.json`,
`/data-manifest`, and range-readable `/data/*`, with COOP/COEP isolation
headers.

```sh
cargo build --release
./target/release/nfsu1-server --check
./target/release/nfsu1-server
```

For non-loopback access, use `--public --host 0.0.0.0` (or `NFSU1_PUBLIC=1`).
