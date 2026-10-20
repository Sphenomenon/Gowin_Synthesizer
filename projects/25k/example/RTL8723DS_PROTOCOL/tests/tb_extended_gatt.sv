`timescale 1ns/1ps
// Isolate the actual GATT fragment builder from the recorder's logical bytes.
// The recording test separately checks OPEN_COMPACT, retries and PCM CRCs.
module tb_extended_gatt #(parameter ATT_MTU=247);
    localparam USE_BULK=1;
    reg clk=0;
    always #5 clk=~clk;
    reg resetn=0, done=0, valid=0, compact=1;
    reg [8:0] address=0;
    wire [7:0] data;
    wire start;
    wire [8:0] length;
    reg [7:0] source_data=0;
    reg [12:0] logical_length=508;
    wire consume;
    bt_gatt #(.CLK_HZ(100000),.AUDIO_FILE("audio/test_tone.mem")) dut(
        .clk(clk),.resetn(resetn),.enable(1'b1),.boot_id(64'd1),.acl_packet_count(8'd8),
        .rx_valid(1'b0),.rx_type(4'd0),.rx_length(9'd0),.rx_payload_data(8'd0),
        .tx_start(start),.tx_length(length),.tx_ready(1'b1),.tx_done(done),.tx_error(1'b0),
        .tx_payload_addr(address),.tx_payload_data(data)
    );
    assign consume=dut.transfer_consume;
    // Model the same one-cycle synchronous transfer RAM as ble_recording.
    always @(posedge clk) source_data<=dut.transfer_addr[7:0] ^ 8'h5a;
    integer n,i,offset,capacity,header,expected_length;
    reg [7:0] captured[0:255];
    wire mock_bulk=USE_BULK && compact;
    reg [15:0] token;
    task check_message;
        input integer total;
        input integer use_compact;
        begin
            logical_length=total;compact=use_compact;valid=1;
            offset=0;n=0;capacity=use_compact ? (USE_BULK ? ATT_MTU-7 : 16) : 14;header=use_compact ? 4 : 6;
            while(offset<total) begin
                wait(start);@(negedge clk);
                expected_length=(total-offset>capacity ? capacity : total-offset);
                if(length!=11+header+expected_length || length>(USE_BULK && use_compact ? ATT_MTU+8 : 31))$fatal(1,"ATT/ACL length");
                for(i=0;i<length;i=i+1)begin address=i;repeat(2)@(negedge clk);captured[i]=data;end
                if(captured[2]!=length-4 || captured[4]!=length-8 || captured[6]!=4 || captured[8]!=8'h1b || captured[9]!=21)
                    $fatal(1,"ACL/L2CAP/ATT framing");
                if(captured[11]!=(use_compact ? (USE_BULK ? 8'hb3 : 8'hb2) : 8'hb1))$fatal(1,"Profile marker");
                if(n==0)token={captured[13],captured[12]};
                if({captured[13],captured[12]}!=token)$fatal(1,"Token changed mid-message");
                if(use_compact)begin
                    if(captured[14]!=(n | (n==0 ? 64 : 0) | (offset+expected_length==total ? 128 : 0)))$fatal(1,"B2 index/flags");
                end else if(captured[14]!=n || captured[15]!=((n==0 ? 1 : 0)|(offset+expected_length==total ? 2 : 0)) || captured[16]!=expected_length)
                    $fatal(1,"B1 index/flags/size");
                for(i=0;i<expected_length;i=i+1)
                    if(captured[11+header+i]!=(((offset+i)&255)^8'h5a))$fatal(1,"Payload RAM latency/offset at %0d",offset+i);
                offset=offset+expected_length;n=n+1;
                @(negedge clk);done=1;@(negedge clk);done=0;
            end
            if(n!=(total+capacity-1)/capacity)$fatal(1,"Fragment count");
            valid=0;repeat(10)@(negedge clk);
            if(start)$fatal(1,"Extra notification after LAST");
        end
    endtask
    initial begin
        force dut.connected=1;
        force dut.transfer_subscribed=1;
        force dut.tx_credits=8'hff;
        force dut.transfer_valid=valid;
        force dut.transfer_compact=compact;
        force dut.transfer_bulk=mock_bulk;
        force dut.att_mtu=ATT_MTU;
        force dut.transfer_length=logical_length;
        force dut.transfer_data=source_data;
        repeat(4)@(negedge clk);resetn=1;
        check_message(((ATT_MTU-7)*64>8160 ? 8160 : (ATT_MTU-7)*64),1);
        if(USE_BULK)check_message(1020,1);
        check_message(508,1); // 32 fragments, LAST has 12 bytes
        check_message(64,1);  // LAST may contain all sixteen payload bytes
        check_message(52,1);  // minimum four-byte PCM block plus framing
        check_message(508,0); // unchanged 37-fragment B1 transfer
        $display("PASS: negotiated B2/B3 DATA 508/64/52 byte RAM payload, flags, token, exact fragment count; B1 profile restored");
        $finish;
    end
    initial begin #4000000;$fatal(1,"Compact GATT watchdog");end
endmodule
