`timescale 1ns/1ps
module tb_engine_timing_ab;
  reg clk=0,rstn=0,panic=0,event_valid=0,note_on=0,mode_valid=0,expression_valid=0;
  always #5 clk=~clk;
  reg [1:0] requested_mode=0;
  reg [2:0] profile=0;
  reg [6:0] note=0,velocity=0,pressure_note=0,pressure=0;
  reg [21:0] pitch=22'd1048576;
  reg sample_tick=0,frames_enabled=0;
  integer divider=0;
  wire ready_a,ready_b,mode_ready_a,mode_ready_b,expression_ready_a,expression_ready_b;
  wire sample_ready_a,sample_ready_b,valid_a,valid_b;
  wire signed [31:0] sample_a,sample_b;
  wire [1:0] mode_a,mode_b;
  wire [31:0] allocated_a,allocated_b;
`define PORTS(ready,mode_ready,expression_ready,sample_ready,valid,sample_value,mode_value,allocated) \
    .clk_i(clk),.rst_ni(rstn),.panic_i(panic),.mode_set_valid_i(mode_valid), \
    .mode_set_ready_o(mode_ready),.mode_i(requested_mode),.current_mode_o(mode_value), \
    .event_valid_i(event_valid),.event_ready_o(ready),.event_note_on_i(note_on), \
    .expression_valid_i(expression_valid),.expression_ready_o(expression_ready), \
    .expression_note_i(pressure_note),.expression_value_i(pressure), \
    .event_profile_i(profile),.event_midi_note_i(note),.event_velocity_i(velocity), \
    .pitch_ratio_q20_i(pitch),.sample_ce_i(sample_tick),.sample_ready_o(sample_ready), \
    .sample_valid_o(valid),.sample_o(sample_value),.allocated_mask_o(allocated), \
    .active_mask_o(),.active_voice_count_o(),.load_busy_o(),.mix_busy_o(),.issued_slot_count_o()
  unified_oscillator_engine_reference #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(48000)) old_engine(
      `PORTS(ready_a,mode_ready_a,expression_ready_a,sample_ready_a,valid_a,sample_a,mode_a,allocated_a));
  unified_oscillator_engine #(.EXPRESSION_ENABLE(1),.SAMPLE_RATE_HZ(48000)) new_engine(
      `PORTS(ready_b,mode_ready_b,expression_ready_b,sample_ready_b,valid_b,sample_b,mode_b,allocated_b));
`undef PORTS
  always @(negedge clk) begin
    sample_tick=0;
    if(!rstn || !frames_enabled)divider=0;
    else if(divider==1599)begin divider=0;sample_tick=1;end
    else divider=divider+1;
  end
  reg signed [31:0] expected[0:10000];
  integer head=0,tail=0,checked=0,cases=0,case_start=0;
  always @(posedge clk)begin
    if(!rstn || panic)begin head=0;tail=0;end
    else begin
      if(ready_a!==ready_b || sample_ready_a!==sample_ready_b ||
         mode_ready_a!==mode_ready_b || expression_ready_a!==expression_ready_b)
        $fatal(1,"engine input handshake changed");
      #1;
      if(valid_a)begin expected[tail]=sample_a;tail=tail+1;end
      if(valid_b)begin
        if(head>=tail || sample_b!==expected[head])
          $fatal(1,"PCM differs mode=%0d profile=%0d sample=%0d got=%h expected=%h",requested_mode,profile,checked,sample_b,expected[head]);
        head=head+1;checked=checked+1;
      end
    end
  end
  task automatic midi(input bit on,input [6:0] n,input [6:0] v);
    // Ready depends on Note On versus Off when all 32 slots are allocated.
    @(negedge clk);note_on=on;note=n;velocity=v;#1;
    while(!ready_a || !ready_b)@(negedge clk);
    event_valid=1;
    @(negedge clk);event_valid=0;
  endtask
  task automatic frames(input integer count);
    integer target;
    begin
      target=checked+count;@(negedge clk);frames_enabled=1;
      wait(checked>=target);@(negedge clk);frames_enabled=0;
      repeat(12)@(negedge clk);
      if(head!=tail)$fatal(1,"undelivered PCM after drain");
    end
  endtask
  integer m,p,v;
  initial begin
    repeat(8)@(negedge clk);rstn=1;
    for(m=0;m<3;m=m+1)for(p=0;p<5;p=p+1)begin
$display("START mode=%0d profile=%0d checked=%0d time=%0t",m,p,checked,$time);
      @(negedge clk);requested_mode=m[1:0];mode_valid=1;
      while(!mode_ready_a || !mode_ready_b)@(negedge clk);
      @(negedge clk);mode_valid=0;profile=p[2:0];
      for(v=0;v<32;v=v+1)midi(1,7'(36+v),7'(64+v*2));
      while(!sample_ready_a || !sample_ready_b)@(negedge clk);
      frames(128);
      @(negedge clk);pitch=22'd1110928;
      while(!expression_ready_a || !expression_ready_b)@(negedge clk);
      expression_valid=1;pressure_note=60;pressure=77;
      @(negedge clk);expression_valid=0;
      while(!sample_ready_a || !sample_ready_b)@(negedge clk);
      frames(128);
      for(v=0;v<32;v=v+1)midi(0,7'(36+v),0);
      frames(128);
      @(negedge clk);panic=1;@(negedge clk);panic=0;pitch=22'd1048576;
      repeat(12)@(negedge clk);
      if(allocated_a!==0 || allocated_b!==0)$fatal(1,"PANIC did not release allocation");
      cases=cases+1;$display("DONE mode=%0d profile=%0d checked=%0d time=%0t",m,p,checked,$time);
    end
    $display("PASS engine_timing_ab: %0d modes/profiles, 32 voices, %0d identical PCM samples, bend/pressure/release/PANIC, handshakes unchanged",cases,checked);
    $finish;
  end
  initial begin #150000000;$fatal(1,"engine A/B timeout cases=%0d checked=%0d head=%0d tail=%0d mode=%0d profile=%0d ready=%b%b sample_ready=%b%b enabled=%b tick=%b load=%0d busy=%b",cases,checked,head,tail,requested_mode,profile,ready_a,ready_b,sample_ready_a,sample_ready_b,frames_enabled,sample_tick,new_engine.load_state,new_engine.mix_busy_o);end
endmodule
