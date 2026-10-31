#!/usr/bin/env python3
from pathlib import Path
import subprocess,json,hashlib,re,argparse
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description='Verify boot-only recording DDR authority and pre-grant ledger loss')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
rtl=ROOT/'rtl/memory'
tb=Path(__file__).with_name('tb_recording_ddr_authority.sv')
source=rtl/'workstation_recording_ddr_authority.sv';guard=rtl/'workstation_runtime_memory_guard.sv'
records=[]
cmd=['verilator','--lint-only','--top-module','workstation_recording_ddr_authority',str(source),str(guard)]
p=subprocess.run(cmd,capture_output=True,text=True,timeout=60);(out/'authority_lint.log').write_text(p.stdout+p.stderr)
assert p.returncode==0 and '%Warning-' not in p.stdout+p.stderr,p.stdout+p.stderr
records.append({'name':'lint','command':cmd,'exit_code':p.returncode})
def run(label,phase,which,expect_success=True):
 exe=out/(label+'.vvp')
 cmd=['iverilog','-g2012','-Wall','-s','tb_recording_ddr_authority',f'-Ptb_recording_ddr_authority.PHASE={phase}','-o',str(exe),str(tb),str(which),str(guard)]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
 (out/(label+'_compile.log')).write_text(p.stdout+p.stderr);assert p.returncode==0,p.stdout+p.stderr
 run_cmd=['vvp',str(exe)];p=subprocess.run(run_cmd,capture_output=True,text=True,timeout=60)
 log=out/(label+'.log');log.write_text(p.stdout+p.stderr)
 assert (p.returncode==0)==expect_success,(label,p.stdout,p.stderr)
 if expect_success:assert f'phase={phase} phases=17 checks=666' in p.stdout,p.stdout
 if not expect_success:assert 'FATAL:' in p.stdout
 records.append({'name':label,'compile_command':cmd,'run_command':run_cmd,'exit_code':p.returncode,'expected_success':expect_success,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
 print(label,p.stdout.strip())
for phase in range(10):run(f'authority_phase{phase}',phase,source)
original=source.read_text()
variants=[
 ('boot_seen_cleared_locally','posedge memory_clk_i or negedge root_memory_reset_n)\n        if(!root_memory_reset_n)boot_seen<=0','posedge memory_clk_i or negedge survival_reset_n)\n        if(!survival_reset_n)boot_seen<=0'),
 ('survival_rearms','else if(!boot_seen)epoch_survived<=1;','else epoch_survived<=1;'),
 ('survival_ignores_ledger','root_memory_reset_n && ledger_reset_ni','root_memory_reset_n'),
 ('boot_seen_waits_ready','else if(ledger_reset_ni)boot_seen<=1;','else if(ledger_reset_ni && backend_ready_i)boot_seen<=1;'),
 ('guard_only_prearm_gap','backend_ready_i && survived_control[1]','backend_ready_i'),
 ('guard_local_reset','reset_ni(root_reset_ni)','reset_ni(root_reset_ni && ledger_reset_ni)')]
for label,old,new in variants:
 assert old in original,label
 mutant=out/(label+'.sv');text=original.replace(old,new)
 if label=='boot_seen_cleared_locally':
  declaration='    wire survival_reset_n=root_memory_reset_n && ledger_reset_ni;\n'
  text=text.replace(declaration,'').replace('    reg boot_seen;\n',declaration+'    reg boot_seen;\n')
 if label=='guard_only_prearm_gap':text=text.replace('guard_channel && epoch_survived','root_reset_ni && guard_channel')
 mutant.write_text(text);run(label,3,mutant,False)
(out/'authority_commands.json').write_text(json.dumps(records,indent=2)+'\n')

inputs=[source,guard,tb,Path(__file__).resolve()]
verification={'passed':True,'hardware_tested':False,'synthesis_tested':False,'async_phase_runs':10,'scenarios_per_phase':17,'checks_per_phase':666,'negative_mutants_rejected':len(variants),'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},'commands':records,'limits':'standalone authority RTL only; actual controller reset/drain, full BIST, source integration, routed timing/CDC and hardware are separate acceptance'}
(out/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
