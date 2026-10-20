`timescale 1ns/1ps
module tb_second_profile_replay #(parameter OLD_OPCODE=8'h3c,ATT_VALUE=244);
    localparam OPEN_OPCODE=8'h40;
    localparam MAX_CHUNK=((ATT_VALUE-4)*64-48)>8112 ? 8112 : (ATT_VALUE-4)*64-48;
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
    reg transfer_subscribed=1, transfer_consume=0;
    wire transfer_valid;
    wire [12:0] transfer_length;
    wire [7:0] transfer_data;
    reg [12:0] transfer_addr=0;
    reg [7:0] transfer_saved[0:8191];
    reg [31:0] rid,tid,operation,object_crc,ack_crc;
    reg [63:0] nonce=64'h1020304050607080;
    integer watchdog;
    ble_protocol_command #(.CLK_HZ(480000)) dut(.clk(clk),.resetn(resetn),.enable(enable),
        .boot_id(boot_id),.att_value_limit(ATT_VALUE),.boot_valid(boot_id!=0),.response_subscribed(subscribed),
        .recording_enable(1'b1),.transfer_subscribed(transfer_subscribed),
        .transfer_valid(transfer_valid),.transfer_length(transfer_length),
        .transfer_addr(transfer_addr),.transfer_data(transfer_data),.transfer_consume(transfer_consume),
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
            while(!done && watchdog<300000) begin @(negedge clk); watchdog=watchdog+1; end
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
            if(valid && dut.response_is_data!=((request[0]==8'h31 || request[0]==8'h35 || request[0]==8'h41 || request[0]==8'h42) && expected_status==0))
                $fatal(1,"Success DATA receipt classification");
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
    task put32;
        input integer at;
        input [31:0] value;
        integer z;
        begin for(z=0;z<4;z=z+1) request[at+z]=value>>(8*z);end
    endtask
    task put_object;
        begin for(k=0;k<8;k=k+1)request[16+k]=boot_id>>(8*k);put32(24,rid);end
    endtask
    task read32;
        input integer at;
        output [31:0] value;
        integer z;
        begin value=0;for(z=0;z<4;z=z+1) begin out_addr=at+z;#1;value=value|({24'd0,out}<<(8*z));end end
    endtask
    integer dump_number=0,dump_file;
    task transfer_check;
        input integer bytes;
        input integer replay;
        integer z;
        reg [31:0] c,pcm;
        begin
            if(!transfer_valid || transfer_length>bytes+48 || transfer_length<48) $fatal(1,"Transfer missing/length");
            dump_file=$fopen($sformatf("/private/tmp/gw25k-lossless-block-%0d.hex",dump_number),"w");
            dump_number=dump_number+1;
            c=32'hffffffff;pcm=32'hffffffff;
            for(z=0;z<transfer_length;z=z+1) begin
                @(negedge clk);transfer_addr=z;repeat(2)@(negedge clk);
                c=step(c,transfer_data);$fdisplay(dump_file,"%02x",transfer_data);
                if(z>=44 && z<44+bytes)pcm=step(pcm,transfer_data);
                if(replay && transfer_saved[z]!==transfer_data)$fatal(1,"READ replay data differs %0d",z);
                transfer_saved[z]=transfer_data;
            end
            if(c!=32'hdebb20e3)$fatal(1,"Transfer logical CRC %h",c);
            $fclose(dump_file);
            ack_crc={transfer_saved[43],transfer_saved[42],transfer_saved[41],transfer_saved[40]};
            if(transfer_saved[38]==0 && ack_crc!==~pcm)$fatal(1,"RAW CRC");
            if({transfer_saved[43],transfer_saved[42],transfer_saved[41],transfer_saved[40]}!==ack_crc)$fatal(1,"Block CRC actual %h expected %h",{transfer_saved[43],transfer_saved[42],transfer_saved[41],transfer_saved[40]},ack_crc);
            @(negedge clk);transfer_consume=1;@(negedge clk);transfer_consume=0;
        end
    endtask
    initial begin
        repeat(3) @(negedge clk); resetn=1;
        make_request(1,1,nonce,4);send_request();verify_response(0,40);release_response();
        make_request(8'h22,2,nonce,4);send_request();verify_response(0,68);
        out_addr=28;#1;if(out!=0)$fatal(1,"Initial recording not empty");release_response();
        make_request(8'h20,3,nonce,8);request[16]=1;seal_request();send_request();verify_response(1,28);
        read32(16,operation);read32(20,rid);if(rid!=1||operation!=1)$fatal(1,"Start identity");
        save_response();release_response();send_request();verify_response(1,28);compare_saved();release_response();
        if(dut.recording.object_counter!=1)$fatal(1,"Start replay duplicated object");
        make_request(4,4,nonce,4);put32(16,operation);seal_request();send_request();verify_response(0,40);
        out_addr=25;#1;if(out!=2)$fatal(1,"Start operation did not finish");release_response();
        // Disconnect releases session, not the ongoing recorder.
        @(negedge clk);enable=0;repeat(100)@(negedge clk);enable=1;
        nonce=64'h0102030405060708;
        make_request(1,1,nonce,4);send_request();verify_response(0,40);release_response();
        watchdog=0;
        while(dut.recording.record_state!=4 && watchdog<3000000)begin @(negedge clk);watchdog=watchdog+1;end
        if(dut.recording.recorded_frames!=48000)$fatal(1,"Capacity not reached %0d",dut.recording.recorded_frames);
        make_request(8'h22,2,nonce,4);send_request();verify_response(0,68);
        read32(48,object_crc);if(object_crc!=32'ha54a47b0)$fatal(1,"Full ROM recording CRC %h",object_crc);
        release_response();
        transfer_subscribed=0;
        make_request(8'h30,3,nonce,16);put_object();seal_request();send_request();verify_response(8'h83,28);release_response();
        transfer_subscribed=1;send_request();verify_response(0,40);read32(16,tid);release_response();
        make_request(8'h23,4,nonce,12);put_object();seal_request();send_request();verify_response(8'h82,28);release_response();
        make_request(8'h31,4,nonce,12);put32(16,tid);put32(20,0);request[25]=1;seal_request();send_request();verify_response(0,32);
        save_response();release_response();transfer_check(256,0);
        send_request();verify_response(0,32);compare_saved();release_response();transfer_check(256,1);
        // ACK_READ must validate the full next read before committing an ACK.
        make_request(8'h35,5,nonce,16);put32(16,tid);put32(20,256);put32(24,258);put32(28,ack_crc);
        seal_request();send_request();verify_response(8'h89,28);release_response();
        if(dut.recording.confirmed_offset!=0 || !dut.recording.block_pending)$fatal(1,"Invalid next range committed ACK");
        put32(24,256);put32(28,ack_crc^1);seal_request();send_request();verify_response(8'h8d,28);release_response();
        if(dut.recording.confirmed_offset!=0)$fatal(1,"Bad preceding CRC committed ACK");
        put32(24,32'h00010100);put32(28,ack_crc);seal_request();send_request();verify_response(8'h81,28);release_response();
        put32(24,256);seal_request();send_request();verify_response(0,32);save_response();release_response();transfer_check(256,0);
        if(dut.recording.confirmed_offset!=256 || dut.recording.pending_offset!=256)$fatal(1,"ACK_READ commit/read cursor");
        send_request();verify_response(0,32);compare_saved();release_response();transfer_check(256,1);
        if(dut.recording.confirmed_offset!=256 || dut.recording.pending_offset!=256)$fatal(1,"ACK_READ replay mutated cursor");
        // A new ID cannot repeat a combined operation over the wrong pending block.
        put32(4,6);seal_request();send_request();verify_response(8'h8d,28);release_response();
        make_request(8'h32,6,nonce,12);put32(16,tid);put32(20,512);put32(24,ack_crc^1);seal_request();send_request();verify_response(8'h8d,28);release_response();
        put32(24,ack_crc);seal_request();send_request();verify_response(0,28);release_response();
        make_request(8'h32,7,nonce,12);put32(16,tid);put32(20,512);put32(24,ack_crc);seal_request();send_request();verify_response(0,28);release_response();
        make_request(8'h33,8,nonce,8);put32(16,tid);put32(20,object_crc);seal_request();send_request();verify_response(8'h8d,28);release_response();
        // Optional OPEN_WIDE is scoped to this transfer. The legacy OPEN
        // always advertises 256; no 512-byte ring counter may wrap at 460+48.
        make_request(8'h34,9,nonce,4);put32(16,tid);seal_request();send_request();verify_response(0,24);release_response();
        make_request(OPEN_OPCODE,10,nonce,16);put_object();seal_request();send_request();verify_response(0,(OPEN_OPCODE==8'h38 || OPEN_OPCODE==8'h39 || (OPEN_OPCODE==8'h3b || OPEN_OPCODE==8'h40)) ? 44 : 40);read32(16,tid);
        out_addr=32;#1;if(out!=(MAX_CHUNK&255))$fatal(1,"Wide max chunk low");out_addr=33;#1;if(out!=(MAX_CHUNK>>8))$fatal(1,"Wide max chunk high");
        if(dut.recording.transfer_compact!=(OPEN_OPCODE==8'h37 || (OPEN_OPCODE==8'h38 || OPEN_OPCODE==8'h39 || (OPEN_OPCODE==8'h3b || OPEN_OPCODE==8'h40))))$fatal(1,"Compact profile not scoped to OPEN");
        if(dut.recording.transfer_bulk!=((OPEN_OPCODE==8'h38 || OPEN_OPCODE==8'h39 || (OPEN_OPCODE==8'h3b || OPEN_OPCODE==8'h40))))$fatal(1,"Bulk profile not scoped to OPEN");
        if((OPEN_OPCODE==8'h38 || OPEN_OPCODE==8'h39 || (OPEN_OPCODE==8'h3b || OPEN_OPCODE==8'h40)))begin
            out_addr=36;#1;if(out!=ATT_VALUE)$fatal(1,"Bulk ATT limit metadata");
            out_addr=37;#1;if(out!=0)$fatal(1,"Bulk ATT limit high");
            out_addr=38;#1;if(out!=0)$fatal(1,"Bulk reserved metadata");
            out_addr=39;#1;if(out!=0)$fatal(1,"Bulk reserved metadata high");
        end
        if(dut.recording.transfer_direct!=(OPEN_OPCODE==8'h39 || (OPEN_OPCODE==8'h3b || OPEN_OPCODE==8'h40)))$fatal(1,"Direct profile not scoped to OPEN");
        save_response();release_response();baseline=dut.recording.transfer_counter;
        send_request();verify_response(0,(OPEN_OPCODE==8'h38 || OPEN_OPCODE==8'h39 || (OPEN_OPCODE==8'h3b || OPEN_OPCODE==8'h40)) ? 44 : 40);compare_saved();release_response();
        if(dut.recording.transfer_counter!=baseline)$fatal(1,"Wide OPEN replay allocated a transfer");
        make_request(8'h41,11,nonce,12);put32(16,tid);put32(24,MAX_CHUNK+4);seal_request();send_request();verify_response(8'h89,28);release_response();
        put32(24,MAX_CHUNK);seal_request();send_request();verify_response(0,32);release_response();transfer_check(MAX_CHUNK,0);
        make_request(8'h42,12,nonce,16);put32(16,tid);put32(20,MAX_CHUNK);put32(24,MAX_CHUNK+4);put32(28,ack_crc);
        seal_request();send_request();verify_response(8'h89,28);release_response();
        if(dut.recording.confirmed_offset!=0 || !dut.recording.block_pending)$fatal(1,"Wide range failure committed ACK");
        put32(24,MAX_CHUNK);put32(28,ack_crc^1);seal_request();send_request();verify_response(8'h8d,28);release_response();
        put32(28,ack_crc);seal_request();send_request();verify_response(0,32);save_response();release_response();transfer_check(MAX_CHUNK,0);
        send_request();verify_response(0,32);compare_saved();release_response();transfer_check(MAX_CHUNK,1);
        if(dut.recording.confirmed_offset!=MAX_CHUNK || dut.recording.pending_offset!=MAX_CHUNK)$fatal(1,"Wide replay mutated cursor");
        baseline=tid;
        make_request(8'h34,13,nonce,4);put32(16,tid);seal_request();send_request();verify_response(0,24);release_response();
        make_request(OLD_OPCODE,14,nonce,16);put_object();put32(28,920);seal_request();send_request();verify_response(0,OLD_OPCODE==8'h30 ? 40 : 44);read32(16,tid);release_response();
        make_request(8'h41,11,nonce,12);put32(16,baseline);put32(24,MAX_CHUNK);seal_request();send_request();verify_response(8'h8d,28);release_response();
        if(transfer_valid || dut.recording.confirmed_offset!=920)$fatal(1,"Extended replay changed downgraded transfer");
        make_request(8'h34,15,nonce,4);put32(16,tid);seal_request();send_request();verify_response(0,24);release_response();
        make_request(8'h40,16,nonce,16);put_object();seal_request();send_request();verify_response(0,44);read32(16,tid);release_response();
        make_request(8'h41,11,nonce,12);put32(16,baseline);put32(24,MAX_CHUNK);seal_request();send_request();verify_response(0,32);release_response();transfer_check(MAX_CHUNK,0);
        if(dut.recording.confirmed_offset!=0)$fatal(1,"Replayed DATA changed restored cursor");
        make_request(8'h34,17,nonce,4);put32(16,tid);seal_request();send_request();verify_response(0,24);release_response();
        make_request(8'h30,18,nonce,16);put_object();put32(28,920);seal_request();send_request();verify_response(0,40);read32(16,tid);
        out_addr=32;#1;if(out!=0)$fatal(1,"Legacy OPEN retained wide chunk");out_addr=33;#1;if(out!=1)$fatal(1,"Legacy max chunk high");release_response();
        // A cached long READ must not emit 1020 logical bytes through an
        // explicitly reopened legacy B1/512 profile. Its cached success is
        // retained, but the incompatible replay must report a state error.
        make_request(8'h41,11,nonce,12);put32(16,baseline);put32(24,MAX_CHUNK);seal_request();
        send_request();verify_response(8'h8d,28);release_response();
        if(transfer_valid || dut.recording.confirmed_offset!=920)$fatal(1,"Long replay changed legacy transfer");
        make_request(8'h31,19,nonce,12);put32(16,tid);put32(20,920);put32(24,460);seal_request();send_request();verify_response(8'h89,28);release_response();
        put32(24,256);seal_request();send_request();verify_response(0,32);release_response();transfer_check(256,0);
        if(dut.recording.transfer_direct)$fatal(1,"Legacy OPEN retained direct profile");
        if(dut.recording.transfer_compact)$fatal(1,"Legacy OPEN retained compact profile");
        // Drop transfer, keep immutable object, resume at the final frame.
        @(negedge clk);enable=0;repeat(10)@(negedge clk);enable=1;
        nonce=64'h1122334455667788;
        make_request(1,1,nonce,4);send_request();verify_response(0,40);release_response();
        make_request(8'h30,2,nonce,16);put_object();put32(28,191996);seal_request();send_request();verify_response(0,40);read32(16,tid);release_response();
        make_request(8'h31,3,nonce,12);put32(16,tid);put32(20,191996);put32(24,4);seal_request();send_request();verify_response(0,32);release_response();transfer_check(4,0);
        make_request(8'h32,4,nonce,12);put32(16,tid);put32(20,192000);put32(24,ack_crc);seal_request();send_request();verify_response(0,28);release_response();
        make_request(8'h31,5,nonce,12);put32(16,tid);put32(20,192000);put32(24,4);seal_request();send_request();verify_response(8'h89,28);release_response();
        make_request(8'h33,5,nonce,8);put32(16,tid);put32(20,object_crc);seal_request();send_request();verify_response(0,24);release_response();
        make_request(8'h23,6,nonce,12);put_object();seal_request();send_request();verify_response(0,24);release_response();
        make_request(8'h20,7,nonce,8);request[16]=1;seal_request();send_request();verify_response(1,28);read32(20,rid);release_response();
        repeat(100)@(negedge clk);
        make_request(8'h21,8,nonce,12);put_object();seal_request();send_request();verify_response(1,28);read32(16,operation);release_response();
        make_request(4,9,nonce,4);put32(16,operation);seal_request();send_request();verify_response(0,40);release_response();
        if(dut.recording.record_state!=4 || dut.recording.stop_reason!=1 || dut.recording.recorded_frames==0 || dut.recording.recorded_frames>=48000)$fatal(1,"Manual stop prefix");
        $display("PASS: recording START/STOP/tasks, full PCM CRC, READ/ACK_READ replay, atomic ACK_READ rejection, ACK conflict/duplicate, CCCD, disconnect continuation/resume, EOF, CLOSE/CLEAR");$finish;
    end
    initial begin #30000000;$fatal(1,"Recording watchdog");end
endmodule
