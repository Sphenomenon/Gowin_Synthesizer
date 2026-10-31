# Explicit cache/PMA probe v1

This is an opt-in standalone probe, selected only with
`--ae350-local-memory-probe --ae350-probe-gao bsram4 --ae350-probe-program cache-pma-v1`.
The default local-memory/full64/banked4/bsram4 probe and production cache policy
remain unchanged. A new UserCode and new physical evidence are required. The
D0 snapshot transport result is not acceptance of this program or RAM owner.

## Source basis

- Gowin MUG1029 v1.3, PDF pages 50–52 / printed pages 17–19, SHA256
  `3b8c45bdb4612fcafce82626d202ecf640351290a9be4b58571b6d20674f72ee`:
  MCACHE_CTL IC_EN/DC_EN bits 0/1; Table 6-4 CCTL commands D VA invalidate 0,
  writeback 1, writeback+invalidate 2; I VA invalidate 8; D all invalidate 23;
  I index invalidate 24. These manuals do **not** specify the PMA field encoding.
- Gowin-author AE350 BSP commit `019f87ff9c6f77ca467fd15b29694c753eaddbe2`,
  `firmware/ae350_demo/src/bsp/ae350/{csr.h,cache.c,ae350.c}` and
  `firmware/ae350_demo/src/demo/cache/demo_cache.c`: CSR numbers, geometry,
  MMSC PPMA bit30 and CCTLCSR bit16. Reference only; no vendor implementation
  copied into maintained firmware.
- Zephyr fixed commit `0534e997eacb94bae1df6c9a7dd4a9a6cbf1cecf`,
  `arch/riscv/custom/andes/{pma.c,pma.h,andes_csr.h}` (Andes Technology,
  Apache-2.0): ETYPE NAPOT=3, MTYPE noncacheable-bufferable=3 and
  writeback/read+write-allocate=11, RV32 four cfg bytes per CSR,
  PMACFG0..3=0xbc0..3, PMAADDR0..15=0xbd0..f, and NAPOT encoding.
- AndesTech OpenSBI fixed commit `2d821146970e2408540bb9df24e66ba86fd54607`,
  `platform/generic/andes/andes_pma.c` and
  `platform/generic/include/andes/{andes_pma.h,andes.h}` corroborate the PMA
  layout, 4KiB granularity and uncached encoding. Its header does not define
  MTYPE=11. GPL code was consulted as reference, not copied.

The new program requires readback of the actual device configuration, and fails
closed on unsupported CSRs/geometry/attributes. Source documentation alone is
not proof of encrypted-IP behavior. The sealed delivery includes the pinned
reference files and hashes; they are not build inputs or production dependencies.

## Owned addresses and transport

Control executes in ILM; globals and the bounded stack stay in DLM. The cold
loader and 64KiB ROM policy are unchanged. The standalone PL owner has 8KiB
backing RAM at 0..0x1fff. Only 0x1000..0x1fff is cacheable; explicit uncached
alias 0x4000..0x4fff accesses those same 4KiB of backing bytes. This is isolated
scratch storage, with no workstation DDR allocation. F800..F806 must remain
uncached/device; F80000F0 is an APB read counter for an identical-address guard.
No production cache is enabled, and no shared DDR/UI/PCM coherence is claimed.

Entry requires cache off, no prefetch/write-around/coherence mode, both cache
geometry low9bits=0xda (256 sets, 4 ways, 32-byte lines, 32KiB each), MMSC PPMA
and CCTLCSR, and all four existing PMACFGs zero. All 16 PMAADDRs are saved.
The probe changes only entries0/1: cfg0=0x0f2f, addr0=0x5ff, addr1=0x11ff.
NAPOT is `(base>>2)|((size-1)>>3)` for each 4KiB page.

`workstation_ae350_cache_probe_memory.sv` owns the real hard-IP DDR AHB port,
including HBURST and HPROT. It accepts 8/16/32/64-bit aligned accesses; SINGLE,
INCR and WRAP/INCR4/8/16; NONSEQ then exact SEQ addresses/size/burst in the same
1KiB segment. BUSY retains burst state, IDLE closes it. Write data belongs to
the previous accepted address; masks and same-word write→read forwarding are
explicit. Invalid accesses produce two-cycle ERROR (first not-ready, second
ready), clear burst state, and set a sticky fault. Reset cancels pending writes.
The dedicated point-to-point owner has no arbitration/HREADYIN and introduces
no valid-transaction waits; arbitrary shared-bus stall behavior is outside scope.
HPROT is wired but does not itself implement PMA/cache semantics in PL.

## Checks and failure policy

After cold invalidation and attribute readback, enable only IC_EN/DC_EN. Fill
and dirty the 4KiB page, require uncached alias to retain old data, clean and
require publication. Write shared data through alias, require old cached data,
then invalidate and require the shared value. Execute two literal instructions
from the PL page returning17; modify through D-cache to29, require no premature
backing update, clean, require old instruction17 until I-cache maintenance, then
require29. Repeated same-address APB reads must increment. Cleanup writes back
and invalidates the owned page, invalidates all I indices, disables cache with
exact readback, revokes own entries, restores both addresses, and checks all16
addresses plus untouched cfg1..3. A successful path executes2308 CCTL commands.

Ordinary failures take the cleanup path. Unsupported CSR/control or bus traps
are terminal: a stackless handler records cause/PC, disables cache, and, when
armed, revokes only its cfg0 entries and restores addr0/1. Dirty scratch data
can be discarded on terminal traps and is never reported published. A trap in
the cleanup controls can itself prevent complete restoration; this is a failed
candidate requiring reset/rollback, never a passing result. The instruction
budget in the abstract model does not prove a stalled hard-IP/bus operation is
bounded on hardware. Board bring-up must watch phase/progress and enforce host
timeouts. No SRAM/Flash programming occurs during prepare or these tests.

## Diagnostics (64 words, byte address F8000000 + 4*index)

0=CCH1; 1=loader PASS; 5=CAC1; 6=PASS/FAIL; 7=failure bits; 8=phase (10=terminal
ordinary); 9=progress; 10=heartbeat; 11=PC; 12=SP; 15=trap count. 16/17/18 are
MICM/MDCM/MMSC; 19/20/21 initial/enabled/final cache control; 22/23 capacities;
24=packed low9bit geometry. 25..28 initial PMACFGs (27/28 become cause/PC on trap);
29/30 saved addr0/1; 31..33 applied cfg0/addr0/addr1. 34/35/36 cached dirty,
alias before/after clean; 37/38/39 shared new/cached old/after invalidate;
40/41/42 instruction results17/17/29; 43/44 APB read counts; 45 restoration flags
(cache-off=1, PMA restored=2); 46 CCTL count; 48..50 size/page/alias;
52/53 first mismatch expected/actual; 54/55 features; 56 bytes tested;
57 CCTL eligible; 58 upper-ROM seen (not required by this small program);
59 unmapped AHB fault; 60 APB read counter; 61 existing snapshot freshness flags.

`decode_ae350_cache_probe.py` requires the explicit manifest and assesses CRC,
identity, terminal state, behavior and cleanup. A decoder pass alone is not
hardware acceptance. Bind it to the exact candidate source/bitstream/UserCode,
actual synthesis resource/CDC and routed timing gates, JTAG readback and full
fresh UART/GAO evidence. No 32KiB/full-way capacity stress, hard-IP simulation,
physical performance measurement, production integration or Flash acceptance
is established by the 4KiB abstract-model and source tests.
