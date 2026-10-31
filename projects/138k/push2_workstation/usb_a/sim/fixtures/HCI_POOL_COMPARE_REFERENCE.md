# HCI flow-owner equivalence fixture

`workstation_hci_flow_owner_before_pool_compare.sv` preserves the complete original maintained source consumed by W9b candidate `custom138k-workstation-w-demo-v1-01aa047a4d25aaf1` at `workstation/Prj1/rtl/bluetooth/hci_owner/workstation_hci_flow_owner.sv`.

SHA256: `8240975d4f1e119c86b7f5a0dd743f6db96dc67caa688c9992413a5a68e223e5`.

`sim/run_workstation_hci_pool_compare.py` checks those exact bytes, renames only its module, and compares all public outputs plus internal transaction state against the maintained source. It also applies independent full-length and handle-domain oracles and four mutations. This fixture is simulation-only and is never a synthesis input. Preserve its identity when evolving the maintained implementation. The dated proof is in `reports/DUAL138K_HCI_POOL_COMPARE_20261031.md`.
