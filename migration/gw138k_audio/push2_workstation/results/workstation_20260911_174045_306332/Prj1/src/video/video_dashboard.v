`default_nettype none

// Combinational 640x480 dashboard. All interface values are pixel-clock words.
module video_dashboard (
    input wire [9:0] pixel_x,
    input wire [9:0] pixel_y,
    input wire data_enable,
    input wire [31:0] level_data,
    input wire [31:0] active_voices,
    input wire [31:0] status_data,
    output reg [23:0] rgb_data
);
    localparam [255:0] TITLE   = "FPGA SYNTH                      ";
    localparam [255:0] ROUTE   = "UART / HEADPHONE                ";
    localparam [255:0] LEVEL   = "OUTPUT LEVEL                    ";
    localparam [255:0] VOICES  = "ACTIVE VOICES                   ";
    localparam [255:0] STATUS  = "STATUS                          ";
    localparam [255:0] FOOTER  = "32 BIT AUDIO                    ";
    wire [9:0] relative_x = pixel_x - 10'd64;
    wire [4:0] text_index = relative_x[8:4];
    wire [1:0] voice_index = relative_x[8:7];
    wire [9:0] level_width = level_data[31] ? 10'd512 : {1'b0, level_data[30:22]};
    reg [255:0] text_line;
    reg [7:0] character;
    reg [3:0] hex_digit;
    reg [2:0] font_column;
    reg [2:0] font_row;
    reg text_enable;
    wire font_ink;
    video_font_5x7 u_font (.character(character), .column(font_column), .row(font_row), .ink(font_ink));

    always @* begin
        text_line = 0;
        text_enable = 0;
        font_column = relative_x[3:1];
        font_row = pixel_y[3:1];
        character = 8'h20;
        hex_digit = 0;
        if (pixel_x >= 64 && pixel_x < 576) begin
            case (pixel_y[9:4])
                2: begin text_line = TITLE; text_enable = 1; end
                4: begin text_line = ROUTE; text_enable = 1; end
                7: begin text_line = LEVEL; text_enable = 1; end
                13: begin text_line = VOICES; text_enable = 1; end
                23: begin text_line = STATUS; text_enable = 1; end
                27: begin text_line = FOOTER; text_enable = 1; end
                default: begin end
            endcase
            character = text_line[255 - text_index*8 -: 8];
            if (pixel_y >= 272 && pixel_y < 288 && relative_x[6:4] == 3) begin
                character = "1" + {6'b0, voice_index};
                text_enable = 1;
            end
            if (pixel_y >= 368 && pixel_y < 384 && pixel_x >= 224 && pixel_x < 352) begin
                hex_digit = status_data[31 - ((pixel_x-224) >> 4)*4 -: 4];
                character = (hex_digit < 10) ? (8'h30 + hex_digit) : (8'h41 + hex_digit - 10);
                text_enable = 1;
            end
        end
    end

    always @* begin
        rgb_data = 24'h101b2a;
        if (pixel_y < 96) rgb_data = 24'h1a3048;
        if (pixel_y == 95 || pixel_y == 415) rgb_data = 24'h31506c;
        if (pixel_x >= 64 && pixel_x < 576 && pixel_y >= 144 && pixel_y < 176) begin
            rgb_data = 24'h273b50;
            if (relative_x < level_width) begin
                if (relative_x >= 480) rgb_data = 24'hef6572;
                else if (relative_x >= 400) rgb_data = 24'hf1c05a;
                else rgb_data = 24'h3cdbab;
            end
            if (relative_x[4:0] == 31) rgb_data = 24'h101b2a;
        end
        if (pixel_x >= 64 && pixel_x < 576 && pixel_y >= 248 && pixel_y < 320 && relative_x[6:0] < 112) begin
            rgb_data = active_voices[voice_index] ? 24'h157d70 : 24'h263a4f;
            if (pixel_y < 252) rgb_data = active_voices[voice_index] ? 24'h3cdbab : 24'h49627a;
        end
        if (text_enable && font_ink) rgb_data = 24'he5f0fa;
        if (!data_enable) rgb_data = 24'h000000;
    end
endmodule

`default_nettype wire
