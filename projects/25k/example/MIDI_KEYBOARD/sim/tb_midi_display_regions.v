`timescale 1ns/1ps
module tb_midi_display_regions;
 reg clk=0,reset=1,snapshot=0;
 always #5 clk=~clk;
 reg [15:0] keys=16'h1254;
 reg [3:0] channel=3;
 reg signed [7:0] shift=-12;
 reg [6:0] velocity=100,program_number=24;
 reg [1:0] mode=2;
 reg [7:0] brightness=192,strip=128;
 reg [2:0] focus=3;
 reg usb=1,ble=0,touch=1,panic=0;
 reg slider_ready=1,slider_touched=0,slider_overrun=0;
 reg [7:0] raw=132,filtered=128,error=0,general=2,count=8'h7f;
 reg [15:0] theme=16'h07ff,clear=16'h0841;
 wire [26:0] dirty;
 integer checks=0,key_index,old_focus,new_focus;
 reg [26:0] expected;
 reg [15:0] saved_keys;
 midi_display_regions dut(
  .clk(clk),.reset(reset),.snapshot(snapshot),.key_bitmap(keys),
  .midi_channel(channel),.transpose(shift),.velocity(velocity),.program_number(program_number),
  .slider_mode(mode),.brightness(brightness),.strip_value(strip),.focus(focus),
  .usb_online(usb),.ble_online(ble),.touch_ready(touch),.panic_busy(panic),
  .slider_ready(slider_ready),.slider_touched(slider_touched),.slider_overrun(slider_overrun),
  .slider_raw_position(raw),.slider_filtered_position(filtered),.slider_error(error),
  .slider_general_status(general),.slider_sample_count(count),
  .theme_rgb565(theme),.clear_rgb565(clear),.dirty_regions(dirty));

 // All expectations are written from the public scene/region contract.
 // No hierarchical references or DUT comparator expressions are used.
 function [26:0] region;
  input integer index;
  begin region=27'd1<<index;end
 endfunction
 task check_snapshot;
  input [26:0] mask;
  begin
   @(negedge clk);snapshot=1;
   @(posedge clk);#1;
   if(dirty!==mask)$fatal(1,"Snapshot %0d got %h expected %h",checks,dirty,mask);
   checks=checks+1;
   @(negedge clk);snapshot=0;
  end
 endtask
 task check_held;
  input [26:0] mask;
  begin
   repeat(4)begin
    @(posedge clk);#1;
    if(dirty!==mask)$fatal(1,"Mask changed without snapshot: %h expected %h",dirty,mask);
   end
  end
 endtask
 initial begin
  repeat(3)@(negedge clk);reset=0;
  check_held(0);
  check_snapshot(region(0)); // First scene always paints the entire display.
  check_snapshot(0);

  // Each scalar scene field has a separately specified region oracle.
  usb=~usb;check_snapshot(region(1));check_snapshot(0);
  ble=~ble;check_snapshot(region(1));check_snapshot(0);
  touch=~touch;check_snapshot(region(1));check_snapshot(0);
  panic=~panic;check_snapshot(region(1));check_snapshot(0);
  shift=24;check_snapshot(region(2));check_snapshot(0);
  shift=-48;check_snapshot(region(2));check_snapshot(0);
  channel=15;check_snapshot(region(3));check_snapshot(0);
  velocity=1;check_snapshot(region(4));check_snapshot(0);
  mode=1;check_snapshot(region(5)|region(25));check_snapshot(0);
  program_number=127;check_snapshot(region(6));check_snapshot(0);
  brightness=0;check_snapshot(region(7));check_snapshot(0);
  strip=255;check_snapshot(region(25));check_snapshot(0);
  slider_ready=0;check_snapshot(region(8)|region(26));check_snapshot(0);
  slider_touched=1;check_snapshot(region(8));check_snapshot(0);
  raw=255;check_snapshot(region(8));check_snapshot(0);
  filtered=254;check_snapshot(region(8));check_snapshot(0);
  error=8'h80;check_snapshot(region(8)|region(26));check_snapshot(0);
  slider_overrun=1;check_snapshot(region(26));check_snapshot(0);
  general=8'h40;check_snapshot(region(26));check_snapshot(0);
  count=8'hff;check_snapshot(region(26));check_snapshot(0);
  count=0;check_snapshot(region(26));check_snapshot(0); // Counter wraps visibly.

  // Every press and release affects exactly the corresponding logical key.
  for(key_index=0;key_index<16;key_index=key_index+1)begin
   keys=keys^(16'd1<<key_index);check_snapshot(region(9+key_index));
   keys=keys^(16'd1<<key_index);check_snapshot(region(9+key_index));
  end
  keys=~keys;check_snapshot(27'h1fffe00);check_snapshot(0);

  // Exhaust all old/new focus pairs, including invalid values 6 and 7.
  for(old_focus=0;old_focus<8;old_focus=old_focus+1)begin
   focus=old_focus;check_snapshot(expected_focus_mask(old_focus));
   for(new_focus=0;new_focus<8;new_focus=new_focus+1)begin
    expected=0;
    if(new_focus!=old_focus)begin
     expected=region(25);
     if(old_focus<6)expected=expected|region(2+old_focus);
     if(new_focus<6)expected=expected|region(2+new_focus);
    end
    focus=new_focus;check_snapshot(expected);
    focus=old_focus;check_snapshot(expected);
   end
  end

  // The comparator remembers only snapshots: a transient live scene must
  // neither alter the held mask nor contaminate the next comparison.
  check_snapshot(0);saved_keys=keys;
  keys=16'hbeef;channel=0;raw=0;general=0;theme=16'hf800;
  check_held(0);
  keys=saved_keys;channel=15;raw=255;general=8'h40;theme=16'h07ff;
  check_snapshot(0);
  strip=0;check_snapshot(region(25));
  velocity=12;check_held(region(25));
  check_snapshot(region(4));

  // A full repaint suppresses partial masks, while committing all new fields.
  theme=16'hf800;keys=0;error=0;mode=0;
  check_snapshot(region(0));check_snapshot(0);
  clear=16'h0000;usb=~usb;count=8'h33;
  check_snapshot(region(0));check_snapshot(0);
  // Independent, simultaneous dirty regions are retained in one scene mask.
  shift=0;count=8'h34;keys=16'h8001;strip=1;
  check_snapshot(region(2)|region(9)|region(24)|region(25)|region(26));
  check_held(region(2)|region(9)|region(24)|region(25)|region(26));
  @(negedge clk);reset=1;@(posedge clk);#1;
  if(dirty!==0)$fatal(1,"Reset did not clear dirty mask");
  @(negedge clk);reset=0;
  check_snapshot(region(0));check_snapshot(0);
  $display("PASS display regions: %0d snapshots; independent field/key masks, all focus pairs, first/theme/clear repaint, held output, last-snapshot coherence, combined changes and reset",checks);
  $finish;
 end

 // Track only the testbench's last submitted focus, independent of the DUT.
 reg [2:0] oracle_focus=3;
 always @(posedge clk)if(!reset && snapshot)oracle_focus<=focus;
 function [26:0] expected_focus_mask;
  input integer next_focus;
  reg [26:0] mask;
  begin
   mask=0;
   if(next_focus!=oracle_focus)begin
    mask=region(25);
    if(oracle_focus<6)mask=mask|region(2+oracle_focus);
    if(next_focus<6)mask=mask|region(2+next_focus);
   end
   expected_focus_mask=mask;
  end
 endfunction
 initial begin #100000;$fatal(1,"Region simulation timeout");end
endmodule
