`timescale 1ns/1ps
module tb_workstation_runtime_chorus_delay;
  workstation_runtime_chorus_effect u_current(
      .clk_i(1'b0),.rst_ni(1'b0),.clear_i(1'b0),.valid_i(1'b0),.enabled_i(1'b0),
      .left_i(32'sd0),.right_i(32'sd0),.ready_o(),.valid_o(),.active_o(),
      .left_o(),.right_o(),.clip_o(),.config_valid_i(1'b0),.rate_44100_i(1'b0),
      .history_clear_i(1'b0),.config_ready_o(),.config_applied_o(),.history_ready_o(),
      .history_done_o(),.quiescent_o(),.applied_rate_44100_o());
  workstation_previous_chorus_effect u_previous(
      .clk_i(1'b0),.rst_ni(1'b0),.clear_i(1'b0),.valid_i(1'b0),.enabled_i(1'b0),
      .left_i(32'sd0),.right_i(32'sd0),.ready_o(),.valid_o(),.active_o(),
      .left_o(),.right_o(),.clip_o(),.config_valid_i(1'b0),.rate_44100_i(1'b0),
      .history_clear_i(1'b0),.config_ready_o(),.config_applied_o(),.history_ready_o(),
      .history_done_o(),.quiescent_o(),.applied_rate_44100_o());
  workstation_before_affine44_chorus_effect u_before_affine44(
      .clk_i(1'b0),.rst_ni(1'b0),.clear_i(1'b0),.valid_i(1'b0),.enabled_i(1'b0),
      .left_i(32'sd0),.right_i(32'sd0),.ready_o(),.valid_o(),.active_o(),
      .left_o(),.right_o(),.clip_o(),.config_valid_i(1'b0),.rate_44100_i(1'b0),
      .history_clear_i(1'b0),.config_ready_o(),.config_applied_o(),.history_ready_o(),
      .history_done_o(),.quiescent_o(),.applied_rate_44100_o());
  integer rate_index,triangle_index,checks=0,min_tap,max_tap;
  logic [15:0] current_tap,previous_tap,before_affine44_tap;
  logic [31:0] checksum=0;
  longint unsigned physical_q16,expected;
  initial begin
    for(rate_index=0;rate_index<2;rate_index=rate_index+1)begin
      min_tap=65535;max_tap=0;
      for(triangle_index=0;triangle_index<65536;triangle_index=triangle_index+1)begin
        // Invoke functions inside the two actual whole modules. The previous
        // native module is restored byte-exactly, with only its module name changed.
        current_tap=u_current.rate_delay(16'(triangle_index),1'(rate_index));
        previous_tap=u_previous.rate_delay(16'(triangle_index),1'(rate_index));
        before_affine44_tap=u_before_affine44.rate_delay(16'(triangle_index),1'(rate_index));
        // Independent physical-time rational in64 bits; no narrowed formula.
        physical_q16=64'd480*65536+64'(triangle_index)*96;
        expected=rate_index ? (physical_q16*44100+64'd1572864000)/(64'd48000*65536) : physical_q16/65536;
        if(current_tap!==previous_tap || current_tap!==before_affine44_tap || current_tap!==16'(expected))
          $fatal(1,"Chorus delay mismatch rate=%0d triangle=%0d current=%0d previous=%0d physical=%0d",
                 rate_index,triangle_index,current_tap,previous_tap,expected);
        if(current_tap<min_tap)min_tap=32'(current_tap);
        if(current_tap>max_tap)max_tap=32'(current_tap);
        checksum={checksum[26:0],checksum[31:27]}^{16'd0,current_tap};
        checks=checks+1;
      end
      if((rate_index==0 && (min_tap!=480 || max_tap!=575)) ||
         (rate_index==1 && (min_tap!=441 || max_tap!=529)))$fatal(1,"tap coverage incomplete");
      $display("PASS actual Chorus rate_delay rate_index=%0d inputs=65536 taps=%0d..%0d checksum=%h",rate_index,min_tap,max_tap,checksum);
    end
    if(checks!=131072)$fatal(1,"exhaustive domain incomplete");
    $display("PASS actual Chorus rate_delay exhaustive checks=%0d",checks);
    $finish;
  end
endmodule
