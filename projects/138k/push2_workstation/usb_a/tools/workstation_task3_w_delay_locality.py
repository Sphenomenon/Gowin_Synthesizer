"""Reconstruct the diagnosed W delay/FIFO placement without constraining RAMs.

This is an exact physical recipe for the retained fetch-range W candidate.
It changes neither netlist nor timing constraints and grants no release status.
"""
from collections import Counter
import hashlib
import re

POLICY = 'W_new_fetch_range_retained_v22_complete_delay_locality_without_RAM_logic_regions_v1'
DMA = 'u_managed/runtime/delay_dma/'
FIFO = 'u_managed/runtime/service/workstation/runtime_effects.effects/delay_stage/'
SCOPES = ((DMA, 'R[50:60]C[60:75]'),
          (FIFO+'u_write_fifo/', 'R[45:60]C[70:85]'),
          (FIFO+'u_read_fifo/', 'R[45:60]C[70:85]'))
INVENTORIES = (
    dict(LUT4=424, LUT3=123, LUT2=385, DFFCE=811, DFFPE=3, ALU=34, INV=1, VCC=1, GND=1),
    dict(LUT4=32, LUT2=10, LUT3=88, DFFCE=80, SDPX9B=4, ALU=18, INV=3, VCC=1, GND=1),
    dict(LUT4=29, LUT2=11, LUT3=87, DFFCE=80, SDPX9B=4, ALU=18, INV=4, VCC=1, GND=1))


def require(ok, message):
    if not ok:
        raise ValueError('W delay locality: '+message)


def placement(cst, netlist):
    """Select the diagnosed scopes from their exact primitive inventories."""
    from tools.workstation_pinout import parse_locations
    sha = lambda b: hashlib.sha256(b).hexdigest()
    raw = cst.decode(); selected = {}; ram = []; counts = {}
    allowed = {'LUT2', 'LUT3', 'LUT4', 'ALU', 'MUX2_LUT5', 'MUX2_LUT6',
               'MUX2_LUT7', 'MUX2_LUT8', 'DFFCE', 'DFFPE', 'DFFRE', 'SDPX9B'}
    for (scope, region), expected in zip(SCOPES, INVENTORIES):
        cells = {p: c for p, c in netlist.cells.items() if p.startswith(scope)}
        counts[scope] = dict(Counter(c['kind'] for c in cells.values()))
        require(counts[scope] == expected, 'actual primitive inventory drift: '+scope)
        for path, cell in cells.items():
            if cell['kind'] in ('INV', 'VCC', 'GND'):
                continue
            require(cell['kind'] in allowed, 'unreviewed primitive: '+path)
            if cell['kind'] == 'SDPX9B':
                ram.append(path)
                continue
            require(not re.search(r'^INS_LOC "'+re.escape(path)+'" ', raw, re.M),
                    'preconstrained logic: '+path)
            selected[path] = region
    require(len(selected) == 2233 and len(ram) == 8, 'logic/RAM inventory drift')
    lines = []; removed = []; groups = {}
    for line in raw.splitlines():
        if line.startswith('GROUP '):
            name = re.match(r'GROUP (\S+) = ', line)[1]
            members = re.findall(r'"([^"]+)"', line); groups[name] = members
            drop = set(members) & (set(selected) | set(ram)); removed += sorted(drop)
            if drop:
                members = [p for p in members if p not in drop]
                require(bool(members), 'unexpected empty existing group')
                line = 'GROUP '+name+' = { '+' '.join('"'+p+'"' for p in members)+' };'
        lines.append(line)
    new_groups = []
    for i, region in enumerate(sorted(set(selected.values()))):
        name = 'task3_w_v24_delay_'+str(i)
        require(name not in groups, 'duplicate recipe application')
        members = sorted(p for p, target in selected.items() if target == region)
        lines += ['GROUP '+name+' = { '+' '.join('"'+p+'"' for p in members)+' };',
                  'GRP_LOC '+name+' '+region+';']
        new_groups.append(dict(name=name, region=region, members=members))
    result = ('\n'.join(lines)+'\n').encode()
    members = [p for line in lines if line.startswith('GROUP ')
               for p in re.findall(r'"([^"]+)"', line)]
    require(len(members) == len(set(members)) and not set(ram) & set(members),
            'duplicate or hard RAM in logic region')
    require(parse_locations(result.decode()) == parse_locations(raw), 'IO locations changed')
    proof = dict(policy=POLICY, before_CST_sha256=sha(cst),
                 after_CST_sha256=sha(result), scope_kinds=counts, selected_count=2233,
                           RAMs_not_in_logic_regions=ram, new_groups=new_groups,
                           old_members_removed=removed, clocks_changed=False,
                           timing_exceptions_changed=False)
    return result, proof


def reconstruct(cst, netlist, proof):
    """Require the exact selected inventories and reproduce every changed byte."""
    result, expected = placement(cst, netlist)
    for key, value in expected.items():
        require(proof.get(key) == value, 'receipt differs: '+key)
    return result
