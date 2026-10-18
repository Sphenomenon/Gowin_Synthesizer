`timescale 1ns/1ps
// HCI AES results below were calculated independently with OpenSSL AES-128-ECB
// (zero key, no padding), in addition to the Core c1/s1 published examples.
// This checks wire endian/layout rather than mirroring the DUT's c1 algorithm.
module tb_ble_smp;
    reg clk=0;always #5 clk=~clk;
    reg resetn=0,enable=1,connected=0;
    reg [11:0] connection_handle=12'h345;
    reg [47:0] local_address=48'hb1b2b3b4b5b6,peer_address=48'ha1a2a3a4a5a6;
    reg peer_address_type=1;
    reg packet_valid=0;reg [3:0] packet_type=0;
    reg [8:0] packet_length=0;reg [255:0] packet_data=0;
    wire tx_valid;reg tx_ready=0;wire [3:0] tx_type;
    wire [5:0] tx_length;wire [287:0] tx_data;
    wire encrypted,pairing,security_failed,transport_failed;
    reg [287:0] got,held;
    integer checks=0,n;
    localparam [127:0] LR=128'h5783d52156ad6f0e6388274ec6702ee0;
    localparam [127:0] PR=128'h010203040506070899aabbccddeeff00;
    localparam [127:0] PC=128'hc3548a2cd64f1b3083d7bffb5041a463;
    localparam [127:0] LC=128'h967708da054f69a4414c839ea52bcb3c;
    localparam [127:0] STK=128'hec1f63ff9d53fc9ade040ee5354c4cb0;
    localparam [127:0] LTK=128'h99aabbccddeeff001122334455667788;
    localparam [63:0] BR=64'h76543210fedcba98;
    midi_ble_smp #(.CLK_HZ(1000),.PAIR_TIMEOUT_MS(200),.COMMAND_TIMEOUT_MS(50)) dut(
        .clk(clk),.resetn(resetn),.enable(enable),.connected(connected),
        .connection_handle(connection_handle),.local_address(local_address),
        .peer_address(peer_address),.peer_address_type(peer_address_type),
        .packet_valid(packet_valid),.packet_type(packet_type),.packet_length(packet_length),
        .packet_data(packet_data),.tx_valid(tx_valid),.tx_ready(tx_ready),
        .tx_type(tx_type),.tx_length(tx_length),.tx_data(tx_data),
        .encrypted(encrypted),.pairing(pairing),.security_failed(security_failed),
        .transport_failed(transport_failed));
    task tick;begin @(posedge clk);#1;end endtask
    task check;
        input ok;input [639:0] text;
        begin checks=checks+1;if(ok!==1'b1) begin $display("FAIL SMP: %0s",text);$fatal(1);end end
    endtask
    task inject;
        input [3:0] kind;input [8:0] length;input [255:0] value;
        begin packet_type=kind;packet_length=length;packet_data=value;
            packet_valid=1;tick();packet_valid=0;tick();end
    endtask
    task smp;
        input [7:0] opcode;input [4:0] length;input [127:0] body;
        reg [255:0] value;
        begin value=0;value[15:0]={4'd0,connection_handle};
            value[31:16]=length+16'd4;value[47:32]={11'd0,length};
            value[63:48]=6;value[71:64]=opcode;value[199:72]=body;
            inject(2,length+9'd8,value);end
    endtask
    task take;
        input [3:0] kind;input [5:0] length;
        integer guard;
        begin
            guard=0;
            while(!tx_valid && guard<100) begin tick();guard=guard+1;end
            check(tx_valid,"expected a queued transmission");
            check(tx_type==kind && tx_length==length,"transmission kind/length");
            held=tx_data;
            repeat(3) begin tick();check(tx_valid && tx_data===held && tx_type==kind && tx_length==length,
                "valid/data must remain stable under backpressure");end
            got=tx_data;tx_ready=1;tick();tx_ready=0;
        end
    endtask
    task no_tx;
        input integer count;
        integer k;
        begin for(k=0;k<count;k=k+1) begin tick();check(!tx_valid,"unexpected transmission");end end
    endtask
    task cc;
        input [15:0] opcode;input [7:0] status;input [127:0] result;input [8:0] length;
        reg [255:0] value;
        begin value=0;value[7:0]=8'h0e;value[15:8]=length-2;
            value[23:16]=1;value[39:24]=opcode;value[47:40]=status;
            value[175:48]=result;inject(4,length,value);end
    endtask
    task rand_result;
        input [63:0] value;
        begin take(1,3);check(got==288'h002018,"LE Rand has no parameters");
            cc(16'h2018,0,{64'd0,value},14);end
    endtask
    task aes_result;
        input [127:0] plain,result;
        begin take(1,35);
            check(got[23:0]==24'h202017,"LE Encrypt opcode and 32-byte parameter count");
            check(got[151:24]==0,"Just Works TK is zero");
            check(got[279:152]==plain,"independent AES plaintext / HCI little endian");
            check(got[287:280]==0,"unused HCI byte clear");
            cc(16'h2017,0,result,22);end
    endtask
    task pairing_request;
        input [7:0] auth,keylen,ikey,rkey;
        begin smp(1,7,{80'd0,rkey,ikey,keylen,auth,8'd0,8'd3});end
    endtask
    task take_pairing_response;
        begin take(2,15);
            check(got[63:0]=={16'd6,16'd7,16'd11,4'd0,connection_handle},"SMP ACL header");
            check(got[119:64]==56'h01001001000302,
                "NoInputNoOutput, bonding only, max16, responder EncKey only");end
    endtask
    task start_pair;
        begin pairing_request(1,16,0,1);take_pairing_response();
            check(pairing && !security_failed,"pairing starts");
            smp(3,17,PC);
            rand_result(LR[63:0]);rand_result(LR[127:64]);
            aes_result(128'h5683c52056ae6d0f6398264ec5712ee1,128'h5c1747d90943ebf4a97b5d9cf201052b);
            aes_result(128'h5c1747d9a8e148500cddec2e41b5b09d,LC);
            take(2,25);check(got[71:64]==3 && got[199:72]==LC,"local c1 Confirm");
        end
    endtask
    task verify_peer;
        input wrong;
        begin smp(4,17,PR);
            aes_result(128'h000213050505050999babaccdeefff01,128'h3b7de4638ff53f037de43696c947528f);
            aes_result(128'h3b7de4632e579ca7d84287247af3e739,wrong ? PC^128'd1 : PC);
        end
    endtask
    task ltk_request_event;
        input [63:0] random_value;input [15:0] ediv;
        reg [255:0] value;
        begin value=0;value[7:0]=8'h3e;value[15:8]=13;value[23:16]=5;
            value[39:24]={4'd0,connection_handle};value[103:40]=random_value;
            value[119:104]=ediv;inject(4,15,value);end
    endtask
    task ltk_reply;
        input [127:0] key;
        begin take(1,21);
            check(got[23:0]==24'h12201a && got[39:24]=={4'd0,connection_handle} &&
                got[167:40]==key,"LTK Reply handle/key");
            cc(16'h201a,0,{112'd0,4'd0,connection_handle},8);end
    endtask
    task negative_reply;
        begin take(1,5);
            check(got[23:0]==24'h02201b && got[39:24]=={4'd0,connection_handle},"LTK Negative Reply");
            cc(16'h201b,0,{112'd0,4'd0,connection_handle},8);end
    endtask
    task encryption_change;
        input [7:0] status,on;
        reg [255:0] value;
        begin value=0;value[7:0]=8'h08;value[15:8]=4;value[23:16]=status;
            value[39:24]={4'd0,connection_handle};value[47:40]=on;inject(4,6,value);end
    endtask
    task failed;
        input [7:0] reason;
        begin take(2,10);check(got[79:64]=={reason,8'h05},"Pairing Failed reason");
            check(!pairing && security_failed,"pairing stopped after failure");end
    endtask
    task reconnect;
        begin connected=0;repeat(3)tick();connected=1;repeat(3)tick();end
    endtask
    task fresh;
        begin resetn=0;connected=0;packet_valid=0;tx_ready=0;repeat(3)tick();
            resetn=1;connected=1;repeat(3)tick();end
    endtask

    initial begin
        fresh();
        // Bluetooth Core c1 example. Numeric values are MSB-first here; HCI
        // command tests above separately assert LSB-first wire serialization.
        check(dut.c1_p1(56'h07071000000101,56'h05000800000302,1)==
            128'h05000800000302070710000001010001,"Core c1 p1 example");
        check(dut.c1_p2(48'ha1a2a3a4a5a6,48'hb1b2b3b4b5b6)==
            128'h00000000a1a2a3a4a5a6b1b2b3b4b5b6,"Core c1 p2 example");
        // Independent published s1 vector: AES(0, this block) is
        // 9a1fe1f0e8b0f49b5b4216ae796da062.
        check(dut.s1_plain(128'h000f0e0d0c0b0a091122334455667788,
            128'h010203040506070899aabbccddeeff00)==
            128'h112233445566778899aabbccddeeff00,"Core s1 truncated halves order");
        check(dut.sized_key(128'hffeeddccbbaa99887766554433221100,7)==
            128'h00000000000000000066554433221100,"negotiated 7-byte encryption key");

        start_pair();verify_peer(0);
        take(2,25);check(got[71:64]==4 && got[199:72]==LR,"local Random after verified peer c1");
        // The central can request the STK before its controller AES operation
        // completes. It must be queued, never answered with an unready key.
        ltk_request_event(0,0);
        aes_result(128'h6388274ec6702ee099aabbccddeeff00,STK);
        ltk_reply(STK);encryption_change(0,1);
        rand_result(LTK[63:0]);rand_result(LTK[127:64]);
        rand_result(BR);rand_result(64'habcdef012345beef);
        take(2,25);check(got[71:64]==6 && got[199:72]==LTK,"random bond Encryption Information");
        take(2,19);check(got[71:64]==7 && got[151:72]=={BR,16'hbeef},"random bond Master Identification");
        repeat(3)tick();check(encrypted && !pairing && dut.bond_valid,"bond committed after key distribution");
        no_tx(5);

        // A changed private address must not break a bond selected by EDIV/Rand.
        peer_address=48'h123456789abc;reconnect();
        check(!encrypted && dut.bond_valid,"disconnect clears security but retains RAM bond");
        ltk_request_event(BR,16'hbeef);ltk_reply(LTK);encryption_change(0,1);
        check(encrypted && !security_failed,"bond reconnect encrypts without re-pairing");
        ltk_request_event(BR^64'd1,16'hbeef);negative_reply();
        no_tx(3);
        fresh();ltk_request_event(BR,16'hbeef);negative_reply();
        check(!dut.bond_valid,"reset forgets the RAM bond");

        pairing_request(1,6,0,1);failed(6);
        pairing_request(1,17,0,1);failed(6);
        pairing_request(1,16,0,0);failed(3);
        pairing_request(8'hc1,16,0,1);failed(8'h0a);
        smp(1,7,{80'd0,8'd1,8'd0,8'd16,8'd1,8'd1,8'd3});failed(2);
        smp(1,6,0);failed(8'h0a);
        smp(8'h0c,1,0);failed(7);

        // Android commonly requests bonding+MITM+SC (0x0d). NoInputNoOutput
        // selects unauthenticated Legacy Just Works; do not advertise MITM/SC.
        pairing_request(8'h0d,16,8'h07,8'h07);take_pairing_response();
        smp(5,2,128'd8);check(!pairing && security_failed,"peer Pairing Failed stops cleanly");no_tx(3);

        // Compare failure must never emit the responder random or an STK.
        peer_address=48'ha1a2a3a4a5a6;
        start_pair();verify_peer(1);failed(4);no_tx(5);
        check(!dut.bond_valid,"failed confirm cannot create a bond");

        // Late controller completion after peer abort is drained, not reused.
        pairing_request(1,16,0,1);take_pairing_response();smp(3,17,PC);
        take(1,3);smp(5,2,128'd8);cc(16'h2018,0,128'h1234,14);no_tx(5);
        check(!pairing && !dut.command_pending,"late HCI result discarded after cancellation");
        pairing_request(1,16,0,1);take_pairing_response();
        repeat(205)tick();failed(8);

        // A controller timeout raises a transport fault so the surrounding
        // radio watchdog can reset H5/controller, not wait on command credit.
        pairing_request(1,16,0,1);take_pairing_response();smp(3,17,PC);take(1,3);
        repeat(55)tick();failed(8);check(transport_failed,"HCI timeout requests transport recovery");
        cc(16'h2018,0,128'habcdef,14);no_tx(5);
        check(!pairing && dut.command_stalled,"late timed-out completion cannot restart crypto");
        fresh();check(!transport_failed,"reset clears transport fault");

        // Nonbonding still works, but response must not promise persistent keys.
        pairing_request(0,7,7,7);take(2,15);
        check(got[119:64]==56'h00001000000302,"nonbonding has no key distribution or MITM/SC");
        smp(5,2,128'd8);

        // A submitted output is immutable even if a hostile request makes the
        // pairing fail while transport is backpressured.
        pairing_request(1,16,0,1);
        while(!tx_valid)tick();held=tx_data;
        smp(8'h0c,1,0);check(tx_valid && tx_data===held,"failure cannot overwrite stalled output");
        take(2,15);failed(7);no_tx(5);

        // Aborting with the local Random backpressured must also cancel its
        // continuation into s1, both for peer failure and local protocol error.
        start_pair();verify_peer(0);while(!tx_valid)tick();held=tx_data;
        check(tx_type==2 && tx_data[71:64]==4,"local Random queued before peer abort");
        smp(5,2,128'd8);check(tx_valid && tx_data===held,"peer abort preserves submitted output");
        take(2,25);no_tx(10);check(!pairing && dut.state==0,"peer abort cannot revive s1 after Random handshake");
        start_pair();verify_peer(0);while(!tx_valid)tick();
        smp(8'h0c,1,0);take(2,25);failed(7);no_tx(10);
        check(!pairing && dut.state==0,"protocol error cannot revive s1 after Random handshake");

        // A command already offered under backpressure remains a cancelled
        // drain operation after abort; it cannot turn into the next Rand/AES.
        pairing_request(1,16,0,1);take_pairing_response();smp(3,17,PC);
        while(!tx_valid)tick();held=tx_data;smp(5,2,128'd8);
        check(tx_valid && tx_data===held,"unaccepted HCI request remains stable across abort");
        take(1,3);cc(16'h2018,0,128'h1234,14);no_tx(10);
        check(!pairing && !dut.command_pending,"cancelled unsent command completion cannot resume crypto");
        $display("PASS tb_ble_smp: %0d checks, Legacy c1/s1, random RAM bond, RPA reconnect, failures/timeouts",checks);
        $finish;
    end
    initial begin #2000000;$fatal(1,"SMP test watchdog");end
endmodule
