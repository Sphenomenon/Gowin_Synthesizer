`timescale 1ns/1ps
module tb_protocol_command;
    reg clk=0; always #5 clk=~clk;
    reg resetn=0,enable=1,subscribed=1,control_open=1;
    reg [63:0] boot_id=64'h8877665544332211;
    reg [31:0] elapsed=100;
    reg wr=0,start=0,consume=0,latch=0;
    reg [4:0] addr=0,flen=0;
    reg [7:0] data=0;
    wire busy,done,valid,session;
    wire [7:0] error,out;
    wire [6:0] length;
    reg [6:0] out_addr=0;
    wire [159:0] summary;
    wire [31:0] accepted,bad_crc;
    reg [7:0] request[0:519],fragment[0:19],saved[0:127];
    integer request_length,token=1,n,k,baseline;
    reg [31:0] crc;
    ble_protocol_command dut(.clk(clk),.resetn(resetn),.enable(enable),
        .boot_id(boot_id),.boot_valid(boot_id!=0),.response_subscribed(subscribed),
        .recording_enable(enable),.transfer_subscribed(1'b1),
        .transfer_addr(13'd0),.transfer_consume(1'b0),
        .control_open(control_open),.elapsed_ms(elapsed),
        .fragment_write(wr),.fragment_addr(addr),.fragment_data(data),
        .fragment_start(start),.fragment_length(flen),.busy(busy),
        .fragment_done(done),.fragment_error(error),.response_valid(valid),
        .response_length(length),.response_addr(out_addr),.response_data(out),
        .response_consume(consume),.summary_latch(latch),.summary(summary),
        .session_active(session),.accepted_count(accepted),.crc_reject_count(bad_crc));
    function [31:0] step;
        input [31:0] old;
        input [7:0] byte_value;
        reg [31:0] value;
        integer bit_number;
        begin
            value=old;
            for(bit_number=0;bit_number<8;bit_number=bit_number+1)
                value=(value>>1)^((value[0]^byte_value[bit_number])?32'hedb88320:0);
            step=value;
        end
    endfunction
    task make_request;
        input [7:0] op;
        input [31:0] id;
        input [63:0] nonce;
        input integer payload;
        begin
            for(n=0;n<520;n=n+1) request[n]=0;
            request[0]=op; request[2]=payload; request[3]=payload>>8;
            for(n=0;n<4;n=n+1) request[4+n]=id>>(8*n);
            for(n=0;n<8;n=n+1) request[8+n]=nonce>>(8*n);
            if(op==1) request[16]=1;
            request_length=20+payload;
            seal_request();
        end
    endtask
    task seal_request;
        begin
            crc=32'hffffffff;
            for(n=0;n<request_length-4;n=n+1) crc=step(crc,request[n]);
            crc=~crc;
            for(n=0;n<4;n=n+1) request[request_length-4+n]=crc>>(8*n);
        end
    endtask
    task send_fragment;
        input integer size;
        input [7:0] expected_error;
        integer i,watchdog;
        begin
            for(i=0;i<size;i=i+1) begin
                @(negedge clk); wr=1; addr=i; data=fragment[i];
            end
            @(negedge clk); wr=0; flen=size; start=1;
            @(negedge clk); start=0;
            watchdog=0;
            while(!done && watchdog<5000) begin @(negedge clk); watchdog=watchdog+1; end
            if(!done || error!==expected_error) $fatal(1,"Fragment token=%0d index=%0d error=%h expected=%h state=%0d",token,fragment[3],error,expected_error,dut.state);
            @(negedge clk);
        end
    endtask
    task prepare_fragment;
        input integer offset;
        input integer count;
        begin
            fragment[0]=8'hb1; fragment[1]=token; fragment[2]=token>>8;
            fragment[3]=offset/14; fragment[4]=(offset==0 ? 1 : 0) | (offset+count==request_length ? 2 : 0);
            fragment[5]=count;
            for(k=0;k<count;k=k+1) fragment[6+k]=request[offset+k];
        end
    endtask
    task send_request;
        integer offset,count;
        begin
            for(offset=0;offset<request_length;offset=offset+14) begin
                count=request_length-offset>14 ? 14 : request_length-offset;
                prepare_fragment(offset,count); send_fragment(count+6,0);
            end
            token=token+1;
        end
    endtask
    task verify_response;
        input [7:0] expected_status;
        input integer expected_length;
        integer i;
        reg [31:0] c;
        begin
            if(!valid || length!=expected_length) $fatal(1,"Reply missing/length %0d expected %0d",length,expected_length);
            c=32'hffffffff;
            for(i=0;i<length;i=i+1) begin
                out_addr=i; #1;
                c=step(c,out);
                if(i==0 && out!==request[0]) $fatal(1,"Opcode echo");
                if(i==1 && out!==expected_status) $fatal(1,"Status %h expected %h",out,expected_status);
                if(i>=4 && i<16 && out!==request[i]) $fatal(1,"ID/nonce echo");
            end
            if(c!=32'hdebb20e3) $fatal(1,"Response CRC");
        end
    endtask
    task release_response;
        begin @(negedge clk); consume=1; @(negedge clk); consume=0; end
    endtask
    task save_response;
        integer i;
        begin for(i=0;i<length;i=i+1) begin out_addr=i;#1;saved[i]=out;end end
    endtask
    task compare_saved;
        integer i;
        begin for(i=0;i<length;i=i+1) begin out_addr=i;#1;if(saved[i]!==out) $fatal(1,"Replay changed byte %0d",i);end end
    endtask
    initial begin
        repeat(3) @(negedge clk); resetn=1;
        // Independently known CRC32 check vector.
        crc=32'hffffffff; for(k=0;k<9;k=k+1) crc=step(crc,"1"+k);
        if((~crc)!=32'hcbf43926) $fatal(1,"Test CRC check vector");
        make_request(1,1,64'h1020304050607080,4);
        subscribed=0; prepare_fragment(0,14);send_fragment(20,8'h80);token=token+1;
        subscribed=1; boot_id=0;prepare_fragment(0,14);send_fragment(20,8'h80);token=token+1;
        boot_id=64'h8877665544332211;
        request[request_length-1]=request[request_length-1]^1;
        send_request(); if(valid || session || accepted!=0 || bad_crc!=1) $fatal(1,"Bad CRC executed");
        seal_request();send_request();verify_response(0,40);
        if(!session || accepted!=1) $fatal(1,"HELLO not accepted");
        for(k=0;k<8;k=k+1) begin out_addr=16+k;#1;if(out!==(boot_id>>(8*k)&255)) $fatal(1,"boot_id");end
        save_response();release_response(); elapsed=500;
        send_request();verify_response(0,40);compare_saved();release_response();
        if(accepted!=1) $fatal(1,"HELLO replay executed twice");
        make_request(2,2,64'h9988776655443322,0);send_request();verify_response(8'h85,28);release_response();
        make_request(2,2,64'h1020304050607080,0);send_request();verify_response(0,84);
        out_addr=60;#1;if(out!=8) $fatal(1,"Status window flags");
        save_response();release_response();elapsed=900;
        send_request();verify_response(0,84);compare_saved();release_response();
        if(accepted!=2) $fatal(1,"GET_STATUS replay executed twice");
        make_request(2,2,64'h1020304050607080,1);send_request();verify_response(8'h86,28);release_response();
        make_request(8'h7f,3,64'h1020304050607080,492);send_request();verify_response(8'h80,28);release_response();
        if(accepted!=2) $fatal(1,"Unsupported consumed ID");
        make_request(2,3,64'h1020304050607080,0);send_request();verify_response(0,84);release_response();
        // Exact fragment retry is ignored. Out-of-order/token/reserved bits fail.
        make_request(2,4,64'h1020304050607080,0);
        prepare_fragment(0,14);send_fragment(20,0);send_fragment(20,0);
        prepare_fragment(14,6);fragment[2]=fragment[2]^1;send_fragment(12,8'h80);token=token+1;
        prepare_fragment(0,14);fragment[4]=5;send_fragment(20,8'h80);token=token+1;
        prepare_fragment(0,14);fragment[5]=13;send_fragment(19,8'h0d);token=token+1;
        prepare_fragment(0,14);send_fragment(20,0);elapsed=3000;
        prepare_fragment(14,6);send_fragment(12,8'h80);token=token+1;
        send_request();verify_response(0,84);release_response();
        // Bad logical total length with a valid CRC is also silent.
        make_request(2,5,64'h1020304050607080,0);request[2]=1;seal_request();send_request();
        if(valid || accepted!=4) $fatal(1,"Bad logical length executed");
        // More than 512 bytes is rejected before business dispatch.
        make_request(8'h7f,5,64'h1020304050607080,493);
        for(baseline=0;baseline<504;baseline=baseline+14) begin prepare_fragment(baseline,14);send_fragment(20,0);end
        prepare_fragment(504,9);send_fragment(15,8'h0d);token=token+1;
        // Fill and evict the 32-entry completed-request cache.
        for(baseline=5;baseline<=36;baseline=baseline+1) begin
            make_request(2,baseline,64'h1020304050607080,0);send_request();verify_response(0,84);release_response();
        end
        make_request(2,2,64'h1020304050607080,0);send_request();verify_response(8'h87,28);release_response();
        elapsed=64000;
        make_request(2,36,64'h1020304050607080,0);send_request();verify_response(8'h87,28);release_response();
        // A disconnect invalidates the session and cache.
        @(negedge clk);enable=0;repeat(3) @(negedge clk);enable=1;
        make_request(2,1,64'h1020304050607080,0);send_request();verify_response(8'h85,28);release_response();
        make_request(1,1,64'h0011223344556677,4);send_request();verify_response(0,40);release_response();
        $display("PASS: protocol HELLO/GET_STATUS, 512-byte streaming CRC, fragment errors/timeout/retry, nonce, conflict, 32-entry exact replay, expiry/eviction, disconnect");
        $finish;
    end
    initial begin #20000000;$fatal(1,"Protocol watchdog");end
endmodule
