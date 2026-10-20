`timescale 1ns/1ps

// Independent RTL8723DS controller model at the physical UART boundary.
// Expected RAM image is reconstructed from the original vendor binaries,
// never from the DUT ROM. The model checks every downloaded byte and HCI
// parameter, then exercises ATT discovery, CCCD and notification integrity.
module tb_bt_verilog_system;
    parameter RUN_FAST=1;
    parameter MODEL_PATCH_BYTES=30147;
    defparam dut.core.PATCH_BYTES=MODEL_PATCH_BYTES;
    defparam dut.core.FAST_BAUD=RUN_FAST ? 921600 : 115200;
    reg clk=0, resetn=0, enable=0, uart_rx=1;
    wire uart_tx, bt_enable, outputs_active, initialized, failed;
    wire connected, subscribed;
    wire [767:0] debug;
    defparam dut.core.AUDIO_FILE="../../audio/test_tone.mem";
    reg test_passed=0, fast_link_requested=0;
    localparam CLK_HZ=9216000, BAUD=115200;
    integer bit_ns=800;
    integer controller_baud_pending=0, baud_switched=0, bad_fast=0;
    rtl8723ds_ble #(.CLK_HZ(CLK_HZ),
        .STARTUP_MS(2), .DISABLE_MS(1), .SESSION_MS(10000),
        .NOTIFY_MS(5),
        .PATCH_FILE("rtl8723ds_patch.mem")) dut (
        .clk(clk), .resetn(resetn), .enable(enable), .uart_rx(uart_rx),
        .uart_tx(uart_tx), .bt_enable(bt_enable),
        .outputs_active(outputs_active), .initialized(initialized),
        .failed(failed), .connected(connected), .subscribed(subscribed),
        .debug(debug));
    always #5 clk=~clk;

    reg [7:0] firmware[0:48987], config_bytes[0:46];
    reg [7:0] host_frame[0:511];
    reg [7:0] controller_payload[0:511];
    reg [7:0] controller_frame[0:511];
    reg [7:0] att_expected[0:63];
    integer fd, amount, cfg_at, cfg_size, n, i;
    integer host_used=0, collecting=0, escaped=0;
    integer controller_pending=0, controller_busy=0;
    integer controller_type=0, controller_length=0;
    integer host_next_seq=0, controller_next_seq=0;
    integer controller_acked_seq=0;
    integer command_number=0, patch_fragments=0, patch_position=0;
    integer notification_count=0, acl_packets=0;
    integer att_expected_length=0, att_waiting=0;
    integer expected_opcode, expected_parameters, parameter_at;
    integer payload_length, packet_type, opcode, fragment_size, index;
    integer crc_check, last_notification_seq=-1;
    integer wrong_rom=0, bad_rand=0, zero_rand=0, write_command=0;
    integer business_complete=0, business_used=0, business_index=0, business_token=1;
    integer business_opcode=0, business_id=0, business_response_token=1;
    reg [63:0] business_nonce;
    reg [7:0] business_reply[0:127], business_request[0:63];
    reg [31:0] business_crc;
    reg [7:0] received_byte, expected_byte;
    reg [15:0] crc_value;

    function [7:0] patch_byte;
        input integer at;
        begin
            if(at<30096) patch_byte=firmware[18816+at];
            else if(at<30100) patch_byte=firmware[8+at-30096];
            else patch_byte=config_bytes[at-30100];
        end
    endfunction
    function [15:0] h5_crc_step;
        input [15:0] old_crc;
        input [7:0] data;
        reg [15:0] c;
        integer k;
        begin
            c=old_crc ^ data;
            for(k=0;k<8;k=k+1) c=(c>>1) ^ (c[0] ? 16'h8408 : 0);
            h5_crc_step=c;
        end
    endfunction
    function [15:0] reverse16;
        input [15:0] data;
        integer k;
        begin for(k=0;k<16;k=k+1) reverse16[k]=data[15-k]; end
    endfunction
    function [15:0] ccitt_step;
        input [15:0] old_crc;
        input [7:0] data;
        reg [15:0] c;
        integer k;
        begin
            c=old_crc ^ {data,8'b0};
            for(k=0;k<8;k=k+1) c=(c<<1) ^ (c[15] ? 16'h1021 : 0);
            ccitt_step=c;
        end
    endfunction
    function [7:0] setup_parameter;
        input integer cmd;
        input integer at;
        begin
            setup_parameter=0;
            case(cmd)
                3: case(at) 0:setup_parameter='h14; 1:setup_parameter='hc0;
                    2:setup_parameter='h52; 3:setup_parameter='h02; endcase
                6: if(at==0) setup_parameter=1;
                8: setup_parameter=at==7 ? 'h3f : 'hff;
                9: if(at==0) setup_parameter='h1f;
                10: if(at==0 || at==2) setup_parameter='ha0;
                    else if(at==13) setup_parameter=7;
                    else if(at==5) setup_parameter=1;
                11: case(at)
                    0:setup_parameter=8'h15;
                    1:setup_parameter=8'h02;
                    2:setup_parameter=8'h01;
                    3:setup_parameter=8'h06;
                    4:setup_parameter=8'h11;
                    5:setup_parameter=8'h07;
                    6:setup_parameter=8'h01;
                    7:setup_parameter=8'h00;
                    8:setup_parameter=8'h00;
                    9:setup_parameter=8'h00;
                    10:setup_parameter=8'h80;
                    11:setup_parameter=8'h13;
                    12:setup_parameter=8'h31;
                    13:setup_parameter=8'h9a;
                    14:setup_parameter=8'h87;
                    15:setup_parameter=8'h4f;
                    16:setup_parameter=8'h2a;
                    17:setup_parameter=8'h4c;
                    18:setup_parameter=8'h00;
                    19:setup_parameter=8'h00;
                    20:setup_parameter=8'h6d;
                    21:setup_parameter=8'h9b;
                endcase
                12: case(at)
                    0:setup_parameter=8'h0d;
                    1:setup_parameter=8'h0c;
                    2:setup_parameter=8'h09;
                    3:setup_parameter=8'h47;
                    4:setup_parameter=8'h57;
                    5:setup_parameter=8'h32;
                    6:setup_parameter=8'h35;
                    7:setup_parameter=8'h4b;
                    8:setup_parameter=8'h2d;
                    9:setup_parameter=8'h50;
                    10:setup_parameter=8'h52;
                    11:setup_parameter=8'h4f;
                    12:setup_parameter=8'h54;
                    13:setup_parameter=8'h4f;
                endcase
                14: case(at)
                    0:setup_parameter=((8'h11^8'h5c)&8'hfe)|8'h02;1:setup_parameter=8'h22^8'h21;
                    2:setup_parameter=8'h33;3:setup_parameter=8'h44;
                    4:setup_parameter=8'h55;5:setup_parameter=8'he6;
                endcase
                15,16: if(at==0) setup_parameter=1;
            endcase
        end
    endfunction
    task uart_send;
        input [7:0] data;
        integer k;
        reg parity;
        begin
            parity=0;
            uart_rx=0; #bit_ns;
            for(k=0;k<8;k=k+1) begin
                uart_rx=data[k]; parity=parity^data[k]; #bit_ns;
            end
            uart_rx=parity; #bit_ns;
            uart_rx=1; #bit_ns;
        end
    endtask
    task uart_receive;
        output [7:0] data;
        integer k;
        reg parity;
        begin
            @(negedge uart_tx);
            #(bit_ns/2);
            if(uart_tx!==0) $fatal(1,"UART start glitch");
            parity=0;
            for(k=0;k<8;k=k+1) begin
                #bit_ns; data[k]=uart_tx; parity=parity^uart_tx;
            end
            #bit_ns;
            if(uart_tx!==parity) $fatal(1,"UART even parity mismatch");
            #bit_ns;
            if(uart_tx!==1) $fatal(1,"UART stop bit mismatch");
        end
    endtask
    task slip_send;
        input [7:0] data;
        begin
            if(data=='hc0) begin uart_send('hdb); uart_send('hdc); end
            else if(data=='hdb) begin uart_send('hdb); uart_send('hdd); end
            else uart_send(data);
        end
    endtask
    task queue_link;
        input [7:0] a,b;
        input integer size;
        begin
            if(controller_pending) $fatal(1,"Controller response queue collision");
            controller_type=15; controller_length=size;
            controller_payload[0]=a; controller_payload[1]=b;
            controller_payload[2]=1;
            controller_pending=1;
        end
    endtask
    task command_response;
        input integer op;
        integer k;
        begin
            if(controller_pending) $fatal(1,"Command response queue collision");
            for(k=0;k<32;k=k+1) controller_payload[k]=0;
            controller_type=4; controller_length=6;
            controller_payload[0]='h0e; controller_payload[1]=4;
            controller_payload[2]=1;
            controller_payload[3]=op&255; controller_payload[4]=op>>8;
            case(op)
                'hfc17: if(command_number==6 && bad_fast) controller_payload[5]=1;
                'h1001: begin
                    controller_length=14; controller_payload[1]=12;
                    controller_payload[6]=8; controller_payload[7]='h0d;
                    controller_payload[9]=8; controller_payload[10]='h5d;
                    controller_payload[12]='h23; controller_payload[13]='h87;
                end
                'hfc6d: begin
                    controller_length=7; controller_payload[1]=5;
                    controller_payload[6]=wrong_rom ? 1 : 2;
                end
                'h1009: begin
                    controller_length=12; controller_payload[1]=10;
                    controller_payload[6]='hc5; controller_payload[7]='hd1;
                    controller_payload[8]='h46; controller_payload[9]='h63;
                    controller_payload[10]='h75; controller_payload[11]='h34;
                end
                'hfc20: begin
                    controller_length=7; controller_payload[1]=5;
                    controller_payload[6]=host_frame[7];
                end
                'h2018: begin
                    controller_length=14; controller_payload[1]=12;
                    controller_payload[5]=bad_rand ? 1 : 0;
                    for(k=0;k<8;k=k+1) controller_payload[6+k]=zero_rand ? 0 : 8'h11*(k+1);
                end
                'h2002: begin
                    controller_length=9; controller_payload[1]=7;
                    controller_payload[6]=27; controller_payload[7]=0;
                    controller_payload[8]=1;
                end
            endcase
            controller_pending=1;
        end
    endtask
    task credit_event;
        begin
            if(controller_pending) $fatal(1,"Credit response queue collision");
            controller_type=4; controller_length=7;
            controller_payload[0]='h13; controller_payload[1]=5;
            controller_payload[2]=1; controller_payload[3]=16;
            controller_payload[4]=0; controller_payload[5]=1;
            controller_payload[6]=0; controller_pending=1;
        end
    endtask
    task process_host;
        integer k, sum, remaining, seq;
        begin
            if(host_used<4) $fatal(1,"Short H5 frame");
            sum=(host_frame[0]+host_frame[1]+host_frame[2]+host_frame[3])&255;
            if(sum!=255) $fatal(1,"H5 header checksum mismatch");
            payload_length=(host_frame[1]>>4)+(host_frame[2]<<4);
            remaining=4+payload_length+(host_frame[0][6] ? 2 : 0);
            if(host_used!=remaining) $fatal(1,"H5 length mismatch got %0d expected %0d",host_used,remaining);
            if(host_frame[0][6]) begin
                crc_value='hffff;
                for(k=0;k<4+payload_length;k=k+1) crc_value=h5_crc_step(crc_value,host_frame[k]);
                crc_value=reverse16(crc_value);
                if({host_frame[remaining-2],host_frame[remaining-1]}!==crc_value)
                    $fatal(1,"H5 data CRC mismatch");
            end
            packet_type=host_frame[1]&15;
            if(packet_type==15) begin
                if(payload_length>=2 && host_frame[4]==1 && host_frame[5]=='h7e)
                    queue_link(2,'h7d,2);
                else if(payload_length>=2 && host_frame[4]==3 && host_frame[5]=='hfc)
                    queue_link(4,'h7b,3);
                else if(payload_length>=2 && host_frame[4]==2 && host_frame[5]=='h7d) begin end
                else if(payload_length>=2 && host_frame[4]==4 && host_frame[5]=='h7b) begin end
                else if(payload_length>=2 && host_frame[4]==6 && host_frame[5]=='hf9) begin end
                else $fatal(1,"Unexpected H5 link payload");
            end else if(packet_type==0) begin
                if(payload_length!=0 || host_frame[0][7]) $fatal(1,"Invalid H5 ACK");
                controller_acked_seq=(host_frame[0]>>3)&7;
                if(controller_baud_pending && controller_acked_seq==controller_next_seq) begin
                    // Model only the wire command + its final old-rate ACK;
                    // do not observe DUT divider/state to choose peer speed.
                    #(bit_ns*2); bit_ns=100; baud_switched=1; controller_baud_pending=0;
                end
                if(controller_acked_seq!=controller_next_seq &&
                   !(controller_busy && controller_acked_seq==((controller_next_seq+7)&7)))
                    $fatal(1,"Host ACK sequence mismatch got%0d expected%0d",controller_acked_seq,controller_next_seq);
            end else if(packet_type==1 || packet_type==2) begin
                seq=host_frame[0]&7;
                if(!host_frame[0][7] || seq!=host_next_seq)
                    $fatal(1,"Host reliable sequence mismatch got%0d expected%0d",seq,host_next_seq);
                // Full-duplex frames latch ACK before a concurrent controller frame
                // finishes. Accept the last confirmed ACK or the one outstanding
                // controller sequence; wait_idle still requires eventual advance.
                if(((host_frame[0]>>3)&7)!=controller_next_seq &&
                   ((host_frame[0]>>3)&7)!=controller_acked_seq)
                    $fatal(1,"Host piggyback ACK outside outstanding window");
                controller_acked_seq=(host_frame[0]>>3)&7;
                host_next_seq=(host_next_seq+1)&7;
                if(packet_type==1) begin
                    opcode=host_frame[4]+(host_frame[5]<<8);
                    if(payload_length<3 || host_frame[6]+3!=payload_length)
                        $fatal(1,"HCI command length mismatch");
                    if(opcode==16'hfc17 && command_number==6 && RUN_FAST) begin
                        if(baud_switched || payload_length!=7 || host_frame[6]!=4 ||
                           host_frame[7]!=8'h04 || host_frame[8]!=8'h50 ||
                           host_frame[9]!=8'hf7 || host_frame[10]!=8'h05)
                            $fatal(1,"Expected Realtek 921600 baud command after patch/reset");
                        controller_baud_pending=!bad_fast;command_response(opcode);
                        $display("UART_FAST_COMMAND: after full patch/reset at %0t",$time);
                    end else begin
                    case(command_number)
                        0:begin expected_opcode='h1001; expected_parameters=0; end
                        1:begin expected_opcode='hfc6d; expected_parameters=0; end
                        2:begin expected_opcode='h1009; expected_parameters=0; end
                        3:begin expected_opcode='hfc17; expected_parameters=4; end
                        4:begin expected_opcode='hfc20; expected_parameters=0; end
                        5:begin expected_opcode='h0c03; expected_parameters=0; end
                        6:begin expected_opcode='h0c6d; expected_parameters=2; end
                        7:begin expected_opcode='h2002; expected_parameters=0; end
                        8:begin expected_opcode='h0c01; expected_parameters=8; end
                        9:begin expected_opcode='h2001; expected_parameters=8; end
                        10:begin expected_opcode='h2006; expected_parameters=15; end
                        11:begin expected_opcode='h2008; expected_parameters=32; end
                        12:begin expected_opcode='h2009; expected_parameters=32; end
                        13:begin expected_opcode='h2018; expected_parameters=0; end
                        14:begin expected_opcode='h2005; expected_parameters=6; end
                        15,16:begin expected_opcode='h200a; expected_parameters=1; end
                        default:$fatal(1,"Unexpected command after bootstrap %h",opcode);
                    endcase
                    if(opcode!=expected_opcode) $fatal(1,"HCI opcode got%h expected%h step%0d",opcode,expected_opcode,command_number);
                    if(opcode=='hfc20) begin
                        fragment_size=MODEL_PATCH_BYTES-patch_position;
                        if(fragment_size>252) fragment_size=252;
                        index=patch_fragments | (fragment_size<252 ? 'h80 : 0);
                        if(host_frame[6]!=fragment_size+1 || host_frame[7]!=index)
                            $fatal(1,"Patch fragment header mismatch at%0d",patch_position);
                        for(k=0;k<fragment_size;k=k+1)
                            if(host_frame[k+8]!==patch_byte(patch_position+k))
                                $fatal(1,"Patch byte mismatch at%0d got%h expected%h",patch_position+k,host_frame[k+8],patch_byte(patch_position+k));
                        patch_position=patch_position+fragment_size;
                        patch_fragments=patch_fragments+1;
                        if(patch_fragments%30==0) $display("PATCH_PROGRESS: %0d fragments at %0t",patch_fragments,$time);
                        if(fragment_size<252) command_number=command_number+1;
                    end else begin
                        if(host_frame[6]!=expected_parameters) $fatal(1,"HCI parameter count mismatch");
                        for(k=0;k<expected_parameters;k=k+1)
                            if(host_frame[k+7]!==setup_parameter(command_number,k))
                                $fatal(1,"HCI setup parameter mismatch step%0d byte%0d",command_number,k);
                        command_number=command_number+1;
                    end
                    command_response(opcode);
                    end
                end else begin
                    acl_packets=acl_packets+1;
                    if(payload_length<8 || {host_frame[5],host_frame[4]}!=16 ||
                       {host_frame[7],host_frame[6]}!=payload_length-4 ||
                       {host_frame[9],host_frame[8]}!=payload_length-8 ||
                       ({host_frame[11],host_frame[10]}!=4 && {host_frame[11],host_frame[10]}!=5))
                        $fatal(1,"ACL/L2CAP framing or PB bits mismatch");
                    if({host_frame[11],host_frame[10]}==5) begin
                        if(payload_length!=20 || host_frame[12]!=8'h12 || host_frame[13]!=8'h25 ||
                           host_frame[14]!=8 || host_frame[15]!=0 || host_frame[16]!=12 || host_frame[17]!=0 ||
                           host_frame[18]!=12 || host_frame[19]!=0 || host_frame[20]!=0 || host_frame[21]!=0 ||
                           host_frame[22]!=8'h90 || host_frame[23]!=1)
                            $fatal(1,"LE signaling connection parameter request framing/parameters");
                        fast_link_requested=1;
                    end else if(host_frame[12]=='h1b && host_frame[13]==15) begin
                        if(host_frame[14]!=0 || host_frame[15]!=8'hb1 ||
                           {host_frame[17],host_frame[16]}!=business_response_token ||
                           host_frame[18]!=business_index || host_frame[20]<1 || host_frame[20]>14 ||
                           payload_length!=17+host_frame[20]) $fatal(1,"Business notification fragment header");
                        if(host_frame[19]!==((business_index==0 ? 1 : 0) | (host_frame[19]&2)))
                            $fatal(1,"Business FIRST/reserved flags");
                        for(k=0;k<host_frame[20];k=k+1) business_reply[business_used+k]=host_frame[21+k];
                        business_used=business_used+host_frame[20];business_index=business_index+1;
                        if(host_frame[19]&2) begin
                            business_crc=32'hffffffff;
                            for(k=0;k<business_used;k=k+1) business_crc=crc32_byte(business_crc,business_reply[k]);
                            if(business_crc!=32'hdebb20e3 || business_reply[0]!=business_opcode ||
                               business_reply[1]!=0 || business_used!=20+business_reply[2] ||
                               business_reply[3]!=0 || business_reply[4]!=business_id)
                                $fatal(1,"Business CRC/header/length");
                            for(k=0;k<8;k=k+1)
                                if(business_reply[8+k]!==((business_nonce>>(8*k))&255)) $fatal(1,"Business nonce");
                            if(business_opcode==1) begin
                                if(business_used!=40) $fatal(1,"HELLO length");
                                for(k=0;k<8;k=k+1) if(business_reply[16+k]!==8'h11*(k+1)) $fatal(1,"HELLO boot ID");
                            end else if(business_used!=84 || business_reply[60]!=8) $fatal(1,"Status snapshot");
                            business_complete=1;business_index=0;business_used=0;business_response_token=business_response_token+1;
                        end
                    end else if(host_frame[12]=='h1b) begin
                        if(payload_length!=31 || host_frame[13]!=7 || host_frame[14]!=0)
                            $fatal(1,"Notification handle or length mismatch");
                        if({host_frame[15],host_frame[16],host_frame[17],host_frame[18]}!==32'h42545354)
                            $fatal(1,"Notification BTST marker mismatch");
                        seq=host_frame[19]+(host_frame[20]<<8)+(host_frame[21]<<16)+(host_frame[22]<<24);
                        if(seq!=last_notification_seq+1) $fatal(1,"Notification sequence gap");
                        last_notification_seq=seq;
                        for(k=0;k<6;k=k+1) if(host_frame[27+k]!=k) $fatal(1,"Notification data mismatch");
                        crc_value='hffff;
                        for(k=15;k<33;k=k+1) crc_value=ccitt_step(crc_value,host_frame[k]);
                        if({host_frame[34],host_frame[33]}!==crc_value) $fatal(1,"Notification CCITT CRC mismatch");
                        notification_count=notification_count+1;
                    end else begin
                        if(!att_waiting || payload_length-8!=att_expected_length)
                            $fatal(1,"Unexpected ATT response length/opcode%h",host_frame[12]);
                        for(k=0;k<att_expected_length;k=k+1)
                            if(host_frame[k+12]!==att_expected[k])
                                $fatal(1,"ATT response mismatch byte%0d got%h expected%h",k,host_frame[k+12],att_expected[k]);
                        att_waiting=0;
                    end
                    credit_event();
                end
            end else $fatal(1,"Unexpected host H5 packet type%0d",packet_type);
        end
    endtask

    // TX and RX are intentionally concurrent: ACKs may begin while the
    // controller's final delimiter is still in its UART stop bit.
    initial begin : host_uart_monitor
        forever begin
            uart_receive(received_byte);
            if(received_byte=='hc0) begin
                if(escaped) $fatal(1,"Malformed SLIP escape at delimiter");
                if(collecting && host_used) process_host();
                collecting=1; host_used=0; escaped=0;
            end else if(collecting) begin
                if(escaped) begin
                    if(received_byte=='hdc) received_byte='hc0;
                    else if(received_byte=='hdd) received_byte='hdb;
                    else $fatal(1,"Malformed SLIP escape");
                    escaped=0; host_frame[host_used]=received_byte; host_used=host_used+1;
                end else if(received_byte=='hdb) escaped=1;
                else begin host_frame[host_used]=received_byte; host_used=host_used+1; end
                if(host_used>=512) $fatal(1,"Host H5 frame overflow");
            end
        end
    end
    initial begin : controller_uart_sender
        integer k, length, typ, reliable;
        forever begin
            wait(controller_pending);
            controller_busy=1;
            length=controller_length; typ=controller_type;
            reliable=(typ==2 || typ==4);
            controller_frame[0]=(host_next_seq<<3) | (reliable ? ('h80|controller_next_seq) : 0);
            if(reliable) controller_next_seq=(controller_next_seq+1)&7;
            controller_frame[1]=typ|((length&15)<<4);
            controller_frame[2]=length>>4;
            controller_frame[3]=~(controller_frame[0]+controller_frame[1]+controller_frame[2]);
            for(k=0;k<length;k=k+1) controller_frame[k+4]=controller_payload[k];
            controller_pending=0;
            // Let the host finish the outgoing delimiter stop bit.
            #bit_ns;
            uart_send('hc0);
            for(k=0;k<length+4;k=k+1) slip_send(controller_frame[k]);
            uart_send('hc0);
            controller_busy=0;
        end
    end

    task wait_idle;
        begin
            wait(!controller_pending && !controller_busy);
            wait(controller_acked_seq==controller_next_seq);
            #2000;
        end
    endtask
    task send_connection;
        integer k;
        begin
            wait_idle();
            for(k=0;k<21;k=k+1) controller_payload[k]=0;
            controller_type=4; controller_length=21;
            controller_payload[0]='h3e; controller_payload[1]=19;
            controller_payload[2]=1; controller_payload[4]=16;
            controller_payload[6]=1; controller_payload[14]=24;
            controller_payload[18]='hc8; controller_pending=1;
            wait(connected); wait_idle();
        end
    endtask
    task send_att;
        input integer request_length;
        integer k;
        begin
            // Request ATT bytes were placed at controller_payload[8:].
            controller_payload[0]=16; controller_payload[1]=0;
            controller_payload[2]=request_length+4; controller_payload[3]=0;
            controller_payload[4]=request_length; controller_payload[5]=0;
            controller_payload[6]=4; controller_payload[7]=0;
            controller_type=2; controller_length=request_length+8;
            att_waiting=controller_payload[8]!=8'h52; controller_pending=1;
            wait(!att_waiting); wait_idle();
        end
    endtask
    function [31:0] crc32_byte;
        input [31:0] c0; input [7:0] d;
        integer b; reg [31:0] c;
        begin
            c=c0;
            for(b=0;b<8;b=b+1) c=(c>>1)^((c[0]^d[b])?32'hedb88320:0);
            crc32_byte=c;
        end
    endfunction
    task business_command;
        input [7:0] op; input integer id; input [63:0] nonce;
        integer j,offset,count,size;
        reg [31:0] crc;
        begin
            business_complete=0;business_opcode=op;business_id=id;business_nonce=nonce;
            size=op==1 ? 24 : 20;
            for(j=0;j<64;j=j+1) business_request[j]=0;
            business_request[0]=op;business_request[2]=size-20;
            business_request[4]=id;
            for(j=0;j<8;j=j+1) business_request[8+j]=nonce>>(8*j);
            if(op==1) business_request[16]=1;
            crc=32'hffffffff;
            for(j=0;j<size-4;j=j+1) crc=crc32_byte(crc,business_request[j]);
            crc=~crc;
            for(j=0;j<4;j=j+1) business_request[size-4+j]=crc>>(8*j);
            for(offset=0;offset<size;offset=offset+14) begin
                wait_idle();count=size-offset>14 ? 14 : size-offset;
                controller_payload[8]=write_command ? 8'h52 : 8'h12;controller_payload[9]=13;controller_payload[10]=0;
                controller_payload[11]=8'hb1;controller_payload[12]=business_token;controller_payload[13]=0;
                controller_payload[14]=offset/14;
                controller_payload[15]=(offset==0 ? 1 : 0) | (offset+count==size ? 2 : 0);
                controller_payload[16]=count;
                for(j=0;j<count;j=j+1) controller_payload[17+j]=business_request[offset+j];
                att_expected_length=1;att_expected[0]=8'h13;send_att(9+count);
            end
            business_token=business_token+1;
            wait(business_complete);wait_idle();
        end
    endtask
    initial begin : stimulus
        wrong_rom=$test$plusargs("wrong_rom");bad_fast=$test$plusargs("bad_fast");write_command=$test$plusargs("write_command");
        bad_rand=$test$plusargs("bad_rand");zero_rand=$test$plusargs("zero_rand");
        fd=$fopen("firmware/rtl8723ds_fw.bin","rb");
        if(!fd) $fatal(1,"Cannot open original firmware binary");
        amount=$fread(firmware,fd); $fclose(fd);
        if(amount!=48988) $fatal(1,"Original firmware binary size mismatch");
        fd=$fopen("firmware/rtl8723ds_config.bin","rb");
        if(!fd) $fatal(1,"Cannot open original configuration binary");
        amount=$fread(config_bytes,fd); $fclose(fd);
        if(amount!=47) $fatal(1,"Original configuration binary size mismatch");
        cfg_at=6;
        while(cfg_at<47) begin
            cfg_size=config_bytes[cfg_at+2];
            if({config_bytes[cfg_at+1],config_bytes[cfg_at]}=='h0c) begin
                config_bytes[cfg_at+3]='h14; config_bytes[cfg_at+4]='hc0;
                config_bytes[cfg_at+5]='h52; config_bytes[cfg_at+6]='h02;
                config_bytes[cfg_at+15]=config_bytes[cfg_at+15]&'hfb;
            end
            cfg_at=cfg_at+3+cfg_size;
        end
        repeat(5) @(posedge clk);
        @(negedge clk); resetn=1; enable=1;
        if(wrong_rom) begin
            wait(failed); #2000;
            if(command_number!=2 || patch_fragments!=0 || initialized)
                $fatal(1,"Wrong ROM must fail before patch/configuration");
            test_passed=1;
            $display("PASS: pure Verilog system rejects incompatible ROM before download");
            $finish;
        end
        wait(initialized || failed);
        if(bad_fast) begin
            if(!failed || initialized || baud_switched || command_number!=6 || debug[23*32+:32]!=115200)
                $fatal(1,"Rejected baud command must fail closed at original rate");
            $display("PASS: rejected UART baud command fails closed");$finish;
        end
        if(bad_rand || zero_rand) begin
            if(!failed || initialized || command_number!=14) $fatal(1,"Bad LE Rand must prevent advertising/session");
            $display("PASS: unavailable/zero HCI LE Rand fails closed");$finish;
        end
        if(failed) $fatal(1,"BLE bootstrap failed debug=%h",debug);
        if(baud_switched!=RUN_FAST || debug[23*32+:32]!=(RUN_FAST ? 921600 : 115200))
            $fatal(1,"UART rate switch missing or unexpected");
        if(command_number!=16 || patch_position!=MODEL_PATCH_BYTES || patch_fragments!=(MODEL_PATCH_BYTES/252+1))
            $fatal(1,"Incomplete HCI/patch initialization");
        $display("INIT_PASS: all %0d patch bytes and %0d fragment echoes checked",MODEL_PATCH_BYTES,patch_fragments);
        send_connection();
        // MTU request/response.
        controller_payload[8]=2; controller_payload[9]='h05; controller_payload[10]=2;
        att_expected_length=3; att_expected[0]=3; att_expected[1]=247; att_expected[2]=0;
        send_att(3);
        // Windows Find By Type Value for GAP.
        controller_payload[8]=6; controller_payload[9]=1; controller_payload[10]=0;
        controller_payload[11]='hff; controller_payload[12]='hff;
        controller_payload[13]=0; controller_payload[14]='h28;
        controller_payload[15]=0; controller_payload[16]='h18;
        att_expected_length=5; att_expected[0]=7; att_expected[1]=1;
        att_expected[2]=0; att_expected[3]=3; att_expected[4]=0;
        send_att(9);
        // Primary service discovery, three nonoverlapping groups.
        controller_payload[8]='h10; controller_payload[9]=1; controller_payload[10]=0;
        controller_payload[11]='hff; controller_payload[12]='hff;
        controller_payload[13]=0; controller_payload[14]='h28;
        att_expected_length=20; att_expected[0]='h11; att_expected[1]=6;
        att_expected[2]=1; att_expected[3]=0; att_expected[4]=3; att_expected[5]=0;
        att_expected[6]=0; att_expected[7]='h18;
        att_expected[8]=4; att_expected[9]=0; att_expected[10]=4; att_expected[11]=0;
        att_expected[12]=1; att_expected[13]='h18;
        att_expected[14]=5; att_expected[15]=0; att_expected[16]=8; att_expected[17]=0;
        att_expected[18]='hf0; att_expected[19]='hff;
        send_att(7);
        // Notify characteristic declaration.
        controller_payload[8]=8; controller_payload[9]=5; controller_payload[10]=0;
        controller_payload[11]=8; controller_payload[12]=0;
        controller_payload[13]=3; controller_payload[14]='h28;
        att_expected_length=9; att_expected[0]=9; att_expected[1]=7;
        att_expected[2]=6; att_expected[3]=0; att_expected[4]='h12;
        att_expected[5]=7; att_expected[6]=0; att_expected[7]='hf1; att_expected[8]='hff;
        send_att(7);
        // CCCD discovery.
        controller_payload[8]=4; controller_payload[9]=8; controller_payload[10]=0;
        controller_payload[11]=8; controller_payload[12]=0;
        att_expected_length=6; att_expected[0]=5; att_expected[1]=1;
        att_expected[2]=8; att_expected[3]=0; att_expected[4]=2; att_expected[5]='h29;
        send_att(5);
        // Reject unsupported CCCD indications.
        controller_payload[8]='h12; controller_payload[9]=8; controller_payload[10]=0;
        controller_payload[11]=2; controller_payload[12]=0;
        att_expected_length=5; att_expected[0]=1; att_expected[1]='h12;
        att_expected[2]=8; att_expected[3]=0; att_expected[4]='h0d;
        send_att(5);
        if(subscribed) $fatal(1,"Invalid CCCD value subscribed");
        // Enable notifications.
        controller_payload[8]='h12; controller_payload[9]=8; controller_payload[10]=0;
        controller_payload[11]=1; controller_payload[12]=0;
        att_expected_length=1; att_expected[0]='h13;
        send_att(5);
        wait(notification_count>=3);
        if(!subscribed || !connected || failed) $fatal(1,"BLE app state mismatch");
        // Stop legacy notifications before business command traffic.
        wait_idle();controller_payload[8]=8'h12;controller_payload[9]=8;controller_payload[10]=0;
        controller_payload[11]=0;controller_payload[12]=0;att_expected_length=1;att_expected[0]=8'h13;send_att(5);
        // Discover the 128-bit primary service after legacy handles 1..8.
        controller_payload[8]=8'h10;controller_payload[9]=9;controller_payload[10]=0;
        controller_payload[11]=8'hff;controller_payload[12]=8'hff;
        controller_payload[13]=0;controller_payload[14]=8'h28;
        att_expected_length=22;att_expected[0]=8'h11;att_expected[1]=20;
        att_expected[2]=9;att_expected[3]=0;att_expected[4]=22;att_expected[5]=0;
        for(n=0;n<16;n=n+1) att_expected[6+n]=setup_parameter(11,n+6);
        send_att(7);
        // Enable Response CCCD, then HELLO and GET_STATUS over real H5/UART.
        controller_payload[8]=8'h12;controller_payload[9]=16;controller_payload[10]=0;
        controller_payload[11]=1;controller_payload[12]=0;att_expected_length=1;att_expected[0]=8'h13;send_att(5);
        business_command(1,1,64'h1020304050607080);
        business_command(2,2,64'h1020304050607080);
        // Disconnect must re-enable advertising without resetting the module.
        wait_idle();controller_payload[0]=5;controller_payload[1]=4;controller_payload[2]=0;
        controller_payload[3]=16;controller_payload[4]=0;controller_payload[5]=8'h13;
        controller_type=4;controller_length=6;controller_pending=1;
        wait(command_number==17);wait_idle();
        send_connection();business_response_token=1;business_token=1;
        controller_payload[8]=8'h12;controller_payload[9]=16;controller_payload[10]=0;
        controller_payload[11]=1;controller_payload[12]=0;att_expected_length=1;att_expected[0]=8'h13;send_att(5);
        business_command(1,1,64'h8877665544332211);
        // Transfer CCCD requests a faster link using the real UART/H5 path.
        controller_payload[8]=8'h12;controller_payload[9]=22;controller_payload[10]=0;
        controller_payload[11]=1;controller_payload[12]=0;att_expected_length=1;att_expected[0]=8'h13;send_att(5);
        wait(fast_link_requested);wait_idle();
        enable=0; repeat(10) @(posedge clk); #1;
        if(outputs_active || bt_enable) $fatal(1,"Disable did not release active controls");
        test_passed=1;
        $display("PASS: protocol UART8E1/H5 checked patch, LE Rand, 128-bit service, HELLO/GET_STATUS fragmented responses, disconnect advertising/reconnect; legacy %0d notifications",notification_count);
        $finish;
    end
    initial begin
        #1200000000;
        $fatal(1,"Pure Verilog system simulation watchdog debug=%h",debug);
    end
endmodule
