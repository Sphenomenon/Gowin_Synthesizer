`timescale 1ns/1ps
module tb_workstation_request_epoch_delivery;
  reg clk=0,rst_n=0,tick=0,render_valid=0;
  reg [9:0] epoch=0;
  wire valid;
  wire signed [31:0] left_o,right_o;
  always #5 clk=~clk;
  workstation_frame_delivery #(.REQUEST_EPOCH_SNAPSHOT(1)) dut(
      .clk_i(clk),.rst_ni(rst_n),.sample_ce_i(tick),.muted_i(1'b0),
      .cancel_epoch_i(epoch),.render_valid_i(render_valid),.left_i(32'sd123),.right_i(-32'sd456),
      .reference_i(32'd0),.voices_i(32'd1),.valid_o(valid),.left_o,.right_o,
      .reference_o(),.voices_o(),.duplicate_frames_o());
  task automatic drive(input logic accept,input logic [9:0] next_epoch,input logic result,
                       input logic expected_valid,input logic zero);
    begin
      @(negedge clk);tick=accept;epoch=next_epoch;render_valid=result;#1;
      if(valid!==expected_valid)$fatal(1,"request epoch completion identity mismatch");
      if(valid && {left_o,right_o} !== (zero ? 64'd0 : {32'sd123,-32'sd456}))
        $fatal(1,"request epoch payload mismatch");
      @(posedge clk);#1;
    end
  endtask
  initial begin
    repeat(3)@(negedge clk);rst_n=1;
    // A pending old epoch observation must not consume a newly accepted slot.
    drive(1,10'd7,0,0,0);drive(0,10'd7,0,0,0);drive(0,10'd7,1,1,0);
    // A new PANIC after acceptance cancels once and suppresses late render.
    drive(1,10'd7,0,0,0);drive(0,10'd8,0,1,1);drive(0,10'd8,1,0,1);
    // Consecutive accepts rebuild identity, including ten-bit epoch wrap.
    drive(1,10'd1023,0,0,0);drive(1,10'd0,0,0,0);drive(0,10'd0,1,1,0);
    $display("PASS workstation_request_epoch_delivery: old_epoch_accept new_panic late_result consecutive_accept wrap");
    $finish;
  end
endmodule
