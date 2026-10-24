# Synthetic ABI fixture

`guest_abi.mjs` hand-encodes an authored Wasm module with arithmetic functions
and typed indirect dispatch. It tests the web runtime's CPU-pointer calling
convention, guest memory access, stack cleanup and bounds traps:

It contains no game code and does not validate game execution, rendering,
audio or browser scheduling. Build setup is documented in
[the build guide](../docs/building.md).
