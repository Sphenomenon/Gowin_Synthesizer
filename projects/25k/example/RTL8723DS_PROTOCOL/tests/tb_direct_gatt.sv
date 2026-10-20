`timescale 1ns/1ps
module tb_direct_gatt;
    reg clk=0,resetn=0,reply=0,direct=0,receipt=0,done=0;
    always #5 clk=~clk;
    wire start;
    wire [8:0] length;
    reg [8:0] addr=0;
    wire [7:0] data;
    reg [6:0] reply_length=32;
    integer i,packets;
    bt_gatt #(.CLK_HZ(100000),.AUDIO_FILE("audio/test_tone.mem")) dut(
        .clk(clk),.resetn(resetn),.enable(1'b1),.boot_id(64'd1),.acl_packet_count(8'd8),
        .rx_valid(1'b0),.rx_type(4'd0),.rx_length(9'd0),.rx_payload_data(8'd0),
        .tx_start(start),.tx_length(length),.tx_ready(1'b1),.tx_done(done),.tx_error(1'b0),
        .tx_payload_addr(addr),.tx_payload_data(data));
    task omitted;
        begin
            reply=1;wait(dut.reply_consume);@(negedge clk);reply=0;
            repeat(20)begin @(negedge clk);if(start)$fatal(1,"Direct success produced a Response notification");end
        end
    endtask
    task notified;
        input integer bytes;
        integer offset,n;
        begin
            reply_length=bytes;reply=1;offset=0;packets=0;
            while(offset<bytes)begin
                wait(start);@(negedge clk);n=bytes-offset>14 ? 14 : bytes-offset;
                if(length!=17+n)$fatal(1,"Legacy Response length");
                addr=11;repeat(2)@(negedge clk);if(data!=8'hb1)$fatal(1,"Response marker");
                addr=17;repeat(2)@(negedge clk);if(data!=8'h5a)$fatal(1,"Response payload");
                offset=offset+n;packets=packets+1;
                if(offset==bytes)reply=0;
                done=1;@(negedge clk);done=0;
            end
            repeat(15)@(negedge clk);
            if(packets!=(bytes+13)/14)$fatal(1,"Response notification count");
        end
    endtask
    initial begin
        force dut.connected=1;force dut.response_subscribed=1;force dut.transfer_subscribed=1;
        force dut.tx_credits=8'hff;force dut.transfer_valid=0;
        force dut.reply_valid=reply;force dut.reply_length=reply_length;force dut.reply_data=8'h5a;
        force dut.transfer_direct=direct;force dut.response_is_data=receipt;
        repeat(4)@(negedge clk);resetn=1;
        direct=1;receipt=1;omitted();omitted(); // Original and exact request replay.
        receipt=0;notified(28); // Errors always produce original B1 Response.
        notified(24); // Other successful commands still respond.
        direct=0;receipt=1;notified(32); // Old OPEN/BULK retain positive Responses.
        $display("PASS: direct DATA receipts omit only opted-in READ success, replay, errors and legacy Responses retained");$finish;
    end
    initial begin #1000000;$fatal(1,"Direct GATT watchdog");end
endmodule
