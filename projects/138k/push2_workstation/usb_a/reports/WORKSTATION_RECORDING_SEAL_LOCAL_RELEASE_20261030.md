# Recording seal bridge local release and ready publisher

The R00 normal-seal channel previously released all functional state directly
from common reset and sampled a combinational memory ready/pending/hold expression
in the control domain. It now has separate two-FF local release chains and one
registered memory-domain ready publisher. Only that publisher Q crosses the ready
synchronizer. Common reset still asserts asynchronously in both domains; a
stopped domain remains reset until its own clock releases it.

Accepted seal requests retain a registered source hold until the real backend
terminal, even if the caller withdraws hold or its CPU observer resets. Same-edge
request/hold acceptance remains supported. Failure wins simultaneous done/failed,
the terminal payload stays stable across its token crossing, and the returned
failure detail persists until the next acceptance/common reset. Readiness lost
between observation and backend delivery still returns failure 11 without a
backend request. CPU reset is absent from this bridge; common reset cancels only
its reset-scoped channel. Object lifetime remains with the recording service.

The [source contract](../rtl/services/RECORDING_SEAL_BRIDGE_CONTRACT.md) gives the
release, handshake, hold and rearm rules. The source is based on `f2f11fc4`; the
bridge SHA-256 is `1512a14e01725845350a76d2ea78e521f0a99bc362015f8cf87d3db8d61883f4`.
All four development profile locks record the changed source/real-runtime test
inputs and new regression/contract files. These source locks do not create a
prepared or synthesized candidate. Accepted/frozen inputs are unchanged.

Offline checks passed:

- 11 seal-bridge scenarios, including seven reset phases, each clock stopped
  across common reset, exact receiving-edge release, simultaneous request/hold,
  source withdrawal, readiness race, an unregistered ready pulse, stale terminal,
  error retention, repeated pending requests and post-reset token isolation.
- 12 targeted negative variants rejected: raw and one-stage releases in both
  domains, raw combinational ready crossing, caller-controlled pending hold,
  same-edge request loss, fabricated early result, dropped failure, transient
  failure detail, raw failure payload and stale delivery terminal acceptance.
- The original 13 real recording-runtime cases and five existing negative
  variants, plus a new case that resets the CPU observer and withdraws hold while
  an actual owner8 DDR drain remains stalled. The bridge retains its fence and
  later reports the real immutable READY object with the exact recorded bytes.
- The new runtime case fails with the original `2323b54f...` bridge bytes at
  `observer reset abandoned pending seal or its hold`. This old-source comparison
  uses a separate simulation output and preserves the product source.
- Media preparation's nine scenarios/two negative variants, strict Verilator
  lint with zero warnings, 17 accepted-source tests and all four source-lock
  checks. Recording-profile regression passes seven tests with two existing
  opt-in prepare prerequisites skipped; those skips are not prepare validation.

Exact source/test hashes, results, old-source negative identity and evidence paths
are in [the machine record](workstation_task_20261030/recording_seal_local_release_source.json).
Reproduce the targeted checks with `python3 sim/test_workstation_recording_seal_bridge.py`
and `python3 sim/services/run_workstation_recording_runtime.py --output <new-directory>`
from `usb_a/`.

No synthesis, mapped CDC/reset inventory, P&R, routed payload/setup/hold or reset
recovery/removal check was performed for this source. Complete recording CDC,
whole-workstation functional/physical and board acceptance remain false. There
is no bitstream, SRAM operation or Flash write. Old candidate results do not
transfer; the parent integration must create a new prepare/synthesis identity.
Rollback is the previous bridge and its matching development source locks,
not a claim that the previously audited physical candidate contains this fix.
