`timescale 1ns/1ps

module partial_step_generator_variable #(
    parameter string RATIO_MEM_FILE =
        "sim/matlab/output/stage13_note_voice/stage13_ratio_q18.mem",
    parameter int PROFILE_COUNT = 5,
    parameter int PARTIAL_COUNT = 32,
    parameter logic [38:0] AUDIBLE_STEP_LIMIT = 39'd1932735283
) (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic        start_i,
    input  logic [2:0]  profile_i,
    input  logic [31:0] base_step_i,
    input  logic [5:0]  partial_count_i,
    output logic        ready_o,
    output logic        busy_o,
    output logic        valid_o,
    output logic        done_o,
    output logic [4:0]  partial_index_o,
    output logic [31:0] partial_step_o,
    output logic        partial_enable_o
);
  localparam int ROM_DEPTH = PROFILE_COUNT * PARTIAL_COUNT;
  localparam int RATIO_FRACTION_BITS = 18;

  (* syn_ramstyle = "block_ram", ram_style = "block" *)
  logic [23:0] ratio_rom [0:ROM_DEPTH-1];
  logic [31:0] base_step_reg;
  logic [2:0] profile_reg;
  logic [4:0] issue_index;
  logic [4:0] last_index_reg;
  logic [7:0] rom_address;

  logic read_valid;
  logic [4:0] read_index;
  logic [23:0] ratio_data;
  logic product_valid;
  logic [4:0] product_index;
  logic [55:0] product;
  logic [38:0] rounded_step;

  initial begin
    $readmemh(RATIO_MEM_FILE, ratio_rom);
  end

  assign ready_o = !busy_o && !read_valid && !product_valid && !valid_o;
  assign rom_address = {profile_reg, 5'b0} + {3'b0, issue_index};
  assign rounded_step = {1'b0, product[55:RATIO_FRACTION_BITS]} +
      (product[RATIO_FRACTION_BITS-1] ? 39'd1 : 39'd0);

  // As with the audio slot RAM, an unreset ROM data register gives both
  // vendor tools a portable synchronous block-memory template.
  always_ff @(posedge clk_i) begin
    if (busy_o) begin
      ratio_data <= ratio_rom[rom_address];
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      busy_o <= 1'b0;
      valid_o <= 1'b0;
      done_o <= 1'b0;
      partial_index_o <= '0;
      partial_step_o <= '0;
      partial_enable_o <= 1'b0;
      base_step_reg <= '0;
      profile_reg <= '0;
      issue_index <= '0;
      last_index_reg <= '0;
      read_valid <= 1'b0;
      read_index <= '0;
      product_valid <= 1'b0;
      product_index <= '0;
      product <= '0;
    end else begin
      valid_o <= product_valid;
      done_o <= product_valid && product_index == last_index_reg;

      if (product_valid) begin
        partial_index_o <= product_index;
        if (rounded_step < AUDIBLE_STEP_LIMIT) begin
          partial_step_o <= rounded_step[31:0];
          partial_enable_o <= 1'b1;
        end else begin
          partial_step_o <= 32'd0;
          partial_enable_o <= 1'b0;
        end
      end else begin
        partial_enable_o <= 1'b0;
      end

      product_valid <= read_valid;
      if (read_valid) begin
        product <= base_step_reg * ratio_data;
        product_index <= read_index;
      end

      read_valid <= busy_o;
      if (busy_o) begin
        read_index <= issue_index;
        if (issue_index == last_index_reg) begin
          busy_o <= 1'b0;
        end else begin
          issue_index <= issue_index + 5'd1;
        end
      end

      if (start_i && ready_o) begin
        base_step_reg <= base_step_i;
        profile_reg <= profile_i;
        issue_index <= 5'd0;
        if (partial_count_i <= 6'd1) begin
          last_index_reg <= 5'd0;
        end else if (partial_count_i >= 6'd32) begin
          last_index_reg <= 5'd31;
        end else begin
          last_index_reg <= partial_count_i[4:0] - 5'd1;
        end
        busy_o <= 1'b1;
      end
    end
  end
endmodule
