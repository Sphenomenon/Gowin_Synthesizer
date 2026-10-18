`timescale 1ns/1ps
`default_nettype none
// Board keypad wiring, confirmed from the physical A--P keys. The QT2160
// bitmap uses zero-based channel indices; every consumer uses A at bit 0.
module midi_key_layout (
    input wire [15:0] raw_keys,
    output wire [15:0] key_bitmap
);
    // Logical A B C D E F G H I J K L M N O P:
    // Raw     5 3 1 7 13 11 9 15 4 2 0 6 12 10 8 14.
    assign key_bitmap = {
        raw_keys[14], raw_keys[8], raw_keys[10], raw_keys[12],
        raw_keys[6],  raw_keys[0], raw_keys[2],  raw_keys[4],
        raw_keys[15], raw_keys[9], raw_keys[11], raw_keys[13],
        raw_keys[7],  raw_keys[1], raw_keys[3],  raw_keys[5]
    };
endmodule
`default_nettype wire
