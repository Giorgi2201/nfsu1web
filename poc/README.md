# Proof of concept

## Catalog reuse

`tools/catalog_bridge.py` accepts the JSON shape written by PC NFSU1's
`scripts/run_lift.py`. It preserves function entries, basic-block half-open
ranges, successor addresses, call targets, and thunk/entry distinctions.
It reports call targets absent from the catalog rather than discovering them.
Absence can mean an import, another module, or an unresolved function.

`attach_catalog(lifter, catalog)` replaces the web lifter's `discover(entry)`
with exact-range instruction decoding. The existing web lifter supplies the
instruction semantics and C emitter. This illustrates reuse of both entry
discovery and block boundaries, beyond passing all entries as fresh seeds.

This is a baseline adapter. It clears jump-table merging state, and the optional
smoke mode clears the relevant whole-program/local-register/inlining environment
overrides. Saved successors, exit markers, jump targets, thunk markers and entry
kinds remain metadata: `attach_catalog()` does not consume them to generate
control flow. Upstream instruction emission still determines branch behavior.
The real-game emitter additionally enables typed tail-routing nodes for existing
catalog entries; it preserves independently decoded overlapping ranges and
rejects missing fallthroughs instead of guessing new code.
The metadata-only converter does not emit shards, import/function tables,
overrides, profiles or build stamps, and does not verify PE identity.
The separate `tools/lift_catalog.py` driver now supplies profile-bound emission,
import metadata and full-pass diagnostics; see [current progress](../docs/progress.md).
Production integration must reject traps, truncated branches and unknown
targets; existing catalogs may need targeted corrections for tail entries.

The dependency-free tests use a fake decoder to verify range handling and
that the prior discovery method is never invoked. They do **not** validate
Capstone or upstream C emission. A separate focused check now exercises the real
emitter: `tools/run_lifter_smoke.py` lifts arithmetic and a three-block conditional,
compiles the resulting synthetic C against the upstream CPU header, and runs it
natively. See [toolchain details](../docs/toolchain.md).

## WebAssembly ABI

`guest_abi.mjs` hand-encodes an original Wasm module with two arithmetic
functions and typed indirect dispatch. Functions receive a CPU pointer;
arguments and return slots occupy guest memory. The CPU fixture uses only
the leading `eax`, `esp`, and `eip` offsets from the web runtime's public header.
It is not a conversion of the PC global-register state.

Tests execute this module in Node's Wasm engine against imported shared linear
memory. They cover unaligned guest reads, uint32 wraparound, cdecl/stdcall stack
cleanup, preserved ECX, separate CPU pointers, unknown table indices and actual
linear-memory bounds traps. The fixture reserves only two small guest stacks
and CPU areas; it does not allocate the production guest arena.

Neither experiment validates browser hosting, worker scheduling, tail calls,
exception handling, graphics, audio, PE loading or game execution. In particular,
Wasm bounds checks
alone do not enforce separation of guest and runtime regions inside one memory.

## Recorded validation

On 2026-10-21, Python's unittest runner passed 5 tests and Node.js v25.9.0 passed
5 tests. The subsequent real upstream emission/native compilation smoke also
passed arithmetic, uint32 wraparound, both conditional paths, EAX/ESP/EIP results
and ECX preservation. Its catalog attachment replaces discovery; no function
search is performed. Native generated-C success does not establish Wasm compiler
or browser compatibility. All instruction bytes and Wasm bodies are original
synthetic fixtures. No game binary, game asset, real catalog or game-derived
generated C was downloaded or committed.
