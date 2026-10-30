# Default-off BLE raw DDR adaptation

`tools/workstation_bluetooth_ddr.py` adapts staged first-party copies of the
existing 25K BLE business source for the 138K workstation. It does not edit 25K,
vendor, baseline, accepted-profile, or historical inputs, select a build profile,
or perform board operations. The native top and owner-8 composition remain the
build profile's responsibility.

Run the existing `workstation_bluetooth.prepare` and copy the native wrapper
before calling `prepare(usb_a_root, stage, enabled=True)`. The stage is the
workstation `Prj1` directory. Disabled preparation reads no source bytes and
modifies no file. Enabled preparation checks the pinned original source closure,
the normal generated GATT input, the reviewed raw store and its contract, every
replacement's exact anchor count, the complete generated output identities, and
the protected encoder/transfer-bank/wire-byte regions before publishing any
transformed source. Missing or changed inputs fail; there is no historical-input
fallback. Re-run `verify_prepared(usb_a_root, stage, evidence)` immediately before
profile publication. It checks fixed expected output hashes as well as the
source closure, so editing both a stage file and its evidence cannot authorize
changed RTL. Both APIs return explicit nondeployment evidence.

The five layers remain `workstation_bluetooth -> bt_verilog_core -> bt_gatt ->
ble_protocol_command -> ble_recording`. Every layer adds
`EXTERNAL_RAW_STORE=0` and `RAW_DRAIN_TIMEOUT_CYCLES=0`; default behavior remains
RAM storage with its existing 64-cycle seal timeout. The native DDR composition
must explicitly set `EXTERNAL_RAW_STORE=1` and
`RAW_DRAIN_TIMEOUT_CYCLES=5_000_000` (100 ms at the 50 MHz control clock), enable
external PCM and the existing external seal protocol, and keep capacity at or
below 16,384 frames. Invalid opt-in combinations fail elaboration. This helper
locks the raw store whose native command and read timeout defaults are each
10,000 memory clock cycles; neither readiness nor a local slot submission is
native DDR acceptance.

The BLE recorder remains the sole owner of boot/object/transfer/task identities,
recording states, the committed frame prefix, CRC, command replay/ACK policy,
codec choice and wire bytes. The raw store owns bytes and its fenced storage
lifetime only; its full contract is
[`WORKSTATION_BLE_RAW_DDR_STORE.md`](../memory/WORKSTATION_BLE_RAW_DDR_STORE.md).
The 138K recording window belongs to the common DDR address authority and must be
assigned by native integration. This adaptation does not allocate a second DDR
window or introduce another protocol.

START allocates the existing object and task only on a real raw START fire.
Capture can begin immediately at that fire; `start_done` is not an audio gate.
The exact existing stereo pair goes to storage without another swap. A capture
is an event: lack of credit fails the object and initiates closure, never pauses
or retries the audio schedule. All CRC bytes of an accepted frame finish before
closure. STOP, capacity and the local seal handshake all hold the business
object in its closing state until native drain and accepted/committed counts
match the recorder's prefix; only then can READY and a successful STOP task
appear. Source loss, count disagreement, storage failure and timeout produce a
failed object. Timeout is terminal failure; later native drain exists solely to
release the cleanup fence and cannot promote the object back to READY.

CLEAR waits for raw acceptance and true completion before clearing business
identity. An accepted CLEAR continues across BLE disconnect or enable loss.
START/CLEAR mutation cannot cross the existing seal hold. The drain budget also
bounds outstanding raw commands/fetches. A failed command preserves the existing
object identity for explicit cleanup; transport channel quarantine still
requires the common reset of storage, native mux and ledger. An audio path never
waits for these transactions.

Each READ/replay first waits for raw fetch readiness, publishes exactly its own
byte descriptor, then enters a distinct WAIT state. Only a completion observed
in that WAIT state with a valid cache grants endpoint cache ownership. The
existing PREP/read/CRC/codec stages retain their original one-clock sample-read
latency. The raw store's `sample_word` is used directly, with no added register.
The existing four transfer banks, Rice encoder and wire message function remain
byte-identical and are checked independently.

Disconnect, disable, transfer consumption, cancellation, a new fetch, CLEAR and
fault withdraw the endpoint's cache reference. Disconnect/cancel does not CLEAR
the raw object: old native reads are allowed to drain internally, retaining
READY for reconnect/resume. A new descriptor waits for its own fetch fire and
completion; old cache validity or a late completion cannot authorize it. A
replayed read must still identify the same READY object.

Offline verification:

```
python3 sim/usb2/run_workstation_ble_raw_ddr.py --output /absolute/new/output
```

The runner uses actual BLE recorder/codec, raw store, async FIFO, native bridge,
framed protocol/request cache and the staged five-layer chain. Its DDR model
separates slot submission, native acceptance and read return. It checks both
asynchronous and 100 MHz memory clocks; RAW, Rice and second-order transfer bytes
against the original RAM recorder; maximum 8,112-byte descriptors; all partial
last beats; STOP CRC phases; disconnect/stale fetch; overflow; timeout with late
cleanup; and CLEAR with a disconnected observer. It includes behavioral mutants
and source/output/evidence tamper controls, and verifies that source inputs are
unchanged during the run. The simulated endpoint budget is shortened to 50,000
control cycles; production policy remains 5,000,000. Protocol/chain tests force
only link state and, for the chain, command injection. Physical RAM packing,
mapped reset/CDC, routed timing, synthesis, P&R, board acceptance, SRAM and Flash
deployment require separate evidence and remain unclaimed by this helper.

Exit criterion for the temporary staged adaptation: move these stable raw ports
and recorder lifetime branches into versioned 138K-owned business sources with
an explicit upstream-sharing decision, preserve the protected bytes/contracts,
and retire this overlay together with its hash/anchor locks. Do not silently
change source policy for accepted profiles in the meantime.
