# Clock monitor reference

`workstation_audio_clock_monitor_pre_m9.sv` is the exact maintained monitor from commit `2e273da` before the opposite-edge release change. Its SHA256 is `1d073cbf98ff683603f36ae521fcc5f62bfc6920526ff442e184c02466519d15`. It is simulation-only, never a production source. The runner pins its bytes, renames only its module in a temporary output, and compares every public output against the maintained implementation. The old implementation also acts as the targeted rising-edge margin negative control.

`d_process_before_exact_mask.svh` contains the actual W9b consumed D function
from module SHA256 `238d1274e1ad5d724632607374f08a8f03a8fe9d4df26c69613f7dbb26de2646`.
Only its function name is changed for simultaneous comparison. Restoring the
name gives function SHA256 `11247717c12f218bd37fe96d399cc6a6e1ae6b7aa6228388bd3c9a6d414742e2`;
`prove_d_process.py` checks that identity before testing. The fixture supplies
the independent old-SV reference for full-function arithmetic, real core_ce
snapshot, and D APB/CDC/I2S tests. It is never a production build input.

`core_ce_before_effect_slot.svh` contains the exact complete `core_ce`
assignment consumed by M11 from `gw138k_event_workstation.sv` SHA256
`5771d9d60e2e150c27a72e9ad1bf031c7d1faf952bf474d8791237171cb886a2`.
With its original two leading spaces and no trailing newline the assignment
SHA256 is `07e61423d09114dbb2ca3a19d0fc2084c35457a366f66890f6b7573e61a0046b`.
`prove_effect_slot_admission.py` checks that identity and extracts the actual
maintained Boolean equations, including the native/legacy `engine_clear`
selection. It proves that only the redundant effects admission terms are
factored out of `core_ce`; complete external `ready_o` remains unchanged.
The fixture is simulation/proof-only and is never a production build input.

`chorus_before_affine44.sv` is the exact complete M12 maintained Chorus before
the 44.1 kHz affine delay replacement, SHA256
`a2e09369634b35628920c3198b0020a51a0d4154fe690a2faf93465f8ff57900`.
The exhaustive delay runner calls its original function for every triangle at
both rates. The complete Chorus test also compares all 12 public outputs and
pipeline/history state at both clock edges, alongside the separate physical
time/PCM oracle. Runners pin the original bytes and rename only the module in
temporary outputs. It is simulation/proof-only, never a production input.
