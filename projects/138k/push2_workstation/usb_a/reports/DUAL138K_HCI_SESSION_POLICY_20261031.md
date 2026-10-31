# M/W native HCI session policy — 2026-10-31

This report covers maintained source and offline native transport verification.
It does not claim controller pairing, physical radio/UART closure, SRAM/Flash
deployment, or full W workstation acceptance. New candidates must record these
changed inputs under a new source/bitstream identity.

## Policy and implementation

W's `SESSION_ONLY_PAIRING=1` accepts only ClassOfDevice command `0c24` with
exact payload `14 04 24` and six total HCI bytes, and permits scan value 3 in
addition to existing scan value 2. The default policy rejects CoD and scan3,
retaining scan2. Existing `0c56` accepts only value1. CPU HCI Reset remains
disallowed; no ownership, GeneralBonding policy, command credit, epoch,
generation, token, response, or physical transport boundary is relaxed.

The actual maintained native transport caches six header bytes, with matching
reset and copy bounds. This fixes the out-of-range sixth-byte read found by W
full synthesis. `cpu_command_shape()` now takes opcode, length and each of
byte3/4/5 explicitly. The new consecutive same-opcode payload tests exposed
Icarus retaining an obsolete continuous-expression result when payload/length
were hidden function dependencies: the direct function result was1 while
`cpu_context` remained0. Explicit inputs make every dependency visible without
inserting unrelated commands into the fixture or weakening the policy.

## Exact native regression

The extended existing testbench uses the actual four-command bootstrap, CPU
MMIO mailbox, registered packet RAM copies, command credit owner, response
queue and physical H5 transport fixture. Each accepted command is checked for
one physical transmission, exact length/bytes, response token, bounded queue
publication and unchanged command credit. Each rejected command must reach no
physical slot, publish no raw response and report schema/context rejection.
Raw response queue publication is waited for separately from command response
completion; these are independent boundaries.

```sh
python3 projects/138k/push2_workstation/usb_a/sim/run_workstation_hci_session.py --output /tmp/dual138k-hci-session-policy-v8
python3 projects/138k/push2_workstation/usb_a/sim/run_workstation_hci_native.py --skip-uart --skip-prior --output /tmp/dual138k-hci-session-native-v2
```

| Check | Result | Evidence |
| --- | --- | --- |
| Default session policy |1293 cases,40636 checks;2 accepted,1291 rejected | `/tmp/dual138k-hci-session-policy-v8/verification.json` |
| W session policy |1293 cases,40666 checks;4 accepted,1289 rejected | same manifest |
| Exhaustive command bytes | All255 alternate values for each of three CoD bytes; all256 scan values; all256 `0c56` values; CoD and scan length/declared-length boundaries; Reset rejection | per-policy `run.log` |
| Five behavior mutations | Missing sixth cache byte, wrong CoD tail allowed, default scan3 leak, unrestricted scan byte, broadened CoD length all rejected | same manifest and mutation logs |
| Existing default native integration |268 checks,11 ownership/flow mutants; lint passed; targeted `--skip-uart --skip-prior` scope | `/tmp/dual138k-hci-session-native-v2/verification.json` |

The runner hashes its actual modules, bridge and testbench, and fails on input
drift. All generated simulations, logs and binaries remain outside source.
The original default integration path is unchanged when session-only contract
testing is disabled. Complete source-stage UART/H5 and real board evidence
remain separate work; `--skip-uart` does not claim them.

## Source identity

| Input | SHA-256 |
| --- | --- |
| `rtl/bluetooth/hci_owner/workstation_hci_native_transport.sv` | `a151aa426f4880dbcbf85239688ec910e8f43a2c2fb240e52161e166f029a10a` |
| `sim/tb_workstation_hci_native_transport.sv` | `9190d7a0d0439b834198001c4bcf1d05aa216e23b914ae025f11724bb1c243a8` |
| `sim/run_workstation_hci_session.py` | `72e9c99807832dfc33b274872a6db2bc2919213dec3c3326450a3281bce8e027` |
