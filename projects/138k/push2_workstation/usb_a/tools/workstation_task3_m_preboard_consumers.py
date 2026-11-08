"""Named consumer review for complete paired M, separate from historical seals.

Source APB inputs are proved as response equations, never treated as resets.
Destination enumeration admits no new clocks, pins, RAM or external consumers.
This inventory proves release ownership; subsystem behavior and routed timing
remain separate gates.
"""
from pathlib import Path
import json
from tools.workstation_task3_m_cpu_source_review import PREBOARD_PROFILE, sources, review
from tools.workstation_task3_peripheral_releases_audit import closure_identity, zero_async_ff

INVENTORIES=('task3_m_preboard_cpu_destination_inventory.json',
             'task3_m_preboard_cpu_destination_inventory_v2.json',
             'task3_m_preboard_cpu_destination_inventory_v3.json',
             'task3_m_preboard_cpu_destination_inventory_v4.json',
             'task3_m_preboard_cpu_destination_inventory_v5.json',
             'task3_m_preboard_cpu_destination_inventory_v6.json',
             'task3_m_preboard_cpu_destination_inventory_v7.json',
             'task3_m_preboard_cpu_destination_inventory_v8.json',
             'task3_m_preboard_cpu_destination_inventory_v9.json',
             'task3_m_preboard_cpu_destination_inventory_v10.json',
             'task3_m_preboard_cpu_destination_inventory_v11.json')


def expanded_inventory(inventory):
    expected={}
    for row in inventory['groups']:
        indices=[None] if row['indices'] is None else [
            i for lo,hi in row['indices'] for i in range(lo,hi+1)]
        for index in indices:
            path=row['register'] if index is None else row['register'].format(index)
            endpoint=path+'/'+row['pin']
            if endpoint in expected:
                raise ValueError('duplicate reviewed destination endpoint '+endpoint)
            expected[endpoint]=row['clock']
    return expected


def verify(n,g,closure,*,role,stage):
    from tools.workstation_task3_m_cpu_source_review import require
    artifact=json.loads((Path(stage).parent.parent/'workstation_profile.json').read_text())
    require(artifact['profile']==PREBOARD_PROFILE,'unselected preboard consumer review')
    if role=='source':
        result=review(n,source=sources(stage))
        require(result['complete_closure']==closure,'source complete closure differs')
        return result
    require(role=='destination','unknown preboard consumer role')
    # Select only an independently reviewed exact endpoint inventory. The VG
    # digest records provenance; it never substitutes for the pin/clock/type
    # checks, so a mutated netlist cannot pass merely by retaining its name.
    matches=[]
    for name in INVENTORIES:
        candidate=json.loads((Path(__file__).parent/name).read_text())
        if expanded_inventory(candidate)==closure['ff_endpoints']:
            matches.append((name,candidate))
    require(len(matches)==1,'named destination FF inventory changed')
    inventory_name,inventory=matches[0]
    require(inventory['profile']==PREBOARD_PROFILE and inventory['legacy_inventory_unchanged'] is True,
            'destination inventory selection changed')
    expected={}
    for row in inventory['groups']:
        require(row['clock']=='clk_50m' and row['pin'] in ('D','CE','CLEAR'),
                'destination inventory permits an unreviewed clock/pin')
        indices=[None]if row['indices'] is None else [i for lo,hi in row['indices']for i in range(lo,hi+1)]
        for index in indices:
            p=row['register'] if index is None else row['register'].format(index)
            endpoint=p+'/'+row['pin']
            require(endpoint not in expected and p in g.regs,'destination group absent/duplicate '+endpoint)
            require(n.cells[p]['kind']==row['primitive'] and n.pin(p,'CLK')=='clk_50m' and
                    n.cells[p]['parameters'].get('INIT',"1'b0")==row['init'],
                    'destination FF type/clock/init changed '+p)
            expected[endpoint]='clk_50m'
    require(len(expected)==inventory['ff_endpoint_count'] and closure['ff_endpoints']==expected,
            'named destination FF inventory changed')
    require(closure['primitive_endpoints']==inventory['primitive_endpoints'] and
            closure['top_output_endpoints']==inventory['top_output_endpoints'],
            'destination RAM/output complete inventory changed')
    return dict(profile=PREBOARD_PROFILE,policy='explicit_complete_M_preboard_destination_consumers_v1',
        reviewed_inventory=inventory_name,inventory_revision=inventory.get('revision',1),
        ff_endpoints=len(expected),named_groups=len(inventory['groups']),
        complete_closure_sha256=closure_identity(closure),
        RAM_and_output_inventory_verified=True,legacy_inventory_unchanged=True,
        downstream_business_function_proven=False,whole_CDC_accepted=False)
