#!/usr/bin/env python3
"""Actual Gowin regression for dynamic and fixed HCI capability captures.

This is a compiler regression, not a workstation builder or physical acceptance.
The removed-attribute negative control must reproduce the constant-ready defect.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.workstation_runtime_pcm_cdc import PcmNetlist,Graph,BooleanDiagram

SOURCE=ROOT/'rtl/bluetooth/hci_owner/workstation_hci_host_bootstrap.sv'
TOP='hci_bootstrap_synthesis_top'
ATTRIBUTE='(* syn_preserve=1 *) reg [15:0] host_length,host_count;'


class CaptureGraph(Graph):
    def support(self,net,cuts=(),active=()):
        drivers=self.drivers[net]
        if net not in cuts and net not in self.high|self.low and len(drivers)==1:
            p,port=drivers[0];cell=self.n.cells[p]
            if cell['kind']=='ALU':
                # The maintained Graph already reviews this exact GW5A NE
                # carry equation in inequality_chain; no generic ALU model.
                require(port=='COUT' and cell['parameters'].get('ALU_MODE')=='3' and
                    self.n.pin(p,'I3') in self.low,'unreviewed capture comparator')
                require(net not in active,'capture comparator cycle')
                return set().union(*(self.support(self.n.pin(p,x),cuts,(*active,net))
                    for x in ('I0','I1','CIN')))
        return super().support(net,cuts,active)


class CaptureDiagram(BooleanDiagram):
    def net(self,graph,net,memo=None,active=()):
        memo={} if memo is None else memo
        if net in self.inputs or net in graph.high|graph.low or net in memo:
            return super().net(graph,net,memo,active)
        drivers=graph.drivers[net]
        if len(drivers)==1 and graph.n.cells[drivers[0][0]]['kind']=='ALU':
            p,port=drivers[0];cell=graph.n.cells[p]
            require(port=='COUT' and cell['parameters'].get('ALU_MODE')=='3' and
                graph.n.pin(p,'I3') in graph.low,'unreviewed capture comparator BDD')
            require(net not in active,'capture comparator BDD cycle')
            a,b,carry=(self.net(graph,graph.n.pin(p,x),memo,(*active,net)) for x in ('I0','I1','CIN'))
            memo[net]=self.either(self.different(a,b),carry)
            return memo[net]
        return super().net(graph,net,memo,active)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value,message):
    if not value:
        raise ValueError('HCI capture synthesis regression: '+message)


def wrapper(text,fixed):
    ports=re.search(r'\)\s*\((.*?)\n\);',text,re.S)
    require(ports is not None,'maintained ANSI interface missing')
    declarations=ports[1].replace('output reg','output wire')
    anchor='    input wire [15:0] host_data_length_i,host_packet_count_i,\n'
    require(declarations.count(anchor)==1,'capability interface anchor changed')
    if fixed:
        declarations=declarations.replace(anchor,'')
    return ('module '+TOP+' ('+declarations+'\n);\n'+
        ('wire [15:0] host_data_length_i=16\'d276,host_packet_count_i=16\'d4;\n' if fixed else '')+
        'workstation_hci_host_bootstrap dut (.*);\nendmodule\n')


def inspect(vg,netlist=None):
    n=netlist or PcmNetlist(vg.read_text(),TOP);g=CaptureGraph(n)
    registers={p:c for p,c in n.cells.items() if c['kind'].startswith('DFF')}
    groups={}
    for stem,width in (('elapsed',32),('host_length',16),('host_count',16)):
        found={}
        for p in registers:
            m=re.fullmatch('dut/'+stem+r'_(\d+)_s\d+',p)
            if m:
                require(int(m[1]) not in found,'duplicate capture/timer bit')
                found[int(m[1])]=p
        require(set(found)==set(range(width)),stem+' register inventory lost')
        require(all(n.pin(p,'CLK')==n.canonical('','clk_i') for p in found.values()),
                stem+' capture/timer clock changed')
        groups[stem]=found
    inputs=set()
    for port,direction in n.directions[TOP].items():
        if direction!='input':continue
        limits=n.ranges[TOP].get(port)
        inputs.update(port+'['+str(i)+']' for i in range(min(limits),max(limits)+1)) if limits else inputs.add(port)
    outputs={}
    for port in ('pool_config_valid_o','ready_o','command_valid_o'):
        buffers=[p for p,c in n.cells.items() if c['kind']=='OBUF' and c['ports'].get('O')==port]
        require(len(buffers)==1,'output buffer changed: '+port)
        net=n.pin(buffers[0],'I');support=g.support(net,cuts=inputs)
        # Interleave each captured/input bit to keep equality BDDs linear.
        ordered=[]
        for bit in range(16):
            for stem,formal in (('host_length','host_data_length_i'),('host_count','host_packet_count_i')):
                for leaf in (n.pin(groups[stem][bit],'Q'),formal+'['+str(bit)+']'):
                    if leaf in support and leaf not in ordered:ordered.append(leaf)
        ordered+=sorted(support-set(ordered))
        bdd=CaptureDiagram(ordered);function=bdd.net(g,net)
        require(function not in (0,1),'constant compiler output: '+port)
        outputs[port]=dict(buffer=buffers[0],driver_net=net,support=sorted(support),
            BDD_nodes=len(bdd.nodes),proven_nonconstant=True)
    return dict(registers=len(registers),capture_registers=32,timer_registers=32,
                outputs=outputs,actual_netlist_checked=True)


def run_case(out,name,text,tool,env,*,fixed):
    directory=out/name;directory.mkdir()
    rtl=directory/SOURCE.name;rtl.write_text(text)
    binding=directory/'binding.sv';binding.write_text(wrapper(text,fixed))
    script=directory/'run.tcl'
    script.write_text('set_device GW5AST-LV138PG484AC2/I1 -device_version C\n'
        'set_option -synthesis_tool gowinsynthesis\nset_option -verilog_std sysv2017\n'
        'set_option -top_module '+TOP+'\nset_option -output_base_name bootstrap\n'
        'add_file -type verilog {'+str(rtl)+'}\nadd_file -type verilog {'+str(binding)+'}\nrun syn\n')
    log=directory/'synthesis.log'
    with log.open('w') as stream:
        result=subprocess.run([str(tool),str(script)],cwd=directory,env=env,
            stdout=stream,stderr=subprocess.STDOUT,timeout=240)
    payload=log.read_text()
    require(result.returncode==0 and payload.count('GowinSynthesis finish')==1 and
            not re.search(r'^ERROR\b',payload,re.M),'actual synthesis failed: '+name)
    vg=directory/'impl/gwsynthesis/bootstrap.vg'
    version=re.search(r'//Tool Version "([^"\n]+)"',vg.read_text())
    require(version is not None,'actual tool version missing')
    record=dict(source_sha256=sha(rtl),binding_sha256=sha(binding),script_sha256=sha(script),
        log_sha256=sha(log),vg_sha256=sha(vg),returncode=result.returncode,fixed_capability=fixed,
        tool_version=version[1])
    n=PcmNetlist(vg.read_text(),TOP);g=Graph(n);direct={}
    for port in ('pool_config_valid_o','ready_o','command_valid_o'):
        buffers=[p for p,c in n.cells.items() if c['kind']=='OBUF' and c['ports'].get('O')==port]
        require(len(buffers)==1,'actual output buffer missing: '+port)
        net=n.pin(buffers[0],'I')
        direct[port]=dict(buffer=buffers[0],driver_net=net,
            constant_value=0 if net in g.low else 1 if net in g.high else None)
    record['direct_output_drivers']=direct
    try:record['gate']=inspect(vg,n)
    except ValueError as error:record['gate_error']=str(error)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gw-sh',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    require(not out.exists(),'output must be a new evidence directory')
    require(ROOT not in out.parents,'evidence must be outside source')
    out.mkdir(parents=True)
    tool=args.gw_sh or Path(shutil.which('gw_sh') or
        '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/bin/gw_sh')
    tool=tool.resolve();require(tool.is_file(),'Gowin executable missing')
    env=dict(os.environ);libraries=tool.parent.parent/'lib'
    if libraries.is_dir():
        env['DYLD_LIBRARY_PATH']=str(libraries)
        env['DYLD_FRAMEWORK_PATH']=str(libraries)
    identities={str(path):sha(path) for path in (SOURCE,Path(__file__).resolve(),
        ROOT/'tools/workstation_runtime_pcm_cdc.py',ROOT/'tools/workstation_synthesis_netlist.py')}
    identity=sha(SOURCE);text=SOURCE.read_text();require(text.count(ATTRIBUTE)==1,'reviewed capture attribute missing')
    cases={}
    for name,fixed,source in (('dynamic',False,text),('fixed_276_4',True,text),
            ('negative_attribute_removed',True,text.replace(ATTRIBUTE,'reg [15:0] host_length,host_count;'))):
        cases[name]=run_case(out,name,source,tool,env,fixed=fixed)
    require(all('gate' in cases[x] for x in ('dynamic','fixed_276_4')),'positive synthesis gate failed: '+json.dumps(cases))
    negative=cases['negative_attribute_removed']
    require('elapsed register inventory lost' in negative.get('gate_error','') and
        all(x['constant_value']==0 for x in negative['direct_output_drivers'].values()),
        'removed capture protection did not reproduce the specific compiler defect')
    require(all(sha(Path(path))==value for path,value in identities.items()),
        'maintained source/auditor changed during synthesis')
    report=dict(stage='actual_hci_capability_capture_compiler_regression',source=str(SOURCE),
        source_sha256=identity,input_sha256=identities,tool=str(tool),tool_sha256=sha(tool),cases=cases,
        PNR=False,hardware_tested=False,workstation_acceptance=False,
        outputs_sha256={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),positive_cases=2,negative_rejected=True)))


if __name__=='__main__':main()
