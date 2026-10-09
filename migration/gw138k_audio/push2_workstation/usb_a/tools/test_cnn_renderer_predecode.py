#!/usr/bin/env python3
"""Two complete raster streams compare under independent random DDR stalls."""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
from cnn_ddr_pipeline_patch import DASHBOARD,RENDERER,predecode_dashboard,align_renderer_predecode,predecode_dashboard_text_coordinates,parallel_dashboard_cards,predecode_dashboard_background,predecode_dashboard_wave_heights,predecode_dashboard_dynamic_ink,parallel_renderer_spectrum_address
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--text-coordinates',action='store_true');p.add_argument('--parallel-cards',action='store_true');p.add_argument('--background-coordinates',action='store_true');p.add_argument('--complete-background-coordinates',action='store_true');p.add_argument('--wave-heights',action='store_true');p.add_argument('--dynamic-background-ink',action='store_true');p.add_argument('--pixel-skid',action='store_true');p.add_argument('--analysis-page',action='store_true');p.add_argument('--parallel-spectrum-address',action='store_true');p.add_argument('--build',type=Path);a=p.parse_args()
if (a.parallel_cards or a.background_coordinates) and not a.text_coordinates:p.error('--parallel-cards requires --text-coordinates')
renderer=(BASE/RENDERER).read_text();dashboard=(BASE/DASHBOARD).read_text();new_renderer=align_renderer_predecode(renderer);new_dashboard=predecode_dashboard(dashboard)
if a.text_coordinates:new_dashboard=predecode_dashboard_text_coordinates(new_dashboard)
if a.parallel_cards:new_dashboard=parallel_dashboard_cards(new_dashboard)
if a.background_coordinates:new_dashboard=predecode_dashboard_background(new_dashboard,a.complete_background_coordinates)
if a.wave_heights:new_dashboard=predecode_dashboard_wave_heights(new_dashboard)
if a.dynamic_background_ink:new_dashboard=predecode_dashboard_dynamic_ink(new_dashboard)
if a.parallel_spectrum_address:new_renderer=parallel_renderer_spectrum_address(new_renderer)
skid_source=ROOT/'src/video/feedback_pixel_skid.v'
if a.build:
 assert a.pixel_skid,'source binding requires --pixel-skid'
 build=a.build.resolve();stage=build/'Prj1'
 metadata=json.loads((build/'build_metadata.json').read_text());assert metadata.get('registered_pixel_ready')
 assert (stage/RENDERER).read_text()==new_renderer and (stage/DASHBOARD).read_text()==new_dashboard,'renderer/dashboard differs from tested overlay'
 assert (stage/'src/memory/ddr_frame_writer.v').read_bytes()==(BASE/'src/memory/ddr_frame_writer.v').read_bytes(),'original writer drift'
 skid_source=stage/'src/video/feedback_pixel_skid.v'
ports=[]
for kind,declaration in re.findall(r'(input|output)\s+(?:wire|reg)\s+([^\n]+)',renderer[:renderer.index('    wire snapshot_ready')]):
 width=re.search(r'\[[^]]+\]',declaration);width=width[0] if width else ''
 for name in declaration.replace(width,'').strip().strip(',').split(','):ports.append((kind,width,name.strip()))
