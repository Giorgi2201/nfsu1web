# NFSU1 Online lobby protocol (reference)

Evidence: HarpyWar/3PriedeZ [nfsuserver](https://github.com/HarpyWar/nfsuserver)
(`nfsuserver.cpp`, `server.cpp`, `objects.cpp`) and PC `Speed.exe` 1.4 format
strings. This is what the browser lobby stand-in in `server/src/online.rs` must
match. U2 Dirtysock articles describe the same 12-byte header shape.

## Transport

| Port | Role |
| --- | --- |
| TCP 10900 | Redirector → `@dir` with lobby `ADDR`/`PORT=10901` |
| TCP 10901 | Lobby (auth, rooms, challenges) |
| TCP 10980 | Reporter (nfsuserver binds; accept thread often disabled) |
| TCP/UDP 10800 | Client reporter / LAN find-server |
| UDP 3658 | Race host P2P (after `+ses`; not lobby TCP) |

Virtual LAN maps `ps2nfs04.ea.com` → `10.77.0.1`.

## Dirtysock frame

12-byte header + payload (nfsuserver `MakeCommand`):

| Offset | Meaning |
| --- | --- |
| 0..3 | Command name (ASCII, e.g. `gcre`, `move`, `+usr`) |
| 4..7 | Error / qualifier (zeros on success; e.g. `room`+`room` → `roomroom`, `gsta`+`nepl` → `gstanepl`) |
| 8..11 | Total length including header (big-endian) |
| 12.. | Params: `KEY=value` fields separated by `0x09`, last terminated `0x00` |

Client bodies often also use `0x0A` between fields. nfsuserver often reads the
first free-form name at **byte 17** (12-byte header + 5).

## Rooms

Global rooms are named `{A-H}.{label}` (`roomIds = "ABCDEFGH"`):

| Prefix | Mode |
| --- | --- |
| A–D | Ranked Circuit / Sprint / Drift / Drag |
| E–H | Unranked Circuit / Sprint / Drift / Drag |

Default label is `LAN` → `A.LAN` … `H.LAN`. The client filters by first letter
for the mode screen. Custom `room` names are whatever the client sends (often
already prefixed).

`+rom` list fields (7): `I` `N` `H` `F=CK` `T=<count>` `L=50` `P=0`.

## Login path (10901)

Typical order: `addr`/`skey` → `acct` → `auth` → `cper`/`pers` → `news` →
`auxi` (car blob at +17) → `sele` → `user` → `+rom` list.

`sele` reply: `GAMES=1 ROOMS=1 USERS=1 MESGS=1 RANKS=0 MORE=1 SLOTS=36`.

## Entering a room

**Client →** `move` with room name at +17.

**Server (RoomClass::AddUser)** → in order:

1. `move` — `IDENT` `NAME` `COUNT` (count *before* add) `FLAGS=C`
2. `+who` — 11 fields (`I` `N` `M` `F` `A` `S` `X` `R` `RI` `RF` `RT`)
3. Broadcast `+usr` (RefreshUser) — `F=H` `P=211` `T=2` …
4. Existing games: each `+agm` (SendInfoToUser)
5. `+usr` for every member (ListToUser)

`S=` is `GetPlayerStat(persona)` (hex CSV) or empty.

**Create room** (`room`): `room` ack → `+who` → AddUser (above) → `+msg` →
broadcast `+rom` (8 fields, `F=CH`) → host `+usr` with `F=HU` `P=223` `T=1`.

## Challenges (Created Games)

Stock server **never** invents a challenge. The PC client builds one after the
FE path:

1. Head-to-Head player list (NAME / CAR / CONNECTION)
2. `FENG_SELECT` → action pop-up → **Send Challenge** → settings overlay
3. Client sends **`gcre`**

`Speed.exe` format string:

```text
NAME=%s ROOM=%s MAXSIZE=%d MINSIZE=2 SYSFLAGS=%d PARAMS=%s
```

`PARAMS` body (≤300): URL-encoded `TRACK=%d\nDIR=%d\nLAPS=%d\nMYIP=%d`
(on the wire: `TRACK%3d1003%0aDIR%3d0%0a…`). Race type is the **room letter**
(A–H); Challenge Settings only picks track/laps/dir. Empty `PARAMS` gets a
room-letter URL-encoded default.

Server parse (nfsuserver): name @+17, then room, max, min, sysflags, params
(positional after fixed key widths / separators).

Then server: `GameClass::AddUser` (`gjoi` to creator) → `gcre` ack (14+ fields)
→ RefreshUser → broadcast `+agm`.

Challenge invite `mesg` (Speed.exe): `PRIV=` `ATTR=` `TEXT=`. `GAME=` and
`PARAMS=` are **inside TEXT**, escaped again by TagFieldSetString. `ATTR` is
a Dirtysock flag string: `E0` for an invite (bits `0x08000020`), `E1` for a
refusal. The `%f` in `PRIV=%s ATTR=%f TEXT=%s` formats flags, not a float.

Forward to the target as `+msg` with `F=<ATTR plus P>` (private), `N=<sender>`
and `T=<original escaped TEXT>`. Keep the escaping intact: the client first
decodes `T`, parses `GAME` and `PARAMS` from it, then decodes `PARAMS` again.
Example wire `T=GAME%3d7%0aPARAMS%3dTRACK%253d1003%250a…`.
Do not echo invites/refusals back to the sender. Ordinary private chat keeps
its sender echo. Forcing `F=EP5` loses the invite bit and displays the control
text as purple chat; top-level `ATTR`/`GAME`/`PARAMS` in `+msg` are not read.

Verified against PC 1.4: sender `0x54ac80`, `+msg` dispatch `0x665c9e`,
frontend handler `0x54be20`; actual emitted TagField parsers were compiled
natively to check the flags and both decoding layers. That does not validate
the complete interactive flow. The user subsequently confirmed challenges work.

Other game cmds: `gjoi` / `gget` / `glea` / `gdel` / `gsta` (or `gstanepl` if
`count < min`). `gsta` success → `StartGame` → per-player `+ses` (adds `SEED`,
`SELF`) + broadcast `+agm`. Race UDP 3658 follows.

`+agm` / `gcre` / `gjoi` core fields: `IDENT` `WHEN` `NAME` `HOST` `PARAMS`
`ROOM` `MAXSIZE` `MINSIZE` `COUNT` `USERFLAGS` `SYSFLAGS` plus
`OPIDn` / `OPPOn` / `ADDRn` per seated player.

## Keepalive

Server sends 12-byte `~png` after ~30s idle; client `~png` resets idle. No
payload reply required.

## What is *not* a lobby API

| Symptom | Cause |
| --- | --- |
| Enter / Next does nothing in room; `EVENT_HANDLER` on HUD | FE / input (`EventHandlerSlotPool` in `Speed.exe`). Action pop-up never runs → **no `gcre`**. Not fixed by extra lobby packets. |
| Empty challenge list | Normal until a client sends `gcre` (or a deliberate server-side seed). |
| Race after `+ses` | UDP 3658 P2P between peers, separate from 10901. |

Language help for the player list: pad to move highlight, **pad right** toggles
Created Games List, **Select** opens the action pop-up for the highlighted
player (`ONLINE_SEND_CHALLENGE`, etc.).

## Implementation (`server/src/online.rs`)

Covered client commands: `@dir`, `addr`/`skey`, `acct`, `auth`, `cper`,
`dper`, `pers`, `news`, `auxi`, `sele`, `user`, `room`, `move`, `mesg`,
`gcre`, `gjoi`, `gget`, `glea`, `gdel`, `gsta`, `snap`, `rank`, `~png`.

Hardcoded (no DB): news text, `GetPlayerStat` CSV, snap top-3 stand-ins,
`rank` → `Unranked` / `TIME=866`.

- Reply frames must be delivered to the **destination VIP** in the LAN header
  (broadcast `+usr` / `+agm` / `+msg` / `+pop` / `+rom`), not only to the
  requesting peer (`lan.rs` `deliver_online_replies`).
- Automated checks: `cargo test --manifest-path server/Cargo.toml`.
- Live command log: server stderr lines `[online] << …`.

**Still client-side:** FE Send Challenge / `EVENT_HANDLER` must emit `gcre`.
**After `+ses`:** race UDP 3658 between peers (not lobby TCP).

NFSU1's Dirtysock NetTick thunk is `0x66e8b0`, not the SPEED2 `0x74b730`.
The runtime wraps it with the upstream monotonic clock, keeping network timers
independent of rendering/loading. The Wasm build retains direct calls to the
thunk so linker wrapping also covers calls within its own shard. Simulation
continues using its existing frame-paced clock. `NFSU2_NETTICK=virtual` restores
the original clock for diagnosis. Car-table compatibility is handled separately
by the local data overlay below.

`runtime/nfsu1_online.c` adds bounded observations around verified PC 1.4 timeout,
quit and cleanup callbacks. `[nfsu1 online]` records caller, cached transport
clock/last-receive, the separate game-level heartbeat age, host heartbeat send
age/gate and session states. Failure callbacks include a short stack trace.
The wrappers preserve the original CPU arguments and decisions; this is
diagnostic instrumentation, not a race compatibility fix.

## Local car-table compatibility

On entering racing, PC 1.4 checks 35 car records (`35 * 0xc90` bytes) with
its CRC routine at `0x5647d0`; expected result is `238562c5`. A mismatch calls
the coordinator abort at `0x43b087` and ultimately sends server quit to
the other player. This happens even if traffic and heartbeats are healthy.

The local install's modified `GlobalB.lzc` has CRC `951b523f`; its stock
`GLOBALB.BUN` has the expected table. Only 26 bytes differ across GOLF, PEUGOT
and LANCER records. `tools/prepare_online_data.py` restores that table into a
copied LZC container, retaining all other bytes and leaving source inputs
untouched. `./build.sh` prepares it and `./start.sh` selects it automatically.
The server validates source/output hashes and changes the data-manifest cache
stamp. The game checksum is unchanged. Actual emitted Wasm rejects the source
table and accepts the overlay. The user confirmed Online races work after the
restoration. Race completion and broader multiplayer coverage remain unverified.
