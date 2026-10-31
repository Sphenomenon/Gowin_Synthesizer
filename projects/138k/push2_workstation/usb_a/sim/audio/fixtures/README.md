# Clock monitor reference

`workstation_audio_clock_monitor_pre_m9.sv` is the exact maintained monitor from commit `2e273da` before the opposite-edge release change. Its SHA256 is `1d073cbf98ff683603f36ae521fcc5f62bfc6920526ff442e184c02466519d15`. It is simulation-only, never a production source. The runner pins its bytes, renames only its module in a temporary output, and compares every public output against the maintained implementation. The old implementation also acts as the targeted rising-edge margin negative control.

`d_process_before_exact_mask.svh` contains the actual W9b consumed D function
from module SHA256 `238d1274e1ad5d724632607374f08a8f03a8fe9d4df26c69613f7dbb26de2646`.
Only its function name is changed for simultaneous comparison. Restoring the
name gives function SHA256 `11247717c12f218bd37fe96d399cc6a6e1ae6b7aa6228388bd3c9a6d414742e2`;
`prove_d_process.py` checks that identity before testing. The fixture supplies
the independent old-SV reference for full-function arithmetic, real core_ce
snapshot, and D APB/CDC/I2S tests. It is never a production build input.
