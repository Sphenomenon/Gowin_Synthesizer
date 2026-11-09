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
TX_CLASS_INVENTORIES = (
    dict(LUT4=424, LUT3=113, LUT2=403, DFFCE=811, DFFPE=3, ALU=34, INV=1, VCC=1, GND=1),
    dict(LUT4=34, LUT2=10, LUT3=85, DFFCE=80, SDPX9B=4, ALU=18, INV=3, VCC=1, GND=1),
    dict(LUT4=29, LUT2=13, LUT3=85, DFFCE=80, SDPX9B=4, ALU=18, INV=4, VCC=1, GND=1))
FIFO_COMPARE_INVENTORIES = (
    dict(LUT4=421, LUT3=123, LUT2=399, DFFCE=811, DFFPE=3, ALU=34, INV=1, VCC=1, GND=1),
    dict(LUT4=34, LUT2=11, LUT3=84, DFFCE=80, SDPX9B=4, ALU=18, INV=3, VCC=1, GND=1),
    dict(LUT4=30, LUT2=11, LUT3=84, DFFCE=80, SDPX9B=4, ALU=18, INV=4, VCC=1, GND=1))
ARITHMETIC_INVENTORIES = (
    dict(LUT4=420, LUT3=111, LUT2=393, DFFCE=800, DFFPE=3, ALU=34, INV=1, VCC=1, GND=1),
    *FIFO_COMPARE_INVENTORIES[1:])
CANCEL_READY_INVENTORIES = (
    dict(LUT4=419, LUT3=108, LUT2=395, DFFCE=800, DFFPE=3, ALU=34, INV=1, VCC=1, GND=1),
    dict(LUT4=34, LUT2=11, LUT3=85, DFFCE=80, SDPX9B=4, ALU=18, INV=3, VCC=1, GND=1),
    dict(LUT4=30, LUT2=13, LUT3=84, DFFCE=80, SDPX9B=4, ALU=18, INV=4, VCC=1, GND=1))

COMBINED_ADMISSION_INVENTORIES = (
    dict(LUT4=426, LUT3=102, LUT2=393, DFFCE=800, DFFPE=3, ALU=34, INV=1, VCC=1, GND=1),
    dict(LUT4=34, LUT2=9, LUT3=86, DFFCE=80, SDPX9B=4, ALU=18, INV=3, VCC=1, GND=1),
    dict(LUT4=31, LUT2=9, LUT3=87, DFFCE=80, SDPX9B=4, ALU=18, INV=3, VCC=1, GND=1))

# v109 CNN retirement refactors shared fault/FIFO logic without changing
# these owners' state or physical regions. Keep prior selections exact.
CNN_RETIREMENT_INVENTORIES = (
    dict(LUT4=426,LUT3=104,LUT2=392,DFFCE=800,DFFPE=3,ALU=34,INV=1,VCC=1,GND=1),
    dict(LUT4=34,LUT2=9,LUT3=87,DFFCE=80,SDPX9B=4,ALU=18,INV=3,VCC=1,GND=1),
    dict(LUT4=31,LUT2=8,LUT3=87,DFFCE=80,SDPX9B=4,ALU=18,INV=3,VCC=1,GND=1))


# Actual v121 ready/response cofactor mapping, including both real FIFOs.
DMA_READY_INVENTORIES = (
    dict(LUT4=431,LUT3=109,LUT2=390,DFFCE=800,DFFPE=3,ALU=34,
         MUX2_LUT5=4,INV=1,VCC=1,GND=1),
    dict(LUT4=34,LUT2=9,LUT3=87,DFFCE=80,SDPX9B=4,ALU=18,INV=3,VCC=1,GND=1),
    dict(LUT4=32,LUT2=9,LUT3=86,DFFCE=80,SDPX9B=4,ALU=18,INV=3,VCC=1,GND=1))

def require(ok, message):
    if not ok:
        raise ValueError('W delay locality: '+message)


def arithmetic_layout(metadata):
    """The reviewed physical inventory requires both exact arithmetic repairs."""
    width = metadata.get('w_watchdog_width', {}).get('policy')
    successor = metadata.get('raw_generation_successor', {}).get('policy')
    if width is None and successor is None:
        return False
    require(width == 'task3_W_bounded_saturating_wait_counter_v1' and
            successor == 'task3_W_registered_generation_successor_v1',
            'unreviewed partial arithmetic composition')
    return True


