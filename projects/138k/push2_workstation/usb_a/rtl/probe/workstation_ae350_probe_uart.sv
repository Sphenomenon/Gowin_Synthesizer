`default_nettype none
// Atomic 64-word APB snapshot across to the independent board reference clock.
// Each byte frame is A138LM01 + UserCode + sequence + word_count + words + CRC32.
module workstation_ae350_probe_uart #(
    parameter [31:0] USER_CODE=0,
    parameter integer BAUD_DIVISOR=434,
    parameter integer PERIOD_CYCLES=5000000,
    parameter integer SNAPSHOT_TIMEOUT=2500000
)(
    input wire clk_50m,reset_n,
    input wire pclk,preset_n,
    input wire [2047:0] source_words,
    input wire [3:0] platform_flags,
    output reg tx=1,
    output reg [511:0] status_50mhz=0
);
    reg request=0,ack=0;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg request_meta=0,request_sync=0;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg ack_meta=0,ack_sync=0;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [3:0] flags_meta=0,flags_sync=0;
    reg [2047:0] held_words=0;
    always @(posedge pclk or negedge preset_n) begin
        if(!preset_n) begin request_meta<=0;request_sync<=0;ack<=0;held_words<=0;end
        else begin
            request_meta<=request;request_sync<=request_meta;
            if(request_sync!=ack) begin held_words<=source_words;ack<=request_sync;end
        end
    end
    reg [2047:0] words=0;
    reg [31:0] next_sequence=0,frame_sequence=0;
    reg [31:0] period=0,wait_count=0;
    reg [2:0] state=0;
    reg [1:0] settle=0;
    reg [8:0] byte_index=0;
    reg [31:0] crc=32'hffffffff;
    reg [9:0] shift=10'h3ff;
    reg [3:0] bits_left=0;
    reg [31:0] baud_count=0;
    wire [63:0] magic="A138LM01";
    function automatic [31:0] crc_byte(input [31:0] previous,input [7:0] value);
        reg [31:0] next;integer bit_index;
        begin next=previous^{24'd0,value};
            for(bit_index=0;bit_index<8;bit_index=bit_index+1)
                next=(next>>1)^(next[0]?32'hedb88320:32'd0);
            crc_byte=next;
        end
    endfunction
    function automatic [7:0] frame_byte(input [8:0] index);
        reg [31:0] tail;
        begin
            tail=~crc;
            if(index<8)frame_byte=magic[(7-index)*8+:8];
            else if(index<12)frame_byte=USER_CODE[(index-8)*8+:8];
            else if(index<16)frame_byte=frame_sequence[(index-12)*8+:8];
            else if(index<20)frame_byte=(index==16)?8'd64:8'd0;
            else if(index<276)frame_byte=words[(index-20)*8+:8];
            else frame_byte=tail[(index-276)*8+:8];
        end
    endfunction
    wire [7:0] next_byte=frame_byte(byte_index);
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin
            request<=0;ack_meta<=0;ack_sync<=0;flags_meta<=0;flags_sync<=0;
            words<=0;next_sequence<=0;frame_sequence<=0;period<=0;wait_count<=0;
            state<=0;settle<=0;byte_index<=0;crc<=32'hffffffff;
            shift<=10'h3ff;bits_left<=0;baud_count<=0;tx<=1;status_50mhz<=0;
        end else begin
            ack_meta<=ack;ack_sync<=ack_meta;flags_meta<=platform_flags;flags_sync<=flags_meta;
            if(bits_left!=0) begin
                if(baud_count==BAUD_DIVISOR-1) begin
                    baud_count<=0;bits_left<=bits_left-1'b1;
                    shift<={1'b1,shift[9:1]};tx<=shift[1];
                end else baud_count<=baud_count+1'b1;
            end
            case(state)
                0:if(period==PERIOD_CYCLES-1) begin
                    // A timed-out request remains outstanding. Toggling it
                    // again could mistake an old/reset ack for a fresh bank.
                    period<=0;
                    if(ack_sync==request)request<=!request;
                    wait_count<=0;state<=1;
                end else period<=period+1'b1;
                1:if(ack_sync==request) begin settle<=2;state<=2;end
                  else if(wait_count==SNAPSHOT_TIMEOUT-1) begin
                    // Retain last complete bank, with an explicit timeout flag.
                    words[61*32+:32]<={27'd0,1'b1,flags_sync};state<=3;
                  end else wait_count<=wait_count+1'b1;
                2:if(settle!=0)settle<=settle-1'b1;
                  else begin words<=held_words;words[61*32+:32]<={28'd0,flags_sync};state<=3;end
                3:begin
                    frame_sequence<=next_sequence;next_sequence<=next_sequence+1'b1;
                    byte_index<=0;crc<=32'hffffffff;state<=4;
                    status_50mhz<={words[35*32+:32],words[34*32+:32],words[32*32+:32],
                        words[20*32+:32],words[19*32+:32],words[18*32+:32],words[17*32+:32],words[16*32+:32],
                        words[14*32+:32],words[12*32+:32],words[11*32+:32],words[9*32+:32],
                        words[8*32+:32],words[7*32+:32],words[6*32+:32],words[1*32+:32]};
                end
                4:if(bits_left==0) begin
                    shift<={1'b1,next_byte,1'b0};tx<=0;bits_left<=10;baud_count<=0;
                    if(byte_index<276)crc<=crc_byte(crc,next_byte);
                    if(byte_index==279)state<=5;else byte_index<=byte_index+1'b1;
                end
                5:if(bits_left==0)state<=0;
                default:state<=0;
            endcase
        end
    end
endmodule
`default_nettype wire
