// Native SDIO command lane, SDR at <=400kHz. CMD changes on falling edges;
// responses are sampled on rising edges. DAT is never driven by this engine.
module sdio_command #(
    parameter integer CLK_HZ=50000000,
    parameter integer SD_HZ=250000,
    parameter integer RESPONSE_CLOCKS=1024
)(
    input wire clk, resetn, start,
    input wire [5:0] command,
    input wire [31:0] argument,
    input wire expect_response, check_crc, wait_busy,
    input wire dat0,
    output reg sd_clk,
    inout wire sd_cmd,
    output wire idle, card_tick,
    output reg done,
    output reg [3:0] error,
    output reg [31:0] response
);
    localparam integer HALF=(CLK_HZ/(2*SD_HZ) < 2) ? 2 : CLK_HZ/(2*SD_HZ);
    localparam IDLE=0, ARM=1, TX=2, WAIT=3, RX=4, CHECK=5, BUSY=6, GAP=7;
    reg [2:0] state;
    reg [31:0] divider, timeout_count;
    reg [47:0] frame, received;
    reg [5:0] bit_index, saved_command;
    reg response_needed, crc_needed, busy_needed, cmd_oe, cmd_value;
    reg [3:0] gap_count;
    // Oversample slow SDIO inputs in the 50MHz domain. All protocol sampling
    // still happens on card rising ticks, >=100 clocks after the card launch.
    (* ASYNC_REG = "TRUE" *) reg cmd_meta, cmd_sync, dat_meta, dat_sync;
    always @(posedge clk) begin
        if(!resetn) begin cmd_meta<=1; cmd_sync<=1; dat_meta<=1; dat_sync<=1; end
        else begin cmd_meta<=sd_cmd; cmd_sync<=cmd_meta; dat_meta<=dat0; dat_sync<=dat_meta; end
    end
    wire falling=divider==HALF-1 && sd_clk;
    wire rising=divider==HALF-1 && !sd_clk;
    assign sd_cmd=cmd_oe ? cmd_value : 1'bz;
    assign idle=state==IDLE;
    assign card_tick=rising;
    function [6:0] crc7;
        input [39:0] bits;
        integer i;
        reg [6:0] c;
        reg feedback;
        begin
            c=0;
            for(i=39;i>=0;i=i-1) begin
                feedback=bits[i]^c[6]; c={c[5:0],1'b0};
                if(feedback) c=c^7'h09;
            end
            crc7=c;
        end
    endfunction
    always @(posedge clk) begin
        if(!resetn) begin
            divider<=0; sd_clk<=0; state<=IDLE; cmd_oe<=0; cmd_value<=1;
            done<=0; error<=0; response<=0; frame<=0; received<=0;
            timeout_count<=0; bit_index<=0; saved_command<=0;
            response_needed<=0; crc_needed<=0; busy_needed<=0; gap_count<=0;
        end else begin
            done<=0;
            if(divider==HALF-1) begin divider<=0; sd_clk<=!sd_clk; end
            else divider<=divider+1'b1;
            case(state)
                IDLE: if(start) begin
                    frame<={2'b01,command,argument,crc7({2'b01,command,argument}),1'b1};
                    saved_command<=command; response_needed<=expect_response;
                    crc_needed<=check_crc; busy_needed<=wait_busy;
                    error<=0; response<=0; timeout_count<=0; state<=ARM;
                end
                ARM: if(falling) begin
                    cmd_oe<=1; cmd_value<=frame[47]; bit_index<=47; state<=TX;
                end
                TX: if(falling) begin
                    if(bit_index==0) begin
                        cmd_oe<=0; timeout_count<=0; gap_count<=0;
                        state<=response_needed ? WAIT : GAP;
                    end else begin bit_index<=bit_index-1'b1; cmd_value<=frame[bit_index-1'b1]; end
                end
                WAIT: if(rising) begin
                    if(cmd_sync==1'b0) begin
                        received<=0; bit_index<=46; state<=RX;
                    end else if(timeout_count==RESPONSE_CLOCKS-1) begin
                        error<=1; state<=GAP; gap_count<=0;
                    end else timeout_count<=timeout_count+1'b1;
                end
                RX: if(rising) begin
                    received[bit_index]<=cmd_sync;
                    if(bit_index==0) state<=CHECK;
                    else bit_index<=bit_index-1'b1;
                end
                CHECK: begin
                    response<=received[39:8]; gap_count<=0; timeout_count<=0;
                    if(received[47:46]!=0 || !received[0]) begin error<=2; state<=GAP; end
                    else if(crc_needed && (received[45:40]!=saved_command ||
                            crc7(received[47:8])!=received[7:1])) begin error<=3; state<=GAP; end
                    else if(!crc_needed && received[45:40]!=6'h3f) begin error<=2; state<=GAP; end
                    else state<=busy_needed ? BUSY : GAP;
                end
                BUSY: if(rising) begin
                    // Allow eight clocks for the card to assert DAT0 busy.
                    if(gap_count<8) gap_count<=gap_count+1'b1;
                    else if(dat_sync==1'b1) begin state<=GAP; gap_count<=0; end
                    else if(timeout_count==RESPONSE_CLOCKS-1) begin error<=4; state<=GAP; gap_count<=0; end
                    else timeout_count<=timeout_count+1'b1;
                end
                GAP: if(rising) begin
                    if(gap_count==7) begin state<=IDLE; done<=1; end
                    else gap_count<=gap_count+1'b1;
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
