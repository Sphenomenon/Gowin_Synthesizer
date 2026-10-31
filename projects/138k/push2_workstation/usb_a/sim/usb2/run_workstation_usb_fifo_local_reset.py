#!/usr/bin/env python3
"""Real FIFO/owner stop-clock regression, negative controls and Gowin gate."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.workstation_baselines import load_baseline
from tools.workstation_resource_timing import event_fifo
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools import workstation_usb_fifo_reset as policy


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok:raise ValueError('USB FIFO local-reset regression: '+message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True,help='Existing prepared support; read only')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gw-sh',type=Path)
    args=parser.parse_args();out=args.output.resolve();project=args.project.resolve()
    require(not out.exists() and ROOT not in out.parents,'new evidence directory outside source required')
    out.mkdir(parents=True)
    source=ROOT/policy.SOURCE;bench=Path(__file__).with_name('tb_workstation_usb_fifo_local_reset.sv')
    owner_bench=Path(__file__).with_name('tb_workstation_usb_stop_clock_fence.sv')
    originals=[source,bench,owner_bench,Path(__file__).resolve(),ROOT/policy.TOOL,
        ROOT/'tools/workstation_resource_timing.py',ROOT/'tools/workstation_synthesis_netlist.py',
        ROOT/'tools/workstation_runtime_pcm_cdc.py']
    owner_sources=[ROOT/name for name in ('rtl/push2_usb_a_control.sv','rtl/audio/push2_controls.sv',
        'rtl/workstation/workstation_usb2_service_adapter.sv','rtl/display_data/push2_surface_pixels.sv',
        'rtl/control/workstation_session.sv')]
    owner_sources += [ROOT/'rtl/push2'/name for name in ('push2_playlist_hold.sv','push2_song_menu.sv',
        'push2_score_guide.sv','push2_lights.sv','push2_led_tx.sv','push2_song_screen.sv')]
    support=[project/name for name in ('src/migration/gw138k_stream_cdc.sv',
        'src/push2/push2_midi_rx.sv','src/video/video_font_5x7.v')]
    originals+=owner_sources+support
    identities={str(p):sha(p) for p in originals}
    old=event_fifo(load_baseline(ROOT,'resource_rework_route0').read_bytes(policy.FIFO).decode()).encode()
    require(policy.adapt(old)==old and policy.sha(old)==policy.INPUT_SHA256,'default generated FIFO changed')
    fifo=out/'fifo.v';fifo.write_bytes(policy.adapt(old,enabled=True))
    local_source=out/source.name;shutil.copyfile(source,local_source)
    local_bench=out/bench.name;shutil.copyfile(bench,local_bench)
    copied=[]
    for index,p in enumerate(owner_sources+support):
        target=out/f'owner_{index}_{p.name}';shutil.copyfile(p,target);copied.append(target)
    copied_owner_bench=out/owner_bench.name;shutil.copyfile(owner_bench,copied_owner_bench)
    result=dict(schema=1,passed=False,policy=policy.POLICY,input_sha256=identities,
        default_generated_fifo_sha256=policy.sha(old),adapted_fifo_sha256=sha(fifo),commands={},
        hardware_tested=False,PNR=False,SRAM_deployed=False,Flash_deployed=False)

    def run(name,command,*,expected=0,cwd=out,env=None,timeout=240):
        result['commands'][name]=list(map(str,command))
        with (out/(name+'.log')).open('w') as stream:
            p=subprocess.run(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
        text=(out/(name+'.log')).read_text()
        require(p.returncode==expected if expected==0 else p.returncode!=0,
                name+' unexpected exit '+str(p.returncode))
        return text

    def compile_and_run(name,src,*,negative=False):
        command=['verilator','--binary','--timing','--timescale-override','1ns/1ps','-j','4',
            '-Wno-fatal','--top-module','tb_workstation_usb_fifo_local_reset','--Mdir',str(out/(name+'_obj')),
            str(fifo),str(src),str(local_bench)]
        run(name+'_compile',command)
        return run(name,[str(out/(name+'_obj/Vtb_workstation_usb_fifo_local_reset'))],expected=1 if negative else 0)

    try:
        log=compile_and_run('two_domains',local_source)
        require('PASS usb_fifo_local_reset: transfers=4 asynchronous_assertions=6 two_edge_releases=4 stopped_usb=1 stopped_audio=1 both_stopped_boundaries=3' in log,
                'incomplete stopped-clock/real-transfer oracle')
        result['two_domain_simulation']=dict(passed=True,asynchronous_assertions=6,transfers=4,
            usb_stop=True,audio_stop=True,both_stopped_boundaries=3,exact_usb_release_edges=2)
        negatives={
            'negative_one_edge':('release_q <= {release_q[0],1\'b1};','release_q <= 2\'b11;','release before two real USB edges'),
            'negative_synchronous_assertion':('always @(posedge clk_i or posedge reset_i)','always @(posedge clk_i)','write state did not assert asynchronously'),
        }
        result['simulation_negative_controls']={}
        for name,(before,after,oracle) in negatives.items():
            text=local_source.read_text();require(text.count(before)==1,'negative source anchor drift')
            mutated=out/(name+'.sv');mutated.write_text(text.replace(before,after,1))
            text=compile_and_run(name,mutated,negative=True)
            require(oracle in text,'negative did not fail its specific oracle: '+name)
            result['simulation_negative_controls'][name]=dict(rejected=True,oracle=oracle)
        run('owner_compile',['verilator','--binary','--timing','--timescale-override','1ns/1ps','-j','4',
            '-Wno-fatal','--top-module','tb_workstation_usb_stop_clock_fence','--Mdir',str(out/'owner_obj'),
            *map(str,copied),str(fifo),str(local_source),str(copied_owner_bench)])
        owner_log=run('owner_run',[str(out/'owner_obj/Vtb_workstation_usb_stop_clock_fence')])
        require('PASS usb_stop_clock_fence:' in owner_log,'real owner/adapter/session oracle missing')
        result['owner_stop_clock_hotplug']=dict(passed=True,summary=[x for x in owner_log.splitlines() if x.startswith('USB_STOP_CLOCK_FENCE ')],
            audio_six_edge_hold_and_six_edge_drain=True,legacy_replay_negative=True,
            concurrent_legacy_and_fenced_instances=True)
        tool=(args.gw_sh or Path(shutil.which('gw_sh') or
            '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE/bin/gw_sh')).resolve()
        require(tool.is_file(),'actual Gowin executable missing')
        env=dict(os.environ);libraries=tool.parent.parent/'lib'
        if libraries.is_dir():env.update(DYLD_LIBRARY_PATH=str(libraries),DYLD_FRAMEWORK_PATH=str(libraries))
        script=out/'run.tcl';script.write_text('set_device GW5AST-LV138PG484AC2/I1 -device_version C\n'
            'set_option -synthesis_tool gowinsynthesis\nset_option -verilog_std sysv2017\n'
            'set_option -top_module gw138k_usb_event_fifo\nset_option -output_base_name fifo\n'
            'add_file -type verilog {'+str(fifo)+'}\nadd_file -type verilog {'+str(local_source)+'}\nrun syn\n')
        text=run('synthesis',[str(tool),str(script)],env=env)
        require(text.count('GowinSynthesis finish')==1 and not re.search(r'^ERROR\b',text,re.M),'actual compiler did not finish')
        vg=out/'impl/gwsynthesis/fifo.vg';n=SynthesisNetlist(vg.read_text(),'gw138k_usb_event_fifo')
        gate=policy.audit_synthesis(n,fifo_scope='fifo/unbuffered')
        result['actual_synthesis']=dict(gate=gate,tool=str(tool),tool_sha256=sha(tool),vg_sha256=sha(vg))
        result['netlist_negative_controls']={}
        release=list(gate['release_registers'].values())
        producer=next(iter(gate['write_groups']['produce_w_bin'].values()))
        for name,path,port,value in (
            ('producer_reset_bypass',producer,'CLEAR',gate['async_assertion_net']),
            ('producer_wrong_clock',producer,'CLK',gate['audio_clock']),
            ('release_wrong_clock',release[0],'CLK',gate['audio_clock']),
            ('release_shortcut',release[1],'D',n.cells[release[0]]['ports']['D']),
            ('memory_admission_bypass',gate['actual_memory_write_pin'].rsplit('/',1)[0],'CEA',"1'b1"),
        ):
            mutant=copy.deepcopy(n);mutant.cells[path]['ports'][port]=value
            try:policy.audit_synthesis(mutant,fifo_scope='fifo/unbuffered')
            except ValueError as error:result['netlist_negative_controls'][name]=dict(rejected=True,error=str(error))
            else:raise ValueError('actual-netlist negative control escaped: '+name)
        require({str(p):sha(p) for p in originals}==identities,'maintained input drift during regression')
        result['passed']=True
    finally:
        result['outputs_sha256']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and not any(x.endswith('_obj') for x in p.relative_to(out).parts)}
        (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),passed=True,actual_write_pointer_registers=13,
        simulation_negative_controls=2,netlist_negative_controls=5)))


if __name__=='__main__':main()
