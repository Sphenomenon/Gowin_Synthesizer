"""Inspect routed combinational data cones; diagnostic, not a replacement for STA."""

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import json
import re
import sys

root = Path(__file__).resolve().parents[2]
physical = Path(sys.argv[1]).resolve()
inputs = json.loads((physical / 'physical_inputs.json').read_text())
stage = Path(inputs['parent_candidate']) / 'workstation/Prj1'
sys.path.insert(0, str(stage / 'scripts'))
from check_video_pll_init import RoutedDesign, numbers

pnr = physical / 'impl/pnr/custom_138k_integration'
design = RoutedDesign(pnr.with_suffix('.sdf').read_text(), pnr.with_suffix('.vo').read_text())
incoming = defaultdict(list)
for (origin, target), delay in design.routes.items():
    incoming[target].append((origin, delay))
registers = {name: pins for name, (kind, pins) in design.cells.items() if kind.startswith('DFF')}
for name, block in design.sdf_cells.items():
    if name in registers:
        continue
    for origin, target, values in re.findall(r'\(IOPATH\s+(\S+)\s+(\S+)\s*([^\n]+)', block):
        incoming[name + '/' + target].append((name + '/' + origin, max(numbers(values)) * design.unit))
clocks = {'audio': design.cells['u_audio_clock/g_hardware.u_pll/PLL_inst'][1]['CLKOUT0'],
          'ddr_ui': design.cells['u_memory/u_ddr3/gw3_top/u_ddr_phy_top/fclkdiv'][1]['CLKOUT']}
all_sources = '--all-sources' in sys.argv[2:]
result = dict(scope='diagnostic data-flight cones only, no setup/hold/clock-skew signoff', clocks={})
for label, clock in clocks.items():
    sources = {name + '/Q' for name, pins in registers.items() if all_sources or pins['CLK'] == clock}
    active = set()

    @lru_cache(maxsize=None)
    def latest(node):
        if node in sources:
            return design.arc(node[:-2], 'CLK', 'Q'), node, None
        if node in active:
            return float('-inf'), None, None
        active.add(node)
        candidates = [(latest(origin)[0] + delay, origin) for origin, delay in incoming[node]]
        active.remove(node)
        if not candidates:
            return float('-inf'), None, None
        delay, previous = max(candidates)
        return delay, latest(previous)[1], previous

    endpoints = []
    for name, pins in registers.items():
        if pins['CLK'] == clock:
            for pin in ('D', 'CE'):
                if pin in pins:
                    target = name + '/' + pin
                    delay, source, previous = latest(target)
                    if source:
                        endpoints.append((delay, source, target))
    entries = []
    for delay, source, target in sorted(endpoints, reverse=True)[:100 if all_sources else 10]:
        chain = [target]
        while chain[-1] != source:
            chain.append(latest(chain[-1])[2])
        entries.append(dict(data_flight_ns=delay, source=source, target=target,
                            source_clock=registers[source[:-2]]['CLK'], chain=list(reversed(chain))))
    result['clocks'][label] = entries
    print(label, json.dumps(entries[:2], indent=2))
    latest.cache_clear()
(physical / ('diagnostic-all-source-cones.json' if all_sources else 'diagnostic-data-cones.json')).write_text(
    json.dumps(result, indent=2) + '\n')
