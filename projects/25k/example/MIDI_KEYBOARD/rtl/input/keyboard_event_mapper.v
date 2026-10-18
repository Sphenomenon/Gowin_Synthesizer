`timescale 1ns/1ps
// Converts abstract physical key changes into complete MIDI note messages.
// key_note is the physical key ID: release always uses that key's saved press
// channel/note, even if the current configuration is invalid or has changed.
module keyboard_event_mapper (
    input wire clk,
    input wire reset,

    input wire key_valid,
    output wire key_ready,
    input wire key_down,
    input wire [6:0] key_note,
    input wire [6:0] key_velocity,
    input wire [3:0] midi_channel,
    input wire signed [7:0] transpose,
    input wire [12:0] timestamp_ms,

    output reg event_valid,
    input wire event_ready,
    output reg [23:0] event_message,
    output reg [1:0] event_length,
    output reg [12:0] event_timestamp,
    output reg [7:0] active_notes,
    output reg [15:0] ignored_events
);
    reg [127:0] active_keys;
    // Only entries selected by active_keys may be read. Their contents do not
    // require reset, permitting storage inference without an array reset loop.
    reg [6:0] pressed_note [0:127];
    reg [3:0] pressed_channel [0:127];

    wire release_key = !key_down || (key_velocity == 7'd0);
    wire signed [8:0] mapped_note = $signed({2'b00, key_note}) +
                                     $signed({transpose[7], transpose});
    wire press_in_range = (transpose >= -8'sd48) && (transpose <= 8'sd48) &&
                          (mapped_note >= 9'sd0) && (mapped_note <= 9'sd127);

    // One elastic slot; every accepted change is resolved exactly once.
    assign key_ready = !reset && (!event_valid || event_ready);

    always @(posedge clk) begin
        if (reset) begin
            active_keys <= 128'd0;
            active_notes <= 8'd0;
            ignored_events <= 16'd0;
            event_valid <= 1'b0;
            event_message <= 24'd0;
            event_length <= 2'd0;
            event_timestamp <= 13'd0;
        end else if (key_ready) begin
            event_valid <= 1'b0;
            if (key_valid) begin
                if (release_key && active_keys[key_note]) begin
                    event_valid <= 1'b1;
                    event_message <= {{4'h8, pressed_channel[key_note]},
                                      {1'b0, pressed_note[key_note]}, 8'd0};
                    event_length <= 2'd3;
                    event_timestamp <= timestamp_ms;
                    active_keys[key_note] <= 1'b0;
                    active_notes <= active_notes - 1'b1;
                end else if (!release_key && !active_keys[key_note] && press_in_range) begin
                    event_valid <= 1'b1;
                    event_message <= {{4'h9, midi_channel},
                                      {1'b0, mapped_note[6:0]}, {1'b0, key_velocity}};
                    event_length <= 2'd3;
                    event_timestamp <= timestamp_ms;
                    active_keys[key_note] <= 1'b1;
                    pressed_note[key_note] <= mapped_note[6:0];
                    pressed_channel[key_note] <= midi_channel;
                    active_notes <= active_notes + 1'b1;
                end else if (ignored_events != 16'hffff) begin
                    ignored_events <= ignored_events + 1'b1;
                end
            end
        end
    end
endmodule
