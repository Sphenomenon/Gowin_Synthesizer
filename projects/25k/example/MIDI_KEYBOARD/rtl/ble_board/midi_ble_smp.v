// LE Legacy Just Works responder. Cryptography and randomness are provided by
// the controller's standard LE Encrypt / LE Rand HCI commands. All packed HCI
// values use wire byte zero in bits [7:0], including 128-bit AES values.
// One RAM-only bond survives disconnects, but not reset/power loss. We distribute
// only an encryption key; no identity, signing, MITM, OOB, or Secure Connections
// support is advertised. A central may offer SC and fall back to Legacy.
module midi_ble_smp #(
    parameter integer CLK_HZ=50000000,
    parameter integer PAIR_TIMEOUT_MS=30000,
    parameter integer COMMAND_TIMEOUT_MS=2000
)(
    input wire clk, resetn, enable,
    input wire connected,
    input wire [11:0] connection_handle,
    input wire [47:0] local_address, peer_address,
    input wire peer_address_type,
    input wire packet_valid,
    input wire [3:0] packet_type,
    input wire [8:0] packet_length,
    input wire [255:0] packet_data,
    output reg tx_valid,
    input wire tx_ready,
    output reg [3:0] tx_type,
    output reg [5:0] tx_length,
    // LE Encrypt is 3 HCI header + 32 parameter bytes, so 32 bytes is too small.
    output reg [287:0] tx_data,
    output reg encrypted, pairing, security_failed,
    output reg transport_failed
);
    localparam [5:0] IDLE=0, TX_WAIT=1, WAIT_CONFIRM=2,
        RANDOM_LOCAL_LO=3, RANDOM_LOCAL_HI=4, AES_LOCAL_1=5,
        AES_LOCAL_2=6, SEND_CONFIRM=7, WAIT_RANDOM=8, AES_PEER_1=9,
        AES_PEER_2=10, SEND_RANDOM=11, AES_STK=12, WAIT_ENCRYPTION=13,
        RANDOM_LTK_LO=14, RANDOM_LTK_HI=15, RANDOM_BOND_RAND=16,
        RANDOM_EDIV=17, SEND_ENCRYPTION_INFO=18, SEND_MASTER_ID=19,
        BOND_FINISHED=20;
    localparam [3:0] C_LOCAL_LO=0,C_LOCAL_HI=1,C_LOCAL_1=2,C_LOCAL_2=3,
        C_PEER_1=4,C_PEER_2=5,C_STK=6,C_LTK_REPLY=7,C_LTK_NEGATIVE=8,
        C_LTK_LO=9,C_LTK_HI=10,C_BOND_RAND=11,C_EDIV=12;
    localparam [31:0] PAIR_LIMIT=(CLK_HZ/1000)*PAIR_TIMEOUT_MS;
    localparam [31:0] COMMAND_LIMIT=(CLK_HZ/1000)*COMMAND_TIMEOUT_MS;
    reg [5:0] state, after_tx;
    reg was_connected;
    reg [11:0] active_handle;
    reg [31:0] pair_timer, command_timer;
    reg command_pending, command_sent, command_cancelled, command_stalled;
    reg [15:0] command_opcode;
    reg [3:0] command_kind;
    reg [55:0] preq, pres;
    reg [47:0] pairing_local_address, pairing_peer_address;
    reg pairing_peer_address_type;
    reg [4:0] key_size;
    reg bonding;
    reg [127:0] local_random, peer_random, local_confirm, peer_confirm;
    reg [127:0] aes_intermediate, stk;
    reg stk_ready, confirm_verified, waiting_encryption;
    // 0=no request, 1=STK, 2=stored bond LTK, 3=negative reply.
    reg [1:0] ltk_request;
    reg failure_pending;
    reg [7:0] failure_reason;
    reg [127:0] candidate_ltk, bond_ltk;
    reg [63:0] candidate_rand, bond_rand;
    reg [15:0] candidate_ediv, bond_ediv;
    reg bond_valid;
    integer i;

    function [15:0] word_at;
        input integer n;
        begin word_at=packet_data[n*8+:16]; end
    endfunction
    // Core Vol 3 Part H c1: least significant bytes are iat, rat, preq, pres.
    function [127:0] c1_p1;
        input [55:0] request, response;
        input initiator_address_type;
        begin c1_p1={response,request,8'h00,{7'd0,initiator_address_type}}; end
    endfunction
    function [127:0] c1_p2;
        input [47:0] initiator_address, responder_address;
        begin c1_p2={32'd0,initiator_address,responder_address}; end
    endfunction
    function [127:0] s1_plain;
        input [127:0] responder_random, initiator_random;
        begin s1_plain={responder_random[63:0],initiator_random[63:0]}; end
    endfunction
    function [127:0] sized_key;
        input [127:0] value;
        input [4:0] size;
        integer n;
        begin
            for(n=0;n<16;n=n+1) sized_key[n*8+:8]=n<size ? value[n*8+:8] : 8'd0;
        end
    endfunction

    task send_smp;
        input [7:0] opcode;
        input [4:0] length;
        input [127:0] body;
        input [5:0] next_state;
        begin
            tx_data<=0;
            tx_data[15:0]<={4'd0,connection_handle};
            tx_data[31:16]<=length+16'd4;
            tx_data[47:32]<={11'd0,length};
            tx_data[63:48]<=16'h0006;
            tx_data[71:64]<=opcode;
            tx_data[199:72]<=body;
            tx_length<=length+6'd8;tx_type<=2;tx_valid<=1;
            state<=TX_WAIT;after_tx<=next_state;
        end
    endtask
    task send_command;
        input [15:0] opcode;
        input [5:0] parameter_length;
        input [255:0] parameters;
        input [3:0] kind;
        begin
            tx_data<=0;tx_data[15:0]<=opcode;
            tx_data[23:16]<={2'd0,parameter_length};
            tx_data[279:24]<=parameters;
            tx_length<=parameter_length+6'd3;tx_type<=1;tx_valid<=1;
            command_pending<=1;command_sent<=0;command_cancelled<=0;
            command_opcode<=opcode;command_kind<=kind;command_timer<=0;
        end
    endtask
    task fail_pairing;
        input [7:0] reason;
        begin
            pairing<=0;security_failed<=1;state<=IDLE;after_tx<=IDLE;
            stk_ready<=0;confirm_verified<=0;ltk_request<=0;
            waiting_encryption<=0;failure_pending<=1;failure_reason<=reason;
            // Drain an already submitted controller operation; its late result
            // must never restart a failed pairing or become another AES stage.
            if(command_pending) command_cancelled<=1;
        end
    endtask

    wire valid_event=packet_type==4 && packet_length>=2 &&
        packet_length=={1'b0,packet_data[15:8]}+9'd2;
    wire smp_acl=packet_type==2 && packet_length>=9 && connected &&
        packet_data[11:0]==connection_handle &&
        (packet_data[13:12]==0 || packet_data[13:12]==2) &&
        packet_data[15:14]==0 && packet_data[31:16]==packet_length-4 &&
        packet_data[47:32]==packet_length-8 && packet_data[63:48]==16'h0006;

    always @(posedge clk) begin
        if(!resetn || !enable) begin
            state<=IDLE;after_tx<=IDLE;was_connected<=0;active_handle<=0;
            tx_valid<=0;tx_type<=0;tx_length<=0;tx_data<=0;
            encrypted<=0;pairing<=0;security_failed<=0;transport_failed<=0;
            pair_timer<=0;command_timer<=0;command_pending<=0;
            command_sent<=0;command_cancelled<=0;command_stalled<=0;
            command_opcode<=0;command_kind<=0;preq<=0;pres<=0;
            pairing_local_address<=0;pairing_peer_address<=0;
            pairing_peer_address_type<=0;key_size<=16;bonding<=0;
            local_random<=0;peer_random<=0;local_confirm<=0;peer_confirm<=0;
            aes_intermediate<=0;stk<=0;stk_ready<=0;confirm_verified<=0;
            waiting_encryption<=0;ltk_request<=0;
            failure_pending<=0;failure_reason<=0;
            candidate_ltk<=0;candidate_rand<=0;candidate_ediv<=0;
            bond_valid<=0;bond_ltk<=0;bond_rand<=0;bond_ediv<=0;
        end else begin
            was_connected<=connected;
            if(pairing || waiting_encryption || ltk_request!=0)
                pair_timer<=pair_timer+1'b1;
            else pair_timer<=0;
            if(tx_valid && tx_ready) begin
                tx_valid<=0;
                if(tx_type==2) state<=after_tx;
                else begin command_sent<=1;command_timer<=0;end
                pair_timer<=0;
            end
            if(command_pending && command_sent && !command_stalled)
                command_timer<=command_timer+1'b1;

            if(!connected || !was_connected || active_handle!=connection_handle) begin
                active_handle<=connection_handle;
                state<=IDLE;after_tx<=IDLE;tx_valid<=0;
                encrypted<=0;pairing<=0;security_failed<=0;
                command_pending<=0;command_sent<=0;command_cancelled<=0;
                command_stalled<=0;pair_timer<=0;command_timer<=0;
                ltk_request<=0;stk_ready<=0;confirm_verified<=0;
                waiting_encryption<=0;failure_pending<=0;
                local_random<=0;peer_random<=0;local_confirm<=0;peer_confirm<=0;
                aes_intermediate<=0;stk<=0;
                candidate_ltk<=0;candidate_rand<=0;candidate_ediv<=0;
                // The one complete RAM bond deliberately survives disconnect.
            end else if(command_pending && command_sent && !command_stalled &&
                command_timer>=COMMAND_LIMIT-1) begin
                // A timed-out HCI operation cannot be safely interleaved with a
                // retry of the same opcode. Refuse new crypto until reconnect.
                command_stalled<=1;command_pending<=0;transport_failed<=1;
                fail_pairing(8'h08);
            end else if((pairing || waiting_encryption || ltk_request!=0) &&
                pair_timer>=PAIR_LIMIT-1) begin
                fail_pairing(8'h08);
            end else if(packet_valid) begin
                if(valid_event && packet_data[7:0]==8'h0e && packet_length>=6 &&
                    command_pending && command_sent && word_at(3)==command_opcode) begin
                    command_pending<=0;command_sent<=0;command_timer<=0;pair_timer<=0;
                    if(command_cancelled) command_cancelled<=0;
                    else if(packet_data[47:40]!=0 ||
                        (command_opcode==16'h2018 && packet_length!=14) ||
                        (command_opcode==16'h2017 && packet_length!=22) ||
                        ((command_opcode==16'h201a || command_opcode==16'h201b) &&
                            (packet_length!=8 || (word_at(6)&16'h0fff)!={4'd0,connection_handle})))
                        fail_pairing(8'h08);
                    else case(command_kind)
                        C_LOCAL_LO:begin local_random[63:0]<=packet_data[111:48];state<=RANDOM_LOCAL_HI;end
                        C_LOCAL_HI:begin local_random[127:64]<=packet_data[111:48];state<=AES_LOCAL_1;end
                        C_LOCAL_1:begin
                            aes_intermediate<=packet_data[175:48]^
                                c1_p2(pairing_peer_address,pairing_local_address);
                            state<=AES_LOCAL_2;
                        end
                        C_LOCAL_2:begin local_confirm<=packet_data[175:48];state<=SEND_CONFIRM;end
                        C_PEER_1:begin
                            aes_intermediate<=packet_data[175:48]^
                                c1_p2(pairing_peer_address,pairing_local_address);
                            state<=AES_PEER_2;
                        end
                        C_PEER_2:begin
                            if(packet_data[175:48]!=peer_confirm) fail_pairing(8'h04);
                            else begin confirm_verified<=1;state<=SEND_RANDOM;end
                        end
                        C_STK:begin
                            stk<=sized_key(packet_data[175:48],key_size);
                            stk_ready<=1;state<=WAIT_ENCRYPTION;
                        end
                        C_LTK_REPLY:begin end
                        C_LTK_NEGATIVE:begin end
                        C_LTK_LO:begin candidate_ltk[63:0]<=packet_data[111:48];state<=RANDOM_LTK_HI;end
                        C_LTK_HI:begin
                            candidate_ltk<=sized_key({packet_data[111:48],candidate_ltk[63:0]},key_size);
                            state<=RANDOM_BOND_RAND;
                        end
                        C_BOND_RAND:begin candidate_rand<=packet_data[111:48];state<=RANDOM_EDIV;end
                        C_EDIV:begin
                            // Keep the all-zero EDIV/Rand tuple reserved for STK.
                            if(packet_data[63:48]==0 && candidate_rand==0) state<=RANDOM_BOND_RAND;
                            else begin candidate_ediv<=packet_data[63:48];state<=SEND_ENCRYPTION_INFO;end
                        end
                        default:fail_pairing(8'h08);
                    endcase
                end else if(valid_event && packet_data[7:0]==8'h0f && packet_length==6 &&
                    command_pending && command_sent && word_at(4)==command_opcode &&
                    packet_data[23:16]!=0) begin
                    command_pending<=0;command_sent<=0;fail_pairing(8'h08);
                end else if(valid_event && packet_data[7:0]==8'h3e && packet_length==15 &&
                    packet_data[23:16]==8'h05 && (word_at(3)&16'h0fff)=={4'd0,connection_handle}) begin
                    pair_timer<=0;
                    if(pairing && confirm_verified && word_at(13)==0 && packet_data[103:40]==0)
                        ltk_request<=1;
                    else if(!pairing && bond_valid && word_at(13)==bond_ediv &&
                        packet_data[103:40]==bond_rand) ltk_request<=2;
                    else ltk_request<=3;
                end else if(valid_event && packet_data[7:0]==8'h08 && packet_length==6 &&
                    (word_at(3)&16'h0fff)=={4'd0,connection_handle}) begin
                    pair_timer<=0;
                    if(packet_data[23:16]!=0 || packet_data[47:40]==0) begin
                        encrypted<=0;waiting_encryption<=0;
                        if(pairing) fail_pairing(8'h08);else security_failed<=1;
                    end else begin
                        encrypted<=1;security_failed<=0;waiting_encryption<=0;
                        if(pairing && confirm_verified && stk_ready) begin
                            if(bonding) state<=RANDOM_LTK_LO;
                            else begin pairing<=0;state<=IDLE;stk_ready<=0;end
                        end
                    end
                end else if(valid_event && packet_data[7:0]==8'h30 && packet_length==5 &&
                    (word_at(3)&16'h0fff)=={4'd0,connection_handle} && packet_data[23:16]!=0) begin
                    encrypted<=0;waiting_encryption<=0;
                    if(pairing) fail_pairing(8'h08);else security_failed<=1;
                end else if(smp_acl) begin
                    pair_timer<=0;
                    case(packet_data[71:64])
                        8'h01:begin
                            if(pairing || command_pending || tx_valid || command_stalled)
                                fail_pairing(8'h08);
                            else if(packet_length!=15) fail_pairing(8'h0a);
                            else if(packet_data[87:80]!=0) fail_pairing(8'h02);
                            else if(packet_data[79:72]>4 || packet_data[95:94]!=0 ||
                                packet_data[89:88]>1 || packet_data[111:108]!=0 || packet_data[119:116]!=0)
                                fail_pairing(8'h0a);
                            else if(packet_data[103:96]<7 || packet_data[103:96]>16)
                                fail_pairing(8'h06);
                            else if(packet_data[88] && !packet_data[112])
                                fail_pairing(8'h03);
                            else begin
                                preq<=packet_data[119:64];
                                // NoInputNoOutput, no OOB, at most bonding, max16,
                                // no central keys, responder EncKey only.
                                pres<={7'd0,packet_data[88],8'd0,8'd16,
                                    7'd0,packet_data[88],8'd0,8'd3,8'h02};
                                pairing_local_address<=local_address;
                                pairing_peer_address<=peer_address;
                                pairing_peer_address_type<=peer_address_type;
                                key_size<=packet_data[100:96];bonding<=packet_data[88];
                                pairing<=1;security_failed<=0;failure_pending<=0;
                                stk_ready<=0;confirm_verified<=0;waiting_encryption<=0;
                                ltk_request<=0;state<=TX_WAIT;after_tx<=WAIT_CONFIRM;
                                // Use the just-received bonding bit, not old pres.
                                send_smp(8'h02,7,{80'd0,7'd0,packet_data[88],8'd0,
                                    8'd16,7'd0,packet_data[88],8'd0,8'd3},WAIT_CONFIRM);
                            end
                        end
                        8'h03:begin
                            if(packet_length!=25) fail_pairing(8'h0a);
                            else if(pairing && state==WAIT_CONFIRM) begin
                                peer_confirm<=packet_data[199:72];state<=RANDOM_LOCAL_LO;
                            end else fail_pairing(8'h08);
                        end
                        8'h04:begin
                            if(packet_length!=25) fail_pairing(8'h0a);
                            else if(pairing && state==WAIT_RANDOM) begin
                                peer_random<=packet_data[199:72];state<=AES_PEER_1;
                            end else fail_pairing(8'h08);
                        end
                        8'h05:begin
                            if(packet_length!=10) fail_pairing(8'h0a);
                            else begin
                                pairing<=0;security_failed<=1;state<=IDLE;after_tx<=IDLE;
                                stk_ready<=0;confirm_verified<=0;ltk_request<=0;
                                waiting_encryption<=0;failure_pending<=0;
                                if(command_pending) command_cancelled<=1;
                            end
                        end
                        default:fail_pairing(8'h07);
                    endcase
                end
            end else if(!tx_valid) begin
                if(failure_pending) begin
                    send_smp(8'h05,2,{120'd0,failure_reason},IDLE);
                    failure_pending<=0;
                end else if(!command_pending && !command_stalled) begin
                    if(ltk_request==3) begin
                        send_command(16'h201b,2,{240'd0,4'd0,connection_handle},C_LTK_NEGATIVE);
                        ltk_request<=0;
                    end else if(ltk_request==2 || (ltk_request==1 && stk_ready)) begin
                        send_command(16'h201a,18,{112'd0,ltk_request==1?stk:bond_ltk,
                            4'd0,connection_handle},C_LTK_REPLY);
                        waiting_encryption<=1;ltk_request<=0;
                    end else case(state)
                        RANDOM_LOCAL_LO:send_command(16'h2018,0,0,C_LOCAL_LO);
                        RANDOM_LOCAL_HI:send_command(16'h2018,0,0,C_LOCAL_HI);
                        AES_LOCAL_1:send_command(16'h2017,32,
                            {local_random^c1_p1(preq,pres,pairing_peer_address_type),128'd0},C_LOCAL_1);
                        AES_LOCAL_2:send_command(16'h2017,32,{aes_intermediate,128'd0},C_LOCAL_2);
                        SEND_CONFIRM:send_smp(8'h03,17,local_confirm,WAIT_RANDOM);
                        AES_PEER_1:send_command(16'h2017,32,
                            {peer_random^c1_p1(preq,pres,pairing_peer_address_type),128'd0},C_PEER_1);
                        AES_PEER_2:send_command(16'h2017,32,{aes_intermediate,128'd0},C_PEER_2);
                        SEND_RANDOM:send_smp(8'h04,17,local_random,AES_STK);
                        AES_STK:send_command(16'h2017,32,
                            {s1_plain(local_random,peer_random),128'd0},C_STK);
                        RANDOM_LTK_LO:send_command(16'h2018,0,0,C_LTK_LO);
                        RANDOM_LTK_HI:send_command(16'h2018,0,0,C_LTK_HI);
                        RANDOM_BOND_RAND:send_command(16'h2018,0,0,C_BOND_RAND);
                        RANDOM_EDIV:send_command(16'h2018,0,0,C_EDIV);
                        SEND_ENCRYPTION_INFO:send_smp(8'h06,17,candidate_ltk,SEND_MASTER_ID);
                        SEND_MASTER_ID:send_smp(8'h07,11,{48'd0,candidate_rand,candidate_ediv},BOND_FINISHED);
                        BOND_FINISHED:begin
                            bond_ltk<=candidate_ltk;bond_rand<=candidate_rand;
                            bond_ediv<=candidate_ediv;bond_valid<=1;
                            pairing<=0;stk_ready<=0;state<=IDLE;
                            local_random<=0;peer_random<=0;stk<=0;
                        end
                        default:begin end
                    endcase
                end
            end
        end
    end
endmodule
