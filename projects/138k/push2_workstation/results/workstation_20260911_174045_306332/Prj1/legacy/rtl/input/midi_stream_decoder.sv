`timescale 1ns/1ps
// One selected MIDI channel; realtime bytes never disturb running status.
// Packed event: {type[3:0], data1[6:0], data2[6:0]}.
// type: 0 NoteOff, 1 NoteOn, 2 CC, 3 ProgramChange, 4 PitchBend.
module midi_stream_decoder #(
    parameter logic [3:0] CHANNEL = 0,
    parameter integer FIFO_DEPTH = 32
) (
    input logic clk_i, rst_ni, byte_valid_i,
    input logic [7:0] byte_i,
    output logic event_valid_o,
    input logic event_ready_i,
    output logic [17:0] event_o,
    output logic [31:0] overflow_count_o
);
  localparam integer AW = $clog2(FIFO_DEPTH);
  (* ram_style="distributed" *) logic [17:0] fifo [0:FIFO_DEPTH-1];
  logic [AW-1:0] rd, wr;
  logic [AW:0] count;
  logic [7:0] running_status;
  logic [6:0] first_data;
  logic have_first, sysex;
  logic push, pop;
  logic [17:0] decoded;
  assign event_valid_o = count != 0;
  assign event_o = fifo[rd];
  assign pop = event_valid_o && event_ready_i;
  always_comb begin
    push = 0; decoded = 0;
    if (byte_valid_i && !byte_i[7] && !sysex &&
        running_status[7] && running_status[3:0] == CHANNEL) begin
      case (running_status[7:4])
        4'h8: if (have_first) begin push=1; decoded={4'd0,first_data,byte_i[6:0]}; end
        4'h9: if (have_first) begin push=1; decoded={byte_i[6:0]==0 ? 4'd0:4'd1,first_data,byte_i[6:0]}; end
        4'hb: if (have_first) begin push=1; decoded={4'd2,first_data,byte_i[6:0]}; end
        4'hc: begin push=1; decoded={4'd3,byte_i[6:0],7'd0}; end
        4'he: if (have_first) begin push=1; decoded={4'd4,first_data,byte_i[6:0]}; end
        default: begin end
      endcase
    end
  end
  always_ff @(posedge clk_i) begin
    if(push && (count < FIFO_DEPTH || pop)) fifo[wr]<=decoded;
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rd<=0; wr<=0; count<=0; running_status<=0; first_data<=0;
      have_first<=0; sysex<=0; overflow_count_o<=0;
    end else begin
      if (pop) rd<=rd+1'b1;
      if (push && (count < FIFO_DEPTH || pop)) begin
        wr<=wr+1'b1;
      end else if (push) overflow_count_o<=overflow_count_o+1;
      case ({push && (count < FIFO_DEPTH || pop),pop})
        2'b10: count<=count+1'b1;
        2'b01: count<=count-1'b1;
        default: begin end
      endcase
      if (byte_valid_i && byte_i < 8'hf8) begin
        if (byte_i[7]) begin
          have_first<=0;
          if (byte_i < 8'hf0) begin running_status<=byte_i; sysex<=0; end
          else begin running_status<=0; sysex<=byte_i==8'hf0; end
        end else if (!sysex && running_status[7]) begin
          first_data<=byte_i[6:0];
          if (running_status[7:4]==4'hc || running_status[7:4]==4'hd)
            have_first<=0;
          else have_first<=!have_first;
        end
      end
    end
  end
endmodule
