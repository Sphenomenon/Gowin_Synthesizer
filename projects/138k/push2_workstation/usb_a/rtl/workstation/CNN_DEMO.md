# CNN-DEMO filming configuration

`build.py --cnn-demo` selects an independent custom-carrier candidate. It does
not select or change M, W, BLE, accepted full83, or the resource candidate.

The intended shot is Push song selection from TF, real MP3 decoding/preprocessing and
model E inference, the original single-note Push guidance, and a fresh correct
key advancing the current target with real DAC sound. Start with the historical
TF `travelers.mp3` (historical display label TRAVLER). Historical analysis was
48 kHz; the original 44.1-to-48 kHz analysis resampler remains. The actual file
rate/hash must be recorded from the selected TF file. No song score or MIDI is
built into this configuration. The earlier WAV-only D4/D5 candidates do not
satisfy this MP3 input and are retired from filming delivery.

## Source and board identity

The CNN lineage is the accepted 8bc80e9 full83 snapshot, plus the **six pinned
historical timing85 files**. The model remains CRC32 `AF01A61B`, 104478 bytes.
The small checked diagnostic CDC transform in `tools/workstation_cnn_cdc.py`
synchronizes DDR observation levels; it does not change model arithmetic.
The preparation manifest records both baselines, every prepared input hash,
compiled/retired sources, the transform, and exact constraint retirements.
Frozen baselines and historical acceptance evidence are never edited.

The carrier pin authority remains `boards/custom_138k/pinout.json`, including
the locked `Netlist_my_138k_2026-10-21.tel` and amplifier netlist. CNN-DEMO alone
corrects the inherited TF contact interpretation through
`boards/custom_138k/cnn_demo_tf_spi.json`: U16 DAT0.7→V15 (MISO), CMD.3→Y16
(MOSI), CLK.5→W15 (SCK), DAT3.2→AB15 (CS_n). The original U16 symbol and
carrier hashes, endpoint/ball resolution and exact old/new constraints are
recorded. The inherited plan had assigned DAT2/DAT1/DAT0/CLK to those four
signals; D6's user-observed empty list is a failed hardware result. The shared
native plan and frozen M/W/BLE inputs remain unchanged by this demo correction.
This is **not**
the official carrier's bitstream or pins. Native USB Host, TF/MP3, DDR BIST and
bounded TF/CNN requests, CQT/CNN/BSRAM caches/Viterbi, original Push interaction,
fixed basic instrument, final output router and native FPC DAC remain.
HDMI/LCD, AE350 graphics, framebuffer, visual FFT, effects, vector engines,
BLE, recording/download and rate switching are absent from the selected netlist.
The existing owning subsystem files remain available for other configurations.

## Prepare and validate

Use a new output directory for each candidate:

```sh
python3 projects/138k/push2_workstation/usb_a/build.py --cnn-demo \
  --netlist-dir /absolute/path/to/locked-netlists \
  --custom-board-output /absolute/path/to/new-candidate \
  --riscv-prefix /absolute/path/to/riscv-none-elf
```

Preparation does not run synthesis or program hardware. Run the generated
`scripts/custom_board_synthesis.tcl` with Gowin in `workstation/Prj1`.
`tools.workstation_cnn_demo.prepare_physical` consumes the full hash-checked
prepared closure and actual synthesis hierarchy, checks retained/retired
features and visible SDC selectors, then creates a fresh physical experiment
using the existing implementation functions and an explicit new UserCode.
It preserves clock budgets and the encrypted DDR 3.500 ns minimum-delay policy.
A prior routed DDR boundary may supply checked placement structure; its timing
or hardware acceptance is never inherited.

Run `tools.workstation_cnn_demo_audit.audit(candidate, physical, new_output)`
after P&R. This profile-specific gate rechecks the sealed source/physical
inputs, all seven retained clock requirements, all three actual PLL tuples and
their unchanged 10 ns control budgets, official DDR sequence/configuration
proofs, stopped-clock PHY resets, fixed-reference DAC pins, expanded SDC members,
active constraints, original song/PCM/score/playlist CDC, additional CNN/TF
queues, status/diagnostic levels and native USB/input receivers. The original
complete-workstation auditor keeps its feature requirements. The new gate also
rejects actual-netlist request, PLL-reset and DAC-reference mutations.

