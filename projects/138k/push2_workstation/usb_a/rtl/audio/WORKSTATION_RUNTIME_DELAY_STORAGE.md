# Native delay FIFO storage selection

The maintained `workstation_runtime_stereo_effects` composition explicitly sets
`delay_stage.u_write_fifo.RAM_STYLE` and
`delay_stage.u_read_fifo.RAM_STYLE` to `block_ram`. These are the only two RTL
lines added by this policy. The FIFO implementation, 65-bit data, default
512-entry capacity per FIFO, clocks, prefetch/head behavior, Gray pointers,
ready/valid, flush/PANIC, DDR allocation and delay algorithm are unchanged.
There is no added register or sample latency.

The policy follows the two existing selections in the maintained custom-board
**non-runtime** top. That choice is later maintained source work. The frozen
accepted_full83, timing85 and resource_rework_route0 tops do not contain those
selections, and their FIFO sources are different. No frozen baseline, original
provenance, accepted input or default `music_async_fifo.RAM_STYLE` is changed.
The native runtime path owns this selection beside its delay instance; no new
top overlay or generated production implementation is introduced.

In the unchanged FIFO, the storage attribute is used only for the even/odd
prefetch banks when `WIDTH == 65 && ADDRESS_BITS >= 8`. A depth-128 instance
(`ADDRESS_BITS == 7`) still elaborates the original asynchronous small-head
branch; setting the parameter does not promise BSRAM inference there. All
other FIFO clients retain their own parameters and default selection.

`workstation_runtime_stereo_effects.provenance.json` remains byte-identical,
SHA-256 `5af689e1adc920524e83d0ae9da87382a75a6bc2868c08fc246abb47814df68c`.
The independent `.delay_fifo_storage.json` sidecar records exactly one reversible
insertion and binds the new source, prior native source, unchanged provenance,
current FIFO and maintained top reference. The verifier first restores native
SHA-256 `d8a0d2c787bc8c222bf4dde74069db41163988a646fd70c32774387bfe23a689`,
then reverses the original migration to prepared slice
`5fcabe0bb792efb13a791b3e6f91b6d156dd074d8a89421dedde09a124539742`.
That slice is checked against the original maintained
`rtl/audio/stereo_effects.sv` bytes, full SHA-256
`e1197cd8b843b3f98b6254eca081af51f0e9b8ce61cf30f6cfdcf9e9cb2c98c6`,
matching the historical prepared provenance. This prepared composition is not
the earlier archive baseline file. Both identity chains fail closed on drift.
The verifier does not rewrite any production source.

Runtime preparation records the explicit policy and complete provenance under
`runtime_audio.delay_fifo_storage`; only the existing native runtime profiles
call this verifier. The strict old native policy rejects the changed source.
Candidate verification recomputes this metadata from the maintained source
chain and rejects edited policy, mapping claims or adaptation identities.
New source/profile inputs require a new candidate identity. Old c7, Chorus or
other candidate CDC/resource/timing acceptance cannot be applied to the new
mapped RAMs.

RTL validation uses `sim/test_workstation_runtime_effects.py`, which verifies
the sidecar, checks the unchanged prepared reference, and elaborates both
native FIFO storage parameters and default capacities. It retains all exact
48 kHz per-cycle/PCM comparisons, 44.1 kHz model comparisons, order/mask and
maintenance coverage, rate/history changes, PANIC, missing fence and stopped
clock behavior. `sim/test_workstation_delay_fifo_storage.py
DelayFifoStorage.test_both_clock_ratios_full_capacity_wrap_stall_and_reset`
runs only RTL FIFO comparisons at depths 256/512 under both clock ratios. Its
mapped-memory method requires explicit EDA scheduling. Extra Icarus compile
options are placed before every source input, so `-DMAPPED_FIFO` is parsed as
an option. Completed mapped fixtures may be replayed without rerunning EDA.

Isolated FIFO resource/mapped-model evidence does not establish whole-system
resource use, new primitive input fanout, CDC flight, routed timing or hardware
acceptance. A new actual integrated VG must be checked for exact native
hierarchy, even/odd bank data layout, RAM primitive type/count/mode, clock and
reset bindings, every payload/pointer consumer and the selected CDC constraints.
The metadata keeps physical RAM mapping, physical timing and hardware
inheritance false until that separate candidate validation is completed.
