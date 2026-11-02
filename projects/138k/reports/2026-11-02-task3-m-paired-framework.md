# Task3 M paired board framework — 2026-11-02

This is M source implementation and offline evidence. No target board was operated. It does not identify a deployed bitstream or claim physical resource, timing, latency, LCD, Bluetooth, recognition accuracy or DAC acceptance.

The explicit provider `workstation_profile_task3_m_paired.sv` retains native 32-voice ordinary/vector synthesis, authoritative parameters, original effects/clock service, physical DAC scheduling and HDMI. It selects the existing real PCM1 owner through an optional command aperture. The old local PCM APB page fails explicitly in the paired profile; other providers keep the original default. A read-only real PCM idle chain permits phone rearm after actual queue/history retirement.

The same native SD/FAT/WAV owner now supports a default-off dedicated analysis pass. Playback and analysis cannot run separate SD cursors. W backpressure holds offline decoding, actual file LAST releases M's native owner, and a finite launch timeout prevents waiting forever for the remote producer. The paired top triggers analysis from `music_analysis_enable`, after actual model readiness and settle, rather than the restart/cancel pulse. Ordinary PC performance remains available while W loads or loses the model. This initial analysis format is explicitly stereo16/48 kHz; direct playback retains 48/44.1 kHz. Supporting further analysis formats requires conversion and a separately validated descriptor extension.

Typed analysis/score, record, phone and status lanes bind to real M services. Only matching fresh W status can supply model/HCI state. Each analysis file reserves 65,536 IDs; allocation persists across CPU configuration changes until common root reset. Final recording observes actual serializer completions with a nonblocking CDC and finite queue. Ch9 recording demand/cancel closes W's START dependency: M allocates independent recording generations, prepares or cancels the actual tap and never holds base samples or shared RX credit. A demand expires after one second and cannot later arm silently. W must map wire recording keys to its root-local monotonically increasing ingress keys so an independent M restart remains distinguishable by boot nonce.

The paired stage adapter adds 12 exact reversible edits to the unmodified maintained top. Its API is `apply_top(root,text)`, `inverse_top(root,text)`, `SOURCES`, `DEPENDENCIES` and `MAINTAINED_UPDATES`. Common pair config/transport must be applied after this adapter, and inverses must run in reverse order. The common board adapter must declare `task3_pair_*` wires before the M include, supply F808 `record_arm`/`record_cancel` pulses, and merge F808 into the actual CPU APB page. The exact source helper refuses a changed parent, changed selected top, missing paired include, changed anchor or changed reference.

| Identity | SHA256 |
| --- | --- |
| Parent maintained top | `4b4a99f674a7033b032a3e82b98e553d7d7675689627ca4fb0cebf9746738d0f` |
| Selected paired M top before common adapter | `ce6459cbab667af9510d43b964d0fcd2f2d182b88b33b65a283ba50c7bd36824` |
| Paired M reference | `e1af8daa488fbb704a7fd3fdc04b4b0fae89bdbcbe531643d3f2f97cbcd5e473` |
| Paired M helper | `625d0c1a12b348f86c36ec154e6be21df51588b9d00743f46bac9569b5f0966e` |
| M endpoint | `02182a38cb8b074a450696a974847160ddca864af75b63f2e012b21de94e2827` |
| M board include | `7eb819577d527a61b45e8f05dae0e4e167100534414adb751ae97d977c2f7a75` |
| Modified TF runtime service | `9195f5a23fb3317f99861cd4c39875f2658f8f4d328cbb1250a4301e8ccd708d` |

Evidence resides under `/Users/sphenicidition/.cache/gw138k-task3-20261101/`:

| Receipt | Result and actual scope | verification.json SHA256 |
| --- | --- | --- |
| `m-paired-default-tf-runtime-v2` | PASS, actual SD/FAT/WAV + real DSP/router/I2S, 48 kHz play/cancel; optional remote command branch disabled | `bc21bd16b24b8eeedb49f41c64b32ad46bf1c5e24aca0ecf8797fe208d417390` |
| `m-paired-tf-analysis-arbitration-v4` | PASS 9 checks / 5 scenarios + 5 adapter negative controls; actual runtime service/frame bridge/playback service, deterministic native cursor | `68df82150092c6ca8ea941d23f8019a7e15bcab6eb8a5755022a6ccebd40cdfe` |
| `m-paired-record-demand-v1` | PASS 17 checks / 8 scenarios; actual M endpoint/exporter, deterministic received packets and physical observations | `f4e4e5e6179bb33ad8250422d988dcf19fddc69240b7551d23a82dd6a949de04` |
| `m-paired-runtime-command-elaboration-v1` | PASS, actual runtime elaboration with AE350 PCM + remote command enabled; historical warnings retained, no physical claim | `18d1e470088d2b716b8474eeae6d03eb7ae4d0f42d7c2daf5db063a04d6c6387` |