instances=[]
for i,module in enumerate(['renderer_original','feedback_renderer']):
 connections=[]
 for kind,width,name in ports:
  if kind=='input':
   value={'clk':'clk','rst_n':'rst','source_clk':'source_clk','source_reset_n':'rst','start':'start',
     'pixel_ready':f'pixel_ready[{i}]','sample_data':"32'h40000000",'sample_valid':'sample_valid',
     'trigger_reference':'trigger','shared_done':"1'b1",'shared_render_wave_data':f'wave[{i}]',
     'shared_render_meta':"256'h44495350000000cf400000000000000500000003000000090000000100000003",
     'shared_render_spectrum_left':"8'd111",'shared_render_spectrum_right':"8'd93",'shared_render_stereo_peaks':"32'h6abc78de",
     'shared_render_image_gain':"3'd2",'shared_render_analysis_valid':"1'b1",'shared_render_image_hit':f'image_hit[{i}]',
     'active_voices':"32'h55aa55aa",'effect_mask':"3'd7",'effect_order':"6'b100100"}.get(name,"'0")
  else:value={'frame_ready':f'frame_ready[{i}]','frame_done':f'done[{i}]','pixel_valid':f'valid[{i}]','pixel_data':f'pixel[{i}]','display_meta':f'meta[{i}]' if a.pixel_skid else '', 'shared_render_read_enable':f'read_enable[{i}]','shared_render_wave_addr':f'wave_addr[{i}]','shared_render_image_addr':f'image_addr[{i}]'}.get(name,'')
  connections.append('.'+name+'('+value+')')
 instances.append(module+f' #(.WIDTH(1920),.HEIGHT(1080),.ENABLE_ANALYSIS({int(a.analysis_page)}),.SHARED_EXPORT({int(a.analysis_page)}),.SHARED_WAVE_ZERO_BITS(15),.SHARED_RENDER(1)) r'+str(i)+'('+','.join(connections)+');')
