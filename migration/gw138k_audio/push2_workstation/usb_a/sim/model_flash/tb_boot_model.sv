`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"
module tb_boot_model;
    parameter integer WORDS=31;
    parameter integer CLK_DIV=4;
    localparam integer N=32+2*WORDS;
    reg clk=0,rst_n=0,boot_ready=0,serial=1,miso=1;
    always #10 clk=~clk;
    tri cs,sclk,mosi,wp_n,hold_n;
    wire raw_cs,raw_sclk,raw_mosi,flash_owned,done,req,wr;
    pullup(cs);pulldown(sclk);pullup(wp_n);pullup(hold_n);
    wire [3:0] status;
    wire [1:0] source,flash_error,error_stage;
    wire [31:0] expected,actual,addr;
    wire [15:0] wdata;
    reg [7:0] image[0:N-1],good[0:N-1];
    reg [15:0] memory[0:WORDS-1];
    integer cycles=0,writes=0,reads=0,commands=0,kind=0,zero_rsp=0;
    integer response_delay=0,response_index=0;
    reg pending=0;
    wire ready=(cycles%19>=5) && !pending;
    wire rsp=pending && response_delay==0 || (zero_rsp && req && !wr && ready);
    wire [15:0] rdata=(pending ? memory[response_index] : memory[(addr-`BP_DDR_NN_MODEL_BYTE_BASE)>>1]) ^
                       ((kind==8 && source==0) ? 16'h0001 : 16'h0000);
    reg held=0;
    reg [48:0] held_cmd;
    string image_file;
    basic_pitch_boot_model_loader #(.WORDS(WORDS),.CLK_DIV(CLK_DIV),.UART_BAUD(3125000)) dut (
        .clk_i(clk),.rst_ni(rst_n),.boot_ready_i(boot_ready),.serial_i(serial),.flash_miso_i(miso),
        .flash_cs_n_o(raw_cs),.flash_clk_o(raw_sclk),.flash_mosi_o(raw_mosi),.done_o(done),.status_o(status),
        .source_o(source),.flash_error_o(flash_error),.debug_expected_crc_o(expected),
        .debug_actual_crc_o(actual),.debug_error_stage_o(error_stage),
        .mem_req_o(req),.mem_write_o(wr),.mem_byte_addr_o(addr),.mem_wdata_o(wdata),
        .mem_ready_i(ready),.mem_rsp_valid_i(rsp),.mem_rdata_i(rdata));

    basic_pitch_flash_io_guard io_guard (
        .spi_cs_n_i(raw_cs),.spi_clk_i(raw_sclk),.spi_mosi_i(raw_mosi),
        .flash_cs_n_o(cs),.flash_clk_o(sclk),.flash_mosi_o(mosi),
        .flash_wp_n_o(wp_n),.flash_hold_n_o(hold_n),.owned_o(flash_owned));
    // Independent behavioural NOR: check opcode and address rather than
    // driving internals. Return bytes on falling SCK edges (mode 0).
    integer sent_bits=0,rx_bit=7,rx_byte=0;
    reg [31:0] command=0;
    reg reading=0;
    always @(negedge cs) if(rst_n) begin
        sent_bits=0;command=0;reading=0;rx_bit=7;rx_byte=0;miso=1;
        commands=commands+1;
    end
    always @(posedge sclk) if(!cs) begin
        if(wp_n!==1 || hold_n!==1 || flash_owned!==1) $fatal(1,"SPI sideband/ownership incorrect");
        if(!reading) begin
            command={command[30:0],mosi};sent_bits=sent_bits+1;
            if(sent_bits==32) begin
                if(command!==32'h03600000) $fatal(1,"bad Flash command/address %h",command);
                reading=1;
            end
        end else begin
            if(rx_byte>=N) $fatal(1,"clocked beyond declared model image");
            if(rx_bit==0) begin rx_bit=7;rx_byte=rx_byte+1; end
            else rx_bit=rx_bit-1;
        end
    end
    always @(negedge sclk) if(!cs && reading) begin
        miso=rx_byte<N ? image[rx_byte][rx_bit] : 1'b1;
    end
    always @(posedge clk) begin
        cycles<=cycles+1;
        if(!rst_n) begin pending<=0;writes<=0;reads<=0;held<=0; end
        else begin
            if(held && {wr,addr,wdata}!==held_cmd) $fatal(1,"DDR command changed under backpressure");
            held<=req && !ready;held_cmd<={wr,addr,wdata};
            if(req && ready) begin
                if(addr<`BP_DDR_NN_MODEL_BYTE_BASE || addr>=`BP_DDR_NN_MODEL_BYTE_BASE+2*WORDS || addr[0])
                    $fatal(1,"model write/read outside aligned DDR window %h",addr);
                if(wr) begin
                    if(addr!==`BP_DDR_NN_MODEL_BYTE_BASE+2*(writes%WORDS)) $fatal(1,"write address skipped/repeated");
                    memory[(addr-`BP_DDR_NN_MODEL_BYTE_BASE)>>1]<=wdata;
                    writes<=writes+1;
                end else begin
                    if(addr!==`BP_DDR_NN_MODEL_BYTE_BASE+2*(reads%WORDS)) $fatal(1,"read address skipped/repeated");
                    reads<=reads+1;
                    if(!zero_rsp) begin
                        pending<=1;response_index<=(addr-`BP_DDR_NN_MODEL_BYTE_BASE)>>1;
                        response_delay<=cycles%11+1;
                    end
                end
            end
            if(pending) begin
                if(response_delay==0) pending<=0;
                else response_delay<=response_delay-1;
            end
            if(done && (status!=14 || pending || expected!==actual)) $fatal(1,"premature DONE/CRC");
        end
    end
    task send_byte(input reg [7:0] b);
        integer k;
        begin
            @(negedge clk);serial=0;repeat(16) @(negedge clk);
            for(k=0;k<8;k=k+1) begin serial=b[k];repeat(16) @(negedge clk);end
            serial=1;repeat(20) @(negedge clk);
        end
    endtask
    integer i;
    initial begin
        if(!$value$plusargs("IMAGE=%s",image_file)) $fatal(1,"IMAGE required");
        if(!$value$plusargs("CASE=%d",kind)) kind=0;
        if(!$value$plusargs("ZERO_RSP=%d",zero_rsp)) zero_rsp=0;
        $readmemh(image_file,good);
        for(i=0;i<N;i=i+1) image[i]=good[i];
        case(kind)
            1: image[0]=0;
            2: image[4]=2;
            3: image[6]=31;
            4: image[8]=image[8]^8'h01;
            5: image[16]=image[16]^8'h01;
            6: image[20]=1;
            7: image[32+WORDS]=image[32+WORDS]^8'h80;
            9: for(i=0;i<N;i=i+1) image[i]=8'hff;
            default: begin end
        endcase
        repeat(10) @(negedge clk);rst_n=1;
        repeat(100) @(negedge clk);
        if(!cs || req || done || commands!=0) $fatal(1,"Flash started before DDR calibration");
        boot_ready=1;
        if(kind==10) begin
            wait(writes==5);@(negedge clk);rst_n=0;boot_ready=0;
            repeat(10) @(negedge clk);rst_n=1;
            repeat(100) @(negedge clk);
            if(!cs || req || done) $fatal(1,"reset did not release Flash");
            boot_ready=1;
        end
        if(kind!=0 && kind!=10) begin
            wait(source==2);repeat(10) @(negedge clk);
            if(done || !cs || sclk || pending) $fatal(1,"invalid fallback handover");
            if(kind==7 && flash_error!=2 || kind==8 && flash_error!=3 ||
               kind!=7 && kind!=8 && flash_error!=1) $fatal(1,"wrong explicit failure stage %d",flash_error);
            if(kind!=7 && kind!=8 && writes!=0) $fatal(1,"malformed header wrote DDR");
            send_byte("B");send_byte("P");send_byte("N");send_byte("1");
            for(i=32;i<N;i=i+1) send_byte(good[i]);
            for(i=12;i<16;i=i+1) send_byte(good[i]);
        end
        wait(done);repeat(10) @(negedge clk);
        for(i=0;i<WORDS;i=i+1)
            if(memory[i]!=={good[33+2*i],good[32+2*i]}) $fatal(1,"wrong DDR content word %d",i);
        if(kind==0 || kind==10) begin
            if(source!=1 || writes!=WORDS || reads!=WORDS) $fatal(1,"Flash success counts/source");
        end else if(source!=2) $fatal(1,"UART fallback did not persist");
        if(!cs || sclk) $fatal(1,"Flash bus not idle after DONE");
        // UART bytes cannot mutate a valid Flash model.
        if(kind==0 && WORDS<100) begin
            send_byte("B");send_byte("P");send_byte("N");send_byte("1");
            repeat(100) @(negedge clk);
            if(!done || writes!=WORDS) $fatal(1,"UART changed accepted Flash model");
        end
        $display("PASS case=%0d words=%0d clk_div=%0d zero_rsp=%0d cycles=%0d writes=%0d reads=%0d source=%0d crc=%h flash_error=%0d",kind,WORDS,CLK_DIV,zero_rsp,cycles,writes,reads,source,actual,flash_error);
        $finish;
    end
    initial begin #500000000; $fatal(1,"simulation timeout status=%h source=%0d",status,source);end
endmodule
