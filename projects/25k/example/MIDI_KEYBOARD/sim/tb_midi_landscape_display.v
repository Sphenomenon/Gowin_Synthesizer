`timescale 1ns/1ps
// Real 50 MHz, exact 60 Hz scene cadence, physical DDR SPI decoding. Only
// initialization millisecond delays are shortened. No transport acceleration.
module tb_midi_landscape_display;
 reg clk=0,reset=1;
 always #10 clk=~clk;
 reg[26:0]dirty_regions=0;
 wire[8:0]x;wire[7:0]y;
 wire snapshot,ncs,dc,sck,mosi;
 wire[31:0]refreshes,overruns;
 reg[7:0]live_epoch=8'h12,captured_epoch=0;
 reg[15:0]render_pipe[0:3];
 integer pipe_index,scene=0,byte_index=0;
 reg[26:0]expected_mask=0;
 reg[7:0]expected_epoch=0;
 time last_snapshot=0,scene_started=0;
 real dynamic_time_ms=0,full_time_ms=0;
 integer cadence_checks=0,idle_scenes=0;
 midi_landscape_display #(.MS_TICKS(1),.BOOT_MS(1),.POST_INIT_MS(1)) dut(
  .clk(clk),.reset(reset),.pixel_color(render_pipe[3]),.dirty_regions(dirty_regions),
  .remote_enable(1'b0),.tile_valid(1'b0),.tile_ready(),
  .tile_x(9'd0),.tile_y(8'd0),.tile_width(9'd0),.tile_height(8'd0),
  .tile_read_addr(),.tile_read_data(16'd0),.tile_done(),
  .pixel_x(x),.pixel_y(y),.snapshot(snapshot),.completed_refreshes(refreshes),.overrun_count(overruns),
  .lcd_ncs(ncs),.lcd_dc(dc),.lcd_sck(sck),.lcd_mosi(mosi));
 function[15:0]pattern;
  input integer px,py;input[7:0]epoch;
  begin pattern=(px*16'h0131)^(py*16'h075b)^{epoch,epoch^8'h5a};end
 endfunction
 always @(posedge clk)begin
  if(reset)begin
   captured_epoch<=0;dirty_regions<=0;
   for(pipe_index=0;pipe_index<4;pipe_index=pipe_index+1)render_pipe[pipe_index]<=0;
  end else begin
   if(snapshot)begin
    captured_epoch<=live_epoch;
    case(scene)
     1:dirty_regions<=27'd1;
     2,3:dirty_regions<=27'h7fffffe;
     4:dirty_regions<=0;
     5:dirty_regions<=27'd1<<14;
     6:dirty_regions<=27'd1;
     default:dirty_regions<=0;
    endcase
   end
   render_pipe[0]<=pattern(x,y,captured_epoch);
   for(pipe_index=1;pipe_index<4;pipe_index=pipe_index+1)render_pipe[pipe_index]<=render_pipe[pipe_index-1];
  end
 end
 always @(posedge snapshot)begin
  if(expected_mask!=0)$fatal(1,"New snapshot replaced an unfinished scene mask %h",expected_mask);
  scene=scene+1;expected_epoch=live_epoch;byte_index=0;
  if(scene>=3 && scene<=6)begin
   if($time-last_snapshot<16666660 || $time-last_snapshot>16666680)
    $fatal(1,"60 Hz scene interval was %0t",$time-last_snapshot);
   cadence_checks=cadence_checks+1;
  end
  last_snapshot=$time;scene_started=$time;
  case(scene)
   1,6:expected_mask=1;
   2,3:expected_mask=27'h7fffffe;
   4:begin expected_mask=0;idle_scenes=idle_scenes+1;end
   5:expected_mask=27'd1<<14;
   default:expected_mask=0;
  endcase
 end
 integer expected_region,window_count=0,pixel_total=0;
 integer left,right,top,bottom,col_first,col_last,row_first,row_last;
 integer header_index=0,bit_index=0,pixel_index,px,py;
 reg[7:0]shift=0,received,expected;
 reg[15:0]expected_color;
 reg decoding_window=0,byte_dc;
 function[4:0]first_region;
  input[26:0]mask;integer n;
  begin first_region=0;for(n=26;n>=0;n=n-1)if(mask[n])first_region=n;end
 endfunction
 task set_bounds(input integer id);
  begin
   left=0;right=427;top=0;bottom=141;
   if(id==1)begin left=168;right=369;top=7;bottom=13;end
   else if(id>=2 && id<=7)begin left=8+(id-2)*62;right=left+57;top=29;bottom=71;end
   else if(id==8)begin left=8;right=139;top=74;bottom=80;end
   else if(id>=9 && id<=24)begin left=8+(id-9)*23;right=left+19;top=82;bottom=126;end
   else if(id==25)begin left=384;right=419;top=29;bottom=126;end
   else if(id==26)begin left=208;right=297;top=133;bottom=139;end
   col_first=top;col_last=bottom;row_first=427-right;row_last=427-left;
  end
 endtask
 function[7:0]header_byte;
  input integer index;
  begin case(index)
   0:header_byte=8'h36;1:header_byte=0;2:header_byte=8'h20;
   3:header_byte=8'h2a;4:header_byte=0;5:header_byte=col_first+12;6:header_byte=0;7:header_byte=col_last+12;
   8:header_byte=8'h2b;9:header_byte=row_first>>8;10:header_byte=row_first;
   11:header_byte=row_last>>8;12:header_byte=row_last;13:header_byte=8'h2c;default:header_byte=0;
  endcase end
 endfunction
 function header_dc;
  input integer index;
  begin header_dc=!(index==0 || index==2 || index==3 || index==8 || index==13);end
 endfunction
 time last_rise=0,last_fall=0,mosi_changed=0,dc_changed=0,cs_fell=0;
 integer rises=0,falls=0;
 always @(mosi)begin
  if(!reset && last_rise!=0 && $time-last_rise<10)$fatal(1,"MOSI hold <10ns");
  mosi_changed=$time;
 end
 always @(dc)begin
  if(!reset && (sck || bit_index!=0))$fatal(1,"DC changed inside byte");
  if(!reset && last_rise!=0 && $time-last_rise<5)$fatal(1,"DC hold <5ns");
  dc_changed=$time;
 end
 always @(negedge ncs)begin
  cs_fell=$time;
  if(!reset && scene!=0)begin
   if(expected_mask==0)$fatal(1,"Unchanged scene generated SPI traffic");
   expected_region=first_region(expected_mask);set_bounds(expected_region);
   decoding_window=1;header_index=0;byte_index=0;bit_index=0;
  end
 end
 always @(posedge sck)if(!reset)begin
  if(ncs)$fatal(1,"SCK active outside CS");
  if($time-cs_fell<15 || $time-mosi_changed<10 || $time-dc_changed<5)$fatal(1,"SPI setup violation");
  if(last_fall!=0 && $time-last_fall<10)$fatal(1,"SCK low <10ns");
  last_rise=$time;rises=rises+1;
  if(bit_index==0)byte_dc=dc;else if(dc!==byte_dc)$fatal(1,"DC changed inside byte");
  shift={shift[6:0],mosi};bit_index=bit_index+1;
  if(bit_index==8)begin
   received=shift;bit_index=0;
   if(decoding_window)begin
    if(header_index<14)begin
     if(received!==header_byte(header_index) || dc!==header_dc(header_index))
      $fatal(1,"Scene%0d region%0d header%0d got%02h dc%b expected%02h dc%b",scene,expected_region,header_index,received,dc,header_byte(header_index),header_dc(header_index));
     header_index=header_index+1;
    end else begin
     if(!dc)$fatal(1,"Pixel marked as command");
     pixel_index=byte_index/2;
     px=427-(row_first+pixel_index/(col_last-col_first+1));
     py=col_first+pixel_index%(col_last-col_first+1);
     expected_color=pattern(px,py,expected_epoch);
     expected=byte_index[0]?expected_color[7:0]:expected_color[15:8];
     if(received!==expected)$fatal(1,"Scene%0d region%0d pixel%0d byte%0d got%02h expected%02h (%0d,%0d)",scene,expected_region,pixel_index,byte_index[0],received,expected,px,py);
     byte_index=byte_index+1;
    end
   end
  end
 end
 always @(negedge sck)if(!reset && last_rise!=0)begin
  if($time-last_rise!=10)$fatal(1,"50MHz SCK high period %0t",$time-last_rise);
  last_fall=$time;falls=falls+1;
 end
 always @(posedge ncs)if(!reset)begin
  if(sck || bit_index!=0)$fatal(1,"CS ended in byte");
  if(last_rise!=0 && $time-last_rise<15)$fatal(1,"CS hold <15ns");
  if(decoding_window)begin
   if(header_index!=14 || byte_index!=(right-left+1)*(bottom-top+1)*2)
    $fatal(1,"Incomplete region%0d bytes%0d",expected_region,byte_index);
   expected_mask[expected_region]=0;decoding_window=0;window_count=window_count+1;
   pixel_total=pixel_total+byte_index/2;
   if(expected_mask==0)begin
    if(scene==1)full_time_ms=($time-scene_started)/1000000.0;
    if(scene==2 || scene==3)begin
     dynamic_time_ms=($time-scene_started)/1000000.0;
     if(dynamic_time_ms>=16.66666)$fatal(1,"All dynamic regions missed 60Hz deadline: %0fms",dynamic_time_ms);
    end
   end
  end
 end
 initial begin
  repeat(5)@(negedge clk);reset=0;
  wait(scene==1 && byte_index>4000);live_epoch=8'ha7;
  wait(scene==2 && byte_index>1000);live_epoch=8'h44;
  wait(scene==3 && byte_index>1000);live_epoch=8'he3;
  wait(refreshes==6);#1;
  if(expected_mask || window_count!=55 || pixel_total!=194172 || cadence_checks!=4 || idle_scenes!=1)
   $fatal(1,"Coverage windows%0d pixels%0d cadence%0d idle%0d",window_count,pixel_total,cadence_checks,idle_scenes);
  if(overruns!=2)$fatal(1,"Only two full repaints should miss a tick, got%0d",overruns);
  if(!ncs || sck || rises!=falls)$fatal(1,"Physical SPI did not drain");
  $display("PASS display: 60Hz scene cadence; all26 dynamic regions within %0.6fms; full repaint %0.6fms; 55 windows/194172 exact RGB565 pixels, FIFO prefetch, four-stage snapshot coherence, no traffic for unchanged scene, physical50MHz SPI setup/hold",dynamic_time_ms,full_time_ms);
  $finish;
 end
 initial begin #160000000;$fatal(1,"Display timeout scene%0d state%0d pending%h",scene,dut.state,dut.pending);end
endmodule
