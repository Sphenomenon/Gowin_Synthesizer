#!/usr/bin/env python3
"""Bounded public-port tail protocol test and behavioral negative controls."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
RTL=ROOT/'rtl/tf_audio/workstation_tf_physical_tail_v1.sv'
TB=ROOT/'sim/tf_audio/tb_workstation_tf_physical_tail_v1.sv'
CONTRACT=ROOT/'rtl/tf_audio/WORKSTATION_TF_PHYSICAL_TAIL_V1_CONTRACT.md'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--local-reset',action='store_true');a=ap.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    inputs=[RTL,TB,Path(__file__).resolve()];hashes={str(p):sha(p) for p in inputs}
    result=dict(schema=1,passed=False,input_sha256=hashes,public_endpoint_only=True,real_native_chain=False,physical_CDC_verified=False,hardware_operated=False,cases={})
    original=RTL.read_text()
    mutants={
      'early_compute_observation_EOS':('tail_observed && tail_receipted &&','tail_observed &&'),
      'ignore_physical_sequence':('physical_sequence_i==token_sequence','1\'b1'),
      'ignore_physical_epoch':('physical_epoch_i==token_epoch','1\'b1'),
      'ignore_lifecycle_fence':('if(fence_i)begin','if(1\'b0)begin'),
      'ignore_source_drop_prefix':("reply_prefix!=reply_baseline ||\n                                reply_prefix==32'hffffffff || reply_prefix<reply_baseline","1'b0"),
      'accept_saturated_ARM':("reply_baseline==32'hffffffff","1'b0"),
      'sample_prefix_before_physical_FIFO_edge':('else retire(OK,serial_baseline,observation_source_drops_i,serial_frame_error);','else retire(OK,serial_baseline,serial_baseline,serial_frame_error);'),
    }
    if a.local_reset:
        mutants['raw_compute_reset_bypass']=('wire compute_reset_n=SEPARATE_DOMAIN_RESET ? compute_reset_ni:rst_ni;', 'wire compute_reset_n=rst_ni;')
        mutants['raw_serial_reset_bypass']=('wire serial_reset_n=SEPARATE_DOMAIN_RESET ? serial_reset_ni:rst_ni;', 'wire serial_reset_n=rst_ni;')
    try:
        for name in ['positive',*mutants]:
            folder=out/name;folder.mkdir();source=RTL
            if name!='positive':
                old,new=mutants[name];assert original.count(old)==1,(name,'anchor drift')
                source=folder/'mutant.sv';source.write_text(original.replace(old,new,1))
            compile_cmd=['iverilog','-g2012','-s','tb_workstation_tf_physical_tail_v1','-o',str(folder/'sim.vvp'),str(source),str(TB)]
            if a.local_reset:compile_cmd.insert(1,'-Ptb_workstation_tf_physical_tail_v1.LOCAL_RESET=1')
            p=subprocess.run(compile_cmd,capture_output=True,text=True,timeout=30);(folder/'compile.log').write_text(p.stdout+p.stderr)
            if p.returncode:raise ValueError(name+' must elaborate: '+p.stdout+p.stderr)
            p=subprocess.run(['vvp',str(folder/'sim.vvp')],capture_output=True,text=True,timeout=30);log=p.stdout+p.stderr;(folder/'run.log').write_text(log)
            good=p.returncode==0 and 'PASS physical_tail_endpoint' in log
            if good!=(name=='positive'):raise ValueError(name+' unexpected result '+log)
            result['cases'][name]=dict(expected_result='pass' if name=='positive' else 'behavioral_rejection',observed_returncode=p.returncode,source_sha256=sha(source),VVP_sha256=sha(folder/'sim.vvp'),compile_log_sha256=sha(folder/'compile.log'),run_log_sha256=sha(folder/'run.log'))
            print(('PASS ' if good else 'REJECTED ')+name,flush=True)
        assert hashes=={str(p):sha(p) for p in inputs},'input drift';result['passed']=True
    finally:(out/'verification.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
if __name__=='__main__':main()
