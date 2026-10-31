# Dual-138K M/W HDMI parameter observation — 2026-10-31

This is source and offline integration evidence. It is not a routed candidate,
SRAM/Flash deployment, physical Bluetooth/I2S/HDMI acceptance, or dual-board
concurrency acceptance. The new DEMO profiles must bind these changed inputs;
accepted/default profile input locks must continue to reject drift.

## Behavior and ownership

`workstation_parameters` remains the sole owner of committed parameters. Its
read-only effect observation is passed through the native event/render/runtime
composition to the existing compute-domain service. New read-only APB offset
`0x1b8` is `{23'd0, effect_master, effect_count[1:0], effect_order[5:0]}`. Stage IDs
are Delay=0, Chorus=1, Reverb=2, bypass=3, least significant stage first. Writes
are rejected. Existing state/pitch/options/18-bit event bytes are unchanged;
UI brackets the observations with existing `0x1a0` applied-event reads.

W renders D BLUETOOTH and the actual Crush/Drive/Send depths from committed
`control_options[20:0]`, actual master volume and route, effective effect mask,
and ordered effect stages. Its HDMI local synth keyboard/mode controls are
inactive; old short-snapshot request token polling is retained only by M.
M renders bounded mode/profile/route labels, actual master volume, effect
order, and physical clock state. Mode3 and unknown profile values cannot index
outside label arrays. UI startup reads actual feedback before drawing pages.

Both roles consume `f8030000` clock service `ACTUAL` (`0x2c`) and its latched
`SNAPSHOT_EPOCH` (`0x30`) twice. Torn rate/epoch observations show CLOCK WAIT;
invalid/busy/fault states are not presented as a valid rate. Source media format
is never used to guess the physical I2S clock. Two-row cooperative rendering and
all live analysis rows160..831 remain intact.

The W-only `.SUSTAINED_VERIFIED(D_ONLY_ENABLE)` PCM selection was enabled at the
parent's request after separate long drift regression. This is an offline gate;
it does not claim physical source-rate, drift, or service-cycle acceptance.
The unused MIDI counter `destination_gray` output is explicitly unconnected.

## Verification

| Check | Result | Local evidence |
| --- | --- | --- |
| Actual M/W `ui_main` snapshots and render pixels, native + ASAN/UBSAN | M985 checks; W3513 checks including2520 independent digit pixels; clock tear/fault, PANIC, mode/profile bounds;672 analysis rows preserved | `/tmp/dual138k-ui-truth-v1/verification.json` |
| Full renderer versus bounded slices and patches, native + ASAN/UBSAN | 78 comparisons per build,12 models,15 row-boundary ranges | `/tmp/dual138k-ui-slices-v2/verification.json` |
| Actual bounded M UI service + real UI APB replay | 36052 checks/2889 steps per build;7252 APB reads/5 frame commits;12 behavioral mutations rejected | `/tmp/dual138k-ui-service-v2/verification.json` |
| Default controlled service reverse provenance + APB | 1112 transactions;new effect-state read/readonly reject/old fields preserved | `/tmp/dual138k-ui-effect-services-v2/verification.json` |
| D-only DSP and retirement | 2292 real native effect frames;17 exact valid/ready events;committed order/count/master;27 retired reads +27 writes rejected;FFT128 bins | `/tmp/dual138k-ui-d-feedback-v3/verification.json` |
| Complete native runtime integration with new effect APB |1078 serialized/observed frames;977 nonzero;1077 display tuples;384 FFT bins;1082 APB transactions;effect truth at48k/44.1k and CPU-only reset;warning gate passed | `/tmp/dual138k-ui-runtime-feedback-v2/verification.json` |
| Default maintained UI firmware |15472-byte image fits16KiB ROM | `/tmp/dual138k-ui-default-fw-v1/build_metadata.json` |
| Actual W firmware and callback closure |93600-byte BIN;ILM52064;DLM static7616;peak stack2176/16384;166 JALR sites;4 callback mutations rejected | `/tmp/dual138k-ui-worker-fw-v1/runtime_callgraph_verification.json` |

The complete runtime test used a private temporary stage with versioned control
sources copied over the prepared M support tree; it did not mutate the prepared
M candidate. The D fixture's valid/ready driver was corrected to consume exactly
one edge, which makes non-idempotent append/master-toggle checks meaningful.
No warning suppression, clock relaxation, fake PCM source, UI test image, or
Flash write was introduced into either demo.

Historical imported provenance and frozen baseline bytes are retained. Service
changes append exact reversible before/after records. Firmware build metadata
records maintained source hashes and changes from historical imports.

## Source identities

| Maintained input | SHA-256 |
| --- | --- |
| `firmware/ae350/ui_main.c` | `9283f9af5b0222ce5c3485a74fa4cb76ef7a5748468d874622394b1d4905084c` |
| `firmware/ae350/ui_model.h` | `c8984df950ec06ccd349ca5783f473a102f6c19e6cc7eb9d16c4372527afb450` |
| `firmware/ae350/ui_render.c` | `7a4dab40db09be456d6be7ab198ef57b38f03e68b2cf736328a60f641c753007` |
| `rtl/control/workstation_parameters.sv` | `06fbc08f162bf205520f3d41384c1c5a39e6fc746841773725d26f97edc5be51` |
| `rtl/audio/gw138k_event_workstation.sv` | `64092368b4d0e03fc08beaa4a1d437dd7989dfd2530aa40032363aae3f2d2983` |
| `rtl/audio/workstation_audio_render_service.sv` | `a9b8138e8b40a85a98ab1b3ed769c99ff9ee342a2cd168cb40877bb2383cc979` |
| `rtl/workstation/workstation_runtime_audio.sv` | `85d8bebfa2660e17f79ce522785bdd148b4d69e4183a27f17fd31ff9176b292c` |
| `rtl/workstation/workstation_runtime_controlled.sv` | `70db34344a24bab3270e3c91d7a2a553590c4e0b4432f744252db23e23cfb87a` |
| `rtl/services/workstation_controlled_services.sv` | `d305e341dc12a05f2252991af7f31f94be2735ca53a6251974c227d6c9a31ce2` |
