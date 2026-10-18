`timescale 1ns/1ps

// Independent RTL8723DS controller model at the physical UART boundary.
// Expected RAM image is reconstructed from the original vendor binaries,
// never from the DUT ROM. The model checks every downloaded byte and HCI
// parameter, then exercises ATT discovery, CCCD and notification integrity.
module tb_ble_board_system;
    reg clk=0, resetn=0, enable=0, uart_rx=1;
    wire uart_tx, bt_enable, outputs_active, initialized, failed;
    wire connected, subscribed;
    wire [767:0] debug;
    reg test_passed=0;
    localparam [127:0] service_uuid=128'h03b80e5aede84b33a7516ce34ec4c700;
    localparam [127:0] characteristic_uuid=128'h7772e5db38684112a1a9f2669d106bf3;
    localparam CLK_HZ=1152000, BAUD=115200;
    localparam BIT_NS=100;
    wire online, value_tx_ready, value_rx_valid;
    reg value_tx_valid=0,value_rx_ready=0;
    reg [39:0] value_tx_data=0;
    reg [2:0] value_tx_length=5;
    wire [39:0] value_rx_data;
    wire [2:0] value_rx_length;
    midi_ble_link #(.CLK_HZ(CLK_HZ),.BAUD(BAUD),
        .STARTUP_MS(2), .DISABLE_MS(1),
        .PATCH_FILE("rtl/ble_board/rtl8723ds_patch.mem")) dut (
        .clk(clk),.reset(!resetn),.module_uart_tx(uart_rx),
        .module_uart_rx(uart_tx),.module_bt_dis_n(bt_enable),
        .initialized(initialized),.failed(failed),.online(online),
        .value_tx_valid(value_tx_valid),.value_tx_ready(value_tx_ready),
        .value_tx_data(value_tx_data),.value_tx_length(value_tx_length),
        .value_rx_valid(value_rx_valid),.value_rx_ready(value_rx_ready),
        .value_rx_data(value_rx_data),.value_rx_length(value_rx_length));
    assign connected=dut.application.connected;
    assign subscribed=dut.application.subscribed;
    assign debug=0;
    assign outputs_active=bt_enable;
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
    reg [39:0] expected_value=0;
    integer expected_value_length=5;
    integer att_expected_length=0, att_waiting=0;
    integer expected_opcode, expected_parameters, parameter_at;
    integer payload_length, packet_type, opcode, fragment_size, index;
    integer crc_check, last_notification_seq=-1;
    integer wrong_rom=0;
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
                11: case(at)
                    0:setup_parameter=31;1:setup_parameter=2;2:setup_parameter=1;3:setup_parameter=6;
                    4:setup_parameter=17;5:setup_parameter=7;
                    6:setup_parameter='h00;7:setup_parameter='hc7;8:setup_parameter='hc4;
                    9:setup_parameter='h4e;10:setup_parameter='he3;11:setup_parameter='h6c;
                    12:setup_parameter='h51;13:setup_parameter='ha7;14:setup_parameter='h33;
                    15:setup_parameter='h4b;16:setup_parameter='he8;17:setup_parameter='hed;
                    18:setup_parameter='h5a;19:setup_parameter='h0e;20:setup_parameter='hb8;
                    21:setup_parameter='h03;22:setup_parameter=9;23:setup_parameter=9;
                    24:setup_parameter="G";25:setup_parameter="W";26:setup_parameter="K";
                    27:setup_parameter="-";28:setup_parameter="M";29:setup_parameter="I";
                    30:setup_parameter="D";31:setup_parameter="I";
                endcase
                12,13: if(at==0) setup_parameter=1;
            endcase
        end
    endfunction
    task uart_send;
        input [7:0] data;
        integer k;
        reg parity;
        begin
            parity=0;
            uart_rx=0; #BIT_NS;
            for(k=0;k<8;k=k+1) begin
                uart_rx=data[k]; parity=parity^data[k]; #BIT_NS;
            end
            uart_rx=parity; #BIT_NS;
            uart_rx=1; #BIT_NS;
        end
    endtask
    task uart_receive;
        output [7:0] data;
        integer k;
        reg parity;
        begin
            @(negedge uart_tx);
            #(BIT_NS/2);
            if(uart_tx!==0) $fatal(1,"UART start glitch");
            parity=0;
            for(k=0;k<8;k=k+1) begin
                #BIT_NS; data[k]=uart_tx; parity=parity^uart_tx;
            end
            #BIT_NS;
            if(uart_tx!==parity) $fatal(1,"UART even parity mismatch");
            #BIT_NS;
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
                if(controller_acked_seq!=controller_next_seq &&
                   !(controller_busy && controller_acked_seq==((controller_next_seq+7)&7)))
                    $fatal(1,"Host ACK sequence mismatch got%0d expected%0d",controller_acked_seq,controller_next_seq);
            end else if(packet_type==1 || packet_type==2) begin
                seq=host_frame[0]&7;
                if(!host_frame[0][7] || seq!=host_next_seq)
                    $fatal(1,"Host reliable sequence mismatch got%0d expected%0d",seq,host_next_seq);
                if(((host_frame[0]>>3)&7)!=controller_next_seq)
                    $fatal(1,"Host piggyback ACK sequence mismatch");
                controller_acked_seq=(host_frame[0]>>3)&7;
                host_next_seq=(host_next_seq+1)&7;
                if(packet_type==1) begin
                    opcode=host_frame[4]+(host_frame[5]<<8);
                    if(payload_length<3 || host_frame[6]+3!=payload_length)
                        $fatal(1,"HCI command length mismatch");
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
                        12,13:begin expected_opcode='h200a; expected_parameters=1; end
                        default:$fatal(1,"Unexpected command after bootstrap %h",opcode);
                    endcase
                    if(opcode!=expected_opcode) $fatal(1,"HCI opcode got%h expected%h step%0d",opcode,expected_opcode,command_number);
                    if(opcode=='hfc20) begin
                        fragment_size=30147-patch_position;
                        if(fragment_size>252) fragment_size=252;
                        index=patch_fragments | (fragment_size<252 ? 'h80 : 0);
                        if(host_frame[6]!=fragment_size+1 || host_frame[7]!=index)
                            $fatal(1,"Patch fragment header mismatch at%0d",patch_position);
                        for(k=0;k<fragment_size;k=k+1)
                            if(host_frame[k+8]!==patch_byte(patch_position+k))
                                $fatal(1,"Patch byte mismatch at%0d got%h expected%h",patch_position+k,host_frame[k+8],patch_byte(patch_position+k));
                        patch_position=patch_position+fragment_size;
                        patch_fragments=patch_fragments+1;
                        if(fragment_size<252) command_number=command_number+1;
                    end else begin
                        if(host_frame[6]!=expected_parameters) $fatal(1,"HCI parameter count mismatch");
                        for(k=0;k<expected_parameters;k=k+1)
                            if(host_frame[k+7]!==setup_parameter(command_number,k))
                                $fatal(1,"HCI setup parameter mismatch step%0d byte%0d",command_number,k);
                        command_number=command_number+1;
                    end
                    command_response(opcode);
                end else begin
                    acl_packets=acl_packets+1;
                    if(payload_length<8 || {host_frame[5],host_frame[4]}!=16 ||
                       {host_frame[7],host_frame[6]}!=payload_length-4 ||
                       {host_frame[9],host_frame[8]}!=payload_length-8 ||
                       {host_frame[11],host_frame[10]}!=4)
                        $fatal(1,"ACL/L2CAP framing or PB bits mismatch");
                    if(host_frame[12]=='h1b) begin
                        if(payload_length!=11+expected_value_length || host_frame[13]!=7 || host_frame[14]!=0)
                            $fatal(1,"Notification handle or length mismatch");
                        for(k=0;k<expected_value_length;k=k+1)
                            if(host_frame[15+k]!==expected_value[k*8+:8])
                                $fatal(1,"MIDI notification value mismatch byte %0d",k);
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
            #BIT_NS;
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
            att_waiting=1; controller_pending=1;
            wait(!att_waiting); wait_idle();
        end
    endtask
    initial begin : stimulus
        wrong_rom=$test$plusargs("wrong_rom");
        fd=$fopen("../RTL8723DS_BLE/vendor/rtl8723ds_ble/firmware/rtl8723ds_fw.bin","rb");
        if(!fd) $fatal(1,"Cannot open original firmware binary");
        amount=$fread(firmware,fd); $fclose(fd);
        if(amount!=48988) $fatal(1,"Original firmware binary size mismatch");
        fd=$fopen("../RTL8723DS_BLE/vendor/rtl8723ds_ble/firmware/rtl8723ds_config.bin","rb");
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
        if(failed) $fatal(1,"BLE bootstrap failed debug=%h",debug);
        if(command_number!=13 || patch_position!=30147 || patch_fragments!=120)
            $fatal(1,"Incomplete HCI/patch initialization");
        $display("INIT_PASS: all30147patch bytes and120fragment echoes checked");
        send_connection();
        // MTU request/response.
        controller_payload[8]=2; controller_payload[9]='h05; controller_payload[10]=2;
        att_expected_length=3; att_expected[0]=3; att_expected[1]=23; att_expected[2]=0;
        send_att(3);
        // Primary services: mixed UUID widths require two replies.
        controller_payload[8]='h10; controller_payload[9]=1;controller_payload[10]=0;
        controller_payload[11]='hff;controller_payload[12]='hff;controller_payload[13]=0;controller_payload[14]='h28;
        att_expected_length=14;att_expected[0]='h11;att_expected[1]=6;
        att_expected[2]=1;att_expected[3]=0;att_expected[4]=3;att_expected[5]=0;
        att_expected[6]=0;att_expected[7]='h18;att_expected[8]=4;att_expected[9]=0;
        att_expected[10]=4;att_expected[11]=0;att_expected[12]=1;att_expected[13]='h18;
        send_att(7);
        controller_payload[9]=5;
        att_expected_length=22;att_expected[0]='h11;att_expected[1]=20;
        att_expected[2]=5;att_expected[3]=0;att_expected[4]=8;att_expected[5]=0;
        for(i=0;i<16;i=i+1) att_expected[6+i]=service_uuid[i*8+:8];
        send_att(7);
        // Find By Type Value with full 128-bit MIDI UUID.
        controller_payload[8]=6;controller_payload[9]=1;controller_payload[10]=0;
        controller_payload[11]='hff;controller_payload[12]='hff;controller_payload[13]=0;controller_payload[14]='h28;
        for(i=0;i<16;i=i+1) controller_payload[15+i]=service_uuid[i*8+:8];
        att_expected_length=5;att_expected[0]=7;att_expected[1]=5;att_expected[2]=0;
        att_expected[3]=8;att_expected[4]=0;send_att(23);
        // Characteristic declaration carries Read / WriteWithoutResponse / Notify.
        controller_payload[8]=8;controller_payload[9]=5;controller_payload[10]=0;
        controller_payload[11]=8;controller_payload[12]=0;controller_payload[13]=3;controller_payload[14]='h28;
        att_expected_length=23;att_expected[0]=9;att_expected[1]=21;att_expected[2]=6;
        att_expected[3]=0;att_expected[4]='h16;att_expected[5]=7;att_expected[6]=0;
        for(i=0;i<16;i=i+1) att_expected[7+i]=characteristic_uuid[i*8+:8];send_att(7);
        // FindInformation returns the 128-bit characteristic, then CCCD separately.
        controller_payload[8]=4;controller_payload[9]=7;controller_payload[10]=0;
        controller_payload[11]=8;controller_payload[12]=0;
        att_expected_length=20;att_expected[0]=5;att_expected[1]=2;att_expected[2]=7;att_expected[3]=0;
        for(i=0;i<16;i=i+1) att_expected[4+i]=characteristic_uuid[i*8+:8];send_att(5);
        controller_payload[9]=8;att_expected_length=6;att_expected[1]=1;
        att_expected[2]=8;att_expected[3]=0;att_expected[4]=2;att_expected[5]='h29;send_att(5);
        if(online || value_tx_ready) $fatal(1,"Unsubscribed link must apply backpressure");
        // Reject indication-only CCCD, then enable notifications.
        controller_payload[8]='h12;controller_payload[9]=8;controller_payload[10]=0;
        controller_payload[11]=2;controller_payload[12]=0;
        att_expected_length=5;att_expected[0]=1;att_expected[1]='h12;
        att_expected[2]=8;att_expected[3]=0;att_expected[4]='h0d;send_att(5);
        if(online) $fatal(1,"Invalid CCCD enabled online");
        subscribe_midi();
        // Application accepts opaque three, four and five-byte codec values.
        send_value(40'h0000f8c080,3);
        send_value(40'h00c000c180,4);
        send_value(40'h7f3c90db80,5);
        // ATT Read returns the current characteristic value.
        controller_payload[8]='h0a;controller_payload[9]=7;controller_payload[10]=0;
        att_expected_length=6;att_expected[0]='h0b;
        for(i=0;i<5;i=i+1) att_expected[i+1]=expected_value[i*8+:8];send_att(3);
        // Hold RX ready low. A second write must wait without changing output.
        send_write(40'h403c908180,5);wait(value_rx_valid);
        if(value_rx_length!=5 || value_rx_data!==40'h403c908180) $fatal(1,"First MIDI write mismatch");
        send_write(40'h0000f88280,3);repeat(100) @(posedge clk);
        if(!value_rx_valid || value_rx_data!==40'h403c908180) $fatal(1,"RX changed under backpressure");
        @(negedge clk);value_rx_ready=1;@(negedge clk);value_rx_ready=0;
        wait(value_rx_valid && value_rx_length==3);
        if(value_rx_data[23:0]!==24'hf88280) $fatal(1,"Buffered second write mismatch");
        @(negedge clk);value_rx_ready=1;@(negedge clk);value_rx_ready=0;
        // Disconnect must send a real HCI advertising-enable command.
        wait_idle();controller_type=4;controller_length=6;
        controller_payload[0]=5;controller_payload[1]=4;controller_payload[2]=0;
        controller_payload[3]=16;controller_payload[4]=0;controller_payload[5]='h13;controller_pending=1;
        wait(!connected);#1;if(online || value_tx_ready) $fatal(1,"Disconnected online");
        wait(command_number==14);wait_idle();send_connection();
        if(online) $fatal(1,"CCCD leaked across connections");subscribe_midi();send_value(40'h003c808380,5);
        // No 180 second demo timeout: advance the uptime counter and keep sending.
        force dut.uptime_ms=200000;repeat(20) @(posedge clk);release dut.uptime_ms;
        send_value(40'h0000f88480,3);
        if(failed || !online || !bt_enable) $fatal(1,"Continuous session failed");
        // Reset must pulse BT_DIS# low and restart H5 + all HCI setup from step zero.
        wait_idle();@(negedge clk);resetn=0;repeat(5) @(posedge clk);
        if(bt_enable || online || initialized) $fatal(1,"Reset did not clear controller state");
        command_number=0;patch_fragments=0;patch_position=0;host_next_seq=0;controller_next_seq=0;
        controller_acked_seq=0;host_used=0;collecting=0;escaped=0;
        @(negedge clk);resetn=1;
        wait(patch_fragments==1);if(command_number!=4) $fatal(1,"Reset did not restart patch sequence");
        test_passed=1;
        $display("PASS: BLE MIDI UART8E1/H5 full ROM-v2 patch, UUID discovery, 3..5-byte notify/read/write, RX backpressure, reconnect advertising, continuous session, reset");
        $finish;
    end
    task subscribe_midi;
        begin
            controller_payload[8]='h12;controller_payload[9]=8;controller_payload[10]=0;
            controller_payload[11]=1;controller_payload[12]=0;
            att_expected_length=1;att_expected[0]='h13;send_att(5);
            if(!online) $fatal(1,"CCCD did not enable online");
        end
    endtask
    task send_value;
        input [39:0] data;input integer length;
        integer target_count;
        begin
            expected_value=data;expected_value_length=length;target_count=notification_count+1;
            @(negedge clk);value_tx_data=data;value_tx_length=length;value_tx_valid=1;
            while(!value_tx_ready) @(negedge clk);
            @(negedge clk);value_tx_valid=0;
            wait(notification_count==target_count);wait_idle();
        end
    endtask
    task send_write;
        input [39:0] data;input integer length;
        integer k;
        begin
            wait_idle();controller_payload[0]=16;controller_payload[1]=0;
            controller_payload[2]=length+7;controller_payload[3]=0;
            controller_payload[4]=length+3;controller_payload[5]=0;
            controller_payload[6]=4;controller_payload[7]=0;controller_payload[8]='h52;
            controller_payload[9]=7;controller_payload[10]=0;
            for(k=0;k<length;k=k+1) controller_payload[11+k]=data[k*8+:8];
            controller_type=2;controller_length=length+11;controller_pending=1;wait_idle();
        end
    endtask
    initial begin
        #150000000;
        $fatal(1,"Pure Verilog system simulation watchdog debug=%h",debug);
    end
endmodule
