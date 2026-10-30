# A07 optional native display metadata v1.1 — 2026-10-30

The maintained display writer/reader now support explicit `METADATA_MINOR=1`; their defaults remain minor0. The optional `display_data_analysis_source.sv` binds actual 512-point unfiltered waveform and 2048-point stereo FFT/XY results to the unique audio owner's nonzero opaque epoch and actual 48000/44100 rate. It flushes complete observation workspaces on context loss, including loss with an unchanged owner epoch. Display never remaps epoch zero. The producer/consumer integration contract is `rtl/display_data/DISPLAY_METADATA_CONTEXT.md`; the DDR ABI remains `DISPLAY_DATA_LAYOUT_V1.md`, with no address/package change.

The writer checks source/wave/analysis identity and local cancellation generation before exporting. A context break during RAM acquisition drains an already advertised stalled write unchanged, then aborts publication. Failed attempts retry the inactive side relative to the last successful global commit. Once all source RAM elements have been exported, the sealed packet may finish with its old tags. Minor1 readers use a separate local working bank and publish cache plus tags only after full descriptor, metadata and final seqlock validation. Failures return done/fault while preserving the entire previous local image. Added logical cache storage is 90,112 bits; no physical BSRAM count is claimed.

Parent independently reran the complete runner in `display-metadata-v11-parent-final`; all compatibility, cache, cancellation and actual-rate FFT checks passed. Its exact inputs, logs and metrics are recorded under `parent_independent_verification` in the machine evidence.

Reproducible validation:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/display/run_display_metadata_v11.py \
  --project /Users/sphenicidition/.cache/gw138k-task-20261030/clean-rev2-profile-candidate/workstation/Prj1 \
  --output /tmp/display-metadata-v11-20261030-v1
python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py
```

| Check | Result |
|---|---|
| Original byte-pinned minor0 writer vs current defaults | PASS, 615,641 cycles compared, all request/control bytes, 1,098 accepted beats, deterministic and long stalls |
| Context-aware minor0 producer / default reader | PASS, actual 44100 rejected; unselected minor1 header rejected with last local image retained |
| Existing delayed-response/default-reader regression | PASS, descriptor/length/version, final-header retry, coherent caches |
| Actual minor1 writer→DDR→reader | PASS, 12 full cache oracles, 2,198 writes, 6 commits, 3,712 reads, 5 pre-export rejections, 1 stalled export abort, 6 first synchronous publish reads |
| Context and corruption coverage | PASS, 48→44.1→48, all descriptor versions/epochs, zero epoch, mixed local generation, late metadata/reserved bits, final seqlock, slow reader bank reuse, sealed old snapshot and reset |
| Real PCM→wave/2048 stereo FFT/XY→DDR→reader | PASS, 3 fresh publications, 1,536 waveform samples, 196,608 independently checked XY pixels and 1,536 transported log columns; FFT bin32/64 peaks |
| Frequency from reader's actual rate | 48k: 750/1500 Hz; 44.1k: 689.0625/1378.125 Hz |
| Actual producer cancellation | PASS, context switch during active FFT/export, premature start rejected, same-epoch loss flush, untrusted source blocked |
| Verilator | Zero owned implementation/fixture warnings apart from missing timescales; no UNOPTFLAT. Existing maintained-analysis warnings are recorded in JSON. |
| Accepted input boundary | PASS, 10 tests |

Evidence identity: `native-display-metadata-v11-offline-v1-21f343cc7e281403`. Source-set SHA-256: `21f343cc7e281403a693724cffb5c0422d48c8dfe2605ba3f55a7f2b72b07127`. Full inputs, compile/run arguments, pinned original writer/capture/alignment/ROM hashes, prepared profile identity and metrics are preserved in `reports/workstation_task_20261030/display_metadata_v11_native.json` and the new temporary evidence directory. The runner refuses reference drift, source changes during verification and new display warnings. Prepared/frozen inputs were read only; the compatibility reference was renamed only inside the output directory.

This phase changes no top/profile selection and creates no bitstream. The functional source feeds PCM packets at an accelerated strobe interval; it does not measure physical I2S sample timing. P&R, physical memory allocation, pixel/HDMI verification, hardware acceptance, SRAM and Flash deployment remain separate. A future integration must explicitly select all producer/consumer versions, preserve atomic frame CDC, gate new raster publication on current source context, and require the owner's nonzero-epoch policy. Rollback selects the existing minor0 producer/consumer pair with its fixed-48k source contract; no accepted build identity is reused.
