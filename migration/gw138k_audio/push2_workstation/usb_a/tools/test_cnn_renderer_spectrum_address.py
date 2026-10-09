#!/usr/bin/env python3
"""Exact parallel next/current spectrum address SAT proof all2048x2inputs."""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
from cnn_ddr_pipeline_patch import RENDERER,parallel_renderer_spectrum_address,align_renderer_predecode,quiet_shared_analysis_column
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--build',type=Path);a=p.parse_args()
original=(BASE/RENDERER).read_text();patched=parallel_renderer_spectrum_address(original)
if a.build:
 build=a.build.resolve();metadata=json.loads((build/'build_metadata.json').read_text())
 assert metadata.get('parallel_renderer_spectrum_address') and metadata.get('predecoded_dashboard')
 patched=(build/'Prj1'/RENDERER).read_text()
 expected=parallel_renderer_spectrum_address(align_renderer_predecode(original))
 if metadata.get('quiet_shared_analysis_column'):expected=quiet_shared_analysis_column(expected)
 assert patched==expected,'renderer drift'
def block(text):
 start=text.index('    wire [10:0] '+('spectrum_next_x=' if 'spectrum_next_x=' in text else 'next_x='))
 end=text.index('    wire [10:0] image_x=',start)
 return text[start:end]
checks=[]
with tempfile.TemporaryDirectory(prefix='cnn_spectrum_address_sat_') as tmp:
 source=Path(tmp)/'miter.sv'
 for width in (2,64,1920,2048):
  body=''
  for name,text in [('old',original),('fresh',patched)]:
   body+=f'module {name}(input [10:0] issue_x,input advance,output [8:0] spectrum_column);localparam WIDTH={width};\n'+block(text).replace('wire [8:0] spectrum_column=','assign spectrum_column=')+'\nendmodule\n'
  body+='module miter(input [10:0] issue_x,input advance,output equal);wire [8:0] a,b;old o(issue_x,advance,a);fresh f(issue_x,advance,b);assign equal=a==b;endmodule\n'
  source.write_text(body)
  command=f'read_verilog -sv {source}; hierarchy -top miter; proc; flatten; opt; check -assert; sat -verify -prove equal 1 -show-inputs'
  run=subprocess.run(['yosys','-p',command],capture_output=True,text=True,timeout=120)
  assert run.returncode==0 and 'SUCCESS!' in run.stdout,run.stdout+run.stderr
  checks.append(dict(width=width,passed=True,proof='SAT all12inputbits including wrap/range/advance',miter_sha256=hashlib.sha256(body.encode()).hexdigest()))
result=dict(passed=True,source_bound=bool(a.build),build=str(a.build) if a.build else None,hardware_tested=False,pcm_saved=False,added_cycles=0,checks=checks,original_sha256=hashlib.sha256(original.encode()).hexdigest(),patched_sha256=hashlib.sha256(patched.encode()).hexdigest())
if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
