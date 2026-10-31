# Clock monitor reference

`workstation_audio_clock_monitor_pre_m9.sv` is the exact maintained monitor from commit `2e273da` before the opposite-edge release change. Its SHA256 is `1d073cbf98ff683603f36ae521fcc5f62bfc6920526ff442e184c02466519d15`. It is simulation-only, never a production source. The runner pins its bytes, renames only its module in a temporary output, and compares every public output against the maintained implementation. The old implementation also acts as the targeted rising-edge margin negative control.
