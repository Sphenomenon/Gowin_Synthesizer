# CF synthesis structure audit and D0 CDC endpoint correction

CF (`C21031CF`) completed synthesis of frozen source
`2690a6c31c4bad57b75542c30d61a8238ea553b8`. Root's `run all` then rejected SDC
lines7/8 with `TA2003: Can't set timing constraint to object`; no placement or
routing completed. The source agent only reads these outputs and does not run
EDA or modify root's physical candidate.

Actual SDPB hierarchy is `u_uart/lanes[0].ram/ram` through lane7. The proposed
`u_uart/lanes*/ram/ram/DI*` had an extra slash. D0 changes both held→RAM DI
constraints to `u_uart/lanes*.ram/ram/DI*`. The20ns maxdelay, hold treatment,
source-register selector, clocks, RTC and other CDC constraints remain intact.
The corrected pattern matches all eight actual native DI objects in the CF VG;
only a new root EDA run can establish that Gowin's SDC resolver accepts it.
`C21031D0` was absent from repository evidence, cache candidate names and launch
scripts when selected. It requires a fresh physical output and identity.

The first structure-audit rejection compared wrapper-local GND/VCC net names
literally across lanes. The revised parser normalizes only actual single-driver
GND/VCC primitive outputs to logical0/1. It retains polarity, mode, reset,
address and enable checks; contradictory/multiple constant drivers fail. This
is a parser correction for actual Gowin names and changes no RTL.

CF actual VG then passes the structure gate: top704registered bits, eight
native16 SDPB lanes with one-cycle read mode and canonical50MHz clocks,
1858held bits on `ram_clk`,1292reference FFs below the1600bound,512/384/32-bit
caches,128RAM read bits reaching GAO and no legacy wide snapshot FF names.
The strengthened consumer audit also proves every1858held capture bit reaches
the native DI cone and every128native DO bit reaches the UART cache. A decoy
RAM with disconnected write input or UART consumer cannot pass.
These are actual synthesis structure facts. They do not establish routed
resource count, timing, JTAG identity, SRAM acceptance or external reception.

The D0 source delta changes only preparation/audit/tests/reports. Compiled RTL,
firmware bytes, clock constraints and pin locations remain identical to CF.
Its prepared file comparison records the exact SDC/identity/GAO/TCL and
noncompiled audit-metadata changes. A small preliminary D0 source prepare was
superseded before any root EDA dispatch; root must use the explicitly delivered
final prepare rather than a local latest pointer.

Validation: structure fixture16negative controls, new per-wrapper
constant fixture and contradictory-driver negative control pass; the new CDC
geometry regression covers all eight lanes and sixteen active DI bits/lane.
Actual VG audit and original source-stage UART/GAO evidence remain separately
sealed. The CF failed inputs remain unchanged for evidence and rollback.
