// FPGA-initiated, one-request/one-reply HSPI16 bridge to CH569 USB Host.
// USB transaction completion is accepted only from a CRC-valid reply.
module push2_hspi_link_debug #(
    parameter integer POLL_CYCLES=25000, TIMEOUT_CYCLES=50000000
)(
    input wire clk,rst,host_enable,
    output wire htclk,htreq,htvld,input wire htrdy,
    input wire hrclk,hrreq,hrvld,output wire hrack,inout wire [15:0] hd,
    input wire req_valid,output wire req_ready,
    input wire [6:0] req_address,input wire [3:0] req_endpoint,
    input wire req_data1,input wire [9:0] req_length,
    input wire tx_valid,output wire tx_ready,input wire [7:0] tx_data,input wire tx_last,
    output reg out_done,output reg [2:0] out_response,
    output wire midi_valid,input wire midi_ready,output wire [31:0] midi_event,
    output reg configured,high_speed,output reg [15:0] vid,pid,
    output reg [6:0] address,output reg [7:0] display_ep,midi_ep,
    output reg [10:0] display_mps,midi_mps,
    output reg [31:0] replies,link_errors,usb_in_errors,usb_packets,
    output reg [223:0] diagnostic,
    output reg [7:0] host_state,enum_error,hspi_errors
);
    reg [15:0] txram[0:263];
    // Keep the small fixed header in registers; MIDI payload is two true
    // dual-clock RAM banks. Registered reads avoid an 8192-FF receive array.
    reg [15:0] rxram[0:15];
    reg [15:0] midi_lo[0:127],midi_hi[0:127];
    reg [15:0] midi_lo_read,midi_hi_read;
    reg [8:0] receive_words,reply_words;
    wire [31:0] phy_data,rx_data;
    reg [15:0] tx_read;
    wire [2:0] phy_oe;
    wire [8:0] tx_addr,rx_addr;
    always @(posedge clk) tx_read<=txram[tx_addr];
    wire rx_write,rx_done,rx_crc_error,rx_num_error,phy_tx_done;
    reg tx_start;
    reg bootstrap;reg [3:0] native_sequence;
    reg [11:0] tx_length;
    genvar g;
    generate for(g=0;g<16;g=g+1) begin: data_io
        assign hd[g]=phy_oe[g/8]?phy_data[g]:1'bz;
    end endgenerate
    push_hspi_phy #(.TX_ADDR(0),.RX_ADDR(0)) phy(
        .clk(clk),.rstn(!rst),.dat_mod(2'b01),.HTCLK(htclk),.HTREQ(htreq),
        .HTRDY(htrdy),.HTVLD(htvld),.HTD(phy_data),.HTOE(phy_oe),
        .tx_act(tx_start),.tx_len(tx_length),.HRCLK(hrclk),.HRACT(hrreq),
        .HRVLD(hrvld),.HTACK(hrack),.HRD({16'd0,hd}),
        .ram_rdata({16'd0,tx_read}),.tx_addr(tx_addr),.tx_done(phy_tx_done),
        .rx_write(rx_write),.rx_addr(rx_addr),.rx_data(rx_data),
        .rx_done(rx_done),.rx_crc_error(rx_crc_error),.rx_num_error(rx_num_error),
        .ram_clk(),.ram_csn(),.ram_wen(),.ram_addr(),.ram_wdata(),.rx_crc_value());
    reg reply_toggle,reply_bad;
    wire [7:0] payload_write_index=rx_addr[8:1]-8'd8;
    always @(posedge hrclk) begin
        if(rx_write) begin
            if(rx_addr<16) rxram[rx_addr[3:0]]<=rx_data[15:0];
            else if(rx_addr<272) begin
                if(rx_addr[0]) midi_hi[payload_write_index[6:0]]<=rx_data[15:0];
                else midi_lo[payload_write_index[6:0]]<=rx_data[15:0];
            end
        end
    end
    always @(posedge hrclk or posedge rst) begin
        if(rst) begin reply_toggle<=0;reply_bad<=0;receive_words<=0;reply_words<=0;end
        else begin
            if(rx_write) receive_words<=receive_words+1'b1;
            if(rx_done) begin
                reply_toggle<=~reply_toggle;reply_bad<=rx_crc_error || rx_num_error;
                reply_words<=receive_words;receive_words<=0;
            end
        end
    end
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] reply_sync;
    always @(posedge clk or posedge rst)
        if(rst) reply_sync<=0;else reply_sync<={reply_sync[1:0],reply_toggle};
    // Reply RAM and reply_bad remain unchanged until the next request has
    // completed. The synchronized toggle grants read ownership to clk.
    reg seen;
    localparam IDLE=0,HEADER=1,PAYLOAD=2,START=3,WAIT_REPLY=4,CHECK=5,EVENTS=6,PRIME=7;
    reg [2:0] state;
    reg [15:0] ticket;
    reg [7:0] opcode,endpoint;
    reg [6:0] target_address;
    reg data1;
    reg [9:0] length,position;
    reg [3:0] header_index;
    reg [7:0] low_byte;
    reg [7:0] event_index,event_count;
    reg [31:0] timer,poll_timer;
    assign req_ready=state==IDLE && configured && host_enable;
    assign tx_ready=state==PAYLOAD;
    assign midi_valid=state==EVENTS;
    always @(posedge clk) begin
        midi_lo_read<=midi_lo[event_index[6:0]];
        midi_hi_read<=midi_hi[event_index[6:0]];
    end
    assign midi_event={midi_hi_read,midi_lo_read};
    reg [15:0] header_word;
    always @* begin
        case(header_index)
            0:header_word=16'h3250;1:header_word=16'h3151;
            2:header_word=ticket;3:header_word={endpoint,opcode};
            4:header_word={1'b0,target_address,4'd0,data1,3'd0};
            5:header_word={6'd0,length};6:header_word={7'd0,bootstrap,8'd1};default:header_word={12'd0,native_sequence};
        endcase
    end
    always @(posedge clk or posedge rst) begin
        if(rst) begin
            diagnostic<=0;state<=IDLE;ticket<=0;tx_start<=0;bootstrap<=1;native_sequence<=0;tx_length<=0;seen<=0;
            opcode<=0;endpoint<=0;target_address<=0;data1<=0;length<=0;position<=0;
            header_index<=0;low_byte<=0;event_index<=0;event_count<=0;timer<=0;poll_timer<=0;
            configured<=0;high_speed<=0;vid<=0;pid<=0;address<=0;display_ep<=0;midi_ep<=0;
            display_mps<=0;midi_mps<=0;out_done<=0;out_response<=0;replies<=0;link_errors<=0;
            usb_in_errors<=0;usb_packets<=0;host_state<=0;enum_error<=0;hspi_errors<=0;
        end else begin
            tx_start<=0;out_done<=0;
            if(poll_timer<POLL_CYCLES) poll_timer<=poll_timer+1'b1;
            if(state!=IDLE && state!=EVENTS) timer<=timer+1'b1;else timer<=0;
            if(state!=IDLE && state!=EVENTS && timer==TIMEOUT_CYCLES-1) begin
                link_errors<=link_errors+1'b1;configured<=0;state<=IDLE;
                if(opcode==1) begin out_done<=1;out_response<=4;end
            end else case(state)
                IDLE: if((req_valid && req_ready) || poll_timer==POLL_CYCLES) begin
                    opcode<=req_valid && req_ready?1:host_enable?(host_state==0?2:0):(host_state!=0?3:0);
                    endpoint<=req_valid && req_ready?{4'd0,req_endpoint}:0;
                    target_address<=req_address;data1<=req_data1;
                    length<=req_valid && req_ready?req_length:0;
                    header_index<=0;position<=0;poll_timer<=0;ticket<=ticket+1'b1;state<=HEADER;
                end
                HEADER: begin
                    txram[header_index]<=header_word;
                    if(header_index==7) begin
                        tx_length<={2'd0,length}+12'd15;
                        state<=length==0?START:PAYLOAD;
                    end else header_index<=header_index+1'b1;
                end
                PAYLOAD: if(tx_valid && tx_ready) begin
                    if(!position[0]) low_byte<=tx_data;
                    else txram[9'd8+position[9:1]]<={tx_data,low_byte};
                    if(position==length-1) begin
                        if(!tx_last || position[0]!=1) begin link_errors<=link_errors+1'b1;configured<=0;end
                        state<=START;
                    end else position<=position+1'b1;
                end
                START: begin seen<=reply_sync[2];tx_start<=1;native_sequence<=native_sequence+1'b1;state<=WAIT_REPLY;end
                WAIT_REPLY: if(reply_sync[2]!=seen) begin seen<=reply_sync[2];state<=CHECK;end
                CHECK: begin
                    if(link_errors==0 && replies==0) begin
                        diagnostic[31:0]<={16'd0,ticket};
                        diagnostic[63:32]<={20'd0,reply_bad,rx_crc_error,rx_num_error,reply_words};
                        diagnostic[95:64]<={rxram[1],rxram[0]};
                        diagnostic[127:96]<={rxram[3],rxram[2]};
                        diagnostic[159:128]<={rxram[5],rxram[4]};
                        diagnostic[191:160]<={rxram[7],rxram[6]};
                        diagnostic[223:192]<={16'd0,rxram[10]};
                    end
                    if(reply_bad || reply_words!=9'd272 || rxram[0]!=16'h3250 || rxram[1]!=16'h3152 || rxram[2]!=ticket || rxram[10]>512 || rxram[10][1:0]!=0) begin
                        configured<=0;link_errors<=link_errors+1'b1;
                        if(opcode==1) begin out_done<=1;out_response<=4;end
                        state<=IDLE;
                    end else begin
                        bootstrap<=0;replies<=replies+1'b1;host_state<=rxram[3][15:8];
                        configured<=rxram[3][15:8]==2;
                        vid<=rxram[4];pid<=rxram[5];address<=rxram[6][6:0];high_speed<=rxram[6][15:8]==1;
                        display_ep<=rxram[7][7:0];midi_ep<=rxram[7][15:8];
                        display_mps<=rxram[8][10:0];midi_mps<=rxram[9][10:0];
                        enum_error<=rxram[11][7:0];hspi_errors<=rxram[11][15:8];
                        usb_in_errors<={rxram[13],rxram[12]};usb_packets<={rxram[15],rxram[14]};
                        if(opcode==1) begin out_done<=1;out_response<=rxram[3][2:0];end
                        event_index<=0;event_count<=rxram[10][9:2];
                        state<=rxram[10]==0?IDLE:PRIME;
                    end
                end
                PRIME: state<=EVENTS;
                EVENTS: if(midi_ready) begin
                    if(event_index+1'b1==event_count) state<=IDLE;
                    else begin event_index<=event_index+1'b1;state<=PRIME;end
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
