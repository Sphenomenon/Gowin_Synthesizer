# AE350 checked clock client and first-party staging — 2026-10-30

## Result and scope

The maintained C client now supports one bounded clock submission and one bounded poll against the native runtime clock APB page. Its checked-MMIO host regression passes 821 assertions with AddressSanitizer and UndefinedBehaviorSanitizer. Two complete RV32 firmware builds produce identical ELF, binary and ROM, fit the existing memory limits and contain the linked API with actual RISC-V I/O fences.

This phase supplies a callable API for a future page/service owner. The four original startup/UI compilation sources retain their current bytes and contain no reference to the new API; creating its MMIO adapter performs no access. No page, automatic rate action, product RTL, profile lock, accepted/pinned input, generated ROM in a project, EDA run or board operation was added by this phase. The resulting maintained ROM is a new explicit candidate and requires a fresh whole-workstation source identity before integration.

## Source identity and reproduction

- Identity: `ae350-clock-client-offline-v1-68b32773b5ef9bed`.
- Source-set SHA-256: `68b32773b5ef9bedaad36ba184c18f6d40b070630074b272c940804267bd6469`.
- Versioned evidence: `workstation_task_20261030/ae350_clock_client.json`, an exact copy of the final runner output; SHA-256 `6582d672b8cfe405a62dbdbebc04b5c104fe0cab28cc133df31fe40e8a44ec37`.
- Local evidence directory: `/Users/sphenicidition/.cache/gw138k-task-20261030/ae350-clock-client-final-v3/`.
- ELF SHA-256: `2c49703e2a46d3619a1f5830890b5a17f98ad67a8a4f03e7f965ecb7454f94fe`.
- Binary SHA-256: `25918cf409f3cf0b507da2ffb07be5dadd1f0faf4b4e0878360ae5b9303c840a`.
- ROM SHA-256: `c598c50aa0172be1c5644fa50a17c4a18ea304cce7aaeca476cd55b7dba0e752`.
- New FPGA bitstream identity: none.

```sh
python3 projects/138k/push2_workstation/usb_a/sim/run_ae350_clock_service_api.py \
  --output /path/to/new-evidence \
  --riscv-prefix /Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf

GW138K_RISCV_PREFIX=/Users/sphenicidition/.local/opt/xpack-riscv-none-elf-gcc-15.2.0-1/bin/riscv-none-elf \
python3 projects/138k/push2_workstation/usb_a/sim/test_stage_ae350_firmware.py -v

python3 projects/138k/push2_workstation/usb_a/sim/test_current_workstation_sources.py -v
```

The first command requires a new output directory. It hashes 19 maintained inputs, including all firmware inputs, the runner/test/model, staging implementation and its compiler-discovery/baseline helpers, before and after verification. It does not reuse a previous executable or generated ROM. Nine staging tests and ten accepted/pinned input tests pass separately; Python syntax and owned-file whitespace checks pass.

## Client contract

`firmware/ae350/audio_clock_service.h/.c` own the API. `a138_clock_bus` accepts checked read/write callbacks whose zero result reports an incomplete or erroneous access. The raw adapter uses the existing volatile MMIO helpers and fences before and after every load/store. Checked callbacks need their own transport timeout; raw physical APB faults still require a platform trap handler.

One caller serializes the page. Probe, submit and poll perform at most 2, 9 and 11 accesses, with no retry or audio wait loop. A failed submission leaves the caller's ticket unchanged, including a transport error reported after the write has already committed. Such an error is not permission to retry automatically.

Submit reads the previous command ID, writes one operation, then checks the next nonzero ID and repeats the ID after reading expected epoch and request context. It derives the expected rate from that stable hardware context, including recovery at the current rate. Admission and media preparation remain PL behavior. The client introduces no second authoritative rate or parameter application point.

Poll brackets its observations with command/result ID reads. An unstable bracket or I/O error leaves the caller's status unchanged. Pending snapshots include both IDs so a prior result code cannot be mistaken for the in-flight ticket's result. It reads ACTUAL at `+0x2c` before the associated snapshot epoch at `+0x30`; it never reuses a cached epoch for success. APPLIED requires this ticket's stable result, idle phase, valid/not-busy actual audio, no core/DSP fault, and matching actual rate/epoch. A success record whose actual context has changed returns CONTEXT_LOST. Tickets remain immutable during polling.

The owner must discard tickets after CPU observer reset. Reset and 32-bit ID wrap can reuse values; this interface does not provide a persistent session generation or solve that ABA case.

## ABI and host coverage

