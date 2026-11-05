#!/usr/bin/env python3
"""Explicit isolated Gowin A/B/C probe; never a workstation production build."""
import argparse
from collections import Counter
import datetime
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_custom_board_implementation import DEVICE
from tools.workstation_memory import clock_estimates
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_runtime_pcm_cdc import Graph,COMB
RTL='rtl/music/workstation_task3_score_commit_m.sv'
TOP='task3_score_probe'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def artifact(p):return dict(path=str(p),sha256=sha(p))

def structure(path):
    n=SynthesisNetlist(path.read_text(),TOP);g=Graph(n);active=set();cycles=set();stops=Counter()
    @lru_cache(maxsize=None)
    def depth(net):
        if net in g.high|g.low:return 0
        if net in active:cycles.add(net);return 0
        drivers=g.drivers.get(net,[])
        if len(drivers)!=1:stops['unknown_or_ambiguous_driver']+=1;return 0
        p,port=drivers[0];c=n.cells[p]
        if p in g.regs:stops['FF_Q']+=1;return 0
        if c['kind'] in ('IBUF','BUFG','OBUF','TBUF') or c['kind'] not in COMB:
            stops['buffer_or_macro']+=1;return 0
        active.add(net)
        result=1+max((depth(n.pin(p,pin)) for pin in c['ports'] if pin not in COMB[c['kind']]),default=0)
        active.remove(net);return result
    endpoints=sorted((dict(pin=p+'/'+pin,stages=depth(n.pin(p,pin))) for p,c in g.regs.items()
        for pin in ('D','CE') if pin in c['ports']),key=lambda row:(-row['stages'],row['pin']))
    return dict(known_scalar_FFs=len(g.regs),highest_unit_weight_endpoints=endpoints[:10],
        termination_counts=dict(stops),cycle_nets=sorted(cycles),
        leaf_cell_kinds=dict(Counter(c['kind'] for c in n.cells.values() if c['kind'] not in n.modules)),
        scope='Partial known scalar graph. Unit weights are not delay; macros and buffers terminate traversal.',
        routed_timing_verified=False)

