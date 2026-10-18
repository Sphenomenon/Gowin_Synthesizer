`timescale 1ns / 1ps

// Independently enabled 1 s fade-in + 1 s fade-out channel.
module led_breath_channel #(
    parameter integer CLK_HZ = 50_000_000
) (
    input wire clk,
    input wire enable,
    output wire led
);
    localparam integer STEP_HZ = 256;
    localparam integer ACC_WIDTH = $clog2(CLK_HZ + STEP_HZ);
    reg [ACC_WIDTH-1:0] step_acc = 0;
    reg [7:0] pwm_count = 0;
    reg [8:0] brightness = 0;
    reg fading_down = 0;

    always @(posedge clk) begin
        if (!enable) begin
            step_acc <= 0;
            pwm_count <= 0;
            brightness <= 0;
            fading_down <= 0;
        end else begin
            pwm_count <= pwm_count + 1'b1;
            if (step_acc >= CLK_HZ - STEP_HZ) begin
                step_acc <= step_acc - (CLK_HZ - STEP_HZ);
                if (!fading_down) begin
                    brightness <= brightness + 1'b1;
                    if (brightness == 255) fading_down <= 1'b1;
                end else begin
                    brightness <= brightness - 1'b1;
                    if (brightness == 1) fading_down <= 1'b0;
                end
            end else step_acc <= step_acc + STEP_HZ;
        end
    end
    assign led = enable && ({1'b0, pwm_count} < brightness);
endmodule
