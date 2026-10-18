`timescale 1ns/1ps
// Bit-level peer emulation exercises the two UART directions concurrently.
module tb_bt_h5;
    localparam integer CLOCK_HZ=2000000, BAUD=115200;
    localparam integer DIV=(CLOCK_HZ+BAUD/2)/BAUD;
    reg clk=0, resetn=0, enable=0, peer_tx=1;
    always #250 clk=~clk;
    wire uart_tx;
    reg tx_start=0;
    reg [3:0] tx_type=1;
    reg [8:0] tx_length=3, rx_payload_addr=0;
    wire [8:0] tx_payload_addr;
    reg [7:0] host_payload [0:279];
    wire [7:0] tx_payload_data=host_payload[tx_payload_addr];
    wire tx_ready, tx_done, tx_error, rx_valid, link_up;
    wire [3:0] rx_type;
    wire [8:0] rx_length;
    wire [7:0] rx_payload_data, debug_state;
    reg rx_consume=0;
    wire [31:0] rx_frames, tx_frames, retries, uart_errors, protocol_errors;
    reg test_passed=0;
    bt_h5_transport #(.CLK_HZ(CLOCK_HZ), .BAUD(BAUD), .RETRY_MS(2), .MAX_RETRIES(2)) dut (
        .clk(clk), .resetn(resetn), .enable(enable),
        .uart_rx(peer_tx), .uart_tx(uart_tx),
        .tx_start(tx_start), .tx_type(tx_type), .tx_length(tx_length),
        .tx_payload_addr(tx_payload_addr), .tx_payload_data(tx_payload_data),
        .tx_ready(tx_ready), .tx_done(tx_done), .tx_error(tx_error),
        .rx_valid(rx_valid), .rx_type(rx_type), .rx_length(rx_length),
        .rx_payload_addr(rx_payload_addr), .rx_payload_data(rx_payload_data),
        .rx_consume(rx_consume), .link_up(link_up), .debug_state(debug_state),
        .rx_frames(rx_frames), .tx_frames(tx_frames), .retries(retries),
        .uart_errors(uart_errors), .protocol_errors(protocol_errors)
    );
    wire [7:0] monitor_data;
    wire monitor_valid, monitor_error;
    bt_uart #(.CLK_HZ(CLOCK_HZ), .BAUD(BAUD)) peer_monitor (
        .clk(clk), .resetn(resetn), .enable(enable), .rx(uart_tx), .tx(),
        .tx_data(8'h00), .tx_valid(1'b0), .tx_ready(), .tx_done(),
        .rx_data(monitor_data), .rx_valid(monitor_valid), .rx_error(monitor_error)
    );
    reg [7:0] observed [0:283];
    reg [7:0] last_command [0:279];
    reg [7:0] last_acl [0:279];
    reg [7:0] peer_payload [0:279];
    integer observed_count=0, command_count=0, acl_count=0, unreliable_count=0;
    integer sync_count=0, config_count=0, config_response_count=0, ack_count=0;
    integer completion_count=0, error_count=0;
    integer last_ack=0, last_seq=0, last_length=0, i, before_count;
    integer timeout_count, old_errors, old_uart_errors;
    reg observed_collect=0, observed_escape=0;
    reg [7:0] observation, sum;
    always @(posedge clk) begin
        if (tx_done) completion_count=completion_count+1;
        if (tx_error) error_count=error_count+1;
        if (enable && monitor_error) $fatal(1,"Host UART emitted invalid 8E1");
        if (monitor_valid) begin
            if (monitor_data == 8'hc0) begin
                if (observed_collect && observed_count != 0) begin
                    if (observed_escape || observed_count < 4)
                        $fatal(1,"Host SLIP malformed");
                    sum=observed[0]+observed[1]+observed[2]+observed[3];
                    if (sum != 8'hff) $fatal(1,"Host H5 checksum malformed");
                    last_length={observed[2],observed[1][7:4]};
                    if (last_length+4 != observed_count)
                        $fatal(1,"Host H5 length malformed");
                    if (observed[0][6]) $fatal(1,"Host requested forbidden CRC");
                    case (observed[1][3:0])
                        15: begin
                            case (observed[4])
                                1: sync_count=sync_count+1;
                                3: begin
                                    config_count=config_count+1;
                                    if (last_length != 3 || observed[6] != 1)
                                        $fatal(1,"Host CONFIG must request window1 CRC off");
                                end
                                4: config_response_count=config_response_count+1;
                            endcase
                        end
                        0: begin ack_count=ack_count+1; last_ack=observed[0][5:3]; end
                        1: begin
                            command_count=command_count+1; last_seq=observed[0][2:0];
                            if (!observed[0][7]) $fatal(1,"Command is not reliable");
                            for (i=0;i<last_length;i=i+1) last_command[i]=observed[i+4];
                        end
                        2: begin
                            acl_count=acl_count+1; last_seq=observed[0][2:0];
                            for (i=0;i<last_length;i=i+1) last_acl[i]=observed[i+4];
                        end
                        3: begin
                            unreliable_count=unreliable_count+1;
                            if (observed[0][7]) $fatal(1,"Unreliable packet set reliable bit");
                        end
                        default: $fatal(1,"Unexpected host type");
                    endcase
                end
                observed_count=0; observed_collect=1; observed_escape=0;
            end else if (observed_collect) begin
                if (!observed_escape && monitor_data == 8'hdb) observed_escape=1;
                else begin
                    observation=monitor_data;
                    if (observed_escape) begin
                        if (monitor_data == 8'hdc) observation=8'hc0;
                        else if (monitor_data == 8'hdd) observation=8'hdb;
                        else $fatal(1,"Host emitted bad escape");
                    end
                    observed_escape=0;
                    if (observed_count>=284) $fatal(1,"Host length exceeds buffer");
                    observed[observed_count]=observation;
                    observed_count=observed_count+1;
                end
            end
        end
    end

    task check;
        input condition;
        input [8*100-1:0] message;
        begin if (!condition) $fatal(1,"%0s at %0t",message,$time); end
    endtask
    task send_byte;
        input [7:0] data;
        input corrupt_parity;
        integer bit_number;
        begin
            @(negedge clk); peer_tx=0;
            repeat(DIV) @(negedge clk);
            for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin
                peer_tx=data[bit_number]; repeat(DIV) @(negedge clk);
            end
            peer_tx=(^data)^corrupt_parity; repeat(DIV) @(negedge clk);
            peer_tx=1; repeat(DIV) @(negedge clk);
        end
    endtask
    task slip_byte;
        input [7:0] data;
        begin
            if(data==8'hc0 || data==8'hdb) begin
                send_byte(8'hdb,0); send_byte(data==8'hc0 ? 8'hdc : 8'hdd,0);
            end else send_byte(data,0);
        end
    endtask
    task send_frame;
        input [3:0] packet_type;
        input integer length;
        input reliable;
        input [2:0] sequence_number, acknowledgement;
        input corrupt_header;
        reg [7:0] h0,h1,h2,h3;
        integer n;
        begin
            h0={reliable,1'b0,acknowledgement,sequence_number};
            h1={length[3:0],packet_type}; h2=length>>4;
            h3=~(h0+h1+h2); if(corrupt_header) h3=h3^1;
            send_byte(8'hc0,0); slip_byte(h0); slip_byte(h1);
            slip_byte(h2); slip_byte(h3);
            for(n=0;n<length;n=n+1) slip_byte(peer_payload[n]);
            send_byte(8'hc0,0);
        end
    endtask
    task start_host_packet;
        input [3:0] packet_type;
        input [8:0] length;
        begin
            timeout_count=0;
            while(!tx_ready && timeout_count<60000) begin
                @(negedge clk); timeout_count=timeout_count+1;
            end
            check(tx_ready,"Host did not become ready");
            @(negedge clk); tx_type=packet_type; tx_length=length; tx_start=1;
            @(negedge clk); tx_start=0;
        end
    endtask
    task wait_rx;
        begin
            timeout_count=0;
            while(!rx_valid && timeout_count<30000) begin
                @(negedge clk); timeout_count=timeout_count+1;
            end
            check(rx_valid,"Expected delivered packet");
        end
    endtask
    task consume_rx;
        begin
            @(negedge clk); rx_consume=1;
            @(negedge clk); rx_consume=0;
            check(!rx_valid,"RX valid did not clear on consume");
        end
    endtask
    task check_rx_payload;
        input integer length;
        integer n;
        begin
            check(rx_length==length,"Delivered length mismatch");
            for(n=0;n<length;n=n+1) begin
                rx_payload_addr=n; #1;
                if(rx_payload_data !== peer_payload[n])
                    $fatal(1,"RX payload[%0d]=%h expected %h",n,rx_payload_data,peer_payload[n]);
            end
        end
    endtask

    initial begin
        #1;
        repeat(5) @(negedge clk);
        resetn=1; enable=1;
        timeout_count=0;
        while(sync_count==0 && timeout_count<20000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        check(sync_count>0,"Missing SYNC request");
        peer_payload[0]=2; peer_payload[1]=8'h7d;
        send_frame(15,2,0,0,0,0);
        timeout_count=0;
        while(config_count==0 && timeout_count<20000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        check(config_count>0,"Missing CONFIG request");
        peer_payload[0]=3; peer_payload[1]=8'hfc; peer_payload[2]=1;
        send_frame(15,3,0,0,0,0);
        timeout_count=0;
        while(config_response_count==0 && timeout_count<20000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        check(config_response_count>0,"Missing CONFIG response");
        peer_payload[0]=4; peer_payload[1]=8'h7b; peer_payload[2]=1;
        send_frame(15,3,0,0,0,0);
        repeat(5) @(negedge clk);
        check(link_up,"Link did not become active");

        // An event starts while the host Reset is still being transmitted.
        host_payload[0]=8'h03; host_payload[1]=8'h0c; host_payload[2]=0;
        start_host_packet(1,3);
        wait(dut.wire_host && dut.wire_state==1);
        peer_payload[0]=8'h0e; peer_payload[1]=4; peer_payload[2]=1;
        peer_payload[3]=3; peer_payload[4]=8'h0c; peer_payload[5]=0;
        send_frame(4,6,1,0,1,0);
        wait_rx;
        check_rx_payload(6);
        check(rx_type==4,"Wrong event type");
        check(command_count==1 && last_seq==0,"Reset command malformed or repeated");
        check(last_command[0]==3 && last_command[1]==8'h0c,"Reset opcode wrong");
        repeat(1500) @(negedge clk);
        check(completion_count==1,"Reliable Reset did not complete after ACK");
        check(last_ack==1,"Event ACK did not advance to one");
        consume_rx;

        // Same sequence must be ACKed but never delivered twice.
        before_count=ack_count;
        send_frame(4,6,1,0,1,0);
        repeat(1500) @(negedge clk);
        check(!rx_valid,"Duplicate event was delivered twice");
        check(ack_count>before_count && last_ack==1,"Duplicate event was not ACKed");

        // Drop the command ACK: retry preserves its sequence and data.
        host_payload[0]=1; host_payload[1]=8'h10; host_payload[2]=0;
        start_host_packet(1,3);
        timeout_count=0;
        while(command_count<2 && timeout_count<30000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        send_frame(0,0,0,0,0,0);
        repeat(20) @(negedge clk);
        check(completion_count==1 && !tx_ready,"Wrong ACK falsely completed command");
        timeout_count=0;
        while(command_count<3 && timeout_count<30000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        check(command_count==3 && retries==1,"Reliable retry not observed");
        check(last_seq==1 && last_command[0]==1 && last_command[1]==8'h10,
              "Retry changed sequence or payload");
        send_frame(0,0,0,0,2,0);
        repeat(20) @(negedge clk);
        check(completion_count==2 && tx_ready,"Retry ACK did not complete");

        // Both escape bytes, maximum payload, and independent full-duplex RX.
        for(i=0;i<280;i=i+1) host_payload[i]=i;
        host_payload[279]=8'hdb;
        start_host_packet(2,280);
        timeout_count=0;
        while(acl_count<1 && timeout_count<80000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        check(acl_count==1 && last_length==280 && last_seq==2,"280-byte ACL did not transmit");
        for(i=0;i<280;i=i+1) begin
            if(last_acl[i] !== host_payload[i]) $fatal(1,"Escaped TX data differs at %0d",i);
        end
        // ACK the long ACL during its retry. The old frame must finish before
        // a new source-buffer copy can be accepted.
        timeout_count=0;
        while(!(dut.wire_host && dut.host_sent && dut.wire_state==1) && timeout_count<30000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        check(timeout_count<30000,"Long ACL retry did not begin");
        send_frame(0,0,0,0,3,0);
        repeat(20) @(negedge clk);
        check(completion_count==3 && !tx_ready,"Mid-retry ACK failed or exposed payload RAM");
        @(negedge clk); tx_start=1; tx_type=1; tx_length=3;
        @(negedge clk); tx_start=0;
        timeout_count=0;
        while(acl_count<2 && timeout_count<80000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        repeat(40) @(negedge clk);
        check(acl_count==2 && tx_ready && completion_count==3,
              "ACKed retry did not finish cleanly");
        for(i=0;i<280;i=i+1) begin
            if(last_acl[i] !== host_payload[i]) $fatal(1,"In-progress retry corrupted at %0d",i);
        end

        peer_payload[0]=8'hff; peer_payload[1]=8'hc0;
        peer_payload[2]=8'hdb; peer_payload[3]=0;
        send_frame(4,4,1,1,3,0); wait_rx; check_rx_payload(4);
        // Held mailbox refuses to advance receive sequence for a new frame.
        old_errors=protocol_errors;
        send_frame(4,4,1,2,3,0);
        repeat(1500) @(negedge clk);
        check(rx_valid && protocol_errors>old_errors,"RX overrun was not explicit");
        check(last_ack==2,"RX overrun falsely ACKed acceptance");
        consume_rx;
        send_frame(4,4,1,2,3,0); wait_rx; check_rx_payload(4); consume_rx;

        // Bad header checksum and parity must never become application data.
        old_errors=protocol_errors;
        send_frame(4,4,1,3,3,1);
        repeat(20) @(negedge clk);
        check(!rx_valid && protocol_errors>old_errors,"Bad checksum accepted");
        old_uart_errors=uart_errors;
        send_byte(8'hc0,1);
        repeat(20) @(negedge clk);
        check(uart_errors>old_uart_errors,"Bad parity did not count UART error");
        send_frame(4,4,1,3,3,0); wait_rx; check_rx_payload(4); consume_rx;

        old_errors=protocol_errors;
        send_byte(8'hc0,0); send_byte(8'hdb,0); send_byte(8'h00,0); send_byte(8'hc0,0);
        repeat(20) @(negedge clk);
        check(!rx_valid && protocol_errors>old_errors,"Invalid SLIP escape was not rejected");

        // Maximum-size receive packet also includes both escape octets.
        for(i=0;i<280;i=i+1) peer_payload[i]=i+17;
        send_frame(4,280,1,4,3,0); wait_rx; check_rx_payload(280); consume_rx;

        // An out-of-range host length produces an error, never tx_done.
        before_count=completion_count;
        start_host_packet(1,281);
        repeat(5) @(negedge clk);
        check(error_count==1 && completion_count==before_count,"Invalid length falsely succeeded");
        host_payload[0]=8'hc0; host_payload[1]=8'hdb;
        start_host_packet(3,2);
        timeout_count=0;
        while(completion_count==before_count && timeout_count<20000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        check(unreliable_count==1 && completion_count==before_count+1,
              "Unreliable packet did not complete without ACK");

        // Exhausted retries must fail and restart negotiation, never succeed.
        before_count=completion_count;
        host_payload[0]=3; host_payload[1]=8'h0c; host_payload[2]=0;
        start_host_packet(1,3);
        timeout_count=0;
        while(error_count<2 && timeout_count<60000) begin
            @(negedge clk); timeout_count=timeout_count+1;
        end
        check(error_count==2 && !link_up && completion_count==before_count,
              "Retry exhaustion did not fail/restart the link");
        @(negedge clk); enable=0;
        repeat(5) @(negedge clk);
        check(uart_tx==1 && !link_up && !rx_valid && !tx_ready,"Disable state is not deterministic");
        $display("BT_H5_PASS handshake, full duplex 8E1, ACK, duplicate, retry, SLIP, 280-byte limit, backpressure, checksum, parity");
        test_passed=1; $finish;
    end
    initial begin
        #250000000; $fatal(1,"H5 test watchdog");
    end
endmodule
