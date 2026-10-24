`timescale 1ns/1ps
// Pin-level card model. Checks command frames before constructing independent
// R4/R5/R6/R1 responses. No hierarchical writes to the DUT state machine.
module tb_sdio_identify;
    reg clk=0; always #5 clk=~clk;
    reg resetn=0;
    wire sd_clk, wl_enable, done, identified, failed;
    tri1 sd_cmd;
    tri1 [3:0] sd_dat;
    reg card_drive=0, card_bit=1, busy_low=0;
    assign sd_cmd=card_drive ? card_bit : 1'bz;
    assign sd_dat[0]=busy_low ? 1'b0 : 1'bz;
    wire [255:0] debug;
    sdio_identify #(.CLK_HZ(1000000),.SD_HZ(100000),.POWER_MS(2),.MAX_POLLS(3)) dut(
        .clk(clk),.resetn(resetn),.sd_clk(sd_clk),.sd_cmd(sd_cmd),.sd_dat(sd_dat),
        .wl_enable(wl_enable),.done(done),.identified(identified),.failed(failed),.debug(debug));
    integer scenario=0, bits_seen=0, n, cases, poll_count=0, ready_count=0;
    reg [47:0] incoming=0, reply;
    reg [31:0] value;
    reg [5:0] cmd;
    reg [16:0] addr;
    reg [7:0] enable_register=8'h04;
    reg sending=0;
    function [6:0] crc;
        input [39:0] d;
        reg [46:0] poly;
        integer k;
        begin
            poly={d,7'b0};
            for(k=46;k>=7;k=k-1) if(poly[k]) poly=poly^({40'b0,7'h09}<<(k-7))^(47'b1<<k);
            crc=poly[6:0];
        end
    endfunction
    function [7:0] read_byte;
        input [16:0] address;
        begin
            case(address)
                0: read_byte=8'h32;
                8: read_byte=8'h82;
                9: read_byte=8'h00;
                10: read_byte=8'h10;
                11: read_byte=scenario==9 ? 8'h80 : 0;
                'h100: read_byte=8'h07;
                // Include NULL and an unknown tuple before MANFID.
                'h1000: read_byte=scenario==10 ? 8'hff : 0;
                'h1001: read_byte=8'h15;
                'h1002: read_byte=2;
                'h1003: read_byte=8'hca;
                'h1004: read_byte=8'hfe;
                'h1005: read_byte=8'h20;
                'h1006: read_byte=4;
                'h1007: read_byte=8'h4c;
                'h1008: read_byte=8'h02;
                'h1009: read_byte=scenario==4 ? 8'h24 : 8'h23;
                'h100a: read_byte=8'hd7;
                2: read_byte=enable_register;
                3: read_byte=(scenario!=5 && ready_count>=1) ? 8'h02 : 0;
                default: read_byte=8'hff;
            endcase
        end
    endfunction
    task respond;
        input [47:0] data;
        integer j;
        begin
            sending=1;
            @(negedge sd_clk); #1; card_drive=1; card_bit=data[47];
            for(j=46;j>=0;j=j-1) begin @(negedge sd_clk); #1; card_bit=data[j]; end
            @(negedge sd_clk); #1; card_drive=0; sending=0;
        end
    endtask
    always @(posedge sd_clk) begin
        #1;
        if(!resetn || !wl_enable) begin bits_seen=0; incoming=0; end
        else if(!sending) begin
            if(bits_seen!=0 || sd_cmd===1'b0) begin
                incoming={incoming[46:0],sd_cmd}; bits_seen=bits_seen+1;
                if(bits_seen==48) begin
                    bits_seen=0;
                    if(incoming[47:46]!=2'b01 || incoming[7:1]!=crc(incoming[47:8]) || incoming[0]!=1)
                        $fatal(1,"bad command CRC/frame: %h",incoming);
                    cmd=incoming[45:40]; value=0;
                    case(cmd)
                        0: begin end
                        5: begin
                            poll_count=poll_count+1;
                            if(scenario==8) value=32'h10000001;
                            else value=(incoming[39:8]==0 || poll_count<3) ? 32'h10ff8000 : 32'h90ff8000;
                            if(incoming[39:8]!=0 && incoming[39:8]!=32'h00300000)
                                $fatal(1,"CMD5 unsupported voltage request");
                        end
                        3: value=scenario==11 ? 32'h1234e000 : 32'h12340000;
                        7: begin
                            if(incoming[39:8]!=32'h12340000) $fatal(1,"wrong RCA select");
                            value=0; if(scenario==13) busy_low=1;
                        end
                        52: begin
                            addr=incoming[33:17];
                            if(incoming[38:36]!=0) $fatal(1,"wrong CMD52 function");
                            if(incoming[39]) begin
                                if(addr!=2 || incoming[15:8]!=8'h06) $fatal(1,"IOEx write clobbered other functions");
                                enable_register=incoming[15:8];
                            end
                            value={24'b0,read_byte(addr)};
                            if(addr==3) ready_count=ready_count+1;
                            if(scenario==7 && addr==0) value=value|32'h100;
                        end
                        default: $fatal(1,"unexpected command %d",cmd);
                    endcase
                    if(cmd!=0 && !(scenario==2 && cmd==5)) begin
                        if(cmd==5) reply={2'b00,(scenario==12 ? 6'd5 : 6'h3f),value,7'h7f,1'b1};
                        else reply={2'b00,cmd,value,crc({2'b00,cmd,value}),1'b1};
                        if(scenario==1 && cmd==52) reply[1]=!reply[1];
                        if(scenario==3 && cmd==3) reply[0]=0;
                        respond(reply);
                    end
                end
            end
        end
    end
    task run_case;
        input integer which;
        input [7:0] expected_error;
        integer watchdog;
        begin
            resetn=0; card_drive=0; busy_low=0; scenario=which; bits_seen=0;
            poll_count=0; ready_count=0; enable_register=4;
            repeat(20) @(negedge clk);
            resetn=1; watchdog=0;
            while(!done && !failed && watchdog<250000) begin @(negedge clk); watchdog=watchdog+1; end
            if(watchdog==250000) $fatal(1,"case %d watchdog state=%d step=%d",which,dut.state,dut.step);
            if(expected_error==0) begin
                if(!done || !identified || failed || dut.vendor_id!=16'h024c || dut.device_id!=16'hd723)
                    $fatal(1,"case %d false/missing identification err=%h",which,dut.error_code);
            end else if(!failed || done || dut.error_code!=expected_error)
                $fatal(1,"case %d expected %h got %h",which,expected_error,dut.error_code);
            $display("SDIO case %0d PASS error=%h commands=%d",which,dut.error_code,dut.command_count);
        end
    endtask
    initial begin
        // CMD0 with CRC7 must equal standard 0x95 trailing byte.
        if(crc(40'h4000000000)!=7'h4a) $fatal(1,"model CRC polynomial invalid");
        run_case(0,0);
        run_case(1,8'h13); // bad R5 CRC
        run_case(2,8'h11); // no CMD5 response
        run_case(3,8'h12); // bad end bit
        run_case(4,8'h2b); // wrong product
        run_case(5,8'h2c); // function never ready
        run_case(7,8'h20); // R5 out-of-range error
        run_case(8,8'h22); // incompatible OCR
        run_case(9,8'h26); // invalid CIS pointer
        run_case(10,8'h28); // no MANFID
        run_case(11,8'h24); // R6 status error
        run_case(12,8'h12); // malformed R4
        run_case(13,8'h14); // DAT0 busy timeout
        $display("PASS: SDIO native discovery, CRC, timeout, R5/R6, CIS, function ready");
        $finish;
    end
endmodule
