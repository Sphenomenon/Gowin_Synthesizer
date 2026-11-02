# CNN-DEMO filming configuration

`build.py --cnn-demo` selects an independent custom-carrier candidate. It does
not select or change M, W, BLE, accepted full83, or the resource candidate.

The intended shot is Push song selection from TF, real WAV preprocessing and
model E inference, the original single-note Push guidance, and a fresh correct
key advancing the current target with real DAC sound. Start with the historical
TRAVLER PCM WAV at 48 kHz. No song score or MIDI is built into this configuration.

## Source and board identity

The CNN lineage is the accepted 8bc80e9 full83 snapshot, plus the **six pinned
historical timing85 files**. The model remains CRC32 `AF01A61B`, 104478 bytes.
The small checked diagnostic CDC transform in `tools/workstation_cnn_cdc.py`
synchronizes DDR observation levels; it does not change model arithmetic.
The preparation manifest records both baselines, every prepared input hash,
compiled/retired sources, the transform, and exact constraint retirements.
Frozen baselines and historical acceptance evidence are never edited.

The carrier pin authority remains `boards/custom_138k/pinout.json`, including
the locked `Netlist_my_138k_2026-10-21.tel` and amplifier netlist. This is **not**
the official carrier's bitstream or pins. Native USB Host, TF/WAV, DDR BIST and
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

The dedicated `sim/cnn_demo/run_audio.py` checks continuous 48 kHz scheduling,
actual reference serialization to FPC DAC, PANIC and detach. The inference
runner consumes selected unmodified algorithm sources and parses WAV bytes
through CQT, all six CNN layers, Viterbi and the original score guide. Its
optional generated audio is **test input only**. It preloads model bytes into
behavioural DDR, so it does not establish UART upload or physical TF acceptance.
Viterbi's full 172-frame math/backpointer oracle and original Push wrong-key,
held-key and fresh-correct-key regressions remain separate checks.

## Startup and filming

The current historical path requires an explicit BPN1 UART model upload to DDR;
it has no model Flash boot. Use the existing `tools/upload_cnn_ddr_uart.py`
with the actual serial port. `model_status=E` is valid only after DDR readback
CRC verification. The performance decoder does not consume the model UART.

Use the existing Push Play/list, Left/Right browse, Select song and pad guidance
interaction. The song screen reports model loading/failure, TF failure,
analysis, available guidance and final completion from actual owner state and
actual note counts. A failed source clears the guidance queue. Selecting a new
song retains the existing flush/restart policy and clears the old target.
Analysis does not stop the audio sample schedule. TF playback retains the
original media controls; the dry basic instrument sounds actual pressed notes.

New routed resource, PLL, full STA and CDC gates must pass before SRAM use.
SRAM testing is user-authorized for this task and must run under the shared
serial JTAG lock after rereading the board identity. **Do not write Flash.**
Use the currently verified W/M SRAM image as the explicit rollback; record its
actual hash and board identity before replacement. Physical Push selection,
TRAVLER inference, guidance, correct key, sound and reselection cleanup remain
required filming acceptance and cannot be replaced by simulation.
