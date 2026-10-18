`timescale 1ns/1ps
// USB host BFM: independent NRZI/bit stuffing and CRC5/CRC16, physical D+/D-.
// Models the required external D+ pull-up. Bypasses ONLY the 2s attach counter.
module tb_usb1_cdc_loopback;
    localparam real BIT_NS = 83.330; // 5 cycles of the 60 MHz simulation clock
    reg clk = 0;
    always #8.333 clk = ~clk;
    reg reset_n = 0;
    tri dp, dm;
    pullup(dp);
    pulldown(dm);
    reg host_oe = 0, host_dp = 1, host_dm = 0;
    assign dp = host_oe ? host_dp : 1'bz;
    assign dm = host_oe ? host_dm : 1'bz;
    wire attach_request, usb_reset_released, recv_valid, send_ready;
    wire received_seen, overflow_seen;
    wire [15:0] received_count, echo_queued_count, overflow_count;
    usb1_cdc_loopback dut (
        .clk_60mhz(clk), .reset_n(reset_n), .usb_dp(dp), .usb_dm(dm),
        .attach_request(attach_request), .usb_reset_released(usb_reset_released),
        .recv_valid(recv_valid), .send_ready(send_ready),
        .received_seen(received_seen), .overflow_seen(overflow_seen),
        .received_count(received_count), .echo_queued_count(echo_queued_count),
        .overflow_count(overflow_count)
    );

    reg [7:0] host_bytes [0:2047];
    reg [7:0] payload [0:1023];
    reg [7:0] response [0:2047];
    reg [7:0] control_data [0:1023];
    integer response_len = 0, response_count = 0, response_start_count = 0;
    integer host_ones, previous_response, control_len, current_address = 0;
    reg host_j;

    function automatic [15:0] crc16_byte(input [15:0] old_crc, input [7:0] value);
        reg [15:0] c;
        integer i;
        begin
            c = old_crc;
            for (i = 0; i < 8; i = i+1)
                c = ((c[0] ^ value[i]) ? ((c >> 1) ^ 16'ha001) : (c >> 1));
            crc16_byte = c;
        end
    endfunction

    task automatic symbol(input bit j);
        begin
            host_dp = j; host_dm = ~j;
            repeat (5) @(negedge clk);
        end
    endtask

    task automatic encoded_bit(input bit value, input bit stuffing);
        begin
            if (!value) host_j = ~host_j;
            symbol(host_j);
            if (value) host_ones = host_ones + 1;
            else host_ones = 0;
            if (stuffing && host_ones == 6) begin
                host_j = ~host_j;
                symbol(host_j);
                host_ones = 0;
            end
        end
    endtask

    task automatic send_packet(input integer length);
        integer i, k;
        reg [7:0] sync_byte;
        begin
            // A real bus has idle J before each host transmission.
            repeat (40) @(negedge clk);
            host_oe = 1; host_j = 1; host_ones = 0;
            sync_byte = 8'h80;
            for (k = 0; k < 8; k = k+1) encoded_bit(sync_byte[k], 0);
            for (i = 0; i < length; i = i+1)
                for (k = 0; k < 8; k = k+1) encoded_bit(host_bytes[i][k], 1);
            host_dp = 0; host_dm = 0;
            repeat (10) @(negedge clk); // EOP: two bit times SE0
            symbol(1);                 // one bit time J
            host_oe = 0;
        end
    endtask

    task automatic token(input [3:0] pid, input integer endpoint);
        reg [10:0] bits11;
        reg [4:0] c;
        reg [15:0] bits16;
        integer k;
        begin
            bits11 = {endpoint[3:0], current_address[6:0]};
            c = 5'h1f;
            for (k = 0; k < 11; k = k+1)
                c = ((c[0] ^ bits11[k]) ? ((c >> 1) ^ 5'h14) : (c >> 1));
            bits16 = {~c, bits11};
            host_bytes[0] = {~pid, pid};
            host_bytes[1] = bits16[7:0]; host_bytes[2] = bits16[15:8];
            send_packet(3);
        end
    endtask

    task automatic data_packet(input [3:0] pid, input integer length);
        reg [15:0] c;
        integer i;
        begin
            host_bytes[0] = {~pid, pid}; c = 16'hffff;
            for (i = 0; i < length; i = i+1) begin
                host_bytes[i+1] = payload[i]; c = crc16_byte(c, payload[i]);
            end
            c = ~c;
            host_bytes[length+1] = c[7:0]; host_bytes[length+2] = c[15:8];
            send_packet(length+3);
        end
    endtask

    task automatic host_ack;
        begin host_bytes[0] = 8'hd2; send_packet(1); end
    endtask

    // Decode a device response from physical pins, without using core signals.
    task automatic capture_response;
        reg previous_j, this_j, value;
        reg [7:0] assembled;
        reg [15:0] c;
        integer k, ones, bit_index, length, guard;
        begin
            previous_j = 1; assembled = 0; length = 0; ones = 0; bit_index = 0;
            #(BIT_NS/2.0);
            for (k = 0; k < 8; k = k+1) begin
                if ((dp !== 1'b0 && dp !== 1'b1) || dm !== ~dp)
                    $fatal(1, "Invalid differential SYNC at %t", $time);
                this_j = dp; value = (this_j == previous_j); previous_j = this_j;
                if (value !== (k == 7)) $fatal(1, "Invalid SYNC bit %0d", k);
                #(BIT_NS);
            end
            ones = 1; guard = 0;
            while (!(dp === 1'b0 && dm === 1'b0)) begin
                if (host_oe) $fatal(1, "Host/device bus overlap");
                if ((dp !== 1'b0 && dp !== 1'b1) || dm !== ~dp)
                    $fatal(1, "Invalid device differential data at %t", $time);
                this_j = dp; value = (this_j == previous_j); previous_j = this_j;
                if (ones == 6) begin
                    if (value) $fatal(1, "Device bit stuffing error");
                    ones = 0;
                end else begin
                    assembled[bit_index] = value;
                    bit_index = bit_index + 1;
                    ones = value ? ones + 1 : 0;
                    if (bit_index == 8) begin
                        response[length] = assembled; length = length + 1;
                        bit_index = 0; assembled = 0;
                    end
                end
                guard = guard + 1;
                if (guard > 16000) $fatal(1, "Device packet too long");
                #(BIT_NS);
            end
            if (bit_index != 0 || length < 1) $fatal(1, "Incomplete device packet");
            #(BIT_NS);
            if ({dp,dm} !== 2'b00) $fatal(1, "Short device EOP");
            #(BIT_NS);
            if ({dp,dm} !== 2'b10) $fatal(1, "Device EOP missing J");
            if (response[0][7:4] !== ~response[0][3:0]) $fatal(1, "Invalid PID");
            if (response[0][1:0] == 2'b11) begin
                if (length < 3) $fatal(1, "Data response missing CRC");
                c = 16'hffff;
                for (k = 1; k < length-2; k = k+1) c = crc16_byte(c, response[k]);
                c = ~c;
                if ({response[length-1],response[length-2]} !== c)
                    $fatal(1, "Device CRC16 mismatch");
            end
            response_len = length;
            response_count = response_count + 1;
        end
    endtask

    initial forever begin
        @(negedge dp);
        if (!host_oe && dm === 1'b1) begin
            response_start_count = response_start_count + 1;
            capture_response();
        end
    end

    task automatic expect_packet(input integer before_count, input [3:0] pid,
                                 input integer data_length);
        integer t;
        begin
            t = 0;
            while (response_count == before_count && t < 20000) begin
                @(negedge clk); t = t+1;
            end
            if (response_count != before_count+1) $fatal(1, "Device response timeout");
            if (response[0][3:0] !== pid) $fatal(1, "Expected PID %x, got %x",pid,response[0]);
            if (response_len != (data_length < 0 ? 1 : data_length+3))
                $fatal(1, "Unexpected packet length %0d, expected payload %0d",response_len,data_length);
        end
    endtask

    task automatic expect_silence(input integer before_count, input integer before_starts);
        begin
            repeat(3000) @(negedge clk);
            if(response_count != before_count || response_start_count != before_starts)
                $fatal(1,"Device responded to an unselected/consumed token");
        end
    endtask

    task automatic rejected_address_setup(input [15:0] value, input integer length,
                                         input [3:0] pid);
        integer n;
        begin
            payload[0]=0;payload[1]=5;payload[2]=value[7:0];payload[3]=value[15:8];
            payload[4]=0;payload[5]=0;payload[6]=0;payload[7]=0;payload[8]=0;
            token(4'hd,0);n=response_count;data_packet(pid,length);expect_packet(n,4'h2,-1);
            if(dut.u_cdc.u_usbfs_core.u_address_filter.address_pending)
                $fatal(1,"Malformed SET_ADDRESS armed a pending address");
            // Invalid SETUP response behavior is upstream-defined; recover
            // with a fresh valid request. Only address commit is hardened.
            control_read(8'h80,8'h08,0,1);
            if(control_data[0] !== 1) $fatal(1,"Lost selected address after invalid setup");
        end
    endtask

    task automatic setup(input [7:0] request_type, input [7:0] request,
                         input [15:0] value, input [15:0] index, input [15:0] length);
        integer n;
        begin
            payload[0]=request_type;payload[1]=request;
            payload[2]=value[7:0];payload[3]=value[15:8];
            payload[4]=index[7:0];payload[5]=index[15:8];
            payload[6]=length[7:0];payload[7]=length[15:8];
            token(4'hd,0); n=response_count; data_packet(4'h3,8);
            expect_packet(n,4'h2,-1);
        end
    endtask

    task automatic status_out;
        integer n;
        begin
            token(4'h1,0); n=response_count; data_packet(4'hb,0);
            expect_packet(n,4'h2,-1);
        end
    endtask

    task automatic status_in;
        integer n;
        begin
            n=response_count;token(4'h9,0);expect_packet(n,4'hb,0);host_ack();
        end
    endtask

    task automatic control_read(input [7:0] request_type, input [7:0] request,
                                input [15:0] value, input [15:0] length);
        integer n, chunk, i, remaining;
        reg [3:0] expected_pid;
        begin
            setup(request_type,request,value,0,length);
            control_len=0;remaining=length;expected_pid=4'hb;
            while (remaining > 0) begin
                chunk = remaining > 32 ? 32 : remaining;
                n=response_count;token(4'h9,0);expect_packet(n,expected_pid,chunk);
                for(i=0;i<chunk;i=i+1) control_data[control_len+i]=response[i+1];
                control_len=control_len+chunk;remaining=remaining-chunk;
                host_ack(); expected_pid = expected_pid == 4'hb ? 4'h3 : 4'hb;
            end
            status_out();
        end
    endtask

    localparam [143:0] EXPECT_DEVICE = 144'h12_01_10_01_02_00_00_20_9A_FB_9A_FB_00_01_01_02_00_01;
    localparam [455:0] EXPECT_CONFIG = {
        72'h09_02_39_00_02_01_00_80_64,72'h09_04_00_00_01_02_02_01_00,
        32'h04_24_02_00,40'h05_24_06_00_01,56'h07_05_88_03_08_00_FF,
        72'h09_04_01_00_02_0A_00_00_00,56'h07_05_81_02_40_00_00,
        56'h07_05_01_02_20_00_00};
    integer i, chunk, n, starts, saved_address;
    reg [3:0] data_pid;
    initial begin
        repeat(12) @(negedge clk);
        if (dut.u_cdc.u_usbfs_core.usb_oe !== 1'b0) $fatal(1,"Driving during reset");
        reset_n=1;
        // Accelerate only the documented 120,000,000-cycle detach interval.
        @(negedge clk); dut.u_cdc.u_usbfs_core.usb_rstn_cnt=120000000;
        repeat(50) @(negedge clk);
        if (!attach_request || !usb_reset_released) $fatal(1,"Core reset did not release");
        // Exercise a real physical SE0 bus reset, not only rstn.
        host_oe=1;host_dp=0;host_dm=0;
        repeat(700) @(negedge clk);
        if (usb_reset_released) $fatal(1,"SE0 bus reset not detected");
        host_oe=0;repeat(100) @(negedge clk);
        if (!usb_reset_released) $fatal(1,"J did not release bus reset");

        control_read(8'h80,8'h06,16'h0100,18);
        for(i=0;i<18;i=i+1)
            if(control_data[i] !== EXPECT_DEVICE[(17-i)*8+:8]) $fatal(1,"Device descriptor byte %0d",i);
        // Foreign SETUP/OUT/IN packets (and their DATA) must stay silent.
        current_address=7;
        payload[0]=8'h80;payload[1]=6;payload[2]=0;payload[3]=1;
        payload[4]=0;payload[5]=0;payload[6]=18;payload[7]=0;
        token(4'hd,0);n=response_count;starts=response_start_count;data_packet(4'h3,8);
        expect_silence(n,starts);
        payload[0]=8'hff;token(4'h1,1);n=response_count;starts=response_start_count;data_packet(4'h3,1);
        expect_silence(n,starts);
        n=response_count;starts=response_start_count;token(4'h9,1);expect_silence(n,starts);
        if(received_count !== 0) $fatal(1,"Foreign OUT data escaped address filter");
        current_address=0;
        setup(8'h00,8'h05,16'd5,0,0);
        // Before status IN, the new address must be inactive.
        current_address=5;n=response_count;starts=response_start_count;
        token(4'h9,0);expect_silence(n,starts);
        current_address=0;n=response_count;token(4'h9,0);expect_packet(n,4'hb,0);
        // Sending the status ZLP is not enough: wait for its host ACK.
        current_address=5;n=response_count;starts=response_start_count;
        token(4'h9,0);expect_silence(n,starts);
        current_address=0;status_in();current_address=5;
        current_address=0;n=response_count;starts=response_start_count;
        token(4'h9,0);expect_silence(n,starts);
        current_address=5;control_read(8'h80,8'h06,16'h0100,18);
        for(i=0;i<18;i=i+1)
            if(control_data[i] !== EXPECT_DEVICE[(17-i)*8+:8]) $fatal(1,"New-address descriptor");
        // A duplicate host ACK has no token ownership and cannot flip EP0.
        n=response_count;starts=response_start_count;host_ack();expect_silence(n,starts);
        setup(8'h00,8'h05,16'd9,0,0);
        control_read(8'h80,8'h08,0,1); // a new SETUP aborts pending address 9
        current_address=9;n=response_count;starts=response_start_count;
        token(4'h9,0);expect_silence(n,starts);current_address=5;
        rejected_address_setup(6,0,4'h3);
        rejected_address_setup(6,7,4'h3);
        rejected_address_setup(6,9,4'h3);
        rejected_address_setup(6,8,4'hb);
        rejected_address_setup(128,8,4'h3);
        // One SETUP token cannot own separate short DATA packets totalling 8.
        payload[0]=0;payload[1]=5;payload[2]=6;payload[3]=0;
        payload[4]=0;payload[5]=0;payload[6]=0;payload[7]=0;
        token(4'hd,0);n=response_count;data_packet(4'h3,7);expect_packet(n,4'h2,-1);
        payload[0]=0;n=response_count;starts=response_start_count;data_packet(4'h3,1);
        expect_silence(n,starts);
        if(dut.u_cdc.u_usbfs_core.u_address_filter.address_pending)
            $fatal(1,"Split DATA packets incorrectly armed SET_ADDRESS");
        setup(8'h00,8'h05,16'd127,0,0);status_in();current_address=127;
        control_read(8'h80,8'h06,16'h0200,9);
        if ({control_data[3],control_data[2]} !== 16'd57) $fatal(1,"Configuration length");
        control_read(8'h80,8'h06,16'h0200,57);
        for(i=0;i<57;i=i+1)
            if(control_data[i] !== EXPECT_CONFIG[(56-i)*8+:8]) $fatal(1,"Config byte %0d",i);
        control_read(8'h80,8'h06,16'h0302,32);
        if(control_data[0] !== 32 || control_data[1] !== 3) $fatal(1,"Product string header");
        setup(8'h00,8'h09,1,0,0);status_in();
        control_read(8'h80,8'h08,0,1);
        if(control_data[0] !== 1) $fatal(1,"GET_CONFIGURATION response");
        setup(8'h21,8'h20,0,0,7); // SET_LINE_CODING 115200,8N1
        payload[0]=0;payload[1]=8'hc2;payload[2]=1;payload[3]=0;
        payload[4]=0;payload[5]=0;payload[6]=8;
        token(4'h1,0);n=response_count;data_packet(4'hb,7);expect_packet(n,4'h2,-1);status_in();
        setup(8'h21,8'h22,3,0,0);status_in(); // DTR/RTS accepted, no application gate

        for(chunk=0;chunk<8;chunk=chunk+1) begin
            for(i=0;i<32;i=i+1) payload[i]=chunk*32+i;
            data_pid=chunk[0] ? 4'hb : 4'h3;
            token(4'h1,1);n=response_count;data_packet(data_pid,32);expect_packet(n,4'h2,-1);
            n=response_count;token(4'h9,1);expect_packet(n,data_pid,32);
            for(i=0;i<32;i=i+1)
                if(response[i+1] !== (chunk*32+i)) $fatal(1,"Echo mismatch byte %0d",chunk*32+i);
            host_ack();
        end
        n=response_count;token(4'h9,1);expect_packet(n,4'ha,-1); // empty IN must NAK
        if(received_count !== 256 || echo_queued_count !== 256 || overflow_count !== 0 || overflow_seen)
            $fatal(1,"Echo counters RX=%0d queue=%0d drop=%0d",received_count,echo_queued_count,overflow_count);
        if(!received_seen) $fatal(1,"Received sticky missing");
        // Check a bounded FIFO failure is visible: 1025 bytes without IN.
        for(chunk=0;chunk<33;chunk=chunk+1) begin
            for(i=0;i<32;i=i+1) payload[i]=8'ha5;
            token(4'h1,1);n=response_count;
            data_packet(chunk[0] ? 4'hb : 4'h3,chunk==32 ? 1 : 32);
            expect_packet(n,4'h2,-1);
        end
        if(received_count !== 1281 || echo_queued_count !== 1280 || overflow_count !== 1 || !overflow_seen)
            $fatal(1,"FIFO overflow not reported: RX=%0d queue=%0d drop=%0d",received_count,echo_queued_count,overflow_count);
        // A new physical bus reset restores address zero and clears session data.
        host_oe=1;host_dp=0;host_dm=0;repeat(700) @(negedge clk);
        host_oe=0;repeat(100) @(negedge clk);
        current_address=127;n=response_count;starts=response_start_count;
        token(4'h9,0);expect_silence(n,starts);current_address=0;
        control_read(8'h80,8'h06,16'h0100,18);
        if(received_seen || overflow_seen || received_count != 0) $fatal(1,"Bus reset session state");
        $display("PASS: physical USB NRZI/stuffing/CRC, EP0 descriptors/address/config/class exchanges, delayed SET_ADDRESS commit after status ACK, foreign/old-address silence, malformed/split SETUP rejection, new-SETUP cancellation/reset address0; CDC 256 binary bytes exact echo + empty NAK + visible FIFO overflow.");
        $finish;
    end
    initial begin #10000000; $fatal(1,"Global test timeout"); end
endmodule