The 17 accepted source-boundary tests and `git diff --check` also pass. Whole paired-board prepare/elaboration, firmware provisioning, whole-source locks, routed CDC/PLL/STA and hardware evidence remain subsequent integration gates. The old candidate/rollback bytes remain separate and untouched. Flash requires separate authorization.

## Whole-board synthesis and explicit paired audit

The explicit paired auditor now dispatches both registered M/W identities before the historical native/demo branches. It verifies the captured candidate's mutually bound profile, full staged inventory, actual provider selection, common/role top inverses, exact CST/SDC reconstruction and firmware identities. The old 16 profile locks and the generic native/demo gate behavior are retained. Paired failures are reported together and return a failing process status. A common SDC marker contributes zero timing exceptions and never proves CDC acceptance.

M candidate `custom138k-workstation-task3-m-paired-v1-6e9afcd692dc8b8b` completed actual Gowin whole-board synthesis in `m-paired-board-prepare-v3`. Its immutable prepare closure passes with six rejected metadata/source identity mutations. Actual mapped feature structure, all 32 voices' envelope/state/pressure storage, 25 LCD inout pads plus four explicit reserved CTP location additions, RTC, USB FIFO write reset, bridge reset, original boundary CDC, constraint retirement/rebinding and USB ROM checks pass. The selected source retains ordinary/vector synthesis, native CRC/cache TF playback, final DAC scheduling and HDMI.

| Artifact / resource | Identity / value |
| --- | --- |
| Integration inputs SHA256 | `89dc317dd5c59f693c43e93a3e48461f96f70075bb72cc727aec8437f3bb0da9` |
| Synthesis netlist SHA256 | `112b491b6d0f2319bc49b90377a4585e5ea21394182cd73d845f9c2494870509` |
| Synthesis resource XML SHA256 | `ac7bcdaccd38c1f6bdf77349d4162b7040d48b672363b7a71070474cac4147e1` |
| Synthesis log SHA256 | `d962c8882ae60587004ae64bbe7752687a97c5625d5f55f6dfe7105c07c6d789` |
| Registers / LUT / ALU | 55,427 / 65,183 / 26,658 |
| Synthesis equivalent BSRAM / SSRAM | 220 / 510 |
| MULTALU27X18 / MULT12X12 / MULT27X36 | 33 / 3 / 43 |
| Prepare receipt | `paired-audit-v1/M_prepare_verification.json`, SHA256 `9359f8ffceabdf8fe37a1e25870b60fa7a777068c0ae20123de00e6a8ceb7976` |
| Full audit receipt | `paired-audit-v1/M_synthesis_audit_v3.json`, SHA256 `d80d582e1c310d55d3c1fca0089c6800611fcd6589b016023d311456216c67a1` |

The full synthesis audit **fails**. This historical candidate did not stage four gate policy inputs (`ae350.cst`, `clocks.json`, `usb2_cdc.json`, `input_cdc.json`), so its strict clock/PLL/USB CDC gates remain blocked. The new common dependency list stages those files for subsequent candidates; this candidate is preserved unchanged. Four retained SDC `CLEAR` selectors have no actual endpoint: `u_managed/control_cdc/p_release*`, `u_runtime/u_cpu_cdc/destination_release*`, `u_managed/runtime/g_direct_tf.transport_health_mailbox/source_release_*_s*` and `u_managed/midi_bytes/destination_release_*_s*`. The held-boundary audit reaches the actual root check and rejects its `reset_n`/started-FF connectivity assertion; whether the mapped alias changed still needs independent investigation. None of these failures was waived, and no selector or clock budget was changed to obtain acceptance.

The standalone paired auditor has four additional destructive constraint tests; the existing demo auditor's 17 tests, DIRECT storage's three tests and accepted source-boundary 17 tests pass. Existing root/clock-release tests without their required explicit actual-netlist/official-primitive inputs skip and are not counted as passes. No routed implementation, physical BSRAM count, bitstream, two-board LCD throughput/RTT, Bluetooth stream budget, control-to-sound latency, hardware recognition accuracy, SRAM deployment or Flash deployment is established by this synthesis stage.
