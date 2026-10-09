#!/usr/bin/env python3
"""Compare the actual original/staged song start control HDL every cycle."""
from pathlib import Path
import subprocess,tempfile,json,argparse,sys,hashlib
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'tools'))
from build_workstation_flash_boot import retime_start_delay
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
source=root/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1/src/push2/gw138k_push_workstation_top.v';old=source.read_text();new=retime_start_delay(old)
def control(text,name):
 start=text.index('    reg music_model_ready_q;');end=text.index('    assign debug_uart_tx=');body=text[start:end]
 body=body.replace('    reg [2:0] music_run_reset_count;','    reg [2:0] music_run_reset_count;\n    reg song_pending;')
 return f'''module {name}(input clk_50m,reset_n,input [3:0] music_model_status,input tf_scope_cancel,tf_card_lost,playlist_scan_done,input [3:0] tf_track_count,input song_cmd_valid,tf_mode_50,input [3:0] song_cmd_index,output enabled);
'''+body+'\nassign enabled=music_analysis_enable;\nendmodule\n'
tb='''module tb;
reg clk=0,rst=0;always #10 clk=~clk;
reg [3:0] status=0,tracks=0,index=0;
reg cancel=0,lost=0,scan=0,cmd=0,mode=0;
wire x,y;
original a(clk,rst,status,cancel,lost,scan,tracks,cmd,mode,index,x);
retimed b(clk,rst,status,cancel,lost,scan,tracks,cmd,mode,index,y);
reg [31:0] random_state=32'h19021009;integer count;
task randomize;begin random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};end endtask
initial begin
 repeat(3)@(negedge clk);rst=1;
 for(integer i=0;i<30000;i=i+1)begin
  @(negedge clk);
  randomize();status=random_state[0]?14:0;cancel=random_state[1]&random_state[5];lost=random_state[2]&random_state[6];scan=random_state[3];tracks=random_state[7:4];cmd=random_state[8];mode=random_state[9];index=random_state[13:10];
  // Include forced counter boundaries and coincident controls; the predicate
  // must agree both immediately before and after the real original clock edge.
  case(i%7)0:count=0;1:count=1;2:count=2;3:count=2500000;4:count=2499999;default:count=random_state[21:0];endcase
  a.music_restart_delay=count;b.music_restart_delay=count;b.music_delay_expired=count==0;
  #1;if(x!==y)$fatal(1,"preedge predicate mismatch cycle%0d",i);
  if(i%211==0)begin rst=0;#1;if(x!==y)$fatal(1,"async reset mismatch");end
  @(posedge clk);#1;
  if(x!==y || b.music_delay_expired!==(a.music_restart_delay==0))$fatal(1,"start predicate mismatch cycle%0d original%0d retimed%0d zero%b",i,a.music_restart_delay,b.music_restart_delay,b.music_delay_expired);
  if({a.music_model_ready_q,a.music_restart_delay,a.music_run_reset_count,a.music_song_started,a.tf_song_restart,a.song_pending,a.tf_selected_track,a.pending_track,a.tf_recover,a.tf_recover_wait} !== {b.music_model_ready_q,b.music_restart_delay,b.music_run_reset_count,b.music_song_started,b.tf_song_restart,b.song_pending,b.tf_selected_track,b.pending_track,b.tf_recover,b.tf_recover_wait})$fatal(1,"control state changed");
  rst=1;
 end
 $display("PASS start-delay actual HDL,30000 cycles,all control registers,0/1/2/load/random boundaries,coincident controls,resets,no latency change");$finish;
end
endmodule
'''
with tempfile.TemporaryDirectory(prefix='cnn_start_delay_') as temp:
 temp=Path(temp);code=temp/'tb.sv';code.write_text('`timescale 1ns/1ps\n'+control(old,'original')+control(new,'retimed')+tb);exe=temp/'sim'
 c=subprocess.run(['iverilog','-g2012','-s','tb','-o',str(exe),str(code)],capture_output=True,text=True);assert c.returncode==0,c.stdout+c.stderr
 v=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=15);assert v.returncode==0 and 'PASS start-delay actual HDL' in v.stdout,v.stdout+v.stderr
 d=dict(passed=True,cycles=30000,source_sha256=hashlib.sha256(old.encode()).hexdigest(),patched_top_sha256=hashlib.sha256(new.encode()).hexdigest(),log=v.stdout.strip(),hardware_tested=False)
 if a.output:a.output.write_text(json.dumps(d,indent=2)+'\n')
 print(json.dumps(d,indent=2))
