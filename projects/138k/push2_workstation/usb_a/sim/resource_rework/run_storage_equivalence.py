#!/usr/bin/env python3
"""Compare recorder/cue cycles and video pixels against immutable RTL."""
from pathlib import Path
import subprocess,json,hashlib,argparse
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'out/resource_storage_equivalence'
BASE=ROOT/'results/timing_p27_uart_cdc_route1_20261018_142516_456857/Prj1'
def main():
    args=argparse.ArgumentParser();args.add_argument('--vendor',action='store_true')
    args.add_argument('--project',type=Path,help='Bind actual staged RTL instead of workspace')
    args.add_argument('--reference',type=Path,default=BASE)
    args.add_argument('--out',type=Path)
    args=args.parse_args()
    project=args.project.resolve() if args.project else ROOT
    reference=args.reference.resolve()
    global OUT
    if args.vendor:OUT=ROOT/'out/resource_storage_vendor'
    if args.out:OUT=args.out.resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    clients=[('audio_capture_fifo','rtl/audio/audio_capture_fifo.sv','legacy/rtl/audio/audio_capture_fifo.sv'),('score_led_player','rtl/input/score_led_player.sv','legacy/rtl/input/score_led_player.sv'),('video_ddr_scanout','rtl/display_data/video_ddr_scanout.v','src/video/video_ddr_scanout.v')]
    sources=[project/'rtl/memory/workstation_sdp.sv']
    for name,new,old in clients:
        ref=OUT/(name+'_reference.sv');ref.write_text((reference/old).read_text().replace('module '+name,'module '+name+'_reference',1))
        sources.extend([project/old if args.project else ROOT/new,ref])
    tb=r'''`timescale 1ns/1ps
module tb_storage;
reg clk=0,pclk=0,rst=0,prst=0;always #5 clk=~clk;always #3.3670035 pclk=~pclk;
reg [31:0] rng=32'h91a367df;
reg enable=0,sample=0,ready=0;reg signed[31:0] l=0,r=0;
wire fv,rv;wire[95:0] fp,rp;wire[31:0] fd,rd;
audio_capture_fifo fifo(clk,rst,enable,sample,l,r,fv,ready,fp,fd);
audio_capture_fifo_reference fifo_ref(clk,rst,enable,sample,l,r,rv,ready,rp,rd);
reg cw=0,cs=0,ct=0,ce=0;reg[7:0] ca=0;reg[63:0] cd=0;reg[8:0] clen=256;
wire cr,rr,cdone,rdone;wire[31:0] cl,rl,cf,rf;
score_led_player score(clk,rst,ce,cw,ca,cd,cs,ct,clen,cr,cdone,cl,cf);
score_led_player_reference score_ref(clk,rst,ce,cw,ca,cd,cs,ct,clen,rr,rdone,rl,rf);
reg pending=1,composite=1,reqready=0,rsp=0,rspr=0;reg[255:0] data=0,datar=0;
reg[11:0] x=0;reg[10:0] y=0;reg de=0,hs=0,vs=0,vblank=0;
wire swap,bank,front,req,fault;wire[28:0] addr;wire[31:0] under;
wire[23:0] rgb;wire ode,oh,ov;
wire swapr,bankr,frontr,reqr,faultr;wire[28:0] addrr;wire[31:0] underr;
wire[23:0] rgbr;wire oder,ohr,ovr;
`define VIDEO_PORTS .clk(clk),.rst_n(rst),.enabled(1'b1),.new_frame_pending(pending),.new_frame_base(29'h10000),.new_composite(composite),.new_analysis_base(29'h20000),.req_ready(reqready),.pixel_clk(pclk),.pixel_rst_n(prst),.pixel_x(x),.pixel_y(y),.data_enable(de),.hsync(hs),.vsync(vs),.vblank_start(vblank)
video_ddr_scanout #(.HEIGHT(8),.EXPLICIT_BASE(1),.GRAPH_FIRST_LINE(2),.GRAPH_END_LINE(6),.TIMEOUT_CYCLES(9000)) video(`VIDEO_PORTS,.rsp_valid(rsp),.rsp_data(data),.frame_swap(swap),.front_bank(bank),.front_valid(front),.req_valid(req),.req_addr(addr),.fetch_fault(fault),.underruns(under),.rgb(rgb),.out_de(ode),.out_hsync(oh),.out_vsync(ov));
video_ddr_scanout_reference #(.HEIGHT(8),.EXPLICIT_BASE(1),.GRAPH_FIRST_LINE(2),.GRAPH_END_LINE(6),.TIMEOUT_CYCLES(9000)) video_ref(`VIDEO_PORTS,.rsp_valid(rspr),.rsp_data(datar),.frame_swap(swapr),.front_bank(bankr),.front_valid(frontr),.req_valid(reqr),.req_addr(addrr),.fetch_fault(faultr),.underruns(underr),.rgb(rgbr),.out_de(oder),.out_hsync(ohr),.out_vsync(ovr));
integer cycle=0,pixels=0,packets=0,cues=0,colored=0,faults=0,requests=0,frames=0;
integer qrhead=0,qrtail=0;reg[28:0] queuer[0:20000];integer duer[0:20000];
integer qhead=0,qtail=0;reg[28:0] queue[0:20000];integer due[0:20000];reg[95:0] expected[0:40000];integer eh=0,et=0;reg[31:0] seq=0;integer drops=0;
always @(negedge clk)if(rst)begin
  cycle=cycle+1;rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
  enable=cycle<500 || rng[1];sample=cycle<700 || rng[2];ready=cycle<400?0:(cycle<1000?1:rng[3]);l=$signed(rng);r=$signed(~rng);
  ce=rng[4];cw=0;cs=0;ct=0;
  if(cycle<=256)begin cw=1;ca=8'(cycle-1);cd={32'(4*(cycle-1)),32'(32'h10001001^(cycle*65537))};end
  if(cycle==260 || cycle==10000 || cycle==20000)cs=1;
  if(cycle==11000)ct=1;
  if(cycle>12000 && cycle<12256)begin cw=1;ca=8'(cycle-12000);cd={32'(cycle-12000),rng};end
  if(cr && cw)$fatal(1,"test must explicitly account for ignored writes");
  reqready=rng[7];rsp=0;rspr=0;
  if(qhead<qtail && cycle>=due[qhead] && (rng[8] || cycle%31<16))begin
    rsp=1;for(integer k=0;k<16;k=k+1)data[k*16+:16]=16'((queue[qhead]>>3)*16+k+1);qhead=qhead+1;
  end
  if(qrhead<qrtail && cycle>=duer[qrhead] && (rng[8] || cycle%31<16))begin
    rspr=1;for(integer k=0;k<16;k=k+1)datar[k*16+:16]=16'((queuer[qrhead]>>3)*16+k+1);qrhead=qrhead+1;
  end
  if(cycle==150000)begin
    if(packets<1000 || fd==0 || cues<250 || colored<20000 || requests<1000 || faults==0 || frames<4)$fatal(1,"coverage packets=%0d drops=%0d cues=%0d pixels=%0d req=%0d faults=%0d frames=%0d",packets,fd,cues,colored,requests,faults,frames);
    $display("PASS storage (100MHz DDR, 148.5MHz pixels, 64-cycle response latency): packets=%0d drops=%0d cues=%0d colored_pixels=%0d requests=%0d fault_cycles=%0d frames=%0d",packets,fd,cues,colored,requests,faults,frames);$finish;
  end
end
always @(posedge clk)if(rst)begin
  if(fv && ready)begin
    if(eh==et || fp!==expected[eh])$fatal(1,"FIFO order at %0d",packets);
    eh=eh+1;packets=packets+1;
  end
  if(enable && sample)begin
    if((et-eh)<256)begin expected[et]={seq,l,r};et=et+1;end else drops=drops+1;
  end
  if(sample)seq=seq+1;
  if(req && reqready)begin
    // Lose one fetched row in frame 5 to exercise timeout and stale row tags.
    if(!(frames==5 && video.fetch_line==3))begin queue[qtail]=addr;due[qtail]=cycle+64;qtail=qtail+1;end
    requests=requests+1;
  end
  if(reqr && reqready && !(frames==5 && video_ref.fetch_line==3)) begin
    queuer[qrtail]=addrr;duer[qrtail]=cycle+64;qrtail=qrtail+1;
  end
  if(video.outstanding>8 || video.response_count>8)$fatal(1,"video response credit overflow");
  #1;
  if({fv,fd}!=={rv,rd} || (fv && fp!==rp))$fatal(1,"FIFO cycle mismatch %0d",cycle);
  if(fd!=drops)$fatal(1,"drop count mismatch");
  if({cr,cdone,cl,cf}!=={rr,rdone,rl,rf})$fatal(1,"cue mismatch");
  if(score.state==3 && score.cue[63:32]<=cf)cues=cues+1;
  // Fetch requests can be throttled by repacking; rendered pixels and sync
  // must retain the reference timing. Each side gets its own DDR response queue.
  if({bank,front}!=={bankr,frontr})$fatal(1,"video frame selection mismatch");
  if(fault)faults=faults+1;
end
always @(negedge pclk)if(prst)begin
  pixels=pixels+1;vblank=0;
  if(x==2175)begin x=0;if(y==9) y=0; else y=y+1; if(y==8)begin vblank=1;frames=frames+1;end end else x=x+1;
  de=x<1920 && y<8;hs=x<2000;vs=y<9;
end
always @(posedge pclk)if(prst)begin
  #1;if({rgb,ode,oh,ov}!=={rgbr,oder,ohr,ovr})$fatal(1,"video pixel mismatch x=%0d y=%0d got=%h ref=%h",x,y,rgb,rgbr);
  if(ode && rgb!=0)colored=colored+1;
end
initial begin repeat(4)@(negedge clk);rst=1;prst=1;end
endmodule
'''
    # Writes while the score is running are intentionally ignored by both clients.
    tb=tb.replace('  if(cr && cw)$fatal(1,"test must explicitly account for ignored writes");','')
    if args.vendor:
        lib=Path.home()/'.local/opt/gowin-1.9.12.03/IDE/simlib/gw5a/prim_sim.v'
        text=lib.read_text();parts=[]
        for name in ('GSR','SDPB'):
            start=text.index('module '+name+' (');end=text.index('endmodule',start)+len('endmodule');parts.append(text[start:end])
        (OUT/'vendor.v').write_text('\n'.join(parts));sources.append(OUT/'vendor.v')
        tb=tb.replace('module tb_storage;','module tb_storage;\nGSR GSR(.GSRI(1\'b1));')
    (OUT/'tb.sv').write_text(tb);sources.append(OUT/'tb.sv')
    cmd=['iverilog','-g2012','-I',str(project if args.project else BASE),'-s','tb_storage','-o',str(OUT/'sim')]+list(map(str,sources))
    if args.vendor:cmd.insert(1,'-DWORKSTATION_SDP_VENDOR_SIM')
    for label,command in [('build',cmd),('simulation',['vvp',str(OUT/'sim')])]:
        with (OUT/(label+'.log')).open('w') as log:p=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if p.returncode:raise RuntimeError((OUT/(label+'.log')).read_text()[-6000:])
    log=(OUT/'simulation.log').read_text();print(log)
    passed='PASS storage (' in log
    (OUT/'summary.json').write_text(json.dumps(dict(passed=passed,log=log.strip(),source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},hardware_tested=False),indent=2)+'\n')
    if not passed:raise SystemExit(1)
if __name__=='__main__':main()
