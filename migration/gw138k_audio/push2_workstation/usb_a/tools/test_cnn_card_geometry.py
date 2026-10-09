#!/usr/bin/env python3
"""Independent exhaustive card animation and text-relative arithmetic checks."""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
from cnn_ddr_pipeline_patch import DASHBOARD,predecode_dashboard,predecode_dashboard_text_coordinates,parallel_dashboard_cards
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);args=p.parse_args()
source=parallel_dashboard_cards(predecode_dashboard_text_coordinates(predecode_dashboard((BASE/DASHBOARD).read_text())))
functions='\n'.join(re.search(r'    function(?: automatic)? \['+width+r'\] '+name+r'\(.*?    endfunction',source,re.S)[0] for width,name in [('10:0','slide'),('10:0','slide_destinations'),('9:0','card_text_relative')])
tb='''module tb;
reg [2:0] effect_mask;reg [5:0] effect_order;
'''+functions+'''
reg [10:0] target,distance,step,expected;reg [10:0] x,position;reg [9:0] text_expected;integer checks=0;
initial begin
 for(integer mask=0;mask<8;mask=mask+1)for(integer order=0;order<64;order=order+1)for(integer id=0;id<3;id=id+1)for(integer pos=0;pos<2048;pos=pos+1)begin
  effect_mask=mask;effect_order=order;position=pos;
  if(!effect_mask[id])target=1120;
  else if(effect_order[1:0]==id)target=64;
  else if(effect_order[3:2]==id)target=400;
  else if(effect_order[5:4]==id)target=736;
  else target=1120;
  distance=position<target ? target-position : position-target;
  step=(distance+11'd3)>>2;if(step>32)step=32;
  expected=position<target ? position+step : position-step;
  if(slide_destinations(position,id)!==expected)$fatal(1,"animation mismatch %d %d %d %d",mask,order,id,pos);
  checks=checks+1;
 end
 for(integer px=0;px<2048;px=px+1)for(integer pos=0;pos<2048;pos=pos+1)begin
  x=px;position=pos;text_expected=x-position-16;
  if(card_text_relative(x,position)!==text_expected)$fatal(1,"card text relative mismatch %d %d",px,pos);
  checks=checks+1;
 end
 $display("PASS card animation all8masks/64orders/3ids/2048positions and all2048x2048 geometry; %0dchecks",checks);$finish;
end
endmodule'''
with tempfile.TemporaryDirectory(prefix='cnn_card_geometry_') as temp:
 folder=Path(temp);(folder/'tb.sv').write_text(tb)
 compile=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(folder/'sim'),str(folder/'tb.sv')],capture_output=True,text=True);assert compile.returncode==0,compile.stdout+compile.stderr
 run=subprocess.run(['vvp',str(folder/'sim')],capture_output=True,text=True,timeout=120);assert run.returncode==0 and 'PASS card animation' in run.stdout,run.stdout+run.stderr
 result=dict(passed=True,hardware_tested=False,pcm_saved=False,dashboard_sha256=hashlib.sha256(source.encode()).hexdigest(),animation_checks=8*64*3*2048,geometry_checks=2048*2048,log=run.stdout.strip())
 if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
