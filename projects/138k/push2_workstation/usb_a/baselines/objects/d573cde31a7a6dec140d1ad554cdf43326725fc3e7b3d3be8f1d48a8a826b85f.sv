`timescale 1ns/1ps
// Send the FAT reader's 8.3 name RAM after each directory scan. A falling
// scan_done sends a zero-count header so Push drops stale names/selection.
module tf_playlist_bridge (
    input wire clk_50m, reset_n,
    input wire usb_clk, usb_reset_n,
    input wire scan_done,
    input wire [4:0] track_count,
    output reg [7:0] name_addr,
    input wire [7:0] name_data,
    output wire playlist_valid,
    input wire playlist_ready,
    output wire [15:0] playlist_word
);
    localparam [2:0] WAIT_SCAN=0, HEADER=1, READ=2, FETCH=3, SEND=4, DONE=5,
                     INVALIDATE=6;
    reg [2:0] state;
    reg [7:0] index;
    reg scan_done_q;
    wire fifo_ready;
    wire [15:0] fifo_word = state==HEADER ? {8'hff,3'd0,track_count} :
                            state==INVALIDATE ? 16'hff00 :
                            {index,name_data};
    music_async_fifo #(.WIDTH(16),.ADDRESS_BITS(2)) fifo(
        .write_clk_i(clk_50m),.write_rst_ni(reset_n),
        .write_valid_i(state==HEADER || state==SEND || state==INVALIDATE),.write_ready_o(fifo_ready),
        .write_data_i(fifo_word),
        .read_clk_i(usb_clk),.read_rst_ni(usb_reset_n),
        .read_valid_o(playlist_valid),.read_ready_i(playlist_ready),
        .read_data_o(playlist_word));
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin state<=WAIT_SCAN;index<=0;name_addr<=0;scan_done_q<=0;end
        else begin
            scan_done_q<=scan_done;
            if(scan_done_q && !scan_done) state<=INVALIDATE;
            else case(state)
            WAIT_SCAN: if(scan_done) state<=HEADER;
            HEADER: if(fifo_ready) state<=track_count==0 ? DONE : READ;
            READ: begin name_addr<=index;state<=FETCH;end
            FETCH: state<=SEND;
            SEND: if(fifo_ready) begin
                if(index+8'd1 >= {track_count,3'b0}+{track_count,2'b0}) state<=DONE;
                else begin index<=index+8'd1;state<=READ;end
            end
            INVALIDATE: if(fifo_ready) begin index<=0;state<=WAIT_SCAN;end
            default: state<=DONE;
            endcase
        end
    end
endmodule
