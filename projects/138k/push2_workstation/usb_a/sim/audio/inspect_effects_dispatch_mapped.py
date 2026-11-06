#!/usr/bin/env python3
"""Compare the retained divider-valid to reverb-RAM-enable synthesis cone.

This inspects combinational topology, not sensitization, STA or full CDC.
Unknown or multiply driven primitives in the queried cone fail closed.
"""
from pathlib import Path
import argparse, hashlib, json, sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph,COMB

PREFIX='u_managed/runtime/service/workstation/runtime_effects.effects/'
SOURCE='u_managed/runtime/service/workstation/runtime_engines.engines/oscillator/g_pitch_pipeline.divider/valid_9_s0'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def inspect(path):
    before=sha(path)
    n=protocol_netlist(path.read_text(),mapping='synthesis');g=Graph(n)
    assert SOURCE in g.regs,'actual divider source changed'
    source=n.pin(SOURCE,'Q');memo={};active=set()
    def walk(net):
        if net==source:return []
        if net in memo:return memo[net]
        if net in g.high|g.low:return None
        assert net not in active,'combinational cycle'
        drivers=g.drivers[net]
        assert len(drivers)==1,'unknown or multiple drivers: '+net
        cell,pin=drivers[0]
        if cell in g.regs:return None
        c=n.cells[cell];kind=c['kind']
        assert kind in COMB,'unsupported primitive: '+cell
        active.add(net);longest=None
        for port in c['ports']:
            if port in COMB[kind]:continue
            witness=walk(n.pin(cell,port))
            if witness is not None and (longest is None or len(witness)+1>len(longest)):
                longest=witness+[dict(cell=cell,kind=kind,input=port,output=pin,net=net)]
        active.remove(net);memo[net]=longest;return longest
    rams=[p for p,c in n.cells.items() if p.startswith(PREFIX+'reverb_stage/') and c['kind']=='SDPB']
    assert len(rams)==20,'expected all 20 retained reverb SDPB instances'
    rows=[]
    for p in sorted(rams):
        assert 'CEA' in n.cells[p]['ports'],'expected actual RAM enable CEA'
        witness=walk(n.pin(p,'CEA'))
        rows.append(dict(cell=p,pin='CEA',combinationally_reached=witness is not None,
                         stages=None if witness is None else len(witness),witness=witness))
    regs=[dict(cell=p,kind=n.cells[p]['kind'],pins={pin:n.pin(p,pin) for pin in n.cells[p]['ports']})
          for p in sorted(g.regs) if p.startswith(PREFIX+'config_dispatch/')]
    assert sha(path)==before,'netlist changed during inspection'
    return dict(netlist=str(path),sha256=before,source=SOURCE,source_clock=n.pin(SOURCE,'CLK'),
                RAM_enable_inventory=rows,dispatch_registers=regs)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old',type=Path,required=True)
    parser.add_argument('--new',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    result=dict(passed=False,scope=__doc__,hardware_tested=False,routed_timing_verified=False)
    try:
        old=inspect(args.old);result['old']=old
        new=inspect(args.new);result['new']=new
        assert not old['dispatch_registers'],'reference unexpectedly contains dispatcher'
        assert len(new['dispatch_registers'])==3,'held command state inventory changed'
        assert all(row['combinationally_reached'] for row in old['RAM_enable_inventory']), 'reference path not reproduced'
        assert all(not row['combinationally_reached'] for row in new['RAM_enable_inventory']), 'divider path still reaches RAM enable'
        result['passed']=True
    finally:
        (args.output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS divider-valid path cut before all 20 reverb RAM enables; not STA')

if __name__=='__main__':main()
