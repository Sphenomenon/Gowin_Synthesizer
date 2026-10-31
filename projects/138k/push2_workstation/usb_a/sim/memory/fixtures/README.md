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
