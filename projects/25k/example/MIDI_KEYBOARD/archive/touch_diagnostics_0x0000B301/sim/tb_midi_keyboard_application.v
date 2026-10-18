`timescale 1ns/1ps
module tb_midi_keyboard_application;
    reg clk=0;always #10 clk=~clk;
    reg reset=1,control_reset=0,usb_online=0,ble_online=0;
    reg [15:0] key_bitmap=0;
    reg keypad_ready=1,slider_valid=0,slider_touch=0;
    reg [7:0] slider_position=0;
    reg enc1_step=0,enc1_press=0,enc2_step=0,enc2_press=0;
    reg signed [1:0] enc1_direction=1,enc2_direction=1;
    wire usb_packet_tx_valid;reg usb_packet_tx_ready=1;wire [31:0] usb_packet_tx_data;
    reg usb_packet_rx_valid=0;wire usb_packet_rx_ready;reg [31:0] usb_packet_rx_data=0;
    wire ble_value_tx_valid;reg ble_value_tx_ready=1;wire [39:0] ble_value_tx_data;
    wire [2:0] ble_value_tx_length;
    reg ble_value_rx_valid=0;wire ble_value_rx_ready;reg [39:0] ble_value_rx_data=0;
    reg [2:0] ble_value_rx_length=0;
    reg control_rx_valid=0;wire control_rx_ready;reg [7:0] control_rx_data=0;
    wire control_tx_valid;reg control_tx_ready=0;wire [7:0] control_tx_data;
    reg [255:0] touch_diagnostics =
        256'hffffffff_80000000_12345678_abcdef01_00000008_00000007_00000001_00000000;
    wire slider_scan_pause;
    wire [3:0] midi_channel,screen_page;
    wire signed [7:0] transpose;
    wire [6:0] velocity,program_number;
    wire [1:0] slider_mode;
    wire [7:0] brightness,strip_value;
    wire [2:0] focus;
    wire [15:0] active_keys,lamp_keys,theme_rgb565,clear_rgb565;
    wire panic_busy,screen_update;
    wire [31:0] status_flags,emitted_events;
    midi_keyboard_application #(.CLK_HZ(4000),.FIFO_DEPTH(2)) dut(.*);
    reg [23:0] usb_messages[0:4095],ble_messages[0:4095];
    reg [1:0] usb_lengths[0:4095],ble_lengths[0:4095];
    reg [12:0] ble_timestamps[0:4095];
    integer usb_count=0,ble_count=0,screen_updates=0;
    reg voices[0:1][0:15][0:127];
    reg usb_stalled=0,ble_stalled=0;
    reg [31:0] held_usb;
    reg [39:0] held_ble;
    reg [2:0] held_ble_length;
    reg [23:0] decoded;
    integer channel,note,j,link,usb_mark,ble_mark,c,n,i;
    integer sequence_number=0;
    task record_voice(input integer which,input [23:0] message);
        integer a,b;
        begin
            a=message[19:16];b=message[14:8];
            case(message[23:20])
                9:begin
                    if(voices[which][a][b])$fatal(1,"Duplicate external Note On link%0d channel%0d note%0d",which,a,b);
                    voices[which][a][b]=1;
                end
                8:voices[which][a][b]=0;
                11:if(b==120||b==123)for(b=0;b<128;b=b+1)voices[which][a][b]=0;
            endcase
        end
    endtask
    always @(posedge clk) begin
        if(reset)begin usb_stalled=0;ble_stalled=0;end
        else begin
            if(usb_stalled && usb_online && (!usb_packet_tx_valid||usb_packet_tx_data!==held_usb))
                $fatal(1,"USB packet changed while stalled");
            if(ble_stalled && ble_online && (!ble_value_tx_valid||ble_value_tx_data!==held_ble||ble_value_tx_length!==held_ble_length))
                $fatal(1,"BLE value changed while stalled");
            usb_stalled=usb_online&&usb_packet_tx_valid&&!usb_packet_tx_ready;
            ble_stalled=ble_online&&ble_value_tx_valid&&!ble_value_tx_ready;
            held_usb=usb_packet_tx_data;held_ble=ble_value_tx_data;held_ble_length=ble_value_tx_length;
            if(screen_update)screen_updates=screen_updates+1;
            if(usb_packet_tx_valid&&usb_packet_tx_ready)begin
                if(usb_packet_tx_data[7:4]!==0||usb_packet_tx_data[3:0]!==usb_packet_tx_data[15:12])
                    $fatal(1,"Bad USB-MIDI cable/CIN/status %08h",usb_packet_tx_data);
                decoded={usb_packet_tx_data[15:8],usb_packet_tx_data[23:16],usb_packet_tx_data[31:24]};
                if(decoded[15] || decoded[7])$fatal(1,"Invalid USB MIDI data byte");
                usb_messages[usb_count]=decoded;
                usb_lengths[usb_count]=decoded[23:20]==12?2:3;
                usb_count=usb_count+1;record_voice(0,decoded);
            end
            if(ble_value_tx_valid&&ble_value_tx_ready)begin
                if(ble_value_tx_data[7:6]!==2'b10||ble_value_tx_data[15]!==1)
                    $fatal(1,"Bad BLE-MIDI timestamp header %010h",ble_value_tx_data);
                decoded={ble_value_tx_data[23:16],ble_value_tx_data[31:24],ble_value_tx_data[39:32]};
                if(decoded[15]||decoded[7])$fatal(1,"Invalid BLE MIDI data byte");
                if(ble_value_tx_length!==(decoded[23:20]==12?4:5))$fatal(1,"Wrong BLE MIDI length");
                ble_messages[ble_count]=decoded;
                ble_lengths[ble_count]=decoded[23:20]==12?2:3;
                ble_timestamps[ble_count]={ble_value_tx_data[5:0],ble_value_tx_data[14:8]};
                ble_count=ble_count+1;record_voice(1,decoded);
            end
        end
    end
    task ticks(input integer cycles);begin repeat(cycles)@(negedge clk);end endtask
    task drain;
        integer quiet,limit,prior_usb,prior_ble;reg [31:0] prior_emitted;
        begin : draining
            quiet=0;prior_usb=usb_count;prior_ble=ble_count;prior_emitted=emitted_events;
            for(limit=0;limit<4000;limit=limit+1)begin
                @(negedge clk);
                if(!usb_packet_tx_valid&&!ble_value_tx_valid&&!panic_busy&&
                    prior_usb==usb_count&&prior_ble==ble_count&&prior_emitted==emitted_events)quiet=quiet+1;
                else quiet=0;
                prior_usb=usb_count;prior_ble=ble_count;prior_emitted=emitted_events;
                if(quiet==20)disable draining;
            end
            $fatal(1,"Application did not drain usb=%0d ble=%0d active=%h panic=%b flags=%h",usb_count,ble_count,active_keys,panic_busy,status_flags);
        end
    endtask
    task expect_message(input integer which,input integer first,input [23:0] wanted);
        integer index,last;reg found;
        begin
            found=0;last=which?ble_count:usb_count;
            for(index=first;index<last;index=index+1)
                if((which?ble_messages[index]:usb_messages[index])===wanted)found=1;
            if(!found)$fatal(1,"Missing link%0d message%06h since%0d",which,wanted,first);
        end
    endtask
    task check_silent;
        integer a,b,d;
        begin for(a=0;a<2;a=a+1)for(b=0;b<16;b=b+1)for(d=0;d<128;d=d+1)
            if(voices[a][b][d])$fatal(1,"Stuck external voice link%0d channel%0d note%0d",a,b,d);end
    endtask
    function [15:0] crc_byte(input [15:0] crc,input [7:0] value);
        reg [15:0] work;integer bit_index;
        begin
            work=crc^{value,8'd0};
            for(bit_index=0;bit_index<8;bit_index=bit_index+1)
                if(work[15])work=(work<<1)^16'h1021;else work=work<<1;
            crc_byte=work;
        end
    endfunction
    function [15:0] frame_crc(input [127:0] frame);
        reg [15:0] work;integer k;
        begin work=16'hffff;for(k=0;k<14;k=k+1)work=crc_byte(work,frame[k*8+:8]);frame_crc=work;end
    endfunction
    task control_request(input [7:0] opcode,input [31:0] value,input corrupt_crc,input [31:0] expected_status,input [31:0] expected_result);
        reg [127:0] request,response;reg [7:0] held_byte;integer k;
        begin
            sequence_number=sequence_number+1;
            request={16'd0,32'd0,value,sequence_number[15:0],opcode,8'h01,16'h4b4d};
            request[127:112]=frame_crc(request)^(corrupt_crc?16'd1:16'd0);
            for(k=0;k<16;k=k+1)begin
                @(negedge clk);control_rx_valid=1;control_rx_data=request[k*8+:8];
                while(!control_rx_ready)@(negedge clk);
                @(posedge clk);
            end
            @(negedge clk);control_rx_valid=0;
            while(!control_tx_valid)@(negedge clk);
            held_byte=control_tx_data;
            repeat(4)begin @(negedge clk);if(!control_tx_valid||control_tx_data!==held_byte)$fatal(1,"Control response changed under backpressure");end
            response=0;control_tx_ready=1;
            for(k=0;k<16;k=k+1)begin
                @(posedge clk);if(!control_tx_valid)$fatal(1,"Control response truncated");response[k*8+:8]=control_tx_data;
            end
            @(negedge clk);control_tx_ready=0;
            if(response[15:0]!==16'h4b4d||response[23:16]!==1||response[31:24]!==(opcode|8'h80)||
                response[47:32]!==sequence_number[15:0]||response[79:48]!==expected_status||
                response[111:80]!==expected_result||response[127:112]!==frame_crc(response))
                $fatal(1,"Bad control response %032h status/result wanted%0d/%h",response,expected_status,expected_result);
        end
    endtask
    task host_usb(input [23:0] message);
        begin
            @(negedge clk);usb_packet_rx_valid=1;
            usb_packet_rx_data={message[7:0],message[15:8],message[23:16],4'b0,message[23:20]};
            while(!usb_packet_rx_ready)@(negedge clk);
            @(posedge clk);@(negedge clk);usb_packet_rx_valid=0;
        end
    endtask
    task host_ble(input [23:0] message);
        begin
            @(negedge clk);ble_value_rx_valid=1;ble_value_rx_length=5;
            ble_value_rx_data={message[7:0],message[15:8],message[23:16],8'h80,8'h80};
            while(!ble_value_rx_ready)@(negedge clk);
            @(posedge clk);@(negedge clk);ble_value_rx_valid=0;
        end
    endtask
    task expect_lamps(input [15:0] expected);
        begin ticks(8);if(lamp_keys!==expected)$fatal(1,"Lamp ownership %04h expected%04h",lamp_keys,expected);end
    endtask
    integer prior_emitted;
    initial begin
        for(link=0;link<2;link=link+1)for(c=0;c<16;c=c+1)for(n=0;n<128;n=n+1)voices[link][c][n]=0;
        ticks(5);reset=0;usb_online=1;ble_online=1;drain();
        if(midi_channel!==0||transpose!==0||status_flags[1:0]!==3)$fatal(1,"Application defaults/online status wrong");
        usb_mark=usb_count;ble_mark=ble_count;key_bitmap=16'hffff;drain();
        if(active_keys!==16'hffff||usb_count-usb_mark!=16||ble_count-ble_mark!=16)$fatal(1,"Application lost simultaneous keys");
        for(i=0;i<16;i=i+1)begin
            expect_message(0,usb_mark,{8'h90,8'd48+i[7:0],8'd100});
            expect_message(1,ble_mark,{8'h90,8'd48+i[7:0],8'd100});
        end
        control_request(8'h10,4,0,0,4);control_request(8'h11,32'hfffffff4,0,0,32'hfffffff4);
        if(midi_channel!==4||transpose!==-12)$fatal(1,"Screen configuration did not reach performance engine");
        key_bitmap=0;drain();
        for(i=0;i<16;i=i+1)begin
            expect_message(0,usb_mark,{8'h80,8'd48+i[7:0],8'd0});
            expect_message(1,ble_mark,{8'h80,8'd48+i[7:0],8'd0});
        end
        check_silent();usb_mark=usb_count;ble_mark=ble_count;
        key_bitmap=16'h8001;drain();
        expect_message(0,usb_mark,24'h942464);expect_message(0,usb_mark,24'h943364);
        expect_message(1,ble_mark,24'h942464);expect_message(1,ble_mark,24'h943364);
        key_bitmap=0;drain();check_silent();
        control_request(8'h20,3,0,0,3);control_request(8'h21,32'hf81f,0,0,32'hf81f);control_request(8'h22,32'h001f,0,0,32'h001f);
        if(screen_page!==3||theme_rgb565!==16'hf81f||clear_rgb565!==16'h001f||screen_updates!=3)$fatal(1,"Screen configuration/update pulse integration failed");
        control_request(8'h11,49,0,2,0);control_request(8'h10,7,1,3,0);
        if(midi_channel!==4||transpose!==-12)$fatal(1,"Rejected control changed MIDI settings");
        // USB diagnostics are separate from musical configuration. A requested
        // U2 pause must not suppress any local keys, including physical G/H.
        usb_mark=usb_count;ble_mark=ble_count;prior_emitted=emitted_events;
        for(i=0;i<8;i=i+1)control_request(8'h02,i,0,0,touch_diagnostics[i*32+:32]);
        control_request(8'h12,1,0,0,1);
        control_request(8'h12,0,1,3,0);
        control_request(8'h12,2,0,2,0);
        control_request(8'h02,8,0,2,0);
        if(!slider_scan_pause||usb_count!=usb_mark||ble_count!=ble_mark||emitted_events!=prior_emitted||
            midi_channel!==4||transpose!==-12||screen_page!==3||theme_rgb565!==16'hf81f||
            clear_rgb565!==16'h001f||screen_updates!=3)$fatal(1,"Diagnostic/test request changed performance or screen state");
        key_bitmap=16'h00c0;drain();
        if(active_keys!==16'h00c0)$fatal(1,"Diagnostic pause masked G/H keys");
        expect_message(0,usb_mark,24'h942a64);expect_message(0,usb_mark,24'h942b64);
        expect_message(1,ble_mark,24'h942a64);expect_message(1,ble_mark,24'h942b64);
        key_bitmap=0;drain();check_silent();
        control_request(8'h12,0,0,0,0);
        if(slider_scan_pause)$fatal(1,"Normal acquisition request did not clear pause");
        control_request(8'h10,2,0,0,2);control_request(8'h11,0,0,0,0);drain();
        // Both real decoder RX slots become valid together. Neither event may
        // be lost, and inbound MIDI must update lights without being echoed.
        usb_mark=usb_count;ble_mark=ble_count;
        fork host_usb(24'h923064);host_ble(24'h923164);join
        expect_lamps(16'h0003);
        host_usb(24'h823000);expect_lamps(16'h0002);
        host_ble(24'h923100);expect_lamps(0);
        // Each transport owns its own note state. One host's release must not
        // extinguish a note which the other host still holds.
        fork host_usb(24'h923264);host_ble(24'h923264);join
        expect_lamps(4);host_usb(24'h823200);expect_lamps(4);host_ble(24'h823200);expect_lamps(0);
        fork host_usb(24'h923064);host_ble(24'h923164);join
        expect_lamps(3);host_usb(24'hb27b00);expect_lamps(2);
        host_ble(24'hb27800);expect_lamps(0);
        host_usb(24'h933064);host_ble(24'h921064);expect_lamps(0);
        if(usb_count!=usb_mark||ble_count!=ble_mark)$fatal(1,"Host lamp feedback was echoed into MIDI outputs");
        // Link loss clears only that link's lamp ownership.
        fork host_usb(24'h923064);host_ble(24'h923164);join
        expect_lamps(3);usb_online=0;expect_lamps(2);
        usb_online=1;drain();expect_lamps(2);host_ble(24'h823100);expect_lamps(0);
        // Exhaust both tiny FIFOs while the USB/BLE packet slots are stalled.
        usb_packet_tx_ready=0;ble_value_tx_ready=0;key_bitmap=16'hffff;ticks(60);
        if(!usb_packet_tx_valid||!ble_value_tx_valid||status_flags[3:2]!==3)$fatal(1,"Expected real packet/FIFO backpressure");
        prior_emitted=emitted_events;ticks(10);
        if(emitted_events!=prior_emitted)$fatal(1,"Full router did not backpressure performance");
        control_request(8'h20,6,0,0,6);
        if(screen_page!==6||!usb_packet_tx_valid||!ble_value_tx_valid)$fatal(1,"Control path must remain usable during MIDI congestion");
        key_bitmap=0;usb_packet_tx_ready=1;ble_value_tx_ready=1;drain();
        if(active_keys!==0)$fatal(1,"Rapid release under backpressure left logical notes");check_silent();
        // Discard old-session queued messages, then recover only currently held
        // notes after per-channel panic. Old unsent notes must not leak through.
        usb_packet_tx_ready=0;ble_value_tx_ready=0;key_bitmap=3;
        wait(usb_packet_tx_valid&&ble_value_tx_valid);ticks(8);key_bitmap=4;
        usb_online=0;ble_online=0;#1;
        if(usb_packet_tx_valid||ble_value_tx_valid||usb_packet_rx_ready||ble_value_rx_ready)$fatal(1,"Offline ports not gated immediately");
        ticks(6);usb_packet_tx_ready=1;ble_value_tx_ready=1;drain();
        if(active_keys!==4)$fatal(1,"Offline current-key state was lost");
        usb_mark=usb_count;ble_mark=ble_count;usb_online=1;ble_online=1;drain();
        expect_message(0,usb_mark,24'h923264);expect_message(1,ble_mark,24'h923264);
        for(i=usb_mark;i<usb_count;i=i+1)if(usb_messages[i][23:20]==9&&usb_messages[i]!==24'h923264)$fatal(1,"USB reconnect emitted stale Note On %06h",usb_messages[i]);
        for(i=ble_mark;i<ble_count;i=i+1)if(ble_messages[i][23:20]==9&&ble_messages[i]!==24'h923264)$fatal(1,"BLE reconnect emitted stale Note On %06h",ble_messages[i]);
        for(c=0;c<16;c=c+1)begin
            expect_message(0,usb_mark,{4'hb,c[3:0],8'd120,8'd0});expect_message(0,usb_mark,{4'hb,c[3:0],8'd123,8'd0});expect_message(0,usb_mark,{4'he,c[3:0],8'd0,8'd64});
            expect_message(1,ble_mark,{4'hb,c[3:0],8'd120,8'd0});expect_message(1,ble_mark,{4'hb,c[3:0],8'd123,8'd0});expect_message(1,ble_mark,{4'he,c[3:0],8'd0,8'd64});
        end
        key_bitmap=0;drain();check_silent();
        if(status_flags[11:8]!==0)$fatal(1,"Generated/decoded MIDI protocol errors %h",status_flags);
        // Abort a partial vendor request without disturbing performance state.
        control_request(8'h12,1,0,0,1);
        @(negedge clk);control_rx_valid=1;control_rx_data=8'h4d;
        @(negedge clk);control_rx_data=8'h4b;
        @(negedge clk);control_rx_valid=0;control_reset=1;ticks(2);control_reset=0;ticks(2);
        if(!control_rx_ready||screen_page!==0||midi_channel!==2||transpose!==0||slider_scan_pause)$fatal(1,"Control session reset was not isolated from performance or failed to resume acquisition");
        control_request(8'h20,1,0,0,1);
        $display("PASS application: actual USB/BLE packets for 16 keys, host control CRC/settings, held mapping, RX lamp arbitration and per-link ownership, no echo, MIDI backpressure/control independence, disconnect cleanup and current-note replay");
        $finish;
    end
    initial begin #1_000_000;$fatal(1,"Application timeout usb=%0d ble=%0d lamps=%h active=%h flags=%h",usb_count,ble_count,lamp_keys,active_keys,status_flags);end
endmodule
