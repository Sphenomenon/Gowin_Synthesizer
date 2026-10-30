// Runtime-only adaptation of first-party tf_async_byte_fifo.v. Provenance and
// original identity are recorded in workstation_tf_runtime_storage.provenance.json.
// Clear is a held token under BOTH local admission holds. Non-unit Gray zero
// transitions are hidden from users until all four FIFO sides ACK at the path.
module workstation_tf_runtime_byte_fifo #(
    parameter integer ADDR_WIDTH=12,
    parameter integer SPACE_THRESHOLD=640
) (
    input wire wr_clk,wr_rst_n,wr_hold_i,clear_toggle,
    input wire wr_en,
    input wire [7:0] wr_data,
    output wire wr_full,
    output wire [ADDR_WIDTH:0] wr_count,
    output wire wr_space_ok,
    output reg wr_clear_ack_o,
    input wire rd_clk,rd_rst_n,rd_hold_i,rd_en,
    output reg [7:0] rd_data,
    output reg rd_valid,
    output wire rd_empty,
    output wire [ADDR_WIDTH:0] rd_count,
    output reg rd_clear_ack_o
);
    localparam integer PTR_WIDTH=ADDR_WIDTH+1;
    localparam integer DEPTH=1<<ADDR_WIDTH;
    reg [7:0] mem[0:DEPTH-1];
    reg [PTR_WIDTH-1:0] wr_bin,wr_gray,rd_bin,rd_gray;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [PTR_WIDTH-1:0] rd_gray_w1,rd_gray_w2,wr_gray_r1,wr_gray_r2;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg clear_wr_meta,clear_wr_sync,clear_rd_meta,clear_rd_sync;
    reg [1:0] wr_zero_count,rd_zero_count;
    wire wr_clear_pending=clear_wr_sync!=wr_clear_ack_o;
    wire rd_clear_pending=clear_rd_sync!=rd_clear_ack_o;
    function automatic [PTR_WIDTH-1:0] gray_to_bin(input [PTR_WIDTH-1:0] value);
        integer i;
        begin
            gray_to_bin[PTR_WIDTH-1]=value[PTR_WIDTH-1];
            for(i=PTR_WIDTH-2;i>=0;i=i-1)gray_to_bin[i]=gray_to_bin[i+1]^value[i];
        end
    endfunction
    wire [PTR_WIDTH-1:0] wr_used=wr_bin-gray_to_bin(rd_gray_w2);
    wire [PTR_WIDTH-1:0] rd_used=gray_to_bin(wr_gray_r2)-rd_bin;
    wire [PTR_WIDTH-1:0] full_gray={~rd_gray_w2[PTR_WIDTH-1:PTR_WIDTH-2],rd_gray_w2[PTR_WIDTH-3:0]};
    assign wr_full=wr_hold_i || wr_clear_pending || wr_gray==full_gray;
    assign rd_empty=rd_hold_i || rd_clear_pending || rd_gray==wr_gray_r2;
    assign wr_count=wr_hold_i || wr_clear_pending ? {PTR_WIDTH{1'b0}}:wr_used;
    assign rd_count=rd_hold_i || rd_clear_pending ? {PTR_WIDTH{1'b0}}:rd_used;
    assign wr_space_ok=!wr_hold_i && !wr_clear_pending && (PTR_WIDTH+1)'(DEPTH)-{1'b0,wr_used}>=(PTR_WIDTH+1)'(SPACE_THRESHOLD);
    initial if(ADDR_WIDTH<2 || SPACE_THRESHOLD<1 || SPACE_THRESHOLD>DEPTH)$fatal(1,"runtime byte FIFO geometry");

    always @(posedge wr_clk or negedge wr_rst_n)begin
        if(!wr_rst_n)begin
            wr_bin<=0;wr_gray<=0;rd_gray_w1<=0;rd_gray_w2<=0;
            clear_wr_meta<=0;clear_wr_sync<=0;wr_clear_ack_o<=0;wr_zero_count<=0;
        end else begin
            // First stages have no functional fanout. Pointer receivers keep
            // running through clear; only qualified second stages are used.
            rd_gray_w1<=rd_gray;rd_gray_w2<=rd_gray_w1;
            clear_wr_meta<=clear_toggle;clear_wr_sync<=clear_wr_meta;
            if(wr_clear_pending)begin
                wr_zero_count<=0;
                if(wr_hold_i)begin
                    wr_bin<=0;wr_gray<=0;
                    if(wr_bin==0 && rd_gray_w2==0)begin
                        if(wr_zero_count==1)begin wr_clear_ack_o<=clear_wr_sync;wr_zero_count<=0;end
                        else wr_zero_count<=wr_zero_count+1'b1;
                    end
                end
            end else begin
                wr_zero_count<=0;
                if(wr_en && !wr_full)begin
                    mem[wr_bin[ADDR_WIDTH-1:0]]<=wr_data;
                    wr_bin<=wr_bin+1'b1;wr_gray<=(wr_bin+1'b1)^((wr_bin+1'b1)>>1);
                end
            end
        end
    end
    always @(posedge rd_clk or negedge rd_rst_n)begin
        if(!rd_rst_n)begin
            rd_bin<=0;rd_gray<=0;wr_gray_r1<=0;wr_gray_r2<=0;
            clear_rd_meta<=0;clear_rd_sync<=0;rd_clear_ack_o<=0;rd_zero_count<=0;
            rd_data<=0;rd_valid<=0;
        end else begin
            wr_gray_r1<=wr_gray;wr_gray_r2<=wr_gray_r1;
            clear_rd_meta<=clear_toggle;clear_rd_sync<=clear_rd_meta;
            rd_valid<=0;
            if(rd_clear_pending)begin
                rd_zero_count<=0;
                if(rd_hold_i)begin
                    rd_bin<=0;rd_gray<=0;rd_data<=0;
                    if(rd_bin==0 && wr_gray_r2==0 && !rd_valid)begin
                        if(rd_zero_count==1)begin rd_clear_ack_o<=clear_rd_sync;rd_zero_count<=0;end
                        else rd_zero_count<=rd_zero_count+1'b1;
                    end
                end
            end else begin
                rd_zero_count<=0;
                if(rd_en && !rd_empty)begin
                    rd_data<=mem[rd_bin[ADDR_WIDTH-1:0]];
                    rd_bin<=rd_bin+1'b1;rd_gray<=(rd_bin+1'b1)^((rd_bin+1'b1)>>1);rd_valid<=1;
                end
            end
        end
    end
endmodule
