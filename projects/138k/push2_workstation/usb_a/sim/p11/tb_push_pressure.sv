`timescale 1ns/1ps

module tb_push_pressure;
  logic clk = 1'b0;
  always #10.416 clk = ~clk;
  logic rst = 1'b1;
  logic connected = 1'b0;
  logic valid = 1'b0;
  logic ready;
  logic [3:0] kind = 0, cable = 0, channel = 0;
  logic [6:0] a = 0, b = 0;
  logic [31:0] actual_control = 0, actual_options = 0;
  logic event_valid, event_ready = 1'b1;
  logic [17:0] event_data;
  logic [63:0] held;
  logic [6:0] last_note, last_velocity;
  logic [31:0] mapped, ignored;

  push2_controls dut(
      .clk, .rst, .connected, .valid, .ready, .kind, .cable, .channel, .a, .b,
      .actual_control, .actual_options, .event_valid, .event_ready, .event_data,
      .held, .last_note, .last_velocity, .mapped, .ignored);

  task automatic send(input logic [3:0] k, input logic [6:0] note,
      input logic [6:0] value);
    begin
      @(negedge clk);
      while (!ready) @(negedge clk);
      kind = k; a = note; b = value; valid = 1'b1;
      @(negedge clk);
      valid = 1'b0;
      while (event_valid) @(negedge clk);
    end
  endtask

  initial begin
    repeat (3) @(negedge clk);
    rst = 1'b0;
    connected = 1'b1;
    send(4'd9, 7'd36, 7'd64);
    if (!held[0]) $fatal(1, "note-on did not hold pad");
    if (event_data !== {4'd1,7'd36,7'd92})
      $fatal(1, "note-on force mapping mismatch: %h", event_data);
    send(4'd10, 7'd36, 7'd0);
    if (event_data !== {4'd5,7'd36,7'd0})
      $fatal(1, "pressure zero event mismatch: %h", event_data);
    if (!held[0]) $fatal(1, "pressure zero released pad");
    send(4'd10, 7'd36, 7'd127);
    if (event_data !== {4'd5,7'd36,7'd127})
      $fatal(1, "pressure full event mismatch: %h", event_data);
    send(4'd10, 7'd36, 7'd2);
    if (event_data !== {4'd5,7'd36,7'd30})
      $fatal(1, "requested pressure 002->030 mapping mismatch: %h", event_data);
    // CIN D channel pressure carries no note; the mapper uses the most
    // recently held pad and must not release it.
    send(4'd13, 7'd23, 7'd0);
    if (event_data !== {4'd5,7'd36,7'd51})
      $fatal(1, "channel pressure event mismatch: %h", event_data);
    if (!held[0]) $fatal(1, "channel pressure released pad");
    if (mapped !== 32'd5) $fatal(1, "mapped count %0d", mapped);
    $display("PASS PUSH_PRESSURE held=%h mapped=%0d events=%h", held, mapped, event_data);
    $finish;
  end
endmodule
