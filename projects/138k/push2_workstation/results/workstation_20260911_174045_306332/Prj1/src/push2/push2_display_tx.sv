// Arbitrary 960x160 BGR565 pixels -> exact documented Push 2 display packets.
// One 512-byte packet buffer; no full-frame allocation or CPU dependency.
module push2_display_tx (
    input wire clk, input wire rst,
    input wire frame_start, output wire frame_ready,
    output wire busy, output reg frame_done,
    input wire pixel_valid, output wire pixel_ready,
    input wire [15:0] pixel_bgr565,
    output wire [9:0] pixel_x, output wire [7:0] pixel_y,
    output wire packet_valid, output wire [9:0] packet_length,
    input wire [8:0] packet_index, output reg [7:0] packet_data,
    input wire packet_acked,
    output reg [31:0] frames_acked, output reg [31:0] pixels_accepted
);
    localparam IDLE=2'd0, HEADER=2'd1, FILL=2'd2, PACKET=2'd3;
    reg [1:0] state;
    reg [15:0] buffer [0:255];
    reg [7:0] fill_index, row;
    reg [9:0] column;
    reg final_packet;
    wire filler = column>=10'd960;
    assign frame_ready=state==IDLE;
    assign busy=state!=IDLE;
    assign pixel_ready=state==FILL && !filler;
    assign pixel_x=column;
    assign pixel_y=row;
    assign packet_valid=state==HEADER || state==PACKET;
    assign packet_length=state==HEADER ? 10'd16 : 10'd512;
    wire [15:0] read_word=buffer[packet_index[8:1]];
    wire [7:0] raw_byte=packet_index[0] ? read_word[15:8] : read_word[7:0];
    reg [7:0] xor_byte;
    always @* begin
        case (packet_index[1:0])
            2'd0,2'd2:xor_byte=8'he7;
            2'd1:xor_byte=8'hf3;
            default:xor_byte=8'hff;
        endcase
        packet_data=raw_byte ^ xor_byte;
        if (state==HEADER) begin
            case (packet_index)
                0:packet_data=8'hff;
                1:packet_data=8'hcc;
                2:packet_data=8'haa;
                3:packet_data=8'h88;
                default:packet_data=8'h00;
            endcase
        end
    end
    always @(posedge clk) begin
        if (rst) begin
            state<=IDLE; fill_index<=0; row<=0; column<=0;
            final_packet<=0; frame_done<=0; frames_acked<=0; pixels_accepted<=0;
        end else begin
            frame_done<=0;
            case (state)
                IDLE: if (frame_start) begin
                    state<=HEADER; fill_index<=0; row<=0; column<=0;
                    final_packet<=0; pixels_accepted<=0;
                end
                HEADER: if (packet_acked) state<=FILL;
                FILL: if (filler || pixel_valid) begin
                    buffer[fill_index]<=filler ? 16'h0000 : pixel_bgr565;
                    if (!filler) pixels_accepted<=pixels_accepted+1'b1;
                    if (column==1023) begin column<=0; row<=row+1'b1; end
                    else column<=column+1'b1;
                    if (fill_index==255) begin
                        state<=PACKET; fill_index<=0;
                        final_packet<=row==159 && column==1023;
                    end else fill_index<=fill_index+1'b1;
                end
                PACKET: if (packet_acked) begin
                    if (final_packet) begin
                        state<=IDLE; frame_done<=1; frames_acked<=frames_acked+1'b1;
                    end else state<=FILL;
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
