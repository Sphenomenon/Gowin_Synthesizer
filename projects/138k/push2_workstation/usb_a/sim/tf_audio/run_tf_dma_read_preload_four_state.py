#!/usr/bin/env python3
"""Compare complete pinned TF DMA modules over bounded four-state edges."""
from pathlib import Path
import argparse,hashlib,json,subprocess,time
from tf_dma_read_preload_sources import before_read_preload
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
O=parser.parse_args().output.resolve();O.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=ROOT/'rtl/tf_audio/workstation_tf_runtime_dma.sv'
fixture=Path(__file__).with_name('fixtures')/'workstation_tf_runtime_dma_before_read_preload.sv'
tb=Path(__file__).with_name('tb_tf_dma_read_preload_four_state.sv')
header=ROOT/'rtl/ddr_address_map.vh'
assert sha(tb)=='eb54017d2c49774456b92319422b7aeb28c5bca91a0a3b6cea0cdd16715b7d63'
assert before_read_preload(source.read_text())==fixture.read_text()
reference=O/'reference.sv';text=fixture.read_text();anchor='module workstation_tf_runtime_dma #('
assert text.count(anchor)==1
reference.write_text(text.replace(anchor,'module reference_workstation_tf_runtime_dma #(',1))
I=O/'src/memory';I.mkdir(parents=True);(I/header.name).write_bytes(header.read_bytes())
inputs=[source,fixture,tb,header,Path(__file__).resolve(),Path(__file__).with_name('tf_dma_read_preload_sources.py')]
before={str(p):sha(p)for p in inputs}
for p in inputs:
    copy=O/'inputs'/p.relative_to(ROOT);copy.parent.mkdir(parents=True,exist_ok=True);copy.write_bytes(p.read_bytes())
mutations={
 'overwrite_valid':("1'b1: begin end","1'b1: read_buf <= app_rdata;"),
 'lose_zero_cycle_preload':("1'b0: read_buf <= app_rdata;","1'b0: if (!read_response) read_buf <= app_rdata;"),
 'lose_unknown_validity_fallback':('default: if (read_response) read_buf <= app_rdata;','default: begin end'),
 'corrupt_preloaded_payload':("1'b0: read_buf <= app_rdata;","1'b0: read_buf <= app_rdata ^ 256'd1;"),
}
runs=[]
for label,bank,mutation in [('scaled',64,None),('hardware_capacity',67108864,None)]+[(k,64,v)for k,v in mutations.items()]:
 selected=source
 if mutation:
  text=source.read_text();a,b=mutation;assert text.count(a)==1;selected=O/(label+'.sv');selected.write_text(text.replace(a,b,1))
 command=['iverilog','-g2012','-I',str(O),'-s','tb_tf_read_preload_four','-Ptb_tf_read_preload_four.BANK_BYTES='+str(bank),'-o',str(O/(label+'.vvp')),str(selected),str(reference),str(tb)]
 begin=time.monotonic();compiled=subprocess.run(command,capture_output=True,text=True,timeout=60);(O/(label+'-compile.log')).write_text(compiled.stdout+compiled.stderr);assert compiled.returncode==0,compiled.stderr
 run=subprocess.run(['vvp',str(O/(label+'.vvp'))],capture_output=True,text=True,timeout=600);log=run.stdout+run.stderr;(O/(label+'.log')).write_text(log)
 passed=(run.returncode!=0 and 'preload 'in log and ' differs 'in log)if mutation else(run.returncode==0 and 'PASS actual twin preload four-state:'in log)
 row=dict(label=label,bank_bytes=bank,source_sha256=sha(selected),negative_control=bool(mutation),passed=passed,returncode=run.returncode,elapsed_seconds=time.monotonic()-begin,compile_argv=command,compile_log_sha256=sha(O/(label+'-compile.log')),run_log_sha256=sha(O/(label+'.log')),output=log[-2000:]);runs.append(row)
 (O/'verification.json').write_text(json.dumps(dict(passed=all(r['passed']for r in runs),runs=runs,completed=False,input_sha256=before),indent=2)+'\n')
 print(label,'PASS'if passed else'FAIL',log[-1000:].strip(),flush=True)
 assert passed,row
assert all(sha(Path(p))==h for p,h in before.items())
(O/'verification.json').write_text(json.dumps(dict(passed=True,runs=runs,completed=True,input_sha256=before,inputs_unchanged=True,bounded_four_state_simulation=True,formal_all_four_state_proof=False,EDA_started=False,hardware_tested=False),indent=2)+'\n')
