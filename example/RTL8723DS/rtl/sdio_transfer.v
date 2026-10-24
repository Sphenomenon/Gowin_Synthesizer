// Single-command SDIO engine plus 1-bit CMD53 data/CRC16. Max 2048 bytes.
// The command lane retains the already-verified native SDIO implementation.
module sdio_transfer #(
    parameter integer CLK_HZ=50000000,
    parameter integer SD_HZ=250000
)(
    input wire clk, resetn, start,
    input wire [5:0] command,
    input wire [31:0] argument,
    input wire expect_response, check_crc, wait_busy,
    output wire sd_clk,
    inout wire sd_cmd, sd_dat0,
    output wire idle,
    output reg done,
    output reg [3:0] error,
    output reg [31:0] response,
    output wire [10:0] tx_address,
    input wire [7:0] tx_data,
    output reg rx_write,
    output reg [10:0] rx_address,
    output reg [7:0] rx_data
);
    wire command_done, command_idle;
    wire [3:0] command_error;
    wire [31:0] command_response;
    wire command_start=start && idle;
    sdio_command #(.CLK_HZ(CLK_HZ),.SD_HZ(SD_HZ)) cmd (
        .clk(clk),.resetn(resetn),.start(command_start),.command(command),.argument(argument),
        .expect_response(expect_response),.check_crc(check_crc),.wait_busy(wait_busy),
        .dat0(sd_dat0),.sd_clk(sd_clk),.sd_cmd(sd_cmd),.idle(command_idle),
        .card_tick(),.done(command_done),.error(command_error),.response(command_response));

    localparam D_IDLE=0,R_START=1,R_DATA=2,R_CRC=3,R_END=4,
        W_START=5,W_DATA=6,W_CRC=7,W_END=8,W_RELEASE=9,W_ACK=10,
        W_ACK_BITS=11,W_BUSY=12,D_DONE=13;
    reg [3:0] state=D_IDLE;
    reg busy=0, cmd_finished=0, data_finished=0, has_data=0;
    reg sd_previous=0;
    (* ASYNC_REG="TRUE" *) reg dmeta=1, dsync=1;
    wire rising=sd_clk && !sd_previous;
    wire falling=!sd_clk && sd_previous;
    reg data_oe=0, data_value=1;
    assign sd_dat0=data_oe ? data_value : 1'bz;
    assign idle=!busy && command_idle;
    reg [11:0] length=0;
    reg [14:0] bit_count=0;
    reg [4:0] crc_count=0;
    reg [15:0] crc=0, received_crc=0;
    reg [7:0] partial=0;
    reg [4:0] ack_bits=0;
    reg [16:0] timeout_count=0;
    reg [3:0] data_error=0;
    assign tx_address=bit_count[13:3];
    wire [11:0] requested_length=argument[27] ? {argument[2:0],9'b0} :
                                             (argument[8:0]==0 ? 12'd512 : {3'b0,argument[8:0]});
    function [15:0] crc_bit;
        input [15:0] c;
        input b;
        begin crc_bit={c[14:0],1'b0} ^ ((c[15]^b) ? 16'h1021 : 16'h0000); end
    endfunction
    always @(posedge clk) begin
        if(!resetn) begin
            sd_previous<=0; dmeta<=1; dsync<=1;
        end else begin
            sd_previous<=sd_clk; dmeta<=sd_dat0; dsync<=dmeta;
        end
    end
    always @(posedge clk) begin
        if(!resetn) begin
            busy<=0; done<=0; error<=0; response<=0; state<=D_IDLE;
            cmd_finished<=0; data_finished<=0; has_data<=0;
            data_oe<=0; data_value<=1; rx_write<=0; rx_address<=0; rx_data<=0;
            bit_count<=0; crc_count<=0; crc<=0; received_crc<=0; partial<=0;
            timeout_count<=0; data_error<=0; length<=0; ack_bits<=0;
        end else begin
            done<=0; rx_write<=0;
            if(command_start) begin
                busy<=1; cmd_finished<=0; error<=0; response<=0;
                has_data<=command==53; data_finished<=command!=53;
                length<=requested_length; bit_count<=0; crc_count<=0; crc<=0;
                received_crc<=0; timeout_count<=0; data_error<=0; partial<=0;
                data_oe<=0; data_value<=1;
                if(command==53) begin
                    if((argument[27] && (argument[8:0]==0 || argument[8:0]>4)) ||
                       requested_length==0 || requested_length>2048) begin
                        data_error<=7; data_finished<=1; state<=D_DONE;
                    end else state<=argument[31] ? W_START : R_START;
                end else state<=D_IDLE;
            end
            if(busy && command_done) begin
                cmd_finished<=1; response<=command_response;
                if(command_error!=0 || (has_data && (command_response & 32'hcb00)!=0)) begin
                    error<=command_error!=0 ? command_error : 4'd9;
                    data_finished<=1; data_oe<=0; state<=D_DONE;
                end
            end
            if(busy && cmd_finished && data_finished) begin
                busy<=0; done<=1; state<=D_IDLE; data_oe<=0;
                if(error==0) error<=data_error;
            end
            if(busy && has_data && !data_finished) begin
                if(rising) begin
                    if(timeout_count==17'h1ffff) begin
                        data_error<=4; data_finished<=1; data_oe<=0; state<=D_DONE;
                    end else timeout_count<=timeout_count+1'b1;
                end
                case(state)
                    R_START: if(rising && !dsync) begin
                        state<=R_DATA; timeout_count<=0; crc<=0; received_crc<=0;
                    end
                    R_DATA: if(rising) begin
                        partial<={partial[6:0],dsync}; crc<=crc_bit(crc,dsync);
                        if(bit_count[2:0]==7) begin
                            rx_write<=1; rx_address<=bit_count[13:3];
                            rx_data<={partial[6:0],dsync};
                        end
                        if(bit_count==({length,3'b0}-1) || (argument[27] && bit_count[11:0]==4095)) begin state<=R_CRC; crc_count<=0; end
                        else bit_count<=bit_count+1'b1;
                    end
                    R_CRC: if(rising) begin
                        received_crc<={received_crc[14:0],dsync};
                        if(crc_count==15) state<=R_END;
                        else crc_count<=crc_count+1'b1;
                    end
                    R_END: if(rising) begin
                        if(!dsync) data_error<=5;
                        else if(received_crc!=crc) data_error<=6;
                        if(!dsync || received_crc!=crc || bit_count==({length,3'b0}-1)) begin
                            data_finished<=1; state<=D_DONE;
                        end else begin state<=R_START; bit_count<=bit_count+1'b1; timeout_count<=0; end
                    end
                    W_START: if(cmd_finished && error==0 && falling) begin
                        data_oe<=1; data_value<=0; state<=W_DATA;
                        timeout_count<=0; crc<=0;
                    end
                    W_DATA: if(falling) begin
                        data_value<=tx_data[7-bit_count[2:0]];
                        crc<=crc_bit(crc,tx_data[7-bit_count[2:0]]);
                        if(bit_count==({length,3'b0}-1) || (argument[27] && bit_count[11:0]==4095)) begin state<=W_CRC; crc_count<=0; end
                        else bit_count<=bit_count+1'b1;
                    end
                    W_CRC: if(falling) begin
                        data_value<=crc[15-crc_count];
                        if(crc_count==15) state<=W_END;
                        else crc_count<=crc_count+1'b1;
                    end
                    W_END: if(falling) begin data_value<=1; state<=W_RELEASE; end
                    W_RELEASE: if(falling) begin data_oe<=0; state<=W_ACK; timeout_count<=0; end
                    W_ACK: if(rising && !dsync) begin
                        ack_bits<=0; crc_count<=0; state<=W_ACK_BITS;
                    end
                    W_ACK_BITS: if(rising) begin
                        ack_bits<={ack_bits[3:0],dsync};
                        if(crc_count==3) begin
                            if({ack_bits[3:0],dsync}!=5'b00101) begin
                                data_error<=8; data_finished<=1; state<=D_DONE;
                            end else begin state<=W_BUSY; timeout_count<=0; end
                        end else crc_count<=crc_count+1'b1;
                    end
                    W_BUSY: if(rising && dsync) begin
                        if(bit_count==({length,3'b0}-1)) begin data_finished<=1; state<=D_DONE; end
                        else begin state<=W_START; bit_count<=bit_count+1'b1; timeout_count<=0; end
                    end
                    default: ;
                endcase
            end
        end
    end
endmodule
