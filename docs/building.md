# Build and run

## You only do this

1. **Copy your whole PC install** into `work/data/`  
   Include `Speed.exe` and the usual folders (`Cars`, `FrontEnd`, `Global`,
   `Tracks`, `Languages`, `fx`, `Sound`, `Movies`, …).

   The exe must be Underground **1.4**  
   (`SHA-256 c0fad450912952f53809a54690d235aa8b4e25b9f46650693c7cbee1b4c074b7`).

2. **Build and play**

   ```sh
   ./build.sh
   ./start.sh        # → http://127.0.0.1:8765/
   ```

No second copy of the exe, no symlink. `./build.sh` uses
`work/data/Speed.exe` from that install. It also fetches the WASI SDK, Python
analysis deps, and upstream sources under `work/` when they are missing.

### Already prepared workspace

```sh
./build.sh
./start.sh
```

### OS packages once

Python 3.10+, Node 20+, Rust (`rustup`), curl, tar.

---

## Optional detail

Settings / HD fonts: [settings.md](settings.md).  
Checks: [testing.md](testing.md).  
`J=8 ./build.sh` for more compile jobs. Keep `work/` / `gen/` / game files out
of git.

The build also checks `GlobalB.lzc`'s car table against PC 1.4's Online
checksum. If modified, it restores only that table from the install's verified
stock `GLOBALB.BUN` into `work/mods/online-data/`. Original inputs remain
unchanged. `./start.sh` automatically selects this prepared overlay; the
server changes its manifest cache stamp so reloading clients fetches it.
