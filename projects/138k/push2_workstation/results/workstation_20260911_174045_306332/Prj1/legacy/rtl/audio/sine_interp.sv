`timescale 1ns/1ps

module sine_interp #(
    parameter string MEM_FILE = "sim/matlab/output/stage3_sine2048x24.mem"
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  logic               valid_i,
    input  logic        [31:0] phase_i,
    output logic               valid_o,
    output logic signed [23:0] sample_o
);
  localparam int TABLE_ADDRESS_BITS = 11;
  localparam int TABLE_LENGTH = 1 << TABLE_ADDRESS_BITS;
  localparam int INTERPOLATION_BITS = 12;

  (* syn_ramstyle = "block_ram", ram_style = "block" *)
  logic signed [23:0] sine_rom [0:TABLE_LENGTH-1];

  logic valid_s0;
  logic [TABLE_ADDRESS_BITS-1:0] address_s0;
  logic [TABLE_ADDRESS_BITS-1:0] next_address_s0;
  logic [INTERPOLATION_BITS-1:0] fraction_s0;

  logic valid_s1;
  logic signed [23:0] lower_s1;
  logic signed [23:0] upper_s1;
  logic [INTERPOLATION_BITS-1:0] fraction_s1;

  logic valid_s2;
  logic signed [23:0] lower_s2;
  logic signed [37:0] interpolation_product_s2;

  logic valid_s3;
  logic signed [23:0] lower_s3;
  logic signed [25:0] rounded_offset_s3;

  logic signed [24:0] difference_s1;
  logic signed [12:0] fraction_signed_s1;
  logic signed [37:0] product_magnitude;
  logic signed [37:0] rounded_magnitude_wide;
  logic signed [25:0] rounded_magnitude;
  logic signed [25:0] rounded_offset;
  logic signed [25:0] lower_extended;
  logic signed [25:0] interpolated_value;

  initial begin
    $readmemh(MEM_FILE, sine_rom);
  end

  assign difference_s1 = $signed({upper_s1[23], upper_s1}) -
      $signed({lower_s1[23], lower_s1});
  assign fraction_signed_s1 = $signed({1'b0, fraction_s1});
  assign product_magnitude = interpolation_product_s2[37]
      ? -interpolation_product_s2 : interpolation_product_s2;
  assign rounded_magnitude_wide =
      (product_magnitude + 38'sd2048) >>> INTERPOLATION_BITS;
  assign rounded_magnitude = rounded_magnitude_wide[25:0];
  assign rounded_offset = interpolation_product_s2[37]
      ? -rounded_magnitude : rounded_magnitude;
  assign lower_extended = {{2{lower_s3[23]}}, lower_s3};
  assign interpolated_value = lower_extended + rounded_offset_s3;

  // ROM outputs deliberately have no reset.  valid_s1 keeps their undefined
  // power-up value outside the data stream and permits block-ROM inference.
  always_ff @(posedge clk_i) begin
    lower_s1 <= sine_rom[address_s0];
    upper_s1 <= sine_rom[next_address_s0];
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      valid_s0 <= 1'b0;
      valid_s1 <= 1'b0;
      valid_s2 <= 1'b0;
      valid_s3 <= 1'b0;
      valid_o <= 1'b0;
      address_s0 <= '0;
      next_address_s0 <= '0;
      fraction_s0 <= '0;
      fraction_s1 <= '0;
      lower_s2 <= '0;
      interpolation_product_s2 <= '0;
      lower_s3 <= '0;
      rounded_offset_s3 <= '0;
      sample_o <= '0;
    end else begin
      valid_s0 <= valid_i;
      address_s0 <= phase_i[31:21];
      next_address_s0 <= phase_i[31:21] + 11'd1;
      fraction_s0 <= phase_i[20:9];

      valid_s1 <= valid_s0;
      fraction_s1 <= fraction_s0;

      valid_s2 <= valid_s1;
      lower_s2 <= lower_s1;
      interpolation_product_s2 <= difference_s1 * fraction_signed_s1;

      valid_s3 <= valid_s2;
      lower_s3 <= lower_s2;
      rounded_offset_s3 <= rounded_offset;

      valid_o <= valid_s3;
      if (interpolated_value > 26'sd8388607) begin
        sample_o <= 24'sh7fffff;
      end else if (interpolated_value < -26'sd8388608) begin
        sample_o <= 24'sh800000;
      end else begin
        sample_o <= interpolated_value[23:0];
      end
    end
  end
endmodule
