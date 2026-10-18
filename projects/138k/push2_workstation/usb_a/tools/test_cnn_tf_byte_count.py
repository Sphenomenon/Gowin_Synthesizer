#!/usr/bin/env python3
"""SAT proof of32bit+6bit parallel byte counters, all carries/wrap/increments."""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
from cnn_ddr_pipeline_patch import TF_DMA,parallel_tf_byte_counters,nibble_tf_byte_counters
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--nibble-counters',action='store_true');p.add_argument('--build',type=Path);a=p.parse_args()
original=(BASE/TF_DMA).read_text();patched=parallel_tf_byte_counters(original)
if a.nibble_counters:patched=nibble_tf_byte_counters(patched)
if a.build:
 from build_workstation_flash_boot import expected_tf_dma
 metadata=json.loads((a.build/'build_metadata.json').read_text());assert metadata.get('parallel_tf_byte_counters')
 patched=(a.build/'Prj1'/TF_DMA).read_text();assert patched==expected_tf_dma(metadata),'candidate TF changed beyond supported overlays'
helper=re.search(r'    function \[31:0\] add_byte_count;.*?    endfunction',patched,re.S)[0]
body='module miter(input [31:0] value,input [5:0] increment,output equal);\n'+helper+"\nassign equal=add_byte_count(value,increment)==(value+{26'd0,increment});\nendmodule\n"
with tempfile.TemporaryDirectory(prefix='cnn_tf_count_sat_') as tmp:
 source=Path(tmp)/'miter.sv';source.write_text(body)
 command=f'read_verilog -sv {source}; hierarchy -top miter; proc; flatten; opt; check -assert; sat -verify -prove equal 1 -show-inputs'
 run=subprocess.run(['yosys','-p',command],capture_output=True,text=True,timeout=120)
 assert run.returncode==0 and 'SUCCESS!' in run.stdout,run.stdout+run.stderr
result=dict(passed=True,source_bound=bool(a.build),build=str(a.build) if a.build else None,hardware_tested=False,pcm_saved=False,proof='SAT all38inputbits,exactmodulo32bits includingcarryat8/16/24/32,zero/1..63increments',added_cycles=0,
 helper_sha256=hashlib.sha256(helper.encode()).hexdigest(),miter_sha256=hashlib.sha256(body.encode()).hexdigest(),
 original_sha256=hashlib.sha256(original.encode()).hexdigest(),patched_sha256=hashlib.sha256(patched.encode()).hexdigest(),solver_version=subprocess.check_output(['yosys','-V'],text=True).strip())
if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
