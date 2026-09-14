`timescale 1ns/1ps

module tb_push_surface_refresh;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'b1;
  logic frame_ready = 1'b0;
  logic [9:0] x = 10'd0;
  logic [7:0] y = 8'd0;
  logic frame_start, pixel_valid;
  logic [15:0] pixel;
  logic [31:0] control = 32'h11223344, options = 32'h55667788;
  logic [63:0] held = 64'h1, display_meta = 64'd0;
  logic [6:0] note = 7'd60, velocity = 7'd64;
  logic display_meta_valid = 1'b0;

  push2_surface_pixels dut(
      .clk, .rst, .frame_ready, .frame_start, .x, .y, .pixel_valid, .pixel,
      .control, .options, .held, .note, .velocity,
      .display_meta, .display_meta_valid);

  task automatic request_frame(input logic [31:0] c, input logic [31:0] o,
      input logic [63:0] p, input logic [6:0] n_i, input logic [6:0] v_i);
    begin
      control = c; options = o; held = p; note = n_i; velocity = v_i;
      @(negedge clk); frame_ready = 1'b1;
      @(negedge clk); frame_ready = 1'b0;
      @(posedge clk);
    end
  endtask

  initial begin
    repeat (2) @(negedge clk);
    rst = 1'b0;
    request_frame(32'h11223344, 32'h55667788, 64'h1, 7'd60, 7'd64);
    if (dut.cs !== 32'h11223344 || dut.op !== 32'h55667788 ||
        dut.pads !== 64'h1 || dut.n !== 7'd60 || dut.v !== 7'd64)
      $fatal(1, "first frame snapshot mismatch");

    // This request arrives while the legacy 5,000,000-cycle timer is busy.
    // It must still commit the new values so the Push UI follows state.
    request_frame(32'haabbccdd, 32'h01020304, 64'h8000000000000000,
                  7'd72, 7'd111);
    if (dut.cs !== 32'haabbccdd || dut.op !== 32'h01020304 ||
        dut.pads !== 64'h8000000000000000 || dut.n !== 7'd72 || dut.v !== 7'd111)
      $fatal(1, "second frame snapshot did not refresh");
    $display("PASS PUSH_SURFACE_REFRESH frame_start=%0d control=%h note=%0d velocity=%0d",
             frame_start, dut.cs, dut.n, dut.v);
    $finish;
  end
endmodule