tb=r'''`timescale 1ns/1ps
module tb;
reg clk=0,source_clk=0,rst=0,start=0,sample_valid=0;reg [31:0] trigger=1;
always #5 clk=~clk;always #10 source_clk=~source_clk;
wire [1:0] frame_ready,done,valid,read_enable;reg [1:0] pixel_ready=0;
wire [63:0] pixel[0:1];wire [8:0] wave_addr[0:1];wire [15:0] image_addr[0:1];
reg [31:0] wave[0:1];reg [1:0] image_hit=0;integer count[0:1],completion[0:1],compared=0;
reg [63:0] prior[0:1];reg [1:0] stalled=0;reg [63:0] stream0[0:1036799],stream1[0:1036799];reg [31:0] random_state=32'h709f031b;
__INSTANCES__
always @(negedge clk)if(rst)begin random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);pixel_ready={random_state[5]|random_state[4],random_state[1]|random_state[0]};end
always @(posedge clk)begin
 for(integer i=0;i<2;i=i+1)begin
  if(read_enable[i])begin wave[i]<=32'h23400000^(wave_addr[i]<<17);image_hit[i]<=^image_addr[i];end
  if(rst)begin
   if(stalled[i] && (!valid[i] || pixel[i]!==prior[i]))$fatal(1,"raster changed under stall");
   stalled[i]=valid[i]&&!pixel_ready[i];prior[i]=pixel[i];
   if(valid[i] && pixel_ready[i])begin
    if(i==0)begin
     if(r0.output_x!==(count[i]%960)*2 || r0.output_y!==count[i]/960)$fatal(1,"original raster order");stream0[count[i]]=pixel[i];
    end else begin
     if(r1.output_x!==(count[i]%960)*2 || r1.output_y!==count[i]/960)$fatal(1,"retimed raster order");stream1[count[i]]=pixel[i];
    end
    count[i]=count[i]+1;
   end
   if(done[i])begin if(count[i]!=1036800)$fatal(1,"frame length/completion");completion[i]=completion[i]+1;end
  end
 end
 while(compared<count[0] && compared<count[1])begin
  if(stream0[compared]!==stream1[compared])$fatal(1,"raster data mismatch at%0d expected%h got%h",compared,stream0[compared],stream1[compared]);compared=compared+1;
 end
end
initial begin
 count[0]=0;count[1]=0;completion[0]=0;completion[1]=0;wave[0]=0;wave[1]=0;
 #31;rst=1;
 for(integer i=0;i<1024;i=i+1)begin @(negedge source_clk);sample_valid=1;trigger=i==0?3:1;end
 @(negedge source_clk);sample_valid=0;
 wait(&frame_ready);@(negedge clk);start=1;@(negedge clk);start=0;
 wait(completion[0]==1 && completion[1]==1);repeat(4)@(negedge clk);
 if(compared!=1036800 || valid)$fatal(1,"stream drain mismatch");
 $display("PASS renderer1036800two-pixelbeats,complete1920x1080,independentDDRstalls,orderedvalid/last/address,bitexactpixelcontent");$finish;
end
initial begin #30000000;$fatal(1,"raster timeout");end
endmodule'''.replace('__INSTANCES__','\n'.join(instances))
if a.pixel_skid:
 tb=tb.replace('reg [1:0] pixel_ready=0;','wire [1:0] pixel_ready;')
 tb=tb.replace('wire [63:0] pixel[0:1];','wire [63:0] pixel[0:1];wire [255:0] meta[0:1];')
 begin=tb.index('always @(negedge clk)if(rst)begin')
 end=tb.index('always @(posedge clk)begin',begin)
 tb=tb[:begin]+'''wire skid_valid,skid_ready,skid_done;wire [63:0] skid_data;
wire [1:0] requests,pending;reg [1:0] native_ready=0;
wire [28:0] addresses[0:1];wire [255:0] packed_data[0:1];wire [31:0] frames[0:1];
integer native_count[0:1],native_compared=0,cycles=0;
reg [284:0] native0[0:129600],native1[0:129600];
feedback_pixel_skid skid(.clk(clk),.rst_n(rst),.source_valid(valid[1]),.source_ready(pixel_ready[1]),
 .source_data(pixel[1]),.source_done(done[1]),.sink_valid(skid_valid),.sink_ready(skid_ready),.sink_data(skid_data),.sink_done(skid_done));
ddr_frame_writer w0(.clk(clk),.rst_n(rst),.enabled(1'b1),.front_bank(1'b0),.frame_swap(1'b0),
 .renderer_ready(start),.renderer_done(done[0]),.renderer_start(),.pixel_valid(valid[0]),
 .pixel_ready(pixel_ready[0]),.pixel_data(pixel[0]),.display_meta(meta[0]),.req_valid(requests[0]),
 .req_ready(native_ready[0]),.req_addr(addresses[0]),.req_wdata(packed_data[0]),.frame_pending(pending[0]),.rendered_frames(frames[0]));
ddr_frame_writer w1(.clk(clk),.rst_n(rst),.enabled(1'b1),.front_bank(1'b0),.frame_swap(1'b0),
 .renderer_ready(start),.renderer_done(skid_done),.renderer_start(),.pixel_valid(skid_valid),
 .pixel_ready(skid_ready),.pixel_data(skid_data),.display_meta(meta[1]),.req_valid(requests[1]),
 .req_ready(native_ready[1]),.req_addr(addresses[1]),.req_wdata(packed_data[1]),.frame_pending(pending[1]),.rendered_frames(frames[1]));
always @(negedge clk)if(rst)begin
 cycles=cycles+1;random_state=(random_state>>1)^({32{random_state[0]}}&32'h80200003);
 native_ready=cycles%4096<257 ? 0 : {random_state[5]|random_state[4],random_state[1]|random_state[0]};
end
always @(posedge clk)if(rst)begin
 for(integer i=0;i<2;i=i+1)begin
  if(requests[i]&&native_ready[i])begin
   if(native_count[i]>=129601)$fatal(1,"extra DDR command");
   if(i==0)native0[native_count[i]]={addresses[i],packed_data[i]};else native1[native_count[i]]={addresses[i],packed_data[i]};
   native_count[i]=native_count[i]+1;
  end
  if(pending[i] && (native_count[i]!=129601 || count[i]!=1036800))$fatal(1,"frame published before final DDR beat/meta");
 end
 while(native_compared<native_count[0] && native_compared<native_count[1])begin
  if(native0[native_compared]!==native1[native_compared])$fatal(1,"native DDR address/packed RGB565/meta mismatch %0d",native_compared);
  native_compared=native_compared+1;
 end
end
''' + tb[end:]
 tb=tb.replace('count[0]=0;count[1]=0;','native_count[0]=0;native_count[1]=0;count[0]=0;count[1]=0;',1)
 tb=tb.replace('wait(completion[0]==1 && completion[1]==1);','wait(&pending);',1)
 tb=tb.replace('if(compared!=1036800 || valid)', 'if(compared!=1036800 || native_compared!=129601 || frames[0]!=1 || frames[1]!=1 || skid_valid || valid)',1)
 tb=tb.replace('$display("PASS renderer1036800two-pixelbeats,complete1920x1080,independentDDRstalls,orderedvalid/last/address,bitexactpixelcontent")', '$display("PASS renderer1036800two-pixelbeats +129601native DDR commands,complete1920x1080,independent long/native stalls,RGB565/address/meta exact,skid completion after drain")')
