`timescale 1ns / 1ps

// PCA9685 channels 0..15 form the slider's bar graph.
// Each channel covers sixteen position values; position zero is fully dark.
module midi_slider_led_map (
    input wire enabled,
    input wire [7:0] position,
    output wire [15:0] led_bitmap
);
    genvar channel;
    generate
        for (channel = 0; channel < 16; channel = channel + 1) begin : map_channel
            localparam [7:0] THRESHOLD = channel * 16;
            assign led_bitmap[channel] = enabled && (position > THRESHOLD);
        end
    endgenerate
endmodule