def placement(cst, netlist, *, registered_tx_class=False, fifo_compare_first=False, arithmetic_repair=False, cancel_ready_cofactor=False, combined_admission=False, cnn_retirement=False, dma_ready_cofactor=False):
    """Select the diagnosed scopes from their exact primitive inventories."""
    from tools.workstation_pinout import parse_locations
    sha = lambda b: hashlib.sha256(b).hexdigest()
    raw = cst.decode(); selected = {}; ram = []; counts = {}
    allowed = {'LUT2', 'LUT3', 'LUT4', 'ALU', 'MUX2_LUT5', 'MUX2_LUT6',
               'MUX2_LUT7', 'MUX2_LUT8', 'DFFCE', 'DFFPE', 'DFFRE', 'SDPX9B'}
    require(not fifo_compare_first or registered_tx_class,'FIFO-first layout requires registered W TX class')
    require(not arithmetic_repair or fifo_compare_first,'W arithmetic layout requires FIFO-first composition')
    require(not cancel_ready_cofactor or arithmetic_repair, 'CANCEL ready layout requires reviewed arithmetic composition')
    require(not combined_admission or cancel_ready_cofactor, 'W admission layout requires CANCEL composition')
    require(not cnn_retirement or combined_admission, 'CNN retirement layout requires combined admission')
    require(not dma_ready_cofactor or cnn_retirement, 'DMA cofactor layout requires CNN retirement')
    if dma_ready_cofactor:
        from tools.workstation_w_dma_mapping import audit as audit_dma
        audit_dma(netlist)
    inventories = DMA_READY_INVENTORIES if dma_ready_cofactor else CNN_RETIREMENT_INVENTORIES if cnn_retirement else COMBINED_ADMISSION_INVENTORIES if combined_admission else CANCEL_READY_INVENTORIES if cancel_ready_cofactor else ARITHMETIC_INVENTORIES if arithmetic_repair else FIFO_COMPARE_INVENTORIES if fifo_compare_first else TX_CLASS_INVENTORIES if registered_tx_class else INVENTORIES
    selected_count = 2224 if dma_ready_cofactor else 2211 if cnn_retirement else 2210 if combined_admission else 2212 if cancel_ready_cofactor else 2211 if arithmetic_repair else 2241 if fifo_compare_first else 2240 if registered_tx_class else 2233
    for (scope, region), expected in zip(SCOPES, inventories):
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
    require(len(selected) == selected_count and len(ram) == 8, 'logic/RAM inventory drift')
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
    primitive_region_proof = None
    if dma_ready_cofactor:
        from tools.workstation_task3_w_critical_locality import primitive_regions
        result, primitive_region_proof = primitive_regions(result)
    proof = dict(policy=POLICY, before_CST_sha256=sha(cst),
                 **(dict(primitive_regions=primitive_region_proof) if primitive_region_proof else {}),
                 **(dict(fifo_compare_first_layout=True) if fifo_compare_first else {}),
                 **(dict(arithmetic_repair_layout=True) if arithmetic_repair else {}),
                 **(dict(cancel_ready_cofactor_layout=True) if cancel_ready_cofactor else {}),
                 **(dict(combined_admission_layout=True) if combined_admission else {}),
                 **(dict(dma_ready_cofactor_layout=True) if dma_ready_cofactor else {}),
                 **(dict(registered_tx_class_layout=True) if registered_tx_class else {}),
                 after_CST_sha256=sha(result), scope_kinds=counts, selected_count=selected_count,
                           RAMs_not_in_logic_regions=ram, new_groups=new_groups,
                           old_members_removed=removed, clocks_changed=False,
                           timing_exceptions_changed=False)
    return result, proof


def reconstruct(cst, netlist, proof, *, registered_tx_class=False, fifo_compare_first=False, arithmetic_repair=False, cancel_ready_cofactor=False, combined_admission=False, cnn_retirement=False, dma_ready_cofactor=False):
    """Require the exact selected inventories and reproduce every changed byte."""
    result, expected = placement(cst, netlist, registered_tx_class=registered_tx_class, fifo_compare_first=fifo_compare_first, arithmetic_repair=arithmetic_repair, cancel_ready_cofactor=cancel_ready_cofactor, combined_admission=combined_admission, cnn_retirement=cnn_retirement, dma_ready_cofactor=dma_ready_cofactor)
    for key, value in expected.items():
        require(proof.get(key) == value, 'receipt differs: '+key)
    return result
