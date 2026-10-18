`timescale 1ns/1ps

module tb_push_aftertouch_init;
  logic clk = 0, rst = 1;
  always #5 clk = ~clk;
  logic [63:0] held = 0;
  logic [31:0] control = 0;
  logic cmd_valid, cmd_ready;
  logic [1:0] cmd_kind;
  logic [6:0] cmd_index;
  logic [7:0] cmd_value;
  logic packet_valid, packet_acked = 0;
  logic [9:0] packet_length;
  logic [8:0] packet_index = 0;
  logic [7:0] packet_data;
  logic [31:0] commands_acked, commands_rejected;
  logic [127:0] bytes;

  push2_lights lights(
      .clk, .rst, .held, .control, .valid(cmd_valid), .ready(cmd_ready),
      .kind(cmd_kind), .index(cmd_index), .value(cmd_value));
  push2_led_tx tx(
      .clk, .rst, .cmd_valid, .cmd_ready, .cmd_kind, .cmd_index,
      .cmd_value, .cmd_cable(4'd0), .packet_valid, .packet_length,
      .packet_index, .packet_data, .packet_acked, .commands_acked,
      .commands_rejected);

  task automatic consume_packet;
    begin
      wait(packet_valid);
      bytes = 0;
      for (integer i = 0; i < packet_length; i++) begin
        packet_index = i[8:0];
        #1 bytes[i*8 +: 8] = packet_data;
      end
      @(negedge clk); packet_acked = 1;
      @(negedge clk); packet_acked = 0;
    end
  endtask

  initial begin
    repeat (3) @(negedge clk);
    rst = 0;
    consume_packet();
    if (packet_length != 12 || bytes[95:0] != 96'hf7000a0701011d042100f004)
      $fatal(1, "Live mode packet mismatch: %h", bytes[95:0]);
    consume_packet();
    consume_packet();
    consume_packet();
    if (packet_length != 12 || bytes[95:0] != 96'hf768170701011d042100f004)
      $fatal(1, "touch-strip packet mismatch: %h", bytes[95:0]);
    consume_packet();
    if (packet_length != 12 || bytes[95:0] != 96'hf7011e0701011d042100f004)
      $fatal(1, "poly-aftertouch packet mismatch: %h", bytes[95:0]);
    if (commands_rejected != 0 || commands_acked != 5)
      $fatal(1, "startup accounting mismatch acked=%0d rejected=%0d",
             commands_acked, commands_rejected);
    $display("PASS PUSH_AFTERTOUCH_INIT command=1e mode=1 startup_packets=%0d",
             commands_acked);
    $finish;
  end
endmodule
