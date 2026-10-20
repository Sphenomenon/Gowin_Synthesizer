#!/usr/bin/env python3
"""SAT proof of request-time next byte count for every32bitcount/eof pattern."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from cnn_ddr_pipeline_patch import (TF_BYTE_COUNT_HELPER,TF_DMA,retime_tf_read_total,
    parallel_tf_byte_counters,retime_tf_write_buffer)
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path)
p.add_argument('--build',type=Path)
a=p.parse_args()
original=(BASE/TF_DMA).read_text()
patched=retime_tf_read_total(parallel_tf_byte_counters(retime_tf_write_buffer(original)))
if a.build:
    build=a.build.resolve();metadata=json.loads((build/'build_metadata.json').read_text())
    patched=(build/'Prj1'/TF_DMA).read_text()
    if metadata.get('bus_timing'):
        from workstation_bus_timing import expected_dma,INPUTS,HELPER_SHA256
        assert metadata['bus_timing']['original_sha256']==INPUTS
        assert hashlib.sha256((ROOT/'tools/cnn_ddr_pipeline_patch.py').read_bytes()).hexdigest()==HELPER_SHA256
        assert patched==expected_dma(original),'workstation TF transformation drift'
        assert hashlib.sha256(patched.encode()).hexdigest()==metadata['bus_timing']['transformed_sha256'][TF_DMA]
    else:
        from build_workstation_flash_boot import expected_tf_dma
        assert metadata.get('retimed_tf_read_total') and metadata.get('parallel_tf_byte_counters')
        assert patched==expected_tf_dma(metadata),'TF differs from audited transformation'

helper=re.search(r'    function \[31:0\] add_byte_count;.*?    endfunction',patched,re.S)[0]
from cnn_ddr_pipeline_patch import TF_NIBBLE_COUNT_HELPER
assert helper+'\n' in (TF_BYTE_COUNT_HELPER,TF_NIBBLE_COUNT_HELPER),'actual carry helper drift'
expression=re.search(r'wire \[31:0\] read_total_after_accept=(.*?);',patched,re.S)[1]
for old,new in [('eof_finalized','eof'),('available_bytes','available'),
                ('write_total_bytes','write_count'),('read_total_bytes','read_count')]:
    expression=expression.replace(old,new)
availability_block=''
if 'wire available_lt32=' in patched:
    availability_block=re.search(r'    wire \[31:0\] read_plus32=.*?    wire read_has_full_beat = !available_lt32;',patched,re.S)[0]
    availability_block=availability_block.replace('write_total_bytes','write_count').replace('read_total_bytes','read_count')
body="""module miter(input [31:0] read_count,write_count,input eof,output equal);
"""+helper+availability_block+"""
wire [31:0] available=write_count-read_count;
wire [5:0] bytes=(eof && available<32) ? available[5:0] : 6'd32;
wire [31:0] original=read_count+{26'd0,bytes};
wire [31:0] prepared="""+expression+""";
assign equal=original==prepared;
endmodule
"""
with tempfile.TemporaryDirectory(prefix='cnn_tf_read_count_sat_') as tmp:
    source=Path(tmp)/'miter.sv';source.write_text(body)
    command=f'read_verilog -sv {source}; hierarchy -top miter; proc; flatten; opt; check -assert; sat -verify -prove equal 1 -show-inputs'
    run=subprocess.run(['yosys','-p',command],capture_output=True,text=True,timeout=120)
    assert run.returncode==0 and 'SUCCESS!' in run.stdout,run.stdout+run.stderr
result=dict(passed=True,source_bound=bool(a.build),build=str(a.build) if a.build else None,
    hardware_tested=False,pcm_saved=False,added_cycles=0,
    proof='SAT all65inputbits from actual next-count expression; full/partial/eof/32bitwrap',
    miter_sha256=hashlib.sha256(body.encode()).hexdigest(),
    original_source_sha256=hashlib.sha256(original.encode()).hexdigest(),
    patched_source_sha256=hashlib.sha256(patched.encode()).hexdigest())
if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
