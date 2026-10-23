# Synthetic ABI fixture

`guest_abi.mjs` hand-encodes an authored Wasm module with arithmetic functions
and typed indirect dispatch. It tests the web runtime's CPU-pointer calling
convention, guest memory access, stack cleanup and bounds traps:

```sh
node --test tests/guest_abi.test.mjs
```

It contains no game code and does not validate game execution, rendering,
audio or browser scheduling. The catalog adapter and real-lifter checks are
in `tools/catalog_bridge.py` and `tools/run_lifter_smoke.py`; see
[testing](../docs/testing.md) and [build setup](../docs/building.md).
