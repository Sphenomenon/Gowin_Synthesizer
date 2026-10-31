# Explicit bsram8 GAO export

Select `--ae350-local-memory-probe --ae350-probe-gao bsram8` with a new UserCode.
The initial narrow comparison uses the unchanged `local-memory` program and
C21031D4. The cache/PMA program is intentionally restricted to explicit bsram4.
The old full64, banked4 and bsram4 schemas/selection remain unchanged. This is a
source/prepare candidate, with no inherited D0 physical acceptance.

The canonical snapshot,64 diagnostic words, one-edge pclk held capture, request/
ACK/timeout rules,16×128bit complete inactive-bank copy, double buffering, eight
native16-bit synchronous RAM lanes, UART frame/CRC, DAC safety and clocks are
unchanged. Only GAO export geometry/scheduling/bounded caches change:

- 448 registered top bits =256 data +192 metadata.
- Eight ordered pages,8 words/page,4 reference clocks/page,32 clocks/sweep.
- Metadata words8..13: sequence,UserCode,schema A1386404,page geometry,
  frozen digital IO,frozen health. Geometry is0x08400800 | valid<<3 | page[2:0].
- A256bit prepared page0 and128bit prefetch replace the old512/384bit caches.
  RAM remains128bit per read. At a boundary request group0 of the next page;
  at phase0 request group1, retain its returned data through the next boundary.
  Read-valid/bank/group tags still bind UART cache data. Each32bit word returns
  once per32 reference clocks; UART waits for its tagged word without stealing
  read cycles. Group1 can remain physically at the RAM output while idle.
- New publications are adopted only at page7→0. IO/health freeze there with the
  sequence. Timeout retains the previous bank and marks word61 bit4. Common
  reset suppresses uninitialized RAM through validity gates and resets context.
  Word61 is overwritten with frozen transport flags at page7 localword5.

`decode_ae350_bsram8_gao.py` is a separate strict decoder. It requires the
explicit bsram8 manifest,448 packed and matching individual bit columns, exact
schema/geometry/identity, unchanged page/IO/health for a sequence, ordered8-page
coverage and at least2 stable samples/page. Unknowns/reset/unpublished/newer
partial groups invalidate freshness until another complete group. UART CRC is
never inferred from GAO. Old decoders reject this schema/width.

The structure gate retains eight actual SDPB lanes, all128 read bits reaching
GAO and UART, all held bits reaching RAM, bounded caches and registered output
width; bsram8 uses an1100 reference-register limit, compared with1600 for
bsram4. These are fail-closed netlist expectations, not actual measured counts.
Only actual new synthesis, CDC/routed timing, bitstream/UserCode/JTAG binding and
fresh matching captures can establish a usable board candidate. D0 failed route
in GAO; reduced width is a routing experiment, not a guarantee of closure.
