// Small dual-clock byte FIFO used to cross the TF stream and DDR UI clock.
// Data RAM has independent write/read ports so it can infer BSRAM.
module tf_async_byte_fifo #(
    parameter integer ADDR_WIDTH = 12
) (
    input  wire                   wr_clk,
    input  wire                   wr_rst_n,
    input  wire                   clear_toggle,
    input  wire                   wr_en,
    input  wire [7:0]             wr_data,
    output wire                   wr_full,
    output wire [ADDR_WIDTH:0]    wr_count,
    output wire                   wr_space_ok,
    input  wire                   rd_clk,
    input  wire                   rd_rst_n,
    input  wire                   rd_en,
    output reg  [7:0]             rd_data,
    output reg                    rd_valid,
    output wire                   rd_empty,
    output wire [ADDR_WIDTH:0]    rd_count
);
    localparam integer DEPTH = (1 << ADDR_WIDTH);
    localparam integer PTR_WIDTH = ADDR_WIDTH + 1;
    localparam [PTR_WIDTH:0] FIFO_DEPTH = {2'b01, {ADDR_WIDTH{1'b0}}};

    reg [7:0] mem [0:DEPTH-1];
    reg [PTR_WIDTH-1:0] wr_bin, wr_gray;
    reg [PTR_WIDTH-1:0] rd_bin, rd_gray;
    reg [PTR_WIDTH-1:0] rd_gray_w1, rd_gray_w2;
    reg [PTR_WIDTH-1:0] wr_gray_r1, wr_gray_r2;
    reg clear_wr_meta, clear_wr_seen;
    reg clear_rd_meta, clear_rd_seen;

    function [PTR_WIDTH-1:0] gray_to_bin;
        input [PTR_WIDTH-1:0] value;
        integer i;
        begin
            gray_to_bin[PTR_WIDTH-1] = value[PTR_WIDTH-1];
            for (i = PTR_WIDTH-2; i >= 0; i = i - 1)
                gray_to_bin[i] = gray_to_bin[i+1] ^ value[i];
        end
    endfunction

    wire [PTR_WIDTH-1:0] rd_bin_w = gray_to_bin(rd_gray_w2);
    wire [PTR_WIDTH-1:0] wr_bin_r = gray_to_bin(wr_gray_r2);
    wire [PTR_WIDTH-1:0] wr_used = wr_bin - rd_bin_w;
    wire [PTR_WIDTH-1:0] rd_used = wr_bin_r - rd_bin;
    wire [PTR_WIDTH:0] wr_space_count = FIFO_DEPTH - {1'b0, wr_used};
    wire [PTR_WIDTH-1:0] rd_gray_full = {
        ~rd_gray_w2[PTR_WIDTH-1:PTR_WIDTH-2],
        rd_gray_w2[PTR_WIDTH-3:0]
    };

    assign wr_full = (wr_gray == rd_gray_full);
    assign rd_empty = (rd_gray == wr_gray_r2);
    assign wr_count = wr_used;
    assign rd_count = rd_used;
    assign wr_space_ok = wr_space_count >= 14'd640;

    always @(posedge wr_clk or negedge wr_rst_n) begin
        if (!wr_rst_n) begin
            wr_bin  <= {PTR_WIDTH{1'b0}};
            wr_gray <= {PTR_WIDTH{1'b0}};
            rd_gray_w1 <= {PTR_WIDTH{1'b0}};
            rd_gray_w2 <= {PTR_WIDTH{1'b0}};
            clear_wr_meta <= 1'b0;
            clear_wr_seen <= 1'b0;
        end else begin
            rd_gray_w1 <= rd_gray;
            rd_gray_w2 <= rd_gray_w1;
            clear_wr_meta <= clear_toggle;
            if (clear_wr_meta != clear_wr_seen) begin
                clear_wr_seen <= clear_wr_meta;
                wr_bin <= {PTR_WIDTH{1'b0}};
                wr_gray <= {PTR_WIDTH{1'b0}};
                rd_gray_w1 <= {PTR_WIDTH{1'b0}};
                rd_gray_w2 <= {PTR_WIDTH{1'b0}};
            end else if (wr_en && !wr_full) begin
                mem[wr_bin[ADDR_WIDTH-1:0]] <= wr_data;
                wr_bin  <= wr_bin + 1'b1;
                wr_gray <= (wr_bin + 1'b1) ^ ((wr_bin + 1'b1) >> 1);
            end
        end
    end

    always @(posedge rd_clk or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            rd_bin <= {PTR_WIDTH{1'b0}};
            rd_gray <= {PTR_WIDTH{1'b0}};
            wr_gray_r1 <= {PTR_WIDTH{1'b0}};
            wr_gray_r2 <= {PTR_WIDTH{1'b0}};
            clear_rd_meta <= 1'b0;
            clear_rd_seen <= 1'b0;
            rd_data <= 8'd0;
            rd_valid <= 1'b0;
        end else begin
            wr_gray_r1 <= wr_gray;
            wr_gray_r2 <= wr_gray_r1;
            clear_rd_meta <= clear_toggle;
            rd_valid <= 1'b0;
            if (clear_rd_meta != clear_rd_seen) begin
                clear_rd_seen <= clear_rd_meta;
                rd_bin <= {PTR_WIDTH{1'b0}};
                rd_gray <= {PTR_WIDTH{1'b0}};
                wr_gray_r1 <= {PTR_WIDTH{1'b0}};
                wr_gray_r2 <= {PTR_WIDTH{1'b0}};
                rd_data <= 8'd0;
            end else if (rd_en && !rd_empty) begin
                rd_data <= mem[rd_bin[ADDR_WIDTH-1:0]];
                rd_bin <= rd_bin + 1'b1;
                rd_gray <= (rd_bin + 1'b1) ^ ((rd_bin + 1'b1) >> 1);
                rd_valid <= 1'b1;
            end
        end
    end
endmodule
