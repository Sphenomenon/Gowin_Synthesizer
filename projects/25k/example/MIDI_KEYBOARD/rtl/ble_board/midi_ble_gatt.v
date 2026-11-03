// MIDI ATT server derived from RTL8723DS_BLE/generated/rtl/bt_gatt.v.
// See NOTICE.md. One LE connection, ATT MTU 23, Legacy Just Works SMP.
// Value byte zero is data[7:0]. Values are opaque BLE-MIDI codec packets.
module midi_ble_gatt #(
    parameter integer CLK_HZ=50000000
)(
    input wire clk, resetn, enable,
    input wire [47:0] local_address,
    input wire rx_valid, input wire [3:0] rx_type,
    input wire [8:0] rx_length, output reg [8:0] rx_payload_addr,
    input wire [7:0] rx_payload_data, output reg rx_consume,
    output reg tx_start, output reg [3:0] tx_type,
    output reg [8:0] tx_length, input wire tx_ready, tx_done, tx_error,
    input wire [8:0] tx_payload_addr, output wire [7:0] tx_payload_data,
    input wire value_tx_valid, output wire value_tx_ready,
    input wire [39:0] value_tx_data, input wire [2:0] value_tx_length,
    output reg value_rx_valid, input wire value_rx_ready,
    output reg [39:0] value_rx_data, output reg [2:0] value_rx_length,
    output reg connected, subscribed, output reg failed
);
    localparam IDLE=0,CAPTURE=1,PARSE=2,WAIT_DROP=3,CAPTURE_WAIT=4;
    localparam [127:0] MIDI_SERVICE=128'h03b80e5aede84b33a7516ce34ec4c700;
    localparam [127:0] MIDI_CHARACTERISTIC=128'h7772e5db38684112a1a9f2669d106bf3;
    reg [2:0] state;
    reg [3:0] captured_type;
    reg [8:0] captured_length;
    // MTU 23 and every parsed header fit the first 32 bytes. HCI completed
    // packet entries are reduced while streaming, so 264 flip-flop bytes and
    // their wide random-read mux are unnecessary.
    reg [7:0] packet[0:31], response[0:63], active_tx[0:35];
    reg [8:0] response_length[0:1];
    reg [1:0] queued;
    reg read_slot,write_slot,tx_busy,tx_credit,command_credit;
    reg [11:0] connection_handle;
    reg [47:0] peer_address;
    reg peer_address_type;
    reg restart_advertising,adv_waiting;
    wire [255:0] security_packet;
    wire security_tx_valid,security_tx_ready,security_encrypted,security_pairing,security_failed;
    wire security_transport_failed;
    wire [3:0] security_tx_type;
    wire [5:0] security_tx_length;
    wire [287:0] security_tx_data;
    genvar security_byte;
    generate for(security_byte=0;security_byte<32;security_byte=security_byte+1) begin:security_prefix
        assign security_packet[security_byte*8+:8]=packet[security_byte];
    end endgenerate
    // Command traffic does not consume controller ACL credit. Security ACLs
    // share that credit with ATT and notifications, and get transmit priority.
    assign security_tx_ready=state==IDLE && !rx_valid && !tx_busy && tx_ready && !failed &&
        !restart_advertising && connected &&
        (security_tx_type==1 ? command_credit : tx_credit);
    midi_ble_smp #(.CLK_HZ(CLK_HZ)) security(
        .clk(clk),.resetn(resetn),.enable(enable),.connected(connected),
        .connection_handle(connection_handle),.local_address(local_address),
        .peer_address(peer_address),.peer_address_type(peer_address_type),
        .packet_valid(state==PARSE),.packet_type(captured_type),
        .packet_length(captured_length),.packet_data(security_packet),
        .tx_valid(security_tx_valid),.tx_ready(security_tx_ready),
        .tx_type(security_tx_type),.tx_length(security_tx_length),.tx_data(security_tx_data),
        .encrypted(security_encrypted),.pairing(security_pairing),.security_failed(security_failed),
        .transport_failed(security_transport_failed));
    reg tx_value_pending;
    reg [39:0] tx_value,last_value;
    reg [2:0] tx_value_length,last_value_length;
    reg [31:0] adv_timer;
    reg completion_nonzero,completion_match;
    reg [7:0] completion_handle_low,completion_count_low;
    integer i;
    reg [4:0] used;
    reg [15:0] start_handle,end_handle,attribute_type;
    reg [5:0] response_base;
    reg uuid_matches;
    assign tx_payload_data=tx_payload_addr<36 ? active_tx[tx_payload_addr] : 0;
    assign value_tx_ready=enable && connected && subscribed && !failed &&
        !security_pairing && !security_failed &&
        !tx_value_pending && value_tx_length>=3 && value_tx_length<=5;
    function [15:0] word_at;
        input [4:0] address;
        begin word_at={packet[address+1],packet[address]}; end
    endfunction
    function [15:0] attribute_uuid;
        input [15:0] handle;
        begin case(handle)
            1,4,5:attribute_uuid=16'h2800;
            2,6:attribute_uuid=16'h2803;
            3:attribute_uuid=16'h2a00;
            8:attribute_uuid=16'h2902;
            default:attribute_uuid=0;
        endcase end
    endfunction
    function [7:0] name_byte;
        input integer at;
        begin case(at)
            0:name_byte="G";1:name_byte="W";2:name_byte="K";3:name_byte="-";
            4:name_byte="M";5:name_byte="I";6:name_byte="D";7:name_byte="I";
            default:name_byte=0;
        endcase end
    endfunction
    task response_word;
        input [4:0] at; input [15:0] data;
        begin response[response_base+at]=data[7:0];
            response[response_base+at+1]=data[15:8]; end
    endtask
    task response_uuid;
        input [4:0] at; input [127:0] uuid;
        integer n;
        begin for(n=0;n<16;n=n+1) response[response_base+at+n]=uuid[n*8+:8]; end
    endtask
    task response_begin;
        input [15:0] cid; input [4:0] length;
        begin
            response_word(0,{4'b0000,connection_handle});
            response_word(2,length+4);response_word(4,length);response_word(6,cid);
            response_length[write_slot]<=length+8;
            write_slot<=~write_slot;queued<=queued+1'b1;
        end
    endtask
    task att_error;
        input [7:0] opcode;input [15:0] handle;input [7:0] code;
        begin response_begin(4,5); response[response_base+8]=1;
            response[response_base+9]=opcode;response_word(10,handle);
            response[response_base+12]=code;end
    endtask
    task read_attribute;
        input [15:0] handle;
        begin
            response[response_base+8]=8'h0b;
            case(handle)
                1,4:begin response_begin(4,3);response_word(9,handle==1?16'h1800:16'h1801);end
                2:begin response_begin(4,6);response[response_base+9]=2;
                    response_word(10,3);response_word(12,16'h2a00);end
                3:begin response_begin(4,9);for(i=0;i<8;i=i+1)
                    response[response_base+9+i]=name_byte(i);end
                5:begin response_begin(4,17);response_uuid(9,MIDI_SERVICE);end
                6:begin response_begin(4,20);response[response_base+9]=8'h16;
                    response_word(10,7);response_uuid(12,MIDI_CHARACTERISTIC);end
                7:begin response_begin(4,1+last_value_length);for(i=0;i<5;i=i+1)
                    response[response_base+9+i]=last_value[i*8+:8];end
                8:begin response_begin(4,3);response_word(9,{15'b0,subscribed});end
                default:att_error(8'h0a,handle,1);
            endcase
        end
    endtask
    task process_att;
        begin
            start_handle=word_at(9);end_handle=word_at(11);attribute_type=word_at(13);
            case(packet[8])
                8'h02:if(captured_length!=11) att_error(2,0,4);
                    else begin response_begin(4,3);response[response_base+8]=3;response_word(9,23);end
                8'h06:begin
                    if(captured_length!=17 && captured_length!=31) att_error(6,0,4);
                    else if(start_handle==0 || start_handle>end_handle) att_error(6,start_handle,1);
                    else begin
                        response[response_base+8]=7;used=1;uuid_matches=1;
                        for(i=0;i<16;i=i+1) if(packet[15+i]!=MIDI_SERVICE[i*8+:8]) uuid_matches=0;
                        if(attribute_type==16'h2800) begin
                            if(captured_length==17) begin
                                if(start_handle<=1 && end_handle>=1 && word_at(15)==16'h1800) begin
                                    response_word(9,1);response_word(11,3);used=5;end
                                else if(start_handle<=4 && end_handle>=4 && word_at(15)==16'h1801) begin
                                    response_word(9,4);response_word(11,4);used=5;end
                            end else if(uuid_matches && start_handle<=5 && end_handle>=5) begin
                                response_word(9,5);response_word(11,8);used=5;end
                        end
                        if(used==1) att_error(6,start_handle,8'h0a);else response_begin(4,used);
                    end
                end
                8'h10:begin
                    if(captured_length!=15) att_error(8'h10,0,4);
                    else if(start_handle==0 || start_handle>end_handle) att_error(8'h10,start_handle,1);
                    else if(attribute_type!=16'h2800) att_error(8'h10,start_handle,8'h10);
                    else begin
                        response[response_base+8]=8'h11;used=2;
                        if(start_handle<=4) begin
                            response[response_base+9]=6;
                            if(start_handle<=1 && end_handle>=1) begin response_word(10,1);
                                response_word(12,3);response_word(14,16'h1800);used=8;end
                            if(start_handle<=4 && end_handle>=4) begin response_word(8+used,4);
                                response_word(10+used,4);response_word(12+used,16'h1801);used=used+6;end
                        end
                        if(used==2 && start_handle<=5 && end_handle>=5) begin
                            response[response_base+9]=20;response_word(10,5);response_word(12,8);
                            response_uuid(14,MIDI_SERVICE);used=22;end
                        if(used==2) att_error(8'h10,start_handle,8'h0a);else response_begin(4,used);
                    end
                end
                8'h08:begin
                    if(captured_length!=15 && captured_length!=29) att_error(8,0,4);
                    else if(start_handle==0 || start_handle>end_handle) att_error(8,start_handle,1);
                    else begin
                        response[response_base+8]=9;used=2;
                        if(captured_length==15 && attribute_type==16'h2803) begin
                            if(start_handle<=2 && end_handle>=2) begin
                                response[response_base+9]=7;response_word(10,2);
                                response[response_base+12]=2;response_word(13,3);
                                response_word(15,16'h2a00);used=9;
                            end else if(start_handle<=6 && end_handle>=6) begin
                                response[response_base+9]=21;response_word(10,6);
                                response[response_base+12]=8'h16;response_word(13,7);
                                response_uuid(15,MIDI_CHARACTERISTIC);used=23;end
                        end else if(captured_length==15 && attribute_type==16'h2a00 &&
                            start_handle<=3 && end_handle>=3) begin
                            response[response_base+9]=10;response_word(10,3);
                            for(i=0;i<8;i=i+1) response[response_base+12+i]=name_byte(i);used=12;
                        end else if(captured_length==29 && start_handle<=7 && end_handle>=7) begin
                            uuid_matches=1;for(i=0;i<16;i=i+1)
                                if(packet[13+i]!=MIDI_CHARACTERISTIC[i*8+:8]) uuid_matches=0;
                            if(uuid_matches) begin response[response_base+9]=last_value_length+2;
                                response_word(10,7);for(i=0;i<5;i=i+1)
                                response[response_base+12+i]=last_value[i*8+:8];used=4+last_value_length;end
                        end
                        if(used==2) att_error(8,start_handle,8'h0a);else response_begin(4,used);
                    end
                end
                8'h04:begin
                    if(captured_length!=13) att_error(4,0,4);
                    else if(start_handle==0 || start_handle>end_handle) att_error(4,start_handle,1);
                    else if(start_handle==7) begin response_begin(4,20);
                        response[response_base+8]=5;response[response_base+9]=2;
                        response_word(10,7);response_uuid(12,MIDI_CHARACTERISTIC);end
                    else begin response[response_base+8]=5;response[response_base+9]=1;used=2;
                        for(i=1;i<=8;i=i+1) if(i>=start_handle && i<=end_handle &&
                            i!=7 && !(start_handle<7 && i>7) && used+4<=23) begin
                            response_word(8+used,i);response_word(10+used,attribute_uuid(i));used=used+4;end
                        if(used==2) att_error(4,start_handle,8'h0a);else response_begin(4,used);
                    end
                end
                8'h0a:if(captured_length!=11) att_error(8'h0a,0,4);else read_attribute(start_handle);
                8'h0c:if(captured_length!=13) att_error(8'h0c,0,4);
                    else att_error(8'h0c,start_handle,start_handle<1 || start_handle>8 ? 1 : 8'h0b);
                8'h12,8'h52:begin
                    if(captured_length<11) begin if(packet[8]==8'h12) att_error(8'h12,0,4);end
                    else if(start_handle==8 && captured_length==13 && word_at(11)<=1) begin
                        subscribed<=packet[11][0];
                        if(!packet[11][0]) tx_value_pending<=0;
                        if(packet[8]==8'h12) begin response_begin(4,1);response[response_base+8]=8'h13;end
                    end else if(start_handle==7 && packet[8]==8'h52 &&
                        captured_length>=14 && captured_length<=16) begin
                        if(!value_rx_valid || value_rx_ready) begin
                            value_rx_valid<=1;value_rx_length<=captured_length-11;
                            for(i=0;i<5;i=i+1) value_rx_data[i*8+:8]<=
                                i<captured_length-11 ? packet[11+i] : 8'd0;
                        end else state<=PARSE; // hold packet until the codec accepts its predecessor
                    end else if(packet[8]==8'h12) att_error(8'h12,start_handle,
                        start_handle==8 ? 8'h0d : start_handle==0 || start_handle>8 ? 1 : 3);
                end
                8'h1e:begin end
                default:if(!packet[8][6]) att_error(packet[8],captured_length>=11?start_handle:0,6);
            endcase
        end
    endtask
    always @(posedge clk) begin
        if(!resetn || !enable) begin
            state<=IDLE;captured_type<=0;captured_length<=0;rx_payload_addr<=0;
            rx_consume<=0;tx_start<=0;tx_length<=0;tx_type<=2;
            connected<=0;subscribed<=0;failed<=0;connection_handle<=0;
            peer_address<=0;peer_address_type<=0;
            queued<=0;read_slot<=0;write_slot<=0;tx_busy<=0;tx_credit<=1;command_credit<=1;
            tx_value_pending<=0;tx_value<=0;tx_value_length<=0;
            last_value<=40'h0000f88080;last_value_length<=3;
            value_rx_valid<=0;value_rx_data<=0;value_rx_length<=0;
            restart_advertising<=0;adv_waiting<=0;adv_timer<=0;
            completion_nonzero<=0;completion_match<=0;completion_handle_low<=0;completion_count_low<=0;
        end else begin
            rx_consume<=0;tx_start<=0;
            if(security_transport_failed) failed<=1;
            if(value_rx_valid && value_rx_ready) value_rx_valid<=0;
            if(value_tx_valid && value_tx_ready) begin
                tx_value<=value_tx_data;tx_value_length<=value_tx_length;tx_value_pending<=1;
                last_value<=value_tx_data;last_value_length<=value_tx_length;
            end
            if(tx_busy && (tx_done || tx_error)) begin tx_busy<=0;if(tx_error) failed<=1;end
            if(adv_waiting) begin
                if(adv_timer>=(CLK_HZ/1000)*2000) failed<=1;else adv_timer<=adv_timer+1'b1;
            end
            case(state)
                IDLE:begin
                    if(rx_valid) begin
                        if(rx_length==0 || rx_length>264) begin rx_consume<=1;state<=WAIT_DROP;end
                        else begin captured_type<=rx_type;captured_length<=rx_length;rx_payload_addr<=0;completion_nonzero<=0;state<=CAPTURE_WAIT;end
                    end else if(!tx_busy && tx_ready && !failed) begin
                        if(restart_advertising && !adv_waiting && command_credit) begin
                            active_tx[0]<=8'h0a;active_tx[1]<=8'h20;active_tx[2]<=1;active_tx[3]<=1;
                            tx_type<=1;tx_length<=4;tx_start<=1;tx_busy<=1;adv_waiting<=1;adv_timer<=0;
                            command_credit<=0;
                        end else if(security_tx_valid && security_tx_ready) begin
                            for(i=0;i<36;i=i+1) active_tx[i]<=security_tx_data[i*8+:8];
                            tx_type<=security_tx_type;tx_length<={3'd0,security_tx_length};
                            tx_start<=1;tx_busy<=1;
                            if(security_tx_type==2) tx_credit<=0;
                            else if(security_tx_type==1) command_credit<=0;
                        end else if(tx_credit && connected && queued!=0) begin
                            for(i=0;i<32;i=i+1) active_tx[i]<=response[(read_slot?32:0)+i];
                            tx_type<=2;tx_length<=response_length[read_slot];tx_start<=1;
                            read_slot<=~read_slot;queued<=queued-1'b1;tx_busy<=1;tx_credit<=0;
                        end else if(tx_credit && connected && subscribed && tx_value_pending &&
                            !security_pairing && !security_failed) begin
                            active_tx[0]<=connection_handle[7:0];active_tx[1]<={4'b0,connection_handle[11:8]};
                            active_tx[2]<=tx_value_length+7;active_tx[3]<=0;
                            active_tx[4]<=tx_value_length+3;active_tx[5]<=0;active_tx[6]<=4;active_tx[7]<=0;
                            active_tx[8]<=8'h1b;active_tx[9]<=7;active_tx[10]<=0;
                            for(i=0;i<5;i=i+1) active_tx[11+i]<=tx_value[i*8+:8];
                            tx_type<=2;tx_length<=11+tx_value_length;tx_start<=1;
                            tx_busy<=1;tx_credit<=0;tx_value_pending<=0;
                        end
                    end
                end
                CAPTURE_WAIT:state<=CAPTURE; // synchronous H5 mailbox read
                CAPTURE:begin
                    if(rx_payload_addr<32) packet[rx_payload_addr[4:0]]<=rx_payload_data;
                    if(rx_payload_addr>=3) case(rx_payload_addr[1:0])
                        3:completion_handle_low<=rx_payload_data;
                        0:completion_match<={rx_payload_data[3:0],completion_handle_low}==connection_handle;
                        1:completion_count_low<=rx_payload_data;
                        2:if(completion_match && (completion_count_low!=0 || rx_payload_data!=0)) completion_nonzero<=1;
                    endcase
                    if(rx_payload_addr+1'b1==captured_length) begin rx_consume<=1;state<=PARSE;end
                    else begin rx_payload_addr<=rx_payload_addr+1'b1;state<=CAPTURE_WAIT;end
                end
                PARSE:begin
                    state<=IDLE;response_base=write_slot?32:0;
                    if(captured_type==4 && captured_length>=2 && captured_length==packet[1]+2) begin
                        // H5 acknowledgement only completes transport. The
                        // controller separately grants HCI command credit;
                        // retain an outstanding command across disconnects.
                        if(packet[0]==8'h0e && captured_length>=5)
                            command_credit<=packet[2]!=0;
                        else if(packet[0]==8'h0f && captured_length==6)
                            command_credit<=packet[3]!=0;
                        if(packet[0]==8'h3e && captured_length>=21 &&
                            (packet[2]==1 || packet[2]==8'h0a) && packet[3]==0) begin
                            connected<=1;subscribed<=0;connection_handle<=word_at(4)&16'h0fff;
                            peer_address_type<=packet[7][0];
                            peer_address<={packet[13],packet[12],packet[11],packet[10],packet[9],packet[8]};
                            tx_credit<=1;queued<=0;read_slot<=0;write_slot<=0;
                            tx_value_pending<=0;restart_advertising<=0;adv_waiting<=0;
                        end else if(packet[0]==5 && captured_length==6 && packet[2]==0 &&
                            (word_at(3)&16'h0fff)==connection_handle) begin
                            connected<=0;subscribed<=0;queued<=0;read_slot<=0;write_slot<=0;
                            tx_value_pending<=0;value_rx_valid<=0;tx_credit<=1;
                            restart_advertising<=1;adv_waiting<=0;
                        end else if(packet[0]==8'h0e && captured_length>=6 && word_at(3)==16'h200a && adv_waiting) begin
                            adv_waiting<=0;restart_advertising<=0;if(packet[5]!=0) failed<=1;
                        end else if(packet[0]==8'h13 && captured_length>=7 && captured_length==3+packet[2]*4) begin
                            if(completion_nonzero) tx_credit<=1;
                        end
                    end else if(captured_type==2 && captured_length>=8 && connected &&
                        (word_at(0)&16'h0fff)==connection_handle &&
                        (packet[1][5:4]==0 || packet[1][5:4]==2) && packet[1][7:6]==0 &&
                        word_at(2)==captured_length-4 && word_at(4)==captured_length-8) begin
                        if(word_at(6)==4 && captured_length>8) begin
                            if(queued<2 || packet[8]==8'h52 || packet[8]==8'h1e) process_att();
                            else failed<=1; // ATT permits only one outstanding request on this bearer.
                        end else if(word_at(6)==5 && captured_length>=12 && queued<2) begin
                            response_begin(5,6);response[response_base+8]=1;
                            response[response_base+9]=packet[9];response_word(10,2);response_word(12,0);
                        end
                    end
                end
                WAIT_DROP:if(!rx_valid) state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
