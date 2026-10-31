`timescale 1ns/1ps
module tb_business_mailbox;
    reg clk=0;always #5 clk=~clk;
    reg rst=0,owner_reset=1,boot_valid=1,control_open=1,fence=0,cancel=0,offer=0;
    reg [63:0] boot=64'h1020304050607080;
    reg [31:0] session=11,request_id=42;
    reg [7:0] opcode=8'h20,reserved=0;
    reg [15:0] length=16;
    reg [63:0] nonce=64'h1122334455667788;
    reg [127:0] payload=128'hffeeddccbbaa99887766554433221100;
    wire ready,admitted,rejected;wire [7:0] reject_reason;
    reg bus_valid=0,bus_write=0,consume=0;
    reg [11:0] address=0;reg [31:0] data=0;reg [3:0] strobes=15;
    wire bus_ready,bus_error;wire [31:0] rdata;
    wire done;wire [31:0] ticket,owner,done_session,operation;
    wire [63:0] done_boot;wire [7:0] phase,status,reason;
    wire [6:0] result_length;reg [511:0] result_payload;
    reg payload_read=0;reg [5:0] payload_address=0;
    wire payload_ready,payload_valid;wire [7:0] payload_data;
    workstation_business_mailbox #(.TIMEOUT_CYCLES(128)) dut (
        .clk_i(clk),.rst_ni(rst),.owner_reset_ni(owner_reset),.boot_valid_i(boot_valid),.control_open_i(control_open),
        .boot_id_i(boot),.session_generation_i(session),.fence_i(fence),.cancel_i(cancel),
        .request_offer_i(offer),.request_opcode_i(opcode),.request_reserved_i(reserved),.request_length_i(length),
        .request_id_i(request_id),.request_nonce_i(nonce),.request_payload_i(payload),.request_ready_o(ready),
        .request_admitted_o(admitted),.request_rejected_o(rejected),.request_reject_reason_o(reject_reason),
        .command_valid_i(bus_valid),.command_write_i(bus_write),.command_address_i(address),.command_data_i(data),
        .command_strobes_i(strobes),.command_ready_o(bus_ready),.response_error_o(bus_error),.response_data_o(rdata),
        .completion_valid_o(done),.completion_consume_i(consume),.completion_ticket_o(ticket),.completion_owner_o(owner),
        .completion_session_o(done_session),.completion_boot_o(done_boot),.completion_phase_o(phase),
        .completion_status_o(status),.completion_reason_o(reason),.completion_length_o(result_length),
        .completion_operation_o(operation),.completion_read_valid_i(payload_read),
        .completion_read_ready_o(payload_ready),.completion_read_address_i(payload_address),
        .completion_data_valid_o(payload_valid),.completion_data_o(payload_data));
    integer checks=0;reg [31:0] generation,old_generation,old_ticket,word;
    integer result_bytes,payload_word,payload_byte,abort_kind;
    reg [127:0] expected_request;
    reg [511:0] expected_result,expected_staging;
    task check(input condition,input [511:0] message);
        begin checks=checks+1;if(!condition)$fatal(1,"%0s",message);end
    endtask
    task wr(input [11:0] a,input [31:0] d,input expected_error);
        integer waits;
        begin
            @(negedge clk);bus_valid=1;bus_write=1;address=a;data=d;#1;
            waits=0;
            while(!bus_ready && waits<32)begin @(negedge clk);#1;waits=waits+1;end
            check(bus_ready===1'b1,"MMIO bounded write completion");check(bus_error===expected_error,"MMIO write error mismatch");
            if(a=='h0dc && d==3 && !expected_error)check(waits==18,"COMPLETE has the documented fixed local copy latency");
            @(posedge clk);#1;@(negedge clk);bus_valid=0;bus_write=0;
        end
    endtask
    task rd(input [11:0] a,output [31:0] d,input expected_error);
        integer waits;
        begin
            @(negedge clk);bus_valid=1;bus_write=0;address=a;#1;
            waits=0;
            while(!bus_ready && waits<4)begin @(negedge clk);#1;waits=waits+1;end
            check(bus_ready===1'b1,"MMIO bounded RAM read");check(bus_error===expected_error,"MMIO read error mismatch");d=rdata;
            @(posedge clk);#1;@(negedge clk);bus_valid=0;
        end
    endtask
    task snapshot_payload;
        integer at,waits;
        begin
            for(at=0;at<64;at=at+1)begin
                @(negedge clk);payload_read=1;payload_address=at;#1;waits=0;
                while(!payload_ready && waits<32)begin @(negedge clk);#1;waits=waits+1;end
                check(payload_ready,"bounded result-byte read grant");
                @(posedge clk);#1;check(payload_valid,"one-cycle SDP result-byte response");
                result_payload[at*8+:8]=payload_data;
                @(negedge clk);payload_read=0;
            end
        end
    endtask
    task keys(input [31:0] t,input [31:0] g,input [31:0] s,input [63:0] b);
        begin wr('h080,t,0);wr('h084,g,0);wr('h088,s,0);wr('h08c,b[31:0],0);wr('h090,b[63:32],0);end
    endtask
    task open_owner;
        begin rd('h00c,generation,0);keys(0,generation,session,boot);wr('h0dc,1,0);check(ready,"OPEN should admit");end
    endtask
    task send_request(input expected_admission,input [7:0] expected_reason);
        begin
            @(negedge clk);offer=1;@(posedge clk);#1;
            check(admitted===expected_admission,"request admission mismatch");
            check(rejected===!expected_admission,"request rejection mismatch");
            if(!expected_admission)check(reject_reason==expected_reason,"request reject reason mismatch");
            @(negedge clk);offer=0;
        end
    endtask
    task drain;
        begin check(done,"completion must remain visible");@(negedge clk);consume=1;@(posedge clk);#1;
            @(negedge clk);consume=0;check(!done,"completion not drained");end
    endtask
    task claim_current;
        begin keys(ticket,owner,done_session,done_boot);wr('h0dc,2,0);check(!done,"CLAIM is not a business completion");end
    endtask
    task complete_pending(input [31:0] id);
        begin wr('h094,32'h00050101,0);wr('h098,id,0);wr('h09c,32'h44332211,0);wr('h0a0,32'h88776655,0);wr('h0dc,3,0);end
    endtask
    task start_held_complete;
        begin
            wr('h094,32'h00405a02,0);wr('h098,123,0);
            @(negedge clk);bus_valid=1;bus_write=1;address='h0dc;data=3;#1;
            check(!bus_ready && !bus_error && !done && !payload_ready,"legal COMPLETE begins with backpressure");
            repeat(4)begin @(posedge clk);#1;
                check(!bus_ready && !done,"private copy cannot publish before its handshake");end
            @(negedge clk);
        end
    endtask
    task abort_held_complete(input integer kind);
        reg [7:0] expected_reason;
        begin
            send_request(1,0);claim_current();start_held_complete();
            case(kind)
                0:begin cancel=1;expected_reason=1;end
                1:begin owner_reset=0;expected_reason=2;end
                2:begin session=session+1;expected_reason=3;end
                3:begin dut.age=127;expected_reason=4;end
                4:begin fence=1;expected_reason=3;end
                5:begin boot=boot+1;expected_reason=6;end
                6:begin
                    while(!dut.copy_done)begin @(posedge clk);#1;end
                    @(negedge clk);cancel=1;expected_reason=1;
                end
            endcase
            #1;check(bus_ready && bus_error,"copy interruption acknowledges held COMPLETE as error");
            @(posedge clk);#1;
            check(done && phase==5 && reason==expected_reason && result_length==0,
                "copy interruption publishes only a local UNCERTAIN result");
            @(negedge clk);bus_valid=0;bus_write=0;cancel=0;fence=0;owner_reset=1;
            snapshot_payload();check(result_payload===0,"partial copied RAM is hidden by local zero length");
            check(done && phase==5 && reason==expected_reason && !dut.copy_busy,
                "abandoned copy never publishes a late owner completion");
            drain();
            if(kind==1 || kind==5)begin
                repeat(2)@(posedge clk);open_owner();
                // Reset invalidates staging words without clearing the RAM.
                send_request(1,0);claim_current();wr('h094,32'h00400002,0);wr('h0dc,3,0);
                snapshot_payload();check(result_payload===0,"owner or boot reset clears all staged validity bits");drain();
            end
        end
    endtask
    initial begin
        #2;rst=0;repeat(3)@(posedge clk);@(negedge clk);rst=1;repeat(3)@(posedge clk);
        rd('h000,word,0);check(word==32'h424d4201,"ABI identity");rd('h004,word,0);check(word==32'h00401001,"ABI capacities");
        send_request(0,12);open_owner();
        strobes=7;wr('h080,1,1);strobes=15;wr('h081,1,1);wr('h004,1,1);rd('h074,word,1);
        length=17;send_request(0,9);length=16;reserved=1;send_request(0,11);reserved=0;
        request_id=0;send_request(0,10);request_id=42;
        length=3;send_request(1,0);old_ticket=ticket;old_generation=owner;
        payload=0;opcode=8'hff;rd('h03c,word,0);check(word==32'h00200003,"snapshot opcode/length immutable");
        rd('h040,word,0);check(word==32'h00221100,"request tail zero padding");rd('h044,word,0);check(word==0,"unused request bytes zero");
        send_request(0,8);keys(ticket,owner,done_session,done_boot);wr('h0dc,3,1);
        wr('h088,session+1,0);wr('h0dc,2,1);wr('h088,session,0);wr('h0dc,2,0);check(!done,"claim does not mean ACCEPTED");
        wr('h094,32'h00410001,0);wr('h0dc,3,1);wr('h094,32'h01000001,0);wr('h0dc,3,1);
        wr('h094,32'h00000004,0);wr('h0dc,3,1);wr('h094,32'h00000001,0);wr('h098,0,0);wr('h0dc,3,1);
        complete_pending(77);check(done && phase==1 && status==1 && operation==77 && result_length==5,"pending result fact");
        snapshot_payload();check(result_payload[39:0]==40'h5544332211 && result_payload[511:40]==0,"completion byte order and zero tail");
        wr('h0dc,3,1);wr('h09c,32'hdeadbeef,0);snapshot_payload();check(result_payload[31:0]==32'h44332211,"result immutable during staging");
        drain();wr('h0dc,3,1);rd('h0e0,word,0);check(word==old_ticket,"publication survives consume");
        length=16;send_request(1,0);check(ticket==old_ticket+1,"ticket not reused");
        @(negedge clk);cancel=1;#1;check(!done,"cancel before sampling");@(posedge clk);#1;
        check(done && phase==4 && reason==1 && operation==0,"queued cancel is known undispatched");@(negedge clk);cancel=0;drain();
        send_request(1,0);claim_current();@(negedge clk);cancel=1;@(posedge clk);#1;
        check(done && phase==5 && reason==1,"claimed cancellation is UNCERTAIN");@(negedge clk);cancel=0;drain();
        send_request(1,0);claim_current();complete_pending(88);old_ticket=ticket;old_generation=owner;
        @(negedge clk);owner_reset=0;#1;check(!done,"old result hidden before reset edge");@(posedge clk);#1;
        check(done && phase==5 && reason==2 && operation==88,"reset preserves known task identity and abandons observation");
        repeat(3)@(posedge clk);rd('h00c,generation,0);check(generation==old_generation+1,"reset increments generation once");
        drain();check(!ready,"reset closes admission");@(negedge clk);owner_reset=1;repeat(2)@(posedge clk);open_owner();
        keys(old_ticket,old_generation,session,boot);wr('h0dc,3,1);check(!done,"reset cannot republish an old completion");
        send_request(1,0);check(ticket==old_ticket+1,"observer reset never resets ticket");claim_current();
        @(negedge clk);session=session+1;@(posedge clk);#1;check(done && phase==5 && reason==3,"stale session completion abandoned");
        wr('h0dc,3,1);drain();
        send_request(1,0);repeat(130)@(posedge clk);#1;check(done && phase==4 && reason==4,"unclaimed CPU timeout");drain();
        send_request(1,0);claim_current();repeat(130)@(posedge clk);#1;
        check(done && phase==5 && reason==4,"claimed CPU timeout does not report cancellation");drain();
        send_request(1,0);keys(ticket,owner,done_session,done_boot);
        @(negedge clk);cancel=1;bus_valid=1;bus_write=1;address='h0dc;data=2;#1;
        check(bus_error,"cancel must beat same-cycle CLAIM");@(posedge clk);#1;check(phase==4,"cancel won before claim");
        @(negedge clk);cancel=0;bus_valid=0;bus_write=0;drain();
        send_request(1,0);claim_current();wr('h094,32'h00000002,0);wr('h098,99,0);wr('h0dc,3,0);
        check(done && phase==2 && operation==99 && reason==0,"APPLIED is an explicit owner fact");drain();
        send_request(1,0);claim_current();wr('h094,32'h00008203,0);wr('h098,0,0);wr('h0dc,3,0);
        check(done && phase==3 && status==8'h82 && reason==0,"owner failure passes through without wire reinterpretation");drain();
        send_request(1,0);claim_current();@(negedge clk);fence=1;@(posedge clk);#1;
        check(done && phase==5 && reason==3,"explicit session fence abandons claimed observation");@(negedge clk);fence=0;drain();
        send_request(1,0);@(negedge clk);control_open=0;@(posedge clk);#1;
        check(done && phase==4 && reason==3,"closed control rejects an undispatched request");drain();send_request(0,10);
        @(negedge clk);control_open=1;
        send_request(1,0);claim_current();@(negedge clk);boot=boot+1;@(posedge clk);#1;
        check(done && phase==5 && reason==6 && !ready,"new boot fences old observation");drain();open_owner();
        keys(0,generation,session,boot);
        @(negedge clk);bus_valid=1;bus_write=1;address='h0dc;data=5;offer=1;#1;check(!ready,"CLOSE wins new offer");
        @(posedge clk);#1;check(rejected && !admitted,"no request accepted while closing");
        @(negedge clk);bus_valid=0;bus_write=0;offer=0;open_owner();
        // Exercise every physical payload word and every legal result byte
        // length, including partial words, zero/full payload and later staging.
        for(result_bytes=0;result_bytes<=64;result_bytes=result_bytes+1)begin
            length=result_bytes%17;expected_request=0;
            for(payload_byte=0;payload_byte<16;payload_byte=payload_byte+1)begin
                payload[payload_byte*8+:8]=result_bytes*17+payload_byte;
                if(payload_byte<length)expected_request[payload_byte*8+:8]=payload[payload_byte*8+:8];
            end
            send_request(1,0);
            for(payload_word=0;payload_word<4;payload_word=payload_word+1)begin
                rd('h040+payload_word*4,word,0);
                check(word===expected_request[payload_word*32+:32],"all request words retain padded admission snapshot");
            end
            claim_current();expected_result=0;
            for(payload_word=0;payload_word<16;payload_word=payload_word+1)begin
                word=32'hd1000000^(result_bytes<<16)^(payload_word*32'h00010203);
                expected_result[payload_word*32+:32]=word;wr('h09c+payload_word*4,word,0);
            end
            for(payload_byte=0;payload_byte<64;payload_byte=payload_byte+1)
                if(payload_byte>=result_bytes)expected_result[payload_byte*8+:8]=0;
            wr('h094,(result_bytes<<16)|32'h00005a02,0);wr('h098,result_bytes+1,0);wr('h0dc,3,0);
            check(done && phase==2 && status==8'h5a && result_length==result_bytes,"all legal result lengths publish after bounded handshake");
            snapshot_payload();check(result_payload===expected_result,"all completion bytes and zero tail match staged words");
            for(payload_word=0;payload_word<16;payload_word=payload_word+1)begin
                rd('h09c+payload_word*4,word,0);
                check(word===expected_result[payload_word*32+:32],"all result words select the exact byte lane");
                wr('h09c+payload_word*4,32'hbad00000+payload_word,0);
                snapshot_payload();check(result_payload===expected_result,"later staging cannot modify any published result word");
                rd('h09d+payload_word*4,word,1);wr('h09e+payload_word*4,0,1);
            end
            drain();
        end
        // Consuming a result leaves the last immutable bytes readable in EMPTY.
        snapshot_payload();check(result_payload===expected_result,"result byte API retains publication after consume");
        for(payload_word=0;payload_word<16;payload_word=payload_word+1)begin
            word=32'h12345678^(payload_word*32'h01030507);
            expected_staging[payload_word*32+:32]=word;wr('h09c+payload_word*4,word,0);
        end
        snapshot_payload();check(result_payload===expected_result,"EMPTY staging does not alter retained result");
        send_request(1,0);claim_current();wr('h094,32'h00400002,0);wr('h0dc,3,0);
        snapshot_payload();check(result_payload===expected_staging,"first full staging publication");drain();
        send_request(1,0);claim_current();expected_staging[7*32+:32]=32'hdecafbad;
        wr('h0b8,32'hdecafbad,0);wr('h0dc,3,0);
        snapshot_payload();check(result_payload===expected_staging,"partial staging keeps every untouched word across COMPLETE");drain();
        send_request(1,0);claim_current();wr('h094,32'h00030002,0);wr('h0dc,3,0);
        snapshot_payload();check(result_payload[23:0]===expected_staging[23:0] && result_payload[511:24]===0,
            "short result masks only its published tail");drain();
        send_request(1,0);claim_current();wr('h094,32'h00400002,0);wr('h0dc,3,0);
        snapshot_payload();check(result_payload===expected_staging,"long result recovers staging tail after a short publication");drain();
        // A new MMIO RAM address wins over a simultaneous endpoint byte read.
        // The byte can then issue on the MMIO response edge without changing
        // the word which the CPU samples on that edge.
        @(negedge clk);bus_valid=1;bus_write=0;address='h0b0;payload_read=1;payload_address=43;#1;
        check(!bus_ready && !payload_ready,"MMIO address has read-port priority");
        @(posedge clk);#1;check(bus_ready && !payload_valid,"MMIO data appears after one SDP edge");
        check(rdata===expected_staging[5*32+:32],"MMIO competing read selects its own word");
        @(negedge clk);#1;check(payload_ready,"endpoint byte can issue on MMIO response cycle");
        check(rdata===expected_staging[5*32+:32],"MMIO response stays stable until acceptance");
        @(posedge clk);#1;
        check(payload_valid && payload_data===expected_staging[43*8+:8],"queued endpoint byte selects its own lane");
        @(negedge clk);bus_valid=0;payload_read=0;
        @(posedge clk);#1;check(!payload_valid,"byte response is exactly one cycle");
        @(negedge clk);owner_reset=0;@(posedge clk);#1;
        snapshot_payload();check(result_payload===expected_staging,"owner reset in EMPTY preserves retained result bytes");
        @(negedge clk);owner_reset=1;repeat(2)@(posedge clk);open_owner();
        for(abort_kind=0;abort_kind<7;abort_kind=abort_kind+1)abort_held_complete(abort_kind);
        // A common reset also stops the private copy, without exposing its
        // uninitialised physical RAM. Reopen only with a fresh boot identity.
        send_request(1,0);claim_current();wr('h09c,32'hcafef00d,0);start_held_complete();
        rst=0;boot_valid=0;bus_valid=0;bus_write=0;#1;
        check(!done && !dut.copy_busy && !payload_valid,"common reset aborts the in-progress copy");
        repeat(3)@(posedge clk);@(negedge clk);boot=boot+1;boot_valid=1;rst=1;
        repeat(3)@(posedge clk);snapshot_payload();check(result_payload===0,"common reset masks retained RAM bytes");
        open_owner();send_request(1,0);claim_current();wr('h094,32'h00400002,0);wr('h0dc,3,0);
        snapshot_payload();check(result_payload===0,"common reset invalidates all unwritten staging words");drain();
        @(negedge clk);dut.next_ticket=32'hffffffff;send_request(1,0);check(ticket==32'hffffffff,"last ticket admitted once");
        @(negedge clk);cancel=1;@(posedge clk);@(negedge clk);cancel=0;drain();send_request(0,13);
        @(negedge clk);dut.rejected_count=32'hffffffff;send_request(0,13);rd('h058,word,0);check(word==32'hffffffff,"counter saturates");
        @(negedge clk);dut.owner_generation=32'hffffffff;owner_reset=0;@(posedge clk);@(negedge clk);owner_reset=1;
        repeat(2)@(posedge clk);rd('h008,word,0);check(word[10] && !ready,"owner generation exhaustion quarantines");
        wr('h0dc,1,1);
        $display("PASS business mailbox: %0d checks; claim/reset/session/timeout are fenced observation facts",checks);$finish;
    end
    initial begin #5000000;$fatal(1,"mailbox test timeout");end
endmodule
