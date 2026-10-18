#!/usr/bin/env python3
"""Inductive transaction-equivalence proof of empty-slot payload sampling."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from cnn_ddr_pipeline_patch import sample_idle_client_payload
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
original=(ROOT/'rtl/music/basic_pitch_ddr_client_queues.sv').read_text()
patched=sample_idle_client_payload(original)
if a.build:
    assert (a.build/'Prj1/rtl/music/basic_pitch_ddr_client_queues.sv').read_text()==patched,'frozen client queue drift'
original=original[original.index('module basic_pitch_ddr_client_slot('):]
patched=patched[patched.index('module basic_pitch_ddr_client_slot('):]
body=original.replace('basic_pitch_ddr_client_slot','original_slot',1)+'\n'+patched.replace('basic_pitch_ddr_client_slot','patched_slot',1)+r'''
module miter(input clk,reset_n,request_valid,request_write,queued_ready,
 input [28:0]request_address,input[255:0]request_data,input[31:0]request_mask,
 output equal);
 wire old_ready,new_ready,old_valid,new_valid;
 wire [317:0]old_payload,new_payload;
 original_slot old_slot(.clk(clk),.reset_n(reset_n),.request_valid(request_valid),
 .request_write(request_write),.request_address(request_address),.request_data(request_data),
 .request_mask(request_mask),.request_ready(old_ready),.queued_valid(old_valid),
 .queued_write(old_payload[317]),.queued_address(old_payload[316:288]),
 .queued_data(old_payload[287:32]),.queued_mask(old_payload[31:0]),.queued_ready(queued_ready));
 patched_slot new_slot(.clk(clk),.reset_n(reset_n),.request_valid(request_valid),
 .request_write(request_write),.request_address(request_address),.request_data(request_data),
 .request_mask(request_mask),.request_ready(new_ready),.queued_valid(new_valid),
 .queued_write(new_payload[317]),.queued_address(new_payload[316:288]),
 .queued_data(new_payload[287:32]),.queued_mask(new_payload[31:0]),.queued_ready(queued_ready));
 assign equal=old_ready==new_ready && old_valid==new_valid &&
    (!old_valid || old_payload==new_payload);
endmodule
'''
with tempfile.TemporaryDirectory(prefix='cnn_idle_slot_sat_')as temp:
    src=Path(temp)/'miter.sv';src.write_text(body)
    command=f'read_verilog -sv {src}; hierarchy -top miter; proc; flatten; async2sync; opt; dffunmap; check -assert; sat -verify -tempinduct -seq 2 -set-init-zero -prove equal 1 -show-inputs'
    run=subprocess.run(['yosys','-p',command],capture_output=True,text=True,timeout=120)
    assert run.returncode==0 and 'SUCCESS!' in run.stdout,run.stdout+run.stderr
report=dict(passed=True,source_bound=bool(a.build),build=str(a.build)if a.build else None,
 hardware_tested=False,pcm_saved=False,added_cycles=0,added_bsram=0,
 proof='Temporal induction of actual old/new slot modules: ready/valid every cycle and all318payload bits whenever queued_valid; arbitrary reset/valid/ready/write/address/data/mask sequences.',
 invalid_slot_payload='unobserved by core; may sample request bus while empty',
 patched_source_sha256=hashlib.sha256(sample_idle_client_payload((ROOT/'rtl/music/basic_pitch_ddr_client_queues.sv').read_text()).encode()).hexdigest(),miter_sha256=hashlib.sha256(body.encode()).hexdigest())
if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
