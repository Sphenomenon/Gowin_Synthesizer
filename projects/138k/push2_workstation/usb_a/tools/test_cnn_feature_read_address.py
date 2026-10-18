#!/usr/bin/env python3
"""Formal equivalence of the actual feature-cache read decoder, all bit patterns.

Extracts original HDL and the deterministic narrow-slot overlay. Yosys SAT
compares read valid/address plus internal row/cell values for all 6-bit states,
18-bit signed rows/columns,11-bit starts,8-bit channels, including overflow and
padding. Does not apply the overlay to a build or operate hardware.
"""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
from cnn_ddr_pipeline_patch import narrow_feature_read_slot
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path)
parser.add_argument('--build',type=Path,help='bind proof to exact frozen narrowed-slot build; rejects drift')
args=parser.parse_args()
original=(BASE/'rtl/music/basic_pitch_pcm_pipeline.sv').read_text()
patched=narrow_feature_read_slot(original)
build=None
if args.build:
 build=args.build.resolve()
 metadata=json.loads((build/'build_metadata.json').read_text())
 assert metadata.get('narrowed_feature_read_slot') and metadata.get('retimed_cache_read'),'build has no supported narrow-slot overlay'
 stage=build/'Prj1/rtl/music/basic_pitch_pcm_pipeline.sv'
 candidate=stage.read_text()
 dwell_old="            dwell_count[dwell_bucket(state)] <= dwell_count[dwell_bucket(state)] + 1'b1;"
 dwell_new="            for (integer i=0;i<8;i=i+1)\n                if (dwell_bucket(state)==i) dwell_count[i] <= dwell_count[i] + 1'b1;"
 expected=patched.replace(dwell_old,dwell_new)
 assert candidate==expected,'candidate pipeline changed beyond proven decoder/parallel telemetry'
 inputs_map=json.loads((build/'workstation_inputs.json').read_text())
 assert hashlib.sha256(stage.read_bytes()).hexdigest()==inputs_map['rtl/music/basic_pitch_pcm_pipeline.sv'],'frozen source hash drift'
 patched=candidate

constants="\n".join(re.findall(r"localparam logic \[5:0\] S_.*?;",original,re.S))
assert 'S_START_REDUCE' in constants and 'S_START_ONSET_OUT' in constants
ports=[('state',6,False),('feature_load_start_row',11,True),
       ('reduce_x_row',18,True),('reduce_x_col',18,True),('reduce_x_channel',8,False),
       ('note_out_x_row',18,True),('note_out_x_col',18,True),('note_out_x_channel',8,False),
       ('onset_out_x_row',18,True),('onset_out_x_col',18,True),('onset_out_channel',8,False)]
def inputs():
 return ',\n'.join(f'input {"signed " if signed else ""}[{bits-1}:0] {name}' for name,bits,signed in ports)
def module(name,source,frames):
 a=source.index("            always_comb begin\n                feature_read_valid = 1'b0;")
 b=source.index('            always_ff @(posedge clk_i) begin',a)
 return f"module {name}("+inputs()+""",
 output reg feature_read_valid,output reg [14:0] feature_read_addr,
 output reg signed [11:0] feature_read_rel,
 output reg [10:0] feature_contour_cell,output reg [9:0] feature_note_cell);
"""+f'localparam integer FRAME_LIMIT={frames},CONTOUR_BINS=264,NOTE_BINS=88;\n'+constants+'\n'+source[a:b]+'\nendmodule\n'
checks=[]
with tempfile.TemporaryDirectory(prefix='cnn_feature_read_sat_') as tmp:
 folder=Path(tmp)
 for frames in (1,172,512):
  body=module('original',original,frames)+module('narrow',patched,frames)
  # Include all observable decoder values, not only addresses used when valid.
  connections=','.join('.'+name+'('+name+')' for name,_,_ in ports)
  outputs=[('feature_read_valid',1),('feature_read_addr',15),('feature_read_rel',12),
           ('feature_contour_cell',11),('feature_note_cell',10)]
  body+='module miter('+inputs()+',output equal,output probe_valid,output [14:0] probe_addr);\n'
  for tag in ('a','b'):
   for name,bits in outputs:body+=f'wire [{bits-1}:0] {tag}_{name};\n'
   con=connections+','+','.join('.'+name+'('+tag+'_'+name+')' for name,_ in outputs)
   body+=f'{"original" if tag=="a" else "narrow"} u_{tag}('+con+');\n'
  body+='assign probe_valid=a_feature_read_valid;assign probe_addr=a_feature_read_addr;\n'
  body+='assign equal='+ ' && '.join(f'(a_{name}==b_{name})' for name,_ in outputs)+';\nendmodule\n'
  source=folder/'miter.sv';source.write_text(body)
  command=f'read_verilog -sv {source}; hierarchy -top miter; proc; flatten; opt; check -assert; sat -verify -prove equal 1 -show-inputs -show-outputs'
  run=subprocess.run(['yosys','-p',command],capture_output=True,text=True,timeout=120)
  assert run.returncode==0 and 'SUCCESS!' in run.stdout,run.stdout+run.stderr
  witnesses=[]
  for state,slot,col,channel,prefix,channels in [(8,4,263,7,'reduce',8),(12,6,87,31,'note_out',32),(16,2,87,32,'onset_out',32)]:
   row=frames-1
   expected=(slot*(264 if prefix=='reduce' else 88)+col)*channels+(channel if prefix!='onset_out' else channel-1)
   sets=f'-set state {state} -set feature_load_start_row {(row-slot)&2047} -set {prefix}_x_row {row} -set {prefix}_x_col {col}'
   channel_name=prefix+'_x_channel' if prefix!='onset_out' else 'onset_out_channel'
   sets+=f' -set {channel_name} {channel}'
   command=f'read_verilog -sv {source}; hierarchy -top miter; proc; flatten; opt; check -assert; sat -verify {sets} -prove probe_valid 1 -prove probe_addr {expected}'
   run=subprocess.run(['yosys','-p',command],capture_output=True,text=True,timeout=120)
   assert run.returncode==0 and 'SUCCESS!' in run.stdout,run.stdout+run.stderr
   witnesses.append(dict(state=state,row=row,relative_slot=slot,column=col,channel=channel,expected_address=expected,valid=True,passed=True))
  checks.append(dict(frame_limit=frames,passed=True,all_input_bits=sum(p[1] for p in ports),nonvacuous_boundary_witnesses=witnesses,
                     proof='combinational SAT,all input bit patterns',
                     extracted_miter_sha256=hashlib.sha256(body.encode()).hexdigest()))
result=dict(passed=True,hardware_tested=False,applied_to_B3=False,pcm_saved=False,
 solver_version=subprocess.check_output(['yosys','-V'],text=True).strip(),
 original_sha256=hashlib.sha256(original.encode()).hexdigest(),
 patched_sha256=hashlib.sha256(patched.encode()).hexdigest(),
 added_cycles=0,checks=checks,build=str(build) if build else None,source_bound=bool(build))
if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
