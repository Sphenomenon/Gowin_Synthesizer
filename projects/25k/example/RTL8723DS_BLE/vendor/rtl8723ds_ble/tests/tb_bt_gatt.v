`timescale 1ns/1ps
module tb_bt_gatt;
    reg clk=0, resetn=0, enable=0;
    always #5 clk=~clk;
    reg rx_valid=0;
    reg [3:0] rx_type=0;
    reg [8:0] rx_length=0;
    wire [8:0] rx_addr;
    reg [7:0] receive_data [0:263];
    wire [7:0] rx_data=receive_data[rx_addr];
    wire rx_consume,tx_start;
    wire [3:0] tx_type;
    wire [8:0] tx_length;
    reg tx_ready=1,tx_done=0,tx_error=0;
    reg [8:0] tx_addr=0;
    wire [7:0] tx_data;
    wire connected,subscribed;
    wire [11:0] handle;
    wire [31:0] notifications,acl_received,att_requests,completed,errors,elapsed;
    wire [7:0] state;
    integer tx_count=0, busy_cycles=0, j,k, before_count, before_errors;
    reg [7:0] transmitted [0:4095];
    integer lengths [0:49];
    reg [15:0] checked_crc;
    reg [31:0] first_notification_ms, second_notification_ms;
    reg test_passed=0;
    bt_gatt #(.CLK_HZ(100000),.NOTIFY_MS(8)) dut(
        .clk(clk),.resetn(resetn),.enable(enable),
        .rx_valid(rx_valid),.rx_type(rx_type),.rx_length(rx_length),
        .rx_payload_addr(rx_addr),.rx_payload_data(rx_data),.rx_consume(rx_consume),
        .tx_start(tx_start),.tx_type(tx_type),.tx_length(tx_length),
        .tx_ready(tx_ready),.tx_done(tx_done),.tx_error(tx_error),
        .tx_payload_addr(tx_addr),.tx_payload_data(tx_data),
        .connected(connected),.subscribed(subscribed),.connection_handle(handle),
        .notification_count(notifications),.acl_rx_count(acl_received),
        .att_request_count(att_requests),.completed_packets(completed),
        .debug_state(state),.error_count(errors),.elapsed_ms(elapsed));

    // Mock H5: TX completion alone does not replenish HCI ACL credit.
    always @(posedge clk) begin
        #1;
        tx_done=0;
        if(busy_cycles!=0) begin
            busy_cycles=busy_cycles-1;
            if(busy_cycles==0) begin tx_done=1; tx_ready=1; end
        end
        if(tx_start) begin
            if(!tx_ready || tx_type!=2) $fatal(1,"Invalid ACL transmit handshake");
            lengths[tx_count]=tx_length;
            for(j=0;j<tx_length;j=j+1) begin
                tx_addr=j; #0.01;
                transmitted[tx_count*80+j]=tx_data;
            end
            tx_count=tx_count+1; tx_ready=0; busy_cycles=20;
        end
    end
    task put_word;
        input integer at;
        input [15:0] data;
        begin receive_data[at]=data[7:0]; receive_data[at+1]=data[15:8]; end
    endtask
    task send_packet;
        input [3:0] kind;
        input integer length;
        integer watchdog;
        begin
            @(negedge clk); rx_type=kind; rx_length=length; rx_valid=1;
            watchdog=0;
            while(!rx_consume && watchdog<1000) begin
                @(posedge clk); #2; watchdog=watchdog+1;
            end
            if(!rx_consume) $fatal(1,"RX packet was blocked by TX credit/queue");
            @(negedge clk); rx_valid=0;
            repeat(3) begin @(posedge clk); #2; end
        end
    endtask
    task att_header;
        input [7:0] opcode;
        input integer length;
        begin
            put_word(0,16'h0234); put_word(2,length+4);
            put_word(4,length); put_word(6,4); receive_data[8]=opcode;
        end
    endtask
    task complete_acl;
        input [15:0] connection;
        input [15:0] number;
        begin
            receive_data[0]=8'h13; receive_data[1]=5; receive_data[2]=1;
            put_word(3,connection); put_word(5,number); send_packet(4,7);
        end
    endtask
    task await_tx;
        input integer number;
        integer timeout;
        begin
            timeout=0;
            while(tx_count<number && timeout<5000) begin
                @(posedge clk); #3; timeout=timeout+1;
            end
            if(tx_count!=number) $fatal(1,"Expected TX %0d got %0d",number,tx_count);
        end
    endtask
    task byte_is;
        input integer message;
        input integer at;
        input [7:0] value;
        begin
            if(transmitted[message*80+at]!==value)
                $fatal(1,"TX %0d byte %0d = %h expected %h",message,at,
                       transmitted[message*80+at],value);
        end
    endtask
    task verify_acl;
        input integer message;
        input integer att_length;
        begin
            if(lengths[message]!=att_length+8) $fatal(1,"Wrong ACL length");
            byte_is(message,0,8'h34); byte_is(message,1,2); // PB00
            byte_is(message,2,att_length+4); byte_is(message,3,0);
            byte_is(message,4,att_length); byte_is(message,5,0);
            byte_is(message,6,4); byte_is(message,7,0);
        end
    endtask
    task read_request;
        input [15:0] attribute;
        begin att_header(8'h0a,3); put_word(9,attribute); send_packet(2,11); end
    endtask
    task discovery;
        input [7:0] opcode;
        input [15:0] first;
        input [15:0] last;
        input [15:0] uuid;
        begin
            att_header(opcode,7); put_word(9,first); put_word(11,last);
            put_word(13,uuid); send_packet(2,15);
        end
    endtask
    function [15:0] independent_crc;
        input integer message;
        input integer base;
        integer offset, bit_number;
        reg [15:0] result;
        reg [7:0] data;
        begin
            result=16'hffff;
            for(offset=0;offset<18;offset=offset+1) begin
                data=transmitted[message*80+base+offset];
                for(bit_number=7;bit_number>=0;bit_number=bit_number-1)
                    if(result[15]^data[bit_number]) result=(result<<1)^16'h1021;
                    else result=result<<1;
            end
            independent_crc=result;
        end
    endfunction
    initial begin
        for(k=0;k<264;k=k+1) receive_data[k]=0;
        repeat(3) @(posedge clk);
        @(negedge clk); resetn=1; enable=1;
        // LE connection complete, handle 0x234.
        receive_data[0]=8'h3e; receive_data[1]=19;
        receive_data[2]=1; receive_data[3]=0; put_word(4,16'h0234);
        send_packet(4,21);
        if(!connected || handle!=12'h234 || subscribed) $fatal(1,"Connection event");

        // Fixed MTU and two queued responses while the controller has no credit.
        att_header(2,3); put_word(9,247); send_packet(2,11); await_tx(1);
        verify_acl(0,3); byte_is(0,8,3); byte_is(0,9,23); byte_is(0,10,0);
        read_request(3); read_request(8);
        if(tx_count!=1) $fatal(1,"TX without NumberOfCompletedPackets credit");
        complete_acl(16'h111,1); repeat(30) @(posedge clk);
        if(tx_count!=1 || completed!=0) $fatal(1,"Foreign handle supplied credit");
        complete_acl(16'h0234,1); await_tx(2);
        verify_acl(1,12); byte_is(1,8,8'h0b);
        byte_is(1,9,"R"); byte_is(1,19,"E");
        complete_acl(16'h0234,1); await_tx(3);
        verify_acl(2,3); byte_is(2,8,8'h0b); byte_is(2,9,0);

        // Group discovery contains GAP, GATT and test service boundaries.
        complete_acl(16'h0234,1);
        discovery(8'h10,1,16'hffff,16'h2800); await_tx(4);
        verify_acl(3,20); byte_is(3,8,8'h11); byte_is(3,9,6);
        byte_is(3,10,1); byte_is(3,12,3); byte_is(3,14,0); byte_is(3,15,8'h18);
        byte_is(3,22,5); byte_is(3,24,8); byte_is(3,26,8'hf0); byte_is(3,27,8'hff);
        complete_acl(16'h0234,1);
        discovery(8'h08,1,8,16'h2803); await_tx(5);
        verify_acl(4,16); byte_is(4,8,9); byte_is(4,9,7);
        byte_is(4,10,2); byte_is(4,12,2); byte_is(4,13,3);
        byte_is(4,17,6); byte_is(4,19,8'h12); byte_is(4,20,7);
        byte_is(4,22,8'hf1); byte_is(4,23,8'hff);
        complete_acl(16'h0234,1);
        att_header(4,5); put_word(9,4); put_word(11,8); send_packet(2,13); await_tx(6);
        verify_acl(5,22); byte_is(5,8,5); byte_is(5,9,1);
        byte_is(5,26,8); byte_is(5,28,2); byte_is(5,29,8'h29);
        complete_acl(16'h0234,1);
        att_header(6,9); put_word(9,1); put_word(11,8);
        put_word(13,16'h2800); put_word(15,16'hfff0); send_packet(2,17); await_tx(7);
        verify_acl(6,5); byte_is(6,8,7); byte_is(6,9,5); byte_is(6,11,8);

        // Invalid ranges and missing attributes use ATT error responses.
        complete_acl(16'h0234,1); discovery(8'h10,0,8,16'h2800); await_tx(8);
        verify_acl(7,5); byte_is(7,8,1); byte_is(7,9,8'h10); byte_is(7,12,1);
        complete_acl(16'h0234,1); read_request(9); await_tx(9);
        byte_is(8,8,1); byte_is(8,9,8'h0a); byte_is(8,10,9); byte_is(8,12,1);

        // A continuation is rejected rather than interpreted as a complete ATT.
        before_errors=errors;
        att_header(8'h0a,3); receive_data[1]=8'h12; put_word(9,3);
        send_packet(2,11);
        if(errors!=before_errors+1 || tx_count!=9) $fatal(1,"Fragment rejection");

        // CCCD write response must be sent before notifications, which need a
        // fresh controller completion independently from the H5 TX completion.
        complete_acl(16'h0234,1);
        att_header(8'h12,5); put_word(9,8); put_word(11,1); send_packet(2,13);
        await_tx(10); verify_acl(9,1); byte_is(9,8,8'h13);
        if(!subscribed) $fatal(1,"CCCD write not applied");
        repeat(1200) @(posedge clk);
        if(tx_count!=10 || notifications!=0) $fatal(1,"Notification without credit");
        complete_acl(16'h0234,1); await_tx(11);
        verify_acl(10,23); byte_is(10,8,8'h1b); byte_is(10,9,7); byte_is(10,10,0);
        byte_is(10,11,"B"); byte_is(10,12,"T"); byte_is(10,13,"S"); byte_is(10,14,"T");
        for(k=15;k<=18;k=k+1) byte_is(10,k,0);
        for(k=0;k<6;k=k+1) byte_is(10,23+k,k);
        checked_crc=independent_crc(10,11);
        byte_is(10,29,checked_crc[7:0]); byte_is(10,30,checked_crc[15:8]);
        if(notifications!=1) $fatal(1,"Notification count");
        first_notification_ms={transmitted[10*80+22],transmitted[10*80+21],
                               transmitted[10*80+20],transmitted[10*80+19]};
        if(first_notification_ms==0 || first_notification_ms>elapsed)
            $fatal(1,"Notification timestamp does not use elapsed milliseconds");
        complete_acl(16'h0234,1); await_tx(12);
        byte_is(11,15,1); checked_crc=independent_crc(11,11);
        byte_is(11,29,checked_crc[7:0]); byte_is(11,30,checked_crc[15:8]);
        second_notification_ms={transmitted[11*80+22],transmitted[11*80+21],
                                transmitted[11*80+20],transmitted[11*80+19]};
        if(second_notification_ms<first_notification_ms+8)
            $fatal(1,"Notification interval is shorter than NOTIFY_MS");

        // A write command unsubscribes without a write response.
        att_header(8'h52,5); put_word(9,8); put_word(11,0); send_packet(2,13);
        complete_acl(16'h0234,1); repeat(1200) @(posedge clk);
        if(subscribed || tx_count!=12) $fatal(1,"CCCD write-command disable");

        // Queue overflow must preserve both earlier replies and still allow the
        // later completed-packets event through. Hold tx_ready low to fill it.
        tx_ready=0;
        read_request(3); read_request(8); before_errors=errors; read_request(9);
        if(errors!=before_errors+1) $fatal(1,"Queue overflow not reported");
        complete_acl(16'h0234,1);
        tx_ready=1; await_tx(13); byte_is(12,8,8'h0b); byte_is(12,9,"R");
        complete_acl(16'h0234,1); await_tx(14); byte_is(13,8,8'h0b); byte_is(13,9,0);

        // Read FFF1 returns the same BTST schema with current sequence and CRC.
        complete_acl(16'h0234,1); read_request(7); await_tx(15);
        verify_acl(14,21); byte_is(14,8,8'h0b);
        byte_is(14,9,"B"); byte_is(14,10,"T"); byte_is(14,11,"S"); byte_is(14,12,"T");
        byte_is(14,13,2); for(k=14;k<17;k=k+1) byte_is(14,k,0);
        checked_crc=independent_crc(14,9);
        byte_is(14,27,checked_crc[7:0]); byte_is(14,28,checked_crc[15:8]);

        receive_data[0]=5; receive_data[1]=4; receive_data[2]=0;
        put_word(3,16'h0234); receive_data[5]=8'h13; send_packet(4,6);
        if(connected || subscribed) $fatal(1,"Disconnect event");
        @(negedge clk); enable=0; repeat(2) @(posedge clk); #2;
        if(notifications || att_requests || completed || elapsed || errors)
            $fatal(1,"Session counters did not reset on disable");
        test_passed=1;
        $display("PASS: bt_gatt connection, discovery, ATT errors, CCCD, controller credit, two response slots, PB00, CRC16 and notification sequence");
        $finish;
    end
    initial begin #2000000; $fatal(1,"GATT simulation watchdog"); end
endmodule
