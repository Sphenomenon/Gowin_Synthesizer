# Optional display metadata context

`display_data_analysis_source.sv` is an opt-in adapter for the v1.1 fields in `DISPLAY_DATA_LAYOUT_V1.md`. It consumes completed physical PCM frames after an atomic CDC into its `clk` domain. It does not change the default profiles, own the audio clock or epoch, add an audio ready signal, or certify hardware operation.

## Identity and input domain

All source-adapter inputs and writer inputs are synchronous to the memory/UI clock. A frame is `{44k1, epoch[31:0], sequence[31:0], error, pcm[31:0]}`; PCM is signed left16/right16, with no change to those samples. A caller must cross the complete tuple together. Independent multibit synchronizers are insufficient. Trust is a level and loss is a pulse in the same destination domain; a dropped final frame must also revoke analysis without relying only on the arrival of a later sequence gap.

`frame_epoch_i` comes unchanged from the unique audio owner. Epoch zero is rejected. The future profile must explicitly select the owner's `RESERVE_ZERO_EPOCH=1`, nonzero seed and skip-zero wrap, together with the matching audio-clock service configuration. Display never adds one, maps zero, or creates a second stream epoch. The owner's default epoch-zero mode is preserved for existing callers.

Rate, epoch, sequence error/gap, observation loss and untrusted input reset the waveform capture/alignment and the complete FFT/XY workspace. The first frame establishing a new context is skipped; only complete fresh windows become ready. A separate nonzero **local cancellation generation** prevents reuse after a loss with the same owner epoch. It is compared at the source/writer boundary and is not serialized as the stream epoch. Receipt-time control/status inputs may differ in sampling time from the physical audio; they are display snapshot metadata, never authoritative parameter copies.

The adapter reuses maintained `feedback_capture` (512 unfiltered mono samples, six-pole trigger, 8192-sample timeout), prepared `feedback_wave_align`, and maintained `output_audio_analysis` (2048 stereo samples, actual Hann FFT and XY). Mono is the existing signed `(left16+right16)<<15` scalar. Spectrum format and log columns remain unchanged; frequency uses the actual tagged rate.

## Producer and writer handshake

An integration controller starts only when `start_ready_o && !writer_busy`. Drive the same accepted start to the adapter and `display_data_writer`; its next-cycle SNAPSHOT sees the newly frozen analysis front and tags. Drive writer `done` back to `export_done_i`, including a rejected/aborted attempt, to release the held wave. The controller must inspect diagnostics: `done` alone is not publication success.

Wire source, waveform and analysis `*_context_valid`, `*_sample_rate`, `*_epoch` and `*_generation` outputs directly to their writer inputs. Wire the adapter's compact read interface, metadata, analysis sequence/skipped/peaks/gain/valid to the writer. The writer selects `METADATA_MINOR=1`, which requires `CONTEXT_ENABLE=1`. The default is `METADATA_MINOR=0, CONTEXT_ENABLE=0`; an explicit `CONTEXT_ENABLE=1` minor0 caller rejects actual 44100 rather than relabeling it.

Writer diagnostics are 1 invalid source/zero epoch, 2 unsupported rate, 3 wave identity mismatch, 4 analysis identity mismatch, 5 context cancellation during RAM export. Rejected and aborted are pulses; unavailable stays set until a successful global commit. An already advertised stalled DDR beat is drained unchanged before an abort completes. The inactive bank is chosen relative to the last successful commit, so failed attempts cannot consume the last published bank. After all RAM data has been exported, the immutable old snapshot may finish with its old context tags.

## Reader and renderer

Every consumer of the selected DDR bank must explicitly select `display_data_reader #(.METADATA_MINOR(1))`. The reader verifies all four descriptor versions and nonzero equal epochs, audio rates, metadata rate/epoch, reserved fields, source-sequence relationships and final seqlock. A working local bank never overwrites the published image; publication flips data and metadata together, including the first enabled synchronous read. Added logical storage is 90,112 bits, with physical allocation/timing still requiring implementation evidence.

On minor1 failure, `done=1, fault=1` returns to idle, preserving `valid`, last published metadata and cache. `incompatible_o` identifies selected-version mismatch. Diagnostic codes are 1 version, 2 global record, 3 initial bank header, 4 descriptor, 5 metadata, 6 final seqlock. Renderer scheduling must require a valid initial image and must not flip the reader's published bank during a raster. Rate/epoch change is reported by `render_context_changed_o`; `render_sample_rate_o` and `render_epoch_o` describe the published image. `render_generation_o` is the DDR commit generation (`frame_sequence<<1`), distinct from the adapter's local cancellation generation.

Minor0 retains one local cache and its historical automatic retry. A selected minor0 reader rejects minor1 at the global header and keeps its existing published local data while retrying. Source identities/sequence and DDR generation continue their existing modulo arithmetic; a read must complete before the relevant counter wraps.

## Compilation and verification

The new adapter requires native `display_data_analysis_source.sv`, native `feedback_capture.v` and native `output_audio_analysis.v`, plus the explicit prepared `output_audio_capture.v`, `audio_analysis_rom.v` and `feedback_wave_align.v`. Compile native `display_data_layout_pkg.svh` before native writer/reader. Never compile prepared and native versions of the same module together. The ABI/address package remains unchanged.

Run the explicit closure with a new output directory:

```sh
python3 projects/138k/push2_workstation/usb_a/sim/display/run_display_metadata_v11.py \
  --project /absolute/prepared/workstation/Prj1 \
  --output /absolute/new/evidence-directory
```

The runner checks the original reference bytes, records every source and prepared-profile hash, renames only a temporary original-writer copy, and refuses drift or new display warnings. It tests default writer cycle/bytes, default reader version rejection, full writer/reader DDR/cache behavior, and real waveform/FFT/XY rate binding. Its input PCM strobes are accelerated functional fixtures; this evidence does not measure physical sample timing, HDMI pixels, P&R or a board. A future profile must explicitly select all producer/consumer versions and add the adapter and CDC sources to its compile manifest. Rollback is selection of the existing minor0 producer/consumer pair with its fixed-48k source contract.