def main(args):
    output=args.output.resolve();reference=args.reference_source.resolve()
    if sha(reference)!=args.reference_sha256:raise ValueError('sealed reference source hash mismatch')
    output.mkdir(parents=True,exist_ok=False)
    inputs={str(p):sha(p) for p in (ROOT/RTL,reference,Path(__file__),
        ROOT/'tools/workstation_synthesis_netlist.py',ROOT/'tools/workstation_runtime_pcm_cdc.py')}
    current=(ROOT/RTL).read_text();old=reference.read_text()
    interface=current.split(')(\n',1)[1].split('\n);',1)[0]
    if interface!=old.split(')(\n',1)[1].split('\n);',1)[0]:raise ValueError('reference interface changed')
    ports=re.findall(r'\b(?:input|output)\s+(?:wire|reg)\s+(?:\[[^]]+\]\s*)?([^\n]+)',interface)
    names=[name.strip() for row in ports for name in row.rstrip(',').split(',')]
    if len(names)!=len(set(names)) or len(names)!=25:raise ValueError('unexpected collector interface')
    result=dict(schema=1,passed=False,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_sha256=inputs,device=DEVICE,capacity_notes=2048,synchronous_BSRAM_read=True,
        cases=[],scope='Isolated score collector with real Gowin synthesis; no full M/W candidate or physical route',
        profile_selected=False,timing_closed=False,hardware_tested=False,SRAM_programmed=False,Flash_programmed=False)
    env=os.environ.copy()
    if args.gowin_lib:
        env.update(DYLD_LIBRARY_PATH=str(args.gowin_lib),DYLD_FRAMEWORK_PATH=str(args.gowin_lib))
    try:
        for label,payload,pipe in (('sealed_reference',old,None),('current_direct',current,0),('current_pipeline',current,1)):
            folder=output/label;folder.mkdir();(folder/'score.sv').write_text(payload)
            params=".MAX_NOTES(2048),.SYNC_READ_STORAGE(1'b1)"+(f",.PIPELINED_TERMINAL(1'b{pipe})" if pipe is not None else '')
            wrapper='module '+TOP+'(\n'+interface.replace('output reg','output wire')+'\n);\n'+\
                'workstation_task3_score_commit_m #('+params+') dut(\n'+',\n'.join('.'+p+'('+p+')' for p in names)+');\nendmodule\n'
            (folder/'probe.sv').write_text(wrapper)
            (folder/'clocks.sdc').write_text('create_clock -name clk_i -period 10.000 [get_ports {clk_i}]\n')
            script='set root [file normalize [file dirname [info script]]]\ncd $root\n'+\
                'set_device '+DEVICE+' -device_version C\nset_option -synthesis_tool gowinsynthesis\n'+\
                'set_option -top_module '+TOP+'\nset_option -output_base_name '+TOP+'\n'+\
                'set_option -verilog_std sysv2017\nset_option -timing_driven 1\n'+\
                'add_file -type verilog [file join $root score.sv]\nadd_file -type verilog [file join $root probe.sv]\n'+\
                'add_file -type sdc [file join $root clocks.sdc]\nrun syn\n'
            (folder/'run.tcl').write_text(script)
            before={p.name:sha(p) for p in folder.iterdir() if p.is_file()}
            start=time.monotonic();argv=[str(args.gowin),str(folder/'run.tcl')]
            with (folder/'synthesis.log').open('w') as log:
                p=subprocess.run(argv,cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
            row=dict(label=label,argv=argv,exit_code=p.returncode,elapsed_seconds=time.monotonic()-start,
                input_sha256=before,log=artifact(folder/'synthesis.log'))
            result['cases'].append(row)
            if p.returncode:raise RuntimeError('Gowin synthesis failed '+label)
            stage=folder/'impl/gwsynthesis';vg=stage/(TOP+'.vg');rsc=stage/(TOP+'_syn_rsc.xml')
            xml=ET.parse(rsc).getroot();row['resource_XML_root']=xml.tag
            row['synthesis_resources']={k.removeprefix('T_'):int(v.split('(')[0])
                for k,v in xml.attrib.items() if k.startswith('T_')}
            row['netlist']=artifact(vg);row['resource_report']=artifact(rsc)
            row['clock_estimates']=clock_estimates(stage/(TOP+'_syn.rpt.html'))
            if len(row['clock_estimates'])!=1 or row['clock_estimates'][0]['required_mhz']!=100:
                raise ValueError('expected explicit100 MHz isolated probe clock')
            row['structure']=structure(vg)
            row['inputs_unchanged']=before=={name:sha(folder/name) for name in before}
            if not row['inputs_unchanged']:raise RuntimeError('probe inputs changed')
            print(label,json.dumps(dict(elapsed_seconds=row['elapsed_seconds'],longest=row['structure']['highest_unit_weight_endpoints'][0],
                clocks=row['clock_estimates'])),flush=True)
        if args.gowin_primitives:
            # Use the same behavioral acceptance bench on actual mapped DFF,
            # LUT, ALU and SDPB cells. Rename only the two declared design
            # modules to isolate netlists; vendor primitive bytes stay intact.
            mapped=output/'mapped';mapped.mkdir();netlists=[];renames=[]
            for label in ('current_direct','current_pipeline'):
                source=output/label/'impl/gwsynthesis'/(TOP+'.vg');text=source.read_text()
                modules=re.findall(r'^module\s+(\w+)\s*\(',text,re.M)
                if set(modules)!={'workstation_task3_score_commit_m',TOP}:raise ValueError('mapped module inventory drift')
                for module in modules:text=re.sub(r'\b'+module+r'\b',label+'_'+module,text)
                target=mapped/(label+'.vg');target.write_text(text);netlists.append(target)
                renames.append(dict(input=artifact(source),output=artifact(target),
                    declared_module_renames={m:label+'_'+m for m in modules}))
            bindings=',\n'.join('.'+name+'('+name+')' for name in names)
            adapter='module score_mapped_adapter #(parameter SYNC_READ_STORAGE=1,PIPELINED_TERMINAL=0)(\n'+\
                interface.replace('output reg','output wire')+'\n);\n'+\
                'generate if(PIPELINED_TERMINAL)begin\ncurrent_pipeline_'+TOP+' dut(\n'+bindings+');\n'+\
                'end else begin\ncurrent_direct_'+TOP+' dut(\n'+bindings+');\nend endgenerate\nendmodule\n'
            (mapped/'adapter.sv').write_text(adapter)
            bench=ROOT/'sim/music/tb_task3_score_terminal_pipeline.sv';text=bench.read_text()
            if text.count('workstation_task3_score_commit_m #(')!=1:raise ValueError('mapped bench anchor drift')
            target=mapped/'bench.sv';target.write_text(text.replace('workstation_task3_score_commit_m #(', 'score_mapped_adapter #('))
            binary=mapped/'mapped.vvp'
            argv=['iverilog','-g2012','-s','tb_task3_score_terminal_pipeline','-o',str(binary),
                str(target),str(mapped/'adapter.sv'),*map(str,netlists),str(args.gowin_primitives)]
            p=subprocess.run(argv,cwd=mapped,capture_output=True,text=True,timeout=60)
            (mapped/'build.log').write_text(p.stdout+p.stderr)
            if p.returncode:raise RuntimeError('mapped primitive build failed')
            p=subprocess.run(['vvp',str(binary)],cwd=mapped,capture_output=True,text=True,timeout=60)
            (mapped/'run.log').write_text(p.stdout+p.stderr)
            if p.returncode or 'PASS terminal pipeline' not in p.stdout:raise RuntimeError('mapped primitive behavior failed')
            result['mapped_behavior']=dict(passed=True,build_argv=argv,
                primitive_library=artifact(args.gowin_primitives.resolve()),
                original_bench=artifact(bench),mapped_bench=artifact(target),adapter=artifact(mapped/'adapter.sv'),
                adaptation=renames,run_log=artifact(mapped/'run.log'),
                summary=p.stdout.strip().splitlines()[0],
                actual_SDPS_and_FF_logic=True,async_read_mode_not_mapped=True,
                scope='Actual synchronous-read mapped direct/pipeline cells; both pairs of behavioral bench instances select these identical synchronous mapped implementations. No SDF or physical delays.')
        result.update(passed=True,inputs_unchanged=inputs=={p:sha(Path(p)) for p in inputs},
            tool=artifact(args.gowin.resolve()),integration_criterion='Select through an explicit new M provider/configuration, verify existing endpoint result ready/valid and full paired CDC, then synthesize and route a fresh complete candidate. Retire this probe as acceptance evidence at integration; preserve it only as isolated A/B provenance.')
        if not result['inputs_unchanged']:raise RuntimeError('source drift')
    except Exception as error:result['error']=str(error);raise
    finally:(output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--reference-source',type=Path,required=True)
    p.add_argument('--reference-sha256',required=True);p.add_argument('--gowin',type=Path,required=True)
    p.add_argument('--gowin-lib',type=Path)
    p.add_argument('--gowin-primitives',type=Path)
    main(p.parse_args())