with tempfile.TemporaryDirectory(prefix='cnn_renderer_predecode_') as tmp:
 t=Path(tmp);sources=[]
 for name,text in [('before_renderer.v',renderer.replace('module feedback_renderer #','module renderer_original #').replace('feedback_dashboard #','dashboard_original #')),('before_dashboard.v',dashboard.replace('module feedback_dashboard #','module dashboard_original #')),('after_renderer.v',new_renderer),('after_dashboard.v',new_dashboard),('tb.sv',tb)]:
  file=t/name;file.write_text(text);sources.append(file)
 sources += [BASE/'src/video'/n for n in ['feedback_capture.v','feedback_wave_align.v','video_font_5x7.v']]
 if a.pixel_skid:sources += [skid_source,BASE/'src/memory/ddr_frame_writer.v']
 analysis_names=['output_audio_analysis.v','output_audio_capture.v','audio_analysis_rom.v']
 if a.analysis_page:
  if a.build:
   for name in analysis_names:
    assert (stage/'src/video'/name).read_bytes()==(BASE/'src/video'/name).read_bytes(),'frozen analysis source drift'
  sources += [BASE/'src/video'/n for n in analysis_names]
 c=subprocess.run(['verilator','--binary','--timing','-j','4','-Wno-fatal','-I'+str(BASE),'--top-module','tb','--Mdir',str(t/'obj'),*map(str,sources)],capture_output=True,text=True,timeout=120);assert c.returncode==0,c.stdout[-6000:]+c.stderr[-6000:]
 v=subprocess.run([str(t/'obj/Vtb')],capture_output=True,text=True,timeout=120);assert v.returncode==0 and 'PASS renderer' in v.stdout,v.stdout+v.stderr
 report=dict(passed=True,analysis_source_sha256={n:hashlib.sha256((BASE/'src/video'/n).read_bytes()).hexdigest() for n in analysis_names} if a.analysis_page else {},parallel_spectrum_address=a.parallel_spectrum_address,analysis_page=a.analysis_page,source_bound=bool(a.build),build=str(a.build) if a.build else None,pixel_skid=a.pixel_skid,pixel_skid_sha256=hashlib.sha256(skid_source.read_bytes()).hexdigest() if a.pixel_skid else None,frame_writer_sha256=hashlib.sha256((BASE/'src/memory/ddr_frame_writer.v').read_bytes()).hexdigest() if a.pixel_skid else None,predecoded_text_coordinates=a.text_coordinates,parallel_cards=a.parallel_cards,predecoded_background=a.background_coordinates,complete_background_coordinates=a.complete_background_coordinates,predecoded_wave_heights=a.wave_heights,predecoded_dynamic_ink=a.dynamic_background_ink,hardware_tested=False,pcm_saved=False,dashboard_sha256=hashlib.sha256(new_dashboard.encode()).hexdigest(),renderer_sha256=hashlib.sha256(new_renderer.encode()).hexdigest(),log=v.stdout.strip())
 if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
