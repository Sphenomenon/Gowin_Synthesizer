# Recording owner regression fixtures

`workstation_recording_ddr_owner_mux_before_owned_factor.sv` is the complete,
byte-exact recording owner mux consumed by W10
`custom138k-workstation-w-demo-v1-d1dddd2e83ad1cfd` before the owned-transfer
output-gate factorization. SHA256:
`2af5a52d3bf9c67f93eef803e07bd9b9e636c1f65348676289dc13b487e76bf5`.

This is a simulation-only reference, not a production build input or a second
implementation to maintain. `prove_recording_owned_transfer.py` verifies its
identity, requires that reversing only the reviewed gate block restores the
entire fixture, and compares the complete old/new owner with real native
bridges. Its temporary reference copy changes only the module name to allow
both versions in one simulation. Do not update the fixture to accommodate a
changed implementation; use a new, explicitly identified reference for any
later change.

## Raw-store START initialization

`workstation_ble_raw_ddr_store_before_start_factor.sv` is the complete,
byte-exact raw store consumed by W11
`custom138k-workstation-w-demo-v1-bafd43c180d52b1c` before accepted START
initialization factoring. SHA256:
`ca212e5f93c9110ba63bb5c90399558bcb5edd8ed3d096d8d9ec5956c35363a7`.

It is a simulation-only reference, never a production build input. The START
factor proof checks this identity and reverses the exact reviewed edits to
recover the entire fixture. Old/new full-module twins keep the real FIFO,
cache RAM and native bridge; only the temporary reference module name changes.
Do not update this fixture to accommodate later implementation changes.
