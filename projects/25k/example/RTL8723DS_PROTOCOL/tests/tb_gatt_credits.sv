`timescale 1ns/1ps
module tb_gatt_credits;
    defparam dut.AUDIO_FILE="../../audio/test_tone.mem";
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
        .clk(clk),.resetn(resetn),.enable(enable),.acl_packet_count(8'd4),.boot_id(64'h8877665544332211),
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
            if(!tx_ready || (tx_type!=2 && tx_type!=1)) $fatal(1,"Invalid ACL transmit handshake");
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
        for(k=0;k<264;k=k+1)receive_data[k]=0;
        repeat(3)@(posedge clk);@(negedge clk);resetn=1;enable=1;
        receive_data[0]=8'h3e;receive_data[1]=19;receive_data[2]=1;receive_data[3]=0;put_word(4,16'h0234);send_packet(4,21);
        for(k=1;k<=4;k=k+1)begin read_request(8);await_tx(k);end
        read_request(8);repeat(30)@(posedge clk);
        if(tx_count!=4 || dut.tx_credits!=0)$fatal(1,"Exceeded negotiated 4 ACL buffers");
        complete_acl(16'h111,4);repeat(30)@(posedge clk);
        if(tx_count!=4)$fatal(1,"Foreign completion replenished buffers");
        complete_acl(16'h0234,2);await_tx(5);repeat(30)@(posedge clk);
        if(dut.tx_credits!=1)$fatal(1,"Completed count did not replenish two buffers");
        complete_acl(16'h0234,20);repeat(100)@(posedge clk);
        if(dut.tx_credits!=4)$fatal(1,"Credit count must clamp to controller limit");
        // A peripheral link update is an ACL packet and consumes one buffer.
        att_header(8'h12,5);put_word(9,22);put_word(11,1);send_packet(2,13);await_tx(7);
        if(lengths[6]!=20 || dut.tx_credits!=2 || !dut.fast_link_requested)
            $fatal(1,"Link request must consume one negotiated ACL buffer");
        byte_is(6,2,16);byte_is(6,4,12);byte_is(6,6,5);byte_is(6,8,8'h12);
        byte_is(6,9,8'h25);byte_is(6,10,8);byte_is(6,12,12);byte_is(6,14,12);
        byte_is(6,16,0);byte_is(6,18,8'h90);byte_is(6,19,1);
        before_errors=errors;
        // Both accepted and rejected signaling responses terminate quietly.
        put_word(0,16'h0234);put_word(2,10);put_word(4,6);put_word(6,5);
        receive_data[8]=8'h13;receive_data[9]=8'h25;put_word(10,2);put_word(12,0);send_packet(2,14);
        put_word(12,1);send_packet(2,14);repeat(100)@(posedge clk);
        if(tx_count!=7 || errors!=before_errors || !connected)$fatal(1,"Link response triggered reject loop or disconnected");
        // Repeated subscriptions do not repeatedly request link changes.
        att_header(8'h12,5);put_word(9,22);put_word(11,1);send_packet(2,13);await_tx(8);
        repeat(100)@(posedge clk);if(tx_count!=8)$fatal(1,"Duplicate subscription repeated link request");
        $display("PASS: negotiated ACL credits, exhaustion, foreign handle, multi-completion, saturation; peripheral L2CAP link request and terminal rejection");$finish;
    end
    initial begin #2000000;$fatal(1,"Credit watchdog");end
endmodule
