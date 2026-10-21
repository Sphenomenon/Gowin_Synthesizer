// Shallow stereo-PCM clock crossing between the 50 MHz decoder and the
// 76.8 MHz workstation/DAC domain.  Audio samples stay 16-bit per channel;
// the 32-bit memory word is only the paired L/R transport record.
module tf_async_pcm_fifo #(
    parameter integer ADDR_WIDTH = 4
) (
    input  wire                    wr_clk,
    input  wire                    wr_rst_n,
    input  wire                    clear_toggle,
    input  wire                    wr_en,
    input  wire signed [15:0]      wr_left,
    input  wire signed [15:0]      wr_right,
    output wire                    wr_full,
    input  wire                    rd_clk,
    input  wire                    rd_rst_n,
    input  wire                    rd_en,
    output reg                     rd_valid,
    output reg signed [15:0]       rd_left,
    output reg signed [15:0]       rd_right,
    output wire                    rd_empty
);
    localparam integer PTR_WIDTH = ADDR_WIDTH + 1;
    reg [31:0] mem [0:(1 << ADDR_WIDTH)-1];
    reg [PTR_WIDTH-1:0] wr_bin,wr_gray,rd_bin,rd_gray;
    reg [PTR_WIDTH-1:0] rd_gray_w1,rd_gray_w2,wr_gray_r1,wr_gray_r2;
    reg clear_wr_meta,clear_wr_seen,clear_rd_meta,clear_rd_seen;

    wire [PTR_WIDTH-1:0] wr_next=wr_bin+1'b1;
    wire [PTR_WIDTH-1:0] wr_gray_next=wr_next^(wr_next>>1);
    wire [PTR_WIDTH-1:0] rd_gray_full={~rd_gray_w2[PTR_WIDTH-1:PTR_WIDTH-2],
                                       rd_gray_w2[PTR_WIDTH-3:0]};
    assign wr_full=(wr_gray_next==rd_gray_full);
    assign rd_empty=(rd_gray==wr_gray_r2);

    always @(posedge wr_clk or negedge wr_rst_n) begin
        if(!wr_rst_n) begin
            wr_bin<=0;wr_gray<=0;rd_gray_w1<=0;rd_gray_w2<=0;
            clear_wr_meta<=0;clear_wr_seen<=0;
        end else begin
            rd_gray_w1<=rd_gray;rd_gray_w2<=rd_gray_w1;
            clear_wr_meta<=clear_toggle;
            if(clear_wr_meta!=clear_wr_seen) begin
                clear_wr_seen<=clear_wr_meta;wr_bin<=0;wr_gray<=0;
                rd_gray_w1<=0;rd_gray_w2<=0;
            end else if(wr_en && !wr_full) begin
                mem[wr_bin[ADDR_WIDTH-1:0]]<={wr_right,wr_left};
                wr_bin<=wr_next;wr_gray<=wr_gray_next;
            end
        end
    end

    always @(posedge rd_clk or negedge rd_rst_n) begin
        if(!rd_rst_n) begin
            rd_bin<=0;rd_gray<=0;wr_gray_r1<=0;wr_gray_r2<=0;
            clear_rd_meta<=0;clear_rd_seen<=0;
            rd_valid<=0;rd_left<=0;rd_right<=0;
        end else begin
            wr_gray_r1<=wr_gray;wr_gray_r2<=wr_gray_r1;
            clear_rd_meta<=clear_toggle;rd_valid<=0;
            if(clear_rd_meta!=clear_rd_seen) begin
                clear_rd_seen<=clear_rd_meta;rd_bin<=0;rd_gray<=0;
                wr_gray_r1<=0;wr_gray_r2<=0;rd_left<=0;rd_right<=0;
            end else if(rd_en && !rd_empty) begin
                {rd_right,rd_left}<=mem[rd_bin[ADDR_WIDTH-1:0]];
                rd_bin<=rd_bin+1'b1;
                rd_gray<=(rd_bin+1'b1)^((rd_bin+1'b1)>>1);
                rd_valid<=1;
            end
        end
    end
endmodule
