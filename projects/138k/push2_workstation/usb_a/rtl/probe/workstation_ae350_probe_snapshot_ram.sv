`timescale 1ns/1ps
`default_nettype none
// Explicit bsram4/bsram8 probe modes. One canonical immutable double-buffered snapshot
// serves UART and GAO. No 2048-bit reference-domain words/full/frozen copies.
module workstation_ae350_probe_snapshot_ram #(
    parameter [31:0] USER_CODE=0,
    parameter integer PAGE_WORDS=16,
    parameter integer BAUD_DIVISOR=434,PERIOD_CYCLES=5000000,SNAPSHOT_TIMEOUT=2500000
)(
    input wire clk_50m,reset_n,pclk,preset_n,
    input wire [2047:0] source_words,
    input wire [3:0] platform_flags,
    input wire [31:0] digital_io_50mhz,health_50mhz,
    output reg tx=1,
    output wire [6:0] transport_health_50mhz,
    output reg snapshot_published_50mhz=0,
    // Valid only on sample_update_o. Caller retains the top-level704/448-bit FF
    // bank between updates, preserving exactly four50MHz cycles per page.
    output wire sample_update_o,
    output wire [PAGE_WORDS*32+191:0] sample_50mhz
);
    localparam integer PAGE_COUNT=64/PAGE_WORDS,PAGE_BITS=$clog2(PAGE_COUNT),GROUPS_PER_PAGE=PAGE_WORDS/4;
    initial if(PAGE_WORDS!=16 && PAGE_WORDS!=8)$fatal(1,"only explicit16/8-word GAO pages are supported");
    localparam [2:0] PERIOD=0,WAIT_ACK=1,SETTLE=2,COPY=3,PUBLISH=4,TRANSMIT=5,DRAIN=6;
    reg request=0,ack=0;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg request_meta=0,request_sync=0,ack_meta=0,ack_sync=0;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [3:0] flags_meta=0,flags_sync=0;
    // One-edge pclk snapshot is retained. Local APB reset cannot forge ACK or
    // mutate this held bundle while the reference-domain copy is in flight.
    reg [2047:0] held_words=0;
    always @(posedge pclk or negedge reset_n)begin
        if(!reset_n)begin request_meta<=0;request_sync<=0;ack<=0;held_words<=0;end
        else begin
            request_meta<=request;request_sync<=request_meta;
            if(preset_n && request_sync!=ack)begin held_words<=source_words;ack<=request_sync;end
        end
    end
    reg [2:0] state=PERIOD;
    reg [31:0] period=0,wait_count=0,next_sequence=0,published_sequence=0;
    reg published_bank=0,copy_bank=0,copy_zero=0;
    reg [4:0] published_flags=0,pending_flags=0;
    reg [3:0] copy_group=0;
    reg [PAGE_WORDS*32-1:0] prepared_page0=0;
    reg [8:0] byte_index=0;
    reg [31:0] crc=32'hffffffff;
    reg [9:0] shift=10'h3ff;
    reg [3:0] bits_left=0;
    reg [31:0] baud_count=0;
    assign transport_health_50mhz={state,flags_sync};

    reg frozen_valid=0,frozen_bank=0;
    reg [31:0] frozen_sequence=0,frozen_io=0,frozen_health=0;
    reg [4:0] frozen_flags=0;
    reg [PAGE_BITS-1:0] page=PAGE_BITS'(PAGE_COUNT-1);
    reg [1:0] phase=0;
    reg [PAGE_WORDS*32-129:0] prefetch=0;
    wire boundary=phase==3;
    wire replace_snapshot=boundary && page==PAGE_BITS'(PAGE_COUNT-1) && snapshot_published_50mhz &&
        (!frozen_valid || published_sequence!=frozen_sequence);
    wire [PAGE_BITS-1:0] next_page=page+1'b1;
    // Read group0 of the following page at the current boundary. In16-word mode groups1..3
    // return in the next three cycles. In8-word mode request group1 at phase0,
    // hold its output until the boundary, and bypass that final group at commit.
    wire [1:0] read_group=phase+2'd1;
    wire [PAGE_BITS-1:0] read_page=phase==3 ? page+PAGE_BITS'(2):next_page;
    wire read_bank=replace_snapshot ? published_bank:frozen_bank;
    wire read_enable=reset_n && (frozen_valid || replace_snapshot) &&
        (PAGE_WORDS==16 || phase==0 || phase==3);
    wire narrow_group=phase!=3;
    wire [4:0] read_address=PAGE_WORDS==8 ? {read_bank,3'(read_page),narrow_group}:
        {read_bank,2'(read_page),read_group};
    wire write_enable=reset_n && state==COPY;
    wire [4:0] write_address={copy_bank,copy_group};
    wire [127:0] copy_data=copy_zero ? 128'd0:held_words[copy_group*128+:128];
    wire [127:0] ram_data;
    genvar lane;
    generate for(lane=0;lane<8;lane=lane+1)begin:lanes
        // Native16-bit mode, explicit synchronous read, no RAM reset. Valid
        // ownership gates every consumer until a complete bank is committed.
        workstation_sdp #(.DATA_WIDTH(16),.ADDR_WIDTH(5)) ram(
            .write_clk_i(clk_50m),.write_enable_i(write_enable),.write_addr_i(write_address),
            .write_data_i(copy_data[lane*16+:16]),.read_clk_i(clk_50m),
            .read_enable_i(read_enable),.read_addr_i(read_address),.read_data_o(ram_data[lane*16+:16]));
    end endgenerate
    reg read_valid=0,read_bank_q=0;
    reg [3:0] read_group_q=0;
    always @(posedge clk_50m or negedge reset_n)begin
        if(!reset_n)begin
            read_valid<=0;read_bank_q<=0;read_group_q<=0;
            frozen_valid<=0;frozen_bank<=0;frozen_sequence<=0;frozen_flags<=0;frozen_io<=0;frozen_health<=0;
            page<=PAGE_BITS'(PAGE_COUNT-1);phase<=0;prefetch<=0;
        end else begin
            read_valid<=read_enable;read_bank_q<=read_bank;read_group_q<=PAGE_WORDS==8 ? {3'(read_page),narrow_group}:{2'(read_page),read_group};
            phase<=phase+1'b1;
            if(phase<2'(GROUPS_PER_PAGE-1) && read_valid)prefetch[phase*128+:128]<=ram_data;
            if(boundary)begin
                page<=next_page;
                if(replace_snapshot)begin
                    frozen_valid<=1;frozen_bank<=published_bank;frozen_sequence<=published_sequence;frozen_flags<=published_flags;
                    frozen_io<=digital_io_50mhz;frozen_health<=health_50mhz;
                end
            end
        end
    end
    wire outgoing_valid=frozen_valid || replace_snapshot;
    wire [31:0] outgoing_sequence=replace_snapshot ? published_sequence:frozen_sequence;
    wire [31:0] outgoing_io=replace_snapshot ? digital_io_50mhz:frozen_io;
    wire [31:0] outgoing_health=replace_snapshot ? health_50mhz:frozen_health;
    reg [PAGE_WORDS*32-1:0] outgoing_page;
    always @*begin
        outgoing_page=replace_snapshot ? prepared_page0:{ram_data,prefetch};
        if(next_page==PAGE_BITS'(PAGE_COUNT-1))outgoing_page[(61%PAGE_WORDS)*32+:32]={27'd0,frozen_flags};
        if(!outgoing_valid)outgoing_page=0;
    end
    wire [31:0] metadata=PAGE_WORDS==8 ? {8'd8,8'd64,8'd8,4'd0,outgoing_valid,3'(next_page)}:
        {8'd4,8'd64,8'd16,5'd0,outgoing_valid,2'(next_page)};
    wire [31:0] schema_magic=PAGE_WORDS==8 ? 32'ha1386404:32'ha1386403;
    assign sample_update_o=boundary;
    assign sample_50mhz={outgoing_health,outgoing_io,metadata,schema_magic,USER_CODE,outgoing_sequence,outgoing_page};

    // UART borrows the continuous GAO read stream, never steals a RAM cycle.
    // Every32-bit word appears once per16 (bsram4) or32 (bsram8) reference clocks. A tagged cache
    // absorbs that latency before launching the next 8N1 byte.
    wire payload_byte=byte_index>=20 && byte_index<276;
    wire [5:0] uart_word=6'((byte_index-9'd20)>>2);
    reg cache_valid=0;
    reg [5:0] cache_word=0;
    reg [31:0] cache_data=0;
    wire payload_ready=!payload_byte || (cache_valid && cache_word==uart_word);
    function automatic [31:0] crc_byte(input [31:0] previous,input [7:0] value);
        reg [31:0] v;integer b;begin v=previous^{24'd0,value};
            for(b=0;b<8;b=b+1)v=(v>>1)^(v[0]?32'hedb88320:32'd0);crc_byte=v;end
    endfunction
    wire [63:0] magic="A138LM01";
    wire [31:0] crc_tail=~crc;
    reg [7:0] next_byte;
    always @*begin
        if(byte_index<8)next_byte=magic[(7-byte_index)*8+:8];
        else if(byte_index<12)next_byte=USER_CODE[(byte_index-8)*8+:8];
        else if(byte_index<16)next_byte=published_sequence[(byte_index-12)*8+:8];
        else if(byte_index<20)next_byte=byte_index==16 ? 8'd64:8'd0;
        else if(byte_index<276)next_byte=cache_data[byte_index[1:0]*8+:8];
        else next_byte=crc_tail[(byte_index-276)*8+:8];
    end
    always @(posedge clk_50m or negedge reset_n)begin
        if(!reset_n)begin
            request<=0;ack_meta<=0;ack_sync<=0;flags_meta<=0;flags_sync<=0;
            state<=PERIOD;period<=0;wait_count<=0;next_sequence<=0;published_sequence<=0;
            published_bank<=0;copy_bank<=0;copy_zero<=0;published_flags<=0;pending_flags<=0;
            copy_group<=0;prepared_page0<=0;snapshot_published_50mhz<=0;
            byte_index<=0;crc<=32'hffffffff;shift<=10'h3ff;bits_left<=0;baud_count<=0;tx<=1;
            cache_valid<=0;cache_word<=0;cache_data<=0;
        end else begin
            ack_meta<=ack;ack_sync<=ack_meta;flags_meta<=platform_flags;flags_sync<=flags_meta;
            if(read_valid && read_bank_q==published_bank && read_group_q==uart_word[5:2])begin
                cache_valid<=1;cache_word<=uart_word;
                cache_data<=uart_word==61 ? {27'd0,published_flags}:ram_data[uart_word[1:0]*32+:32];
            end
            if(bits_left!=0)begin
                if(baud_count==BAUD_DIVISOR-1)begin
                    baud_count<=0;bits_left<=bits_left-1'b1;shift<={1'b1,shift[9:1]};tx<=shift[1];
                end else baud_count<=baud_count+1'b1;
            end
            case(state)
                PERIOD:if(period==PERIOD_CYCLES-1)begin
                    // Never overwrite the old bank until the exporter has
                    // adopted the last publication and UART has finished it.
                    if(!snapshot_published_50mhz || (frozen_valid && frozen_sequence==published_sequence))begin
                        period<=0;if(ack_sync==request)request<=!request;
                        wait_count<=0;state<=WAIT_ACK;
                    end
                end else period<=period+1'b1;
                WAIT_ACK:if(ack_sync==request)begin state<=SETTLE;wait_count<=2;end
                    else if(wait_count==SNAPSHOT_TIMEOUT-1)begin
                        pending_flags<={1'b1,flags_sync};
                        if(snapshot_published_50mhz)state<=PUBLISH;
                        else begin copy_group<=0;copy_bank<=!published_bank;copy_zero<=1;state<=COPY;end
                    end else wait_count<=wait_count+1'b1;
                SETTLE:if(wait_count!=0)wait_count<=wait_count-1'b1;
                    else begin pending_flags<={1'b0,flags_sync};copy_group<=0;copy_bank<=!published_bank;copy_zero<=0;state<=COPY;end
                COPY:begin
                    if(copy_group<4'(GROUPS_PER_PAGE))prepared_page0[copy_group*128+:128]<=copy_data;
                    if(copy_group==15)begin published_bank<=copy_bank;state<=PUBLISH;end
                    else copy_group<=copy_group+1'b1;
                end
                PUBLISH:begin
                    published_sequence<=next_sequence;next_sequence<=next_sequence+1'b1;published_flags<=pending_flags;
                    snapshot_published_50mhz<=1;byte_index<=0;crc<=32'hffffffff;cache_valid<=0;state<=TRANSMIT;
                end
                TRANSMIT:if(bits_left==0 && payload_ready)begin
                    shift<={1'b1,next_byte,1'b0};tx<=0;bits_left<=10;baud_count<=0;
                    if(byte_index<276)crc<=crc_byte(crc,next_byte);
                    if(byte_index==279)state<=DRAIN;else byte_index<=byte_index+1'b1;
                end
                DRAIN:if(bits_left==0)state<=PERIOD;
                default:state<=PERIOD;
            endcase
        end
    end
endmodule
`default_nettype wire
