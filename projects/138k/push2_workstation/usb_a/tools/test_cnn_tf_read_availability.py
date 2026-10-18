#!/usr/bin/env python3
"""Prove grouped TF read-count comparisons for all64inputbits, including wrap."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from cnn_ddr_pipeline_patch import (TF_BYTE_COUNT_HELPER,TF_DMA,retime_tf_write_buffer,
    parallel_tf_byte_counters,retime_tf_read_total,fast_tf_read_availability)
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--build',type=Path);a=p.parse_args()
original=(BASE/TF_DMA).read_text()
patched=fast_tf_read_availability(retime_tf_read_total(parallel_tf_byte_counters(retime_tf_write_buffer(original))))
if a.build:
    from build_workstation_flash_boot import expected_tf_dma
    build=a.build.resolve();metadata=json.loads((build/'build_metadata.json').read_text())
    assert metadata.get('fast_tf_read_availability') and metadata.get('retimed_tf_read_total')
    patched=(build/'Prj1'/TF_DMA).read_text()
    assert patched==expected_tf_dma(metadata),'candidate TF source drift'
block=re.search(r'    wire \[31:0\] read_plus32=.*?    wire read_has_full_beat = !available_lt32;',patched,re.S)[0]
body='''module miter(input[31:0]write_total_bytes,read_total_bytes,output equal);
'''+TF_BYTE_COUNT_HELPER+'\n'+block+'''
wire[31:0]delta=write_total_bytes-read_total_bytes;
assign equal=(available_lt32==(delta<32'd32)) &&
             ((write_total_bytes!=read_total_bytes)==(delta!=0));
endmodule
'''
with tempfile.TemporaryDirectory(prefix='cnn_tf_availability_sat_') as tmp:
    source=Path(tmp)/'miter.sv';source.write_text(body)
    command=f'read_verilog -sv {source}; hierarchy -top miter; proc; flatten; opt; check -assert; sat -verify -prove equal 1 -show-inputs'
    run=subprocess.run(['yosys','-p',command],capture_output=True,text=True,timeout=120)
    assert run.returncode==0 and 'SUCCESS!' in run.stdout,run.stdout+run.stderr
result=dict(passed=True,source_bound=bool(a.build),build=str(a.build) if a.build else None,hardware_tested=False,pcm_saved=False,added_cycles=0,
    proof='SAT all64inputbits: unsigned modulo delta<32 and nonzero,including every wrap and low5-bit borrow',
    miter_sha256=hashlib.sha256(body.encode()).hexdigest(),
    original_source_sha256=hashlib.sha256(original.encode()).hexdigest(),
    patched_source_sha256=hashlib.sha256(patched.encode()).hexdigest())
if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
