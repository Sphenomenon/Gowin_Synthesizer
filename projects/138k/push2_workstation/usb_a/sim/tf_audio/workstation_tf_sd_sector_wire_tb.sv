`timescale 1ns/1ps
`default_nettype none
// SPI mode-0 card model. The only DUT connections are its public SPI and
// sector ports: no forced card state, session stub or hierarchical deposits.
module workstation_tf_sd_wire_card #(
    parameter integer CARD_KIND=0 // 0=SDHCv2, 1=SDv2 byte addressing, 2=SDv1
) (
    input wire ssn,sck,mosi,
    output reg miso,
    input integer token_delay_bytes,
    input wire suppress_token,command_error,suppress_r1,
    output integer cmd17_count,payload_bytes,crc_bytes,post_crc_bytes,cs_releases,
    output integer high_clocks,
    output reg [31:0] last_argument
);
    integer bit_count,command_bytes,queue_head,queue_tail,phase,remaining,index;
    reg [7:0] rx_byte,tx_byte,queue[0:31];
    reg [47:0] command_word;
    reg idle_card;
    integer tx_kind,tx_index;
    function automatic [7:0] pattern(input [31:0] argument,input integer offset);
        pattern=argument[7:0]^argument[15:8]^offset[7:0]^{7'b0,offset[8]};
    endfunction
    task automatic enqueue(input [7:0] value);
        begin queue[queue_tail]=value; queue_tail=queue_tail+1; end
    endtask
    task automatic receive_byte(input [7:0] value);
        reg [5:0] command;
        begin
            if(command_bytes==0) begin
                if(value[7:6]==2'b01) begin command_word={40'd0,value}; command_bytes=1; end
            end else begin
                command_word={command_word[39:0],value};
                if(command_bytes==5) begin
                    command_bytes=0;
                    command=command_word[45:40];
                    // Response queue is empty before each command, including
                    // CMD55 + ACMD41 under the same asserted chip select.
                    if(queue_head!=queue_tail) $fatal(1,"card response overlap");
                    queue_head=0; queue_tail=0;
                    case(command)
                        0: begin idle_card=1; enqueue(8'h01); end
                        1: begin idle_card=0; enqueue(8'h00); end
                        8: if(CARD_KIND==2) enqueue(8'h05);
                           else begin enqueue(8'h01); enqueue(0); enqueue(0); enqueue(1); enqueue(8'haa); end
                        55: enqueue(idle_card ? 8'h01 : 8'h00);
                        41: begin idle_card=0; enqueue(8'h00); end
                        58: begin enqueue(0); enqueue(CARD_KIND==0 ? 8'hc0 : 8'h80); enqueue(0); enqueue(0); enqueue(0); end
                        16: begin
                            if(command_word[39:8]!=512) $fatal(1,"CMD16 block size");
                            enqueue(0);
                        end
                        17: begin
                            cmd17_count=cmd17_count+1;
                            last_argument=command_word[39:8];
                            if(!suppress_r1) enqueue(command_error ? 8'h04 : 8'h00);
                            remaining=token_delay_bytes; index=0; phase=1;
                        end
                        default: $fatal(1,"unexpected SPI command %0d",command);
                    endcase
                end else command_bytes=command_bytes+1;
            end
        end
    endtask
    task automatic next_byte;
        begin
            tx_byte=8'hff; tx_kind=0; tx_index=0;
            if(queue_head<queue_tail) begin tx_byte=queue[queue_head]; queue_head=queue_head+1; end
            else case(phase)
                1: if(!suppress_token && !command_error) begin
                    if(remaining>0) remaining=remaining-1;
                    else begin tx_byte=8'hfe; phase=2; end
                end
                2: begin
                    tx_byte=pattern(last_argument,index); tx_kind=1; tx_index=index;
                    if(index==511) begin phase=3; index=0; end
                    else index=index+1;
                end
                3: begin
                    tx_byte=(index==0) ? 8'ha5 : 8'h5a; tx_kind=2;
                    if(index==1) begin phase=4; index=0; end else index=1;
                end
                4: tx_kind=3;
                default: begin end
            endcase
        end
    endtask
    initial begin
        miso=1; bit_count=0; command_bytes=0; queue_head=0; queue_tail=0;
        phase=0; remaining=0; index=0; rx_byte=0; tx_byte=8'hff;
        command_word=0; idle_card=1; tx_kind=0; tx_index=0;
        cmd17_count=0; payload_bytes=0; crc_bytes=0; post_crc_bytes=0;
        cs_releases=0; high_clocks=0; last_argument=0;
    end
    always @(posedge ssn) begin
        if(phase!=0) cs_releases=cs_releases+1;
        bit_count=0; command_bytes=0; queue_head=0; queue_tail=0;
        phase=0; tx_kind=0; miso=1;
    end
    always @(negedge sck) if(!ssn) begin
        if(bit_count==0) next_byte();
        miso=tx_byte[7-bit_count];
    end
    always @(posedge sck) begin
        if(ssn) high_clocks=high_clocks+1;
        else begin
            rx_byte={rx_byte[6:0],mosi};
            if(bit_count==7) begin
                bit_count=0;
                if(tx_kind==1) payload_bytes=payload_bytes+1;
                if(tx_kind==2) crc_bytes=crc_bytes+1;
                if(tx_kind==3) post_crc_bytes=post_crc_bytes+1;
                receive_byte(rx_byte);
            end else bit_count=bit_count+1;
        end
    end
endmodule

module tb_workstation_tf_sd_sector_wire #(
    parameter integer READ_DIV=12,
    parameter integer INIT_DIV=100,
    parameter integer WAIT_CLOCKS=8320,
    parameter integer CARD_KIND=0,
    parameter integer FULL_PATIENCE_ONLY=0,
    parameter integer FIRST_TOKEN_DELAY=0,
    parameter integer HOLD_ARGUMENT=0
);
    reg clk=0;
    always #10 clk=~clk;
    reg rstn=0,start=0;
    reg [31:0] sector_no=0;
    wire ssn,sck,mosi,miso,done,rvalid,read_error;
    wire [8:0] raddr;
    wire [7:0] rdata;
    wire [1:0] card_type,error_code;
    wire [3:0] card_stat;
    integer token_delay_bytes=0;
    reg suppress_token=0,command_error=0,suppress_r1=0;
    wire integer cmd17_count,payload_bytes,crc_bytes,post_crc_bytes,cs_releases,high_clocks;
    wire [31:0] last_argument;
    localparam integer ACTUAL_DIV=(READ_DIV==0) ? INIT_DIV : READ_DIV;
    localparam integer BYTE_CLOCKS=16*(ACTUAL_DIV+1);
    localparam integer TOKEN_BYTES=(WAIT_CLOCKS+BYTE_CLOCKS-1)/BYTE_CLOCKS;
    workstation_tf_sd_sector_reader #(
        .SPI_CLK_DIV(INIT_DIV),.SPI_CLK_DIV_FAST(READ_DIV),.TOKEN_WAIT_CLOCKS(WAIT_CLOCKS)
    ) dut (
        .rstn(rstn),.clk(clk),.spi_ssn(ssn),.spi_sck(sck),.spi_mosi(mosi),.spi_miso(miso),
        .card_type(card_type),.card_stat(card_stat),.start(start),.sector_no(sector_no),
        .done(done),.rvalid(rvalid),.raddr(raddr),.rdata(rdata),
        .debug_cmdrsp(),.debug_rwrsp(),.debug_cardstate(),.debug_spidone(),.debug_rvalid_session(),
        .read_error(read_error),.read_error_code(error_code)
    );
    workstation_tf_sd_wire_card #(.CARD_KIND(CARD_KIND)) card (
        .ssn(ssn),.sck(sck),.mosi(mosi),.miso(miso),.token_delay_bytes(token_delay_bytes),
        .suppress_token(suppress_token),.command_error(command_error),.suppress_r1(suppress_r1),
        .cmd17_count(cmd17_count),.payload_bytes(payload_bytes),.crc_bytes(crc_bytes),
        .post_crc_bytes(post_crc_bytes),.cs_releases(cs_releases),.high_clocks(high_clocks),
        .last_argument(last_argument)
    );
    integer cycles=0,seen_bytes=0,done_count=0,expected_sector=0,expected_address=0;
    integer expected_argument=0,reads_checked=0,aborts_checked=0;
    reg check_data=0;
    integer before_cmd,before_payload,before_crc,before_post,before_release,before_high,before_done;
    integer launched,finished;
    always @(posedge clk) begin
        cycles=cycles+1;
        if(rstn && done) done_count=done_count+1;
        if(rstn && rvalid) begin
            if(!check_data) $fatal(1,"unexpected/stale payload");
            if(raddr!==expected_address[8:0] ||
               rdata!==card.pattern(expected_argument,expected_address))
                $fatal(1,"payload/address mismatch at %0d addr=%0d data=%h",expected_address,raddr,rdata);
            expected_address=expected_address+1;
            seen_bytes=seen_bytes+1;
            if(expected_address>512) $fatal(1,"duplicate payload");
        end
    end
    task automatic wait_cycles(input integer count);
        repeat(count) @(negedge clk);
    endtask
    task automatic reset_and_initialize;
        integer limit;
        begin
            @(negedge clk); rstn=0; start=0; check_data=0;
            wait_cycles(10);
            if(rvalid || done || read_error || !ssn) $fatal(1,"reset did not fence SPI/output");
            rstn=1;
            limit=cycles+8000000;
            while(card_stat!=8 && cycles<limit) @(negedge clk);
            if(card_stat!=8) $fatal(1,"wire-level initialization timeout state=%0d",card_stat);
            if(card_type!==(CARD_KIND==0 ? 2'd3 : CARD_KIND==1 ? 2'd2 : 2'd1))
                $fatal(1,"card classification");
            wait_cycles(4);
        end
    endtask
    task automatic begin_read(input integer sector);
        begin
            expected_sector=sector;
            expected_argument=(CARD_KIND==0) ? sector : (sector<<9);
            before_cmd=cmd17_count; before_payload=payload_bytes; before_crc=crc_bytes;
            before_post=post_crc_bytes; before_release=cs_releases; before_high=high_clocks;
            before_done=done_count;
            expected_address=0; seen_bytes=0; check_data=1;
            @(negedge clk); sector_no=sector; start=1; launched=cycles;
            @(negedge clk); start=0;
            // Mutating the live argument after acceptance must not affect it.
            if(!HOLD_ARGUMENT) sector_no=32'hdeadbeef;
        end
    endtask
    task automatic finish_success;
        integer limit;
        begin
            limit=cycles+WAIT_CLOCKS+BYTE_CLOCKS*1100+100;
            while(done_count==before_done && !read_error && cycles<limit) @(negedge clk);
            finished=cycles;
            if(read_error || done_count!=before_done+1) $fatal(1,"read completion/error code=%0d",error_code);
            wait_cycles(BYTE_CLOCKS*8);
            if(seen_bytes!=512 || cmd17_count!=before_cmd+1 || payload_bytes!=before_payload+512 ||
               crc_bytes!=before_crc+2 || post_crc_bytes!=before_post || cs_releases!=before_release+1 ||
               high_clocks<before_high+8 || last_argument!==expected_argument[31:0] ||
               done_count!=before_done+1 || card_stat!=8)
                $fatal(1,"wire transaction mismatch bytes=%0d cmd17=%0d CRC=%0d tail=%0d release=%0d high=%0d",
                    seen_bytes,cmd17_count-before_cmd,crc_bytes-before_crc,post_crc_bytes-before_post,
                    cs_releases-before_release,high_clocks-before_high);
            check_data=0; reads_checked=reads_checked+1;
        end
    endtask
    task automatic expect_failure(input integer code);
        integer limit,fail_seen;
        begin
            limit=cycles+WAIT_CLOCKS+BYTE_CLOCKS*1100+100;
            while(!read_error && cycles<limit) @(negedge clk);
            if(!read_error || error_code!=code || card_stat!=10 || done_count!=before_done || seen_bytes!=0)
                $fatal(1,"terminal failure mismatch code=%0d bytes=%0d",error_code,seen_bytes);
            fail_seen=cycles;
            // Failure cannot trigger retry traffic, successful silence or a
            // late done. New starts are ignored until explicit owner reset.
            start=1; wait_cycles(BYTE_CLOCKS*20); start=0;
            if(cmd17_count!=before_cmd+1 || done_count!=before_done || rvalid || !ssn)
                $fatal(1,"failure retried/leaked");
            if(fail_seen-launched<WAIT_CLOCKS) $fatal(1,"token patience shortened in wall clocks");
            check_data=0;
        end
    endtask
    initial begin
        reset_and_initialize();
        if(FULL_PATIENCE_ONLY) begin
            // Real production 166.4-ms patience at the fastest legal divider;
            // this exceeds the old fixed 40,000-byte window by over 4x.
            token_delay_bytes=TOKEN_BYTES-2;
            begin_read(32'h00012345); finish_success();
            if(finished-launched<WAIT_CLOCKS) $fatal(1,"full patience not exercised");
        end else begin
            token_delay_bytes=FIRST_TOKEN_DELAY;
            begin_read(32'h00012345); finish_success();
            token_delay_bytes=(TOKEN_BYTES>4) ? 3 : TOKEN_BYTES-2;
            begin_read(32'h00054321);
            // A request while busy is discarded, not queued against a future
            // sector; a start held across completion is also exactly once.
            wait_cycles(BYTE_CLOCKS*12); start=1; sector_no=32'h12345678;
            finish_success(); start=0; wait_cycles(4);
            token_delay_bytes=TOKEN_BYTES-2;
            begin_read(32'h00001002); finish_success();
            suppress_token=1;
            begin_read(9); expect_failure(1);
            reset_and_initialize(); suppress_token=0; token_delay_bytes=0;
            begin_read(10); finish_success();
            command_error=1;
            begin_read(11); expect_failure(2);
            command_error=0; reset_and_initialize();
            // No R1 is sent. A late FE token + complete payload still follow
            // after the session's 32-byte response window. A reset value of
            // cmdrsp==0 must not turn this invalid card exchange into success.
            suppress_r1=1; token_delay_bytes=40;
            begin_read(15); expect_failure(2);
            suppress_r1=0; reset_and_initialize();
            // Cancellation by resetting the owner while waiting for token.
            token_delay_bytes=TOKEN_BYTES-2;
            begin_read(12); wait_cycles(BYTE_CLOCKS*15);
            reset_and_initialize(); aborts_checked=aborts_checked+1;
            token_delay_bytes=0;
            begin_read(13);
            while(seen_bytes<73) @(negedge clk);
            reset_and_initialize(); aborts_checked=aborts_checked+1;
            begin_read(14); finish_success();
        end
        $display("PASS workstation_tf_sd_sector_wire: divider=%0d kind=%0d token_bytes=%0d wait_clocks=%0d reads=%0d aborts=%0d commands=%0d cycles=%0d last_read_clocks=%0d",
            ACTUAL_DIV,CARD_KIND,TOKEN_BYTES,WAIT_CLOCKS,reads_checked,aborts_checked,cmd17_count,cycles,finished-launched);
        $finish;
    end
    initial begin #2000000000; $fatal(1,"global wire fixture timeout"); end
endmodule
`default_nettype wire
