`timescale 1ns/1ps

module midi_step_rom #(
    parameter string MEM_FILE =
        "sim/matlab/output/stage13_note_voice/stage13_midi_step.mem"
) (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        read_i,
    input  logic [6:0]  midi_note_i,
    output logic        valid_o,
    output logic [31:0] phase_step_o
);
  (* syn_ramstyle = "block_ram", ram_style = "block" *)
  logic [31:0] step_rom [0:127];

  initial begin
    $readmemh(MEM_FILE, step_rom);
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      valid_o <= 1'b0;
      phase_step_o <= '0;
    end else begin
      valid_o <= read_i;
      if (read_i) begin
        phase_step_o <= step_rom[midi_note_i];
      end
    end
  end
endmodule
