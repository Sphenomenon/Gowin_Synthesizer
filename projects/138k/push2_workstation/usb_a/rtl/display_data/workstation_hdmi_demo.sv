`default_nettype none
module workstation_hdmi_demo #(
    parameter integer CLOCK_HZ = 50000000,
    parameter integer SAMPLE_HZ = 48000,
    parameter integer DYNAMIC = 1
) (
    input wire clk,
    input wire reset_n,
    output reg sample_valid,
    output wire signed [31:0] sample_data,
    output wire [31:0] output_pcm,
    output wire [31:0] trigger_reference,
    output wire [31:0] active_voices,
    output wire [31:0] status_data,
    output wire [2:0] effect_mask,
    output wire [5:0] effect_order
);
    reg [25:0] sample_accumulator;
    reg [31:0] phase;
    reg [31:0] seconds_counter;
    reg [2:0] scene;
    wire [26:0] next_accumulator = {1'b0, sample_accumulator} + SAMPLE_HZ;
    wire sample_tick = next_accumulator >= CLOCK_HZ;
    wire [15:0] left_triangle = phase[31] ? ~phase[30:15] : phase[30:15];
    wire [31:0] right_phase = {phase[30:0], 1'b0} + 32'h40000000;
    wire [15:0] right_triangle = right_phase[31] ? ~right_phase[30:15] : right_phase[30:15];
    wire signed [15:0] left_pcm = $signed(left_triangle ^ 16'h8000) >>> 2;
    wire signed [15:0] right_pcm = $signed(right_triangle ^ 16'h8000) >>> 2;
    wire signed [31:0] left_extended = {{16{left_pcm[15]}}, left_pcm};
    wire signed [31:0] right_extended = {{16{right_pcm[15]}}, right_pcm};
    assign output_pcm = {left_pcm, right_pcm};
    assign sample_data = (left_extended + right_extended) <<< 15;
    assign trigger_reference = left_extended <<< 16;
    assign active_voices = DYNAMIC ? (32'h00000003 << scene) : 32'h00000007;
    assign status_data = DYNAMIC ? {24'h48444d, 5'd0, scene} : 32'h48444d49;
    assign effect_mask = DYNAMIC ? scene : 3'b101;
    assign effect_order = scene[0] && DYNAMIC ? 6'b00_01_10 : 6'b10_01_00;
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            sample_accumulator <= 0;
            sample_valid <= 0;
            phase <= 0;
            seconds_counter <= 0;
            scene <= 0;
        end else begin
            sample_valid <= sample_tick;
            sample_accumulator <= sample_tick ? next_accumulator - CLOCK_HZ : next_accumulator;
            if (sample_tick)
                phase <= phase + 32'h02000000;
            if (seconds_counter == CLOCK_HZ - 1) begin
                seconds_counter <= 0;
                scene <= scene + 1'b1;
            end else
                seconds_counter <= seconds_counter + 1'b1;
        end
    end
endmodule
`default_nettype wire