The client requires ID `0x434c4b01`, ABI major 1, capabilities bits0/1/2 and media-policy bit4 at the dedicated `0xf8030000` page. COMMAND values 0/1/2 request 48k/44.1k/recovery. Media registers are `+0x60` status, `+0x64` timeout and `+0x68` failure category. Status bits0..5 mean hold, pending, completed, failed, enabled and backend_ready. BUS14 is media-not-ready; RESULT8/9/10 are media failure, media timeout and failed post-stop gate revalidation. Failure categories 1..8 retain TF reasons, 9 is normal recording seal failure and 10 is BLE normal seal failure. Underlying BLE detail remains with its observation owner.

The ABI was coordinated with the clock/media RTL owner. Numeric header assertions cover its register/flag/result layout. The host model checks the C access contract; it is not an RTL, APB CDC or media implementation proof. The separate media/clock RTL regressions retain that responsibility.

`sim/ae350_clock_service_host.c` exercises supported/unsupported capability versions, unarmed/busy admission, 48k and 44.1k/recovery tickets, same-rate no-op context, command and epoch wrap, rejected writes, changed request context and command ID races. Every one of the nine submit accesses and eleven poll accesses has an injected I/O failure. A separate write-error case commits the command before returning failure and still preserves the old ticket.

Polling checks pending versus complete, all result codes2..10, media reasons0..10, stale pre-existing snapshot epoch, exact ACTUAL-before-epoch order, invalid actual state, busy, core/DSP faults, changed rate/epoch, unexpected phase, observer ID clearing and changing command/result IDs during the read sequence. Assertions require bounded access counts, zero poll writes, immutable tickets and unchanged status on unstable or failed reads. The host compiler and both full RV32 builds emit no warnings; sanitizer execution passes.

## Staging provenance and capacity

`stage_ae350_firmware.py` distinguishes `IMPORTED_SOURCES/HEADERS` from `FIRST_PARTY_SOURCES/HEADERS`. The original four compile inputs remain first and the new C source is linked fifth. The original nine import descriptors, baseline provenance and historical ROM descriptor remain unchanged. First-party C/header descriptors separately bind their maintained repository path, kind and current SHA-256. Missing/extra descriptors, incorrect kind/path/hash, unrecorded source bytes, or putting the new C source into the imported inventory fail before compiler discovery and output creation.

Metadata records both input groups and the complete compile-source list. `changed_from_import` continues to describe only the nine imported inputs; the existing `ui_render.c` maintenance change remains the only entry. The baseline and historical ROM bytes are preserved. The new ROM differs from the historical locked reference in 2,955 words and uses its own hashes; a different compiler/current maintenance output is not historical ROM reproduction.

| Checked item | Result |
| --- | ---: |
| ROM binary/text | 12,380 / 16,384 bytes |
| ROM headroom | 4,004 bytes |
| Initialized data / BSS | 0 / 60 bytes |
| Reserved RAM prefix | 512 bytes |
| Static RAM end | `0x23c` |
| Stack top / remaining capacity | `0x2000` / 7,620 bytes |
| Required stack reserve | 4,096 bytes |
| Largest compiler single frame | 368 bytes |
| Clock probe / submit / poll single frames | 48 / 80 / 80 bytes |
| MMIO read / write fences in RV32 code | 2 / 2 |

The runner checks all four API symbols in the full linked firmware and decodes the actual `fence iorw,iorw` instruction bytes in both raw adapters. Both complete stages retain the existing linker/independent-symbol range checks and produce exactly 4,096 little-endian ROM words. Per-function frames and free capacity do not establish a whole-call-chain stack bound or physical stack watermark.

## Integration and rollback

The parent must incorporate these maintained source/tool hashes into a fresh explicit workstation profile, prepare and validate its whole input closure, and keep physical acceptance separate. This evidence does not cover ROM execution on AE350 hardware, real APB errors, RTL/media behavior, routed timing/resources, or a deployed FPGA.

No physical rollback is required. Source rollback restores the explicit maintained firmware source list/provenance and prepares a new identified ROM; it must not overwrite the historical baseline or reuse this result identity for changed release inputs.

## Independent parent verification

The parent reran the complete API runner in a new output directory, reproduced all 821 sanitizer assertions and both deterministic RV32 builds, and compared the complete input hashes and host metrics with the frozen child evidence. The separate 9 staging and 10 accepted/pinned tests pass. Raw independent evidence is [ae350_clock_client_parent.json](workstation_task_20261030/ae350_clock_client_parent.json), SHA-256 `bf49ad9530ad4afbb2a1f4710fa19fe9fcac9969d3447f256f30a8260725d277`. This remains an offline callable API; the ROM has not been installed in a project or executed on hardware.
