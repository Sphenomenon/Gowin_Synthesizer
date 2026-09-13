`timescale 1ns/1ps

module mode_timbre_rom #(
    parameter string GAIN_MEM_FILE =
        "sim/matlab/output/stage15_unified_modes/stage15_mode_gain_q15.mem",
    parameter string ADSR_MEM_FILE =
        "sim/matlab/output/stage13_note_voice/stage13_adsr_q24.mem",
    parameter int MODE_COUNT = 3,
    parameter int PROFILE_COUNT = 5,
    parameter int PARTIAL_COUNT = 32
) (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        gain_read_i,
    input  logic [1:0]  mode_i,
    input  logic [2:0]  profile_i,
    input  logic [4:0]  partial_index_i,
    output logic        gain_valid_o,
    output logic [15:0] gain_q15_o,
    output logic [23:0] attack_step_q24_o,
    output logic [23:0] decay_step_q24_o,
    output logic [23:0] sustain_level_q24_o,
    output logic [23:0] release_step_q24_o
);
  localparam int GAIN_ROM_DEPTH = MODE_COUNT * PROFILE_COUNT * PARTIAL_COUNT;
  localparam int ADSR_ROM_DEPTH = PROFILE_COUNT * 4;

  (* syn_ramstyle = "block_ram", ram_style = "block" *) logic [15:0]
      gain_rom [0:GAIN_ROM_DEPTH-1];
  logic [23:0] adsr_rom [0:ADSR_ROM_DEPTH-1];
  logic [8:0] mode_base_address;
  logic [8:0] gain_address;
  logic [4:0] adsr_base_address;

  initial begin
    $readmemh(GAIN_MEM_FILE, gain_rom);
    $readmemh(ADSR_MEM_FILE, adsr_rom);
  end

  always @* begin
    case (mode_i)
      2'd0: mode_base_address = 9'd0;
      2'd1: mode_base_address = 9'd160;
      default: mode_base_address = 9'd320;
    endcase
  end

  assign gain_address = mode_base_address + {profile_i, 5'b0} +
      {4'b0, partial_index_i};
  assign adsr_base_address = {profile_i, 2'b0};
  assign attack_step_q24_o = adsr_rom[adsr_base_address];
  assign decay_step_q24_o = adsr_rom[adsr_base_address + 5'd1];
  assign sustain_level_q24_o = adsr_rom[adsr_base_address + 5'd2];
  assign release_step_q24_o = adsr_rom[adsr_base_address + 5'd3];

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      gain_valid_o <= 1'b0;
      gain_q15_o <= '0;
    end else begin
      gain_valid_o <= gain_read_i;
      if (gain_read_i) begin
        gain_q15_o <= gain_rom[gain_address];
      end
    end
  end
endmodule