The predecessor with manual UART loading is `D21102D4`, source candidate
`ad205f0df5065543`. Its routed BSRAM is 145/340; setup/hold/recovery/removal
worst slacks are +0.017/+0.140/+1.096/+0.287 ns. These are offline physical
results. The dated physical report records exact hashes and remaining hardware
acceptance; this paragraph does not establish that the board runs this image.

The dedicated `sim/cnn_demo/run_audio.py` checks continuous 48 kHz scheduling,
actual reference serialization to FPC DAC, PANIC and detach. The inference
runner consumes selected unmodified algorithm sources and parses WAV bytes
through CQT, all six CNN layers, Viterbi and the original score guide. Its
optional generated audio is **test input only**. The automatic model loader
uses behavioural DDR, so it does not establish physical DDR or TF acceptance.
Viterbi's full 172-frame math/backpointer oracle and original Push wrong-key,
held-key and fresh-correct-key regressions remain separate checks.

## Startup and filming

The current CNN-DEMO embeds the same 104478-byte model E in configuration
BSRAM ROM. It automatically copies all 52239 words into the existing DDR model
allocation and verifies a complete DDR readback CRC32 AF01A61B before reporting
`model_status=E`. No model UART cable or host upload is required. Status F means
CRC failure or five seconds without progress on a DDR request/response; guidance
remains unavailable. Audio scheduling continues independently. Song reselection
clears analysis/guidance and retains the verified model. Configuration reload
automatically reloads it. This uses no model Flash writes or Flash boot logic.

The demo memory owner masks both request-valid and request-ready until DDR
calibration and BIST complete successfully. Masking valid alone acknowledges
requests into an empty slot that never receives them: the D7 negative regression
loses 138 model writes and ends with CRC 929A0F8F. The integrated
`sim/cnn_demo/run_boot_transport.py` runs the actual request/reply CDC FIFOs,
DDR16 adapter, client slots, arbiter and BIST against behavioral native DDR.
The corrected path writes and reads all 52239 words and obtains AF01A61B;
the old D7 source remains an explicit negative control. This is transport
simulation evidence, not physical model readiness or song acceptance.

The demo preparation selects maintained `workstation_cnn_demo_model_loader.sv`
through two hash/anchor-checked loader references in the locked timing85 PCM
pipeline. It disables the historical UART loader and receiver in this compiler
input only; arithmetic and the original DDR, score and guidance interfaces stay
unchanged. The manifest records the exact replacement and source hashes. Other
profiles retain their original model startup policy.

`sim/cnn_demo/tb_cnn_demo_model_boot.sv` checks the complete real model under
backpressure, readback corruption, timeout and reset. The joined inference test
now starts with empty behavioural DDR and real automatic ROM boot, without a
forced model-ready state. Song bytes begin after model readiness, matching the
playback service's existing readiness fence. Neither test establishes physical
DDR, TF, Push or DAC acceptance. The routed gate reconstructs all 52239 model
words from the 64 physical ROM planes and compares their bytes and CRC with E.

Only CNN-DEMO defaults `TF_AUDIO_KIND=1`, so the existing FAT root directory
reader selects `MP3` and the existing `tf_audio_decoder_ip` elaborates the Tang
MP3 branch. Decoder, PCM drain/FIFO, synchronous tables and the required MP3
sources are compiler inputs. They retain the accepted full83 bytes, including
GPL notices; no substitute decoder or converted song is used on the board.
Other profiles retain their existing format defaults.

Use the existing Push Play/list, Left/Right browse, Select song and pad guidance
interaction. The song screen reports model loading/failure, TF failure,
analysis, available guidance and final completion from actual owner state and
actual note counts. A failed source clears the guidance queue. Selecting a new
song retains the existing flush/restart policy and clears the old target.
Analysis does not stop the audio sample schedule. TF playback retains the
original media controls; the dry basic instrument sounds actual pressed notes.
An empty list displays TF scanning or a completed scan with no MP3 in the root,
plus actual filesystem/card FSM values. These statuses use the existing coherent
Push mailbox; the audio schedule never waits for feedback.

New routed resource, PLL, full STA and CDC gates must pass before SRAM use.
SRAM testing is user-authorized for this task and must run under the shared
serial JTAG lock after rereading the board identity. **Do not write Flash.**
Use the currently verified W/M SRAM image as the explicit rollback; record its
actual hash and board identity before replacement. Physical Push selection,
TRAVLER inference, guidance, correct key, sound and reselection cleanup remain
required filming acceptance and cannot be replaced by simulation.
