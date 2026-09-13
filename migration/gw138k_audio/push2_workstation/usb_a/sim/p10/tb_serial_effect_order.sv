`timescale 1ns/1ps
module tb_serial_effect_order;
  logic clk=0,rst_n=0,valid_i=0;
  always #5 clk=~clk;
  logic signed [31:0] sample_i=0;
  logic [2:0] mask=0;
  wire [5:0] order[0:5];
  assign order[0]=6'b10_01_00;
  assign order[1]=6'b01_10_00;
  assign order[2]=6'b10_00_01;
  assign order[3]=6'b00_10_01;
  assign order[4]=6'b01_00_10;
  assign order[5]=6'b00_01_10;
  wire ready[0:5],out_valid[0:5];
  wire signed [31:0] out_l[0:5],out_r[0:5];
  wire ref_ready,ref_valid;
  wire signed [31:0] ref_l,ref_r;
  for(genvar i=0;i<6;i++) begin: variants
    stereo_effects #(.DELAY_BITS(6),.ECHO_SAMPLES(7),.CHORUS_BASE(3),.CHORUS_DEPTH(2),.COMB_A(5),.COMB_B(9)) dut(
      .clk_i(clk),.rst_ni(rst_n),.valid_i(valid_i),.synth_i(sample_i),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
      .synth_gain_i(16'd32768),.pcm_gain_i(16'd0),.effect_mask_i(mask),.effect_order_i(order[i]),
      .ready_o(ready[i]),.valid_o(out_valid[i]),.left_o(out_l[i]),.right_o(out_r[i]),.clip_o());
  end
  stereo_effects #(.DELAY_BITS(6),.ECHO_SAMPLES(7),.CHORUS_BASE(3),.CHORUS_DEPTH(2),.COMB_A(5),.COMB_B(9)) dry_reference(
      .clk_i(clk),.rst_ni(rst_n),.valid_i(valid_i),.synth_i(sample_i),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
      .synth_gain_i(16'd32768),.pcm_gain_i(16'd0),.effect_mask_i(3'b000),.effect_order_i(6'b11_11_11),
      .ready_o(ref_ready),.valid_o(ref_valid),.left_o(ref_l),.right_o(ref_r),.clip_o());
  wire all_ready=ready[0]&ready[1]&ready[2]&ready[3]&ready[4]&ready[5]&ref_ready;
  wire all_valid=out_valid[0]&out_valid[1]&out_valid[2]&out_valid[3]&out_valid[4]&out_valid[5]&ref_valid;
  logic [63:0] signature[0:5];
  integer frame=0,phase_frame,changed_from_dry=0;

  task send_frame(input logic signed [31:0] value);
    begin
      wait(all_ready);@(negedge clk);sample_i=value;valid_i=1;
      @(negedge clk);valid_i=0;wait(all_valid);@(negedge clk);frame=frame+1;
    end
  endtask
  task assert_all_equal_reference;
    begin
      for(integer i=0;i<6;i++)
        if(out_l[i]!==ref_l||out_r[i]!==ref_r)$fatal(1,"bypass/order mismatch instance %0d",i);
    end
  endtask
  function automatic logic signed [31:0] stimulus(input integer n);
    logic signed [63:0] value;
    begin
      value=64'sd190000000*$signed((n*37)%19-9)+64'sd70000000*$signed((n*11)%13-6);
      stimulus=value>64'sd1500000000 ? 32'sd1500000000 :
               value< -64'sd1500000000 ? -32'sd1500000000 : value[31:0];
    end
  endfunction

  initial begin
    for(integer i=0;i<6;i++)signature[i]=64'hcbf29ce484222325;
    repeat(5)@(negedge clk);rst_n=1;
    // Fully bypassed: the order bus must have no effect at all.
    mask=0;
    for(phase_frame=0;phase_frame<96;phase_frame++)begin send_frame(stimulus(phase_frame));assert_all_equal_reference();end
    // One selected effect must sound once and remain independent of which
    // numbered slot its ID occupies in the six permutations.
    mask=1;
    for(phase_frame=0;phase_frame<120;phase_frame++)begin
      send_frame(stimulus(phase_frame+96));
      for(integer i=1;i<6;i++)if(out_l[i]!==out_l[0]||out_r[i]!==out_r[0])$fatal(1,"single delay depends on unused slots");
      if(out_l[0]!=ref_l||out_r[0]!=ref_r)changed_from_dry=1;
    end
    if(!changed_from_dry)$fatal(1,"single enabled effect never changed audio");
    // All effects: every permutation must create its own deterministic result.
    mask=7;
    for(phase_frame=0;phase_frame<360;phase_frame++)begin
      send_frame(stimulus(phase_frame+216));
      if(phase_frame>=96)
        for(integer i=0;i<6;i++)signature[i]<=(signature[i]^out_l[i]^({32'd0,out_r[i]}<<1))*64'h100000001b3;
    end
    for(integer i=0;i<6;i++)for(integer j=i+1;j<6;j++)
      if(signature[i]==signature[j])$fatal(1,"effect permutations %0d and %0d have identical audio signatures",i,j);
    // Clearing all effects retains the previous path only for its 64-frame
    // gain ramp, then converges exactly to the dry reference.
    mask=0;
    for(phase_frame=0;phase_frame<80;phase_frame++)send_frame(stimulus(phase_frame+576));
    assert_all_equal_reference();
    $display("PASS serial effects: bypass exact; single effect once; six orders have six audio signatures; clear fades then exact dry; %0d frames",frame);
    $finish;
  end
  initial begin #20000000;$fatal(1,"timeout frame=%0d",frame);end
endmodule
