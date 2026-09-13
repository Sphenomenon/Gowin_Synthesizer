`timescale 1ns/1ps
// Actual serial pins and the original ready/valid command path are exercised.
// Short bit dividers accelerate fault injection; all timestamps are clock ticks.
module tb_uart_latency;
    localparam integer BIT_CLKS=16;
    localparam integer PACKET_ACCEPT_DELAY=119*BIT_CLKS+BIT_CLKS/2+1;
    localparam integer ACK_WIRE_DELAY=80*BIT_CLKS+7;
    reg clk=0;
    always #10 clk=~clk;
    reg rst_n=0, serial_rx=1;
    reg [31:0] time_cycles=0;
    wire serial_tx;
    wire [31:0] cmd_data,error_count;
    wire cmd_valid,cmd_first,cmd_last,rsp_ready;
    reg cmd_ready=1,rsp_valid=0;
    reg [31:0] rsp_data=0;
    wire trace_packet_valid,trace_ack_ready,trace_ack_done;
    wire [31:0] trace_packet_header,trace_packet_start,trace_packet_end;
    wire [31:0] trace_ack_header,trace_ack_ready_time;
    wire [31:0] trace_ack_done_header,trace_ack_done_time;
    uart_control #(.CLK_HZ(1843200),.BAUD(115200)) dut(
        .clk(clk),.rst_n(rst_n),.uart_rx(serial_rx),.uart_tx(serial_tx),.time_cycles(time_cycles),
        .cmd_data(cmd_data),.cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_first(cmd_first),.cmd_last(cmd_last),
        .rsp_data(rsp_data),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.error_count(error_count),
        .trace_packet_valid(trace_packet_valid),.trace_packet_header(trace_packet_header),
        .trace_packet_start(trace_packet_start),.trace_packet_end(trace_packet_end),
        .trace_ack_ready(trace_ack_ready),.trace_ack_header(trace_ack_header),
        .trace_ack_ready_time(trace_ack_ready_time),.trace_ack_done(trace_ack_done),
        .trace_ack_done_header(trace_ack_done_header),.trace_ack_done_time(trace_ack_done_time));

    function [15:0] crc_byte(input [15:0] original,input [7:0] value);
        reg [15:0] result;
        integer bit_number;
        begin
            result=original^{value,8'b0};
            for(bit_number=0;bit_number<8;bit_number=bit_number+1)
                result=result[15] ? (result<<1)^16'h1021 : result<<1;
            crc_byte=result;
        end
    endfunction

    task send_byte(input [7:0] value,input bad_stop);
        integer bit_number;
        begin
            serial_rx=0; repeat(BIT_CLKS) @(negedge clk);
            for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin
                serial_rx=value[bit_number]; repeat(BIT_CLKS) @(negedge clk);
            end
            serial_rx=!bad_stop; repeat(BIT_CLKS) @(negedge clk);
            serial_rx=1;
        end
    endtask

    reg [31:0] expected_header[0:15],expected_value[0:15],expected_start[0:15];
    integer expected_packets=0,packet_traces=0,command_words=0;
    reg saw_packet_wrap=0,saw_ack_wrap=0;
    task send_packet(input [7:0] seq,input [31:0] value,input bad_crc,input repeated_a5,input accepted);
        integer byte_number;
        reg [7:0] value_byte;
        reg [15:0] crc;
        begin
            @(negedge clk);
            if(repeated_a5) send_byte(8'ha5,0);
            if(accepted) begin
                expected_header[expected_packets]={seq,8'h01,8'h1f,8'h00};
                expected_value[expected_packets]=value;
                // Pin falls at a negedge. Two synchronizer stages plus the
                // receiver's observation give the third following posedge.
                expected_start[expected_packets]=time_cycles+32'd2;
                expected_packets=expected_packets+1;
            end
            send_byte(8'ha5,0); send_byte(8'h5a,0);
            crc=16'hffff;
            for(byte_number=0;byte_number<8;byte_number=byte_number+1) begin
                case(byte_number)
                    0: value_byte=seq;
                    1: value_byte=8'h01;
                    2: value_byte=8'h1f;
                    3: value_byte=0;
                    4: value_byte=value[7:0];
                    5: value_byte=value[15:8];
                    6: value_byte=value[23:16];
                    7: value_byte=value[31:24];
                endcase
                send_byte(value_byte,0); crc=crc_byte(crc,value_byte);
            end
            send_byte(crc[7:0]^{7'd0,bad_crc},0); send_byte(crc[15:8],0);
        end
    endtask

    task false_start;
        begin
            @(negedge clk); serial_rx=0;
            @(negedge clk); serial_rx=1;
            repeat(2*BIT_CLKS) @(negedge clk);
        end
    endtask

    reg [31:0] expected_ack[0:1],wire_ack_start[0:1],wire_ack_end[0:1];
    integer ready_traces=0,done_traces=0,wire_acks=0,wire_bytes=0;
    reg [31:0] cycle_at_edge;
    reg previous_packet_valid=0,previous_ack_ready=0,previous_ack_done=0;
    always @(posedge clk) begin
        cycle_at_edge=time_cycles;
        if(!rst_n) time_cycles<=0;
        else begin
            time_cycles<=time_cycles+1'b1;
            if(cmd_valid && cmd_ready) begin
                if(command_words/2>=expected_packets) $fatal(1,"unexpected command emitted");
                if(command_words%2==0) begin
                    if(!cmd_first || cmd_last || cmd_data!==expected_header[command_words/2])
                        $fatal(1,"first command word changed by timestamp instrumentation");
                end else if(cmd_first || !cmd_last || cmd_data!==expected_value[command_words/2])
                    $fatal(1,"second command word changed by timestamp instrumentation");
                command_words=command_words+1;
            end
        end
        #2;
        if(rst_n) begin
            if((trace_packet_valid && previous_packet_valid) ||
               (trace_ack_ready && previous_ack_ready) || (trace_ack_done && previous_ack_done))
                $fatal(1,"trace events must be one-clock pulses");
            previous_packet_valid=trace_packet_valid;
            previous_ack_ready=trace_ack_ready;
            previous_ack_done=trace_ack_done;
            if(trace_packet_valid) begin
                if(packet_traces>=expected_packets) $fatal(1,"invalid packet published a latency trace");
                if(trace_packet_header!==expected_header[packet_traces] ||
                   trace_packet_start!==expected_start[packet_traces] || trace_packet_end!==cycle_at_edge)
                    $fatal(1,"packet trace mismatch index=%0d header=%h start=%h expected=%h end=%h now=%h",
                        packet_traces,trace_packet_header,trace_packet_start,expected_start[packet_traces],trace_packet_end,cycle_at_edge);
                if((trace_packet_end-trace_packet_start)!==32'(PACKET_ACCEPT_DELAY))
                    $fatal(1,"start-to-CRC interval mismatch: %0d",trace_packet_end-trace_packet_start);
                if(trace_packet_end<trace_packet_start) saw_packet_wrap=1;
                packet_traces=packet_traces+1;
            end
            if(trace_ack_ready) begin
                if(ready_traces>=2 || trace_ack_header!==expected_ack[ready_traces] || trace_ack_ready_time!==cycle_at_edge)
                    $fatal(1,"ACK acceptance trace does not identify its ready/valid edge");
                ready_traces=ready_traces+1;
            end
            if(trace_ack_done) begin
                if(done_traces>=2 || trace_ack_done_header!==expected_ack[done_traces] ||
                   trace_ack_done_time!==cycle_at_edge || wire_acks!=done_traces+1 ||
                   trace_ack_done_time!==wire_ack_end[done_traces])
                    $fatal(1,"ACK completion is premature or belongs to the next response: got header=%h time=%h wire_count=%0d",
                        trace_ack_done_header,trace_ack_done_time,wire_acks);
                if(trace_ack_done_time<wire_ack_start[done_traces]) saw_ack_wrap=1;
                done_traces=done_traces+1;
            end
        end
    end

    // Independent UART sink samples only serial_tx, never transmitter state.
    // It waits through the entire stop bit, rather than stopping at its center.
    reg [7:0] decoded_byte,reply[0:7];
    reg [15:0] decoded_crc;
    reg [31:0] byte_wire_start;
    integer data_bit,reply_index=0,crc_index;
    initial begin
        forever begin
            @(negedge serial_tx);
            if(rst_n) begin
                #1; byte_wire_start=time_cycles-1'b1;
                if(reply_index==0) wire_ack_start[wire_acks]=byte_wire_start;
                repeat(BIT_CLKS/2) @(posedge clk);
                #1; if(serial_tx!==0) $fatal(1,"bad ACK start bit");
                for(data_bit=0;data_bit<8;data_bit=data_bit+1) begin
                    repeat(BIT_CLKS) @(posedge clk);
                    #1; decoded_byte[data_bit]=serial_tx;
                end
                repeat(BIT_CLKS) @(posedge clk);
                #1; if(serial_tx!==1) $fatal(1,"bad ACK stop bit");
                reply[reply_index]=decoded_byte;
                repeat(BIT_CLKS/2) @(posedge clk);
                #1; if(serial_tx!==1) $fatal(1,"ACK stop bit shortened");
                wire_bytes=wire_bytes+1;
                if(reply_index==7) begin
                    wire_ack_end[wire_acks]=time_cycles-1'b1;
                    if((wire_ack_end[wire_acks]-wire_ack_start[wire_acks])!==32'(ACK_WIRE_DELAY))
                        $fatal(1,"ACK serial duration changed");
                    if(reply[0]!==8'ha5 || reply[1]!==8'h5a ||
                       {reply[2],reply[3],reply[4],reply[5]}!==expected_ack[wire_acks])
                        $fatal(1,"ACK bytes changed by instrumentation");
                    decoded_crc=16'hffff;
                    for(crc_index=2;crc_index<6;crc_index=crc_index+1)
                        decoded_crc=crc_byte(decoded_crc,reply[crc_index]);
                    if({reply[7],reply[6]}!==decoded_crc) $fatal(1,"ACK CRC mismatch");
                    wire_acks=wire_acks+1; reply_index=0;
                end else reply_index=reply_index+1;
            end
        end
    end

    task give_response(input [31:0] value);
        begin
            @(negedge clk);
            while(!rsp_ready) @(negedge clk);
            rsp_data=value; rsp_valid=1;
            @(negedge clk); rsp_valid=0;
        end
    endtask

    integer old_traces,old_errors;
    reg [31:0] saved_start,saved_end,saved_header;
    initial begin
        repeat(4) @(negedge clk); rst_n=1;
        repeat(4) @(negedge clk);
        false_start();
        if(packet_traces || error_count) $fatal(1,"false start escaped receiver qualification");
        send_packet(1,32'h12345678,0,0,1);
        send_packet(2,32'h7abcdef0,0,1,1);
        saved_start=trace_packet_start; saved_end=trace_packet_end; saved_header=trace_packet_header;
        old_traces=packet_traces; old_errors=error_count;
        send_packet(3,32'h11111111,1,0,0);
        false_start();
        if(packet_traces!=old_traces || error_count!=old_errors+1 ||
           trace_packet_start!==saved_start || trace_packet_end!==saved_end || trace_packet_header!==saved_header)
            $fatal(1,"bad CRC or false start corrupted the last accepted trace");
        send_packet(4,32'h22222222,0,0,1);

        old_traces=packet_traces; old_errors=error_count;
        @(negedge clk); send_byte(8'ha5,0); send_byte(8'h5a,0); send_byte(8'h77,0);
        repeat(35*BIT_CLKS) @(negedge clk);
        if(packet_traces!=old_traces || error_count!=old_errors+1) $fatal(1,"partial packet timeout changed a valid trace");
        send_packet(5,32'h33333333,0,0,1);
        old_traces=packet_traces; old_errors=error_count;
        @(negedge clk); send_byte(8'ha5,1);
        repeat(2*BIT_CLKS) @(negedge clk);
        if(packet_traces!=old_traces || error_count!=old_errors+1) $fatal(1,"framing error changed a valid trace");
        send_packet(6,32'h44444444,0,0,1);

        // CRC acceptance is measured before a potentially delayed command
        // transfer. A following valid CRC cannot overwrite the blocked record.
        @(negedge clk); cmd_ready=0;
        send_packet(7,32'h55555555,0,0,1);
        old_traces=packet_traces; old_errors=error_count;
        repeat(40) @(negedge clk);
        if(!cmd_valid || !cmd_first || cmd_data!==32'h07011f00 || packet_traces!=old_traces)
            $fatal(1,"command or packet trace changed under backpressure");
        send_packet(8,32'h66666666,0,0,0);
        if(packet_traces!=old_traces || error_count!=old_errors+1 || trace_packet_header!==32'h07011f00)
            $fatal(1,"occupied emitter published an unaccepted packet");
        @(negedge clk); cmd_ready=1;
        repeat(4) @(negedge clk);

        @(negedge clk); time_cycles=32'hfffffc00;
        send_packet(9,32'h77777777,0,0,1);
        repeat(4) @(negedge clk);
        if(!saw_packet_wrap || packet_traces!=expected_packets || command_words!=2*expected_packets)
            $fatal(1,"packet coverage incomplete");

        expected_ack[0]=32'h1100a501; expected_ack[1]=32'h22005a02;
        @(negedge clk); time_cycles=32'hfffffc00;
        give_response(expected_ack[0]);
        wait(dut.final_byte_inflight);
        if(done_traces!=0 || !rsp_ready) $fatal(1,"last byte launch misreported as ACK completion");
        give_response(expected_ack[1]);
        if(done_traces!=0 || dut.response!==expected_ack[1]) $fatal(1,"next response did not overlap the preceding CRC byte");
        wait(done_traces==2);
        repeat(4) @(negedge clk);
        if(ready_traces!=2 || wire_acks!=2 || wire_bytes!=16 || !saw_ack_wrap)
            $fatal(1,"ACK coverage incomplete");
        $display("PASS UART latency: exact synchronized start/CRC timestamps, A5 overlap, CRC/false-start/framing/timeout rejection, command backpressure, full-stop ACK completion with overlapping next response, serial CRC/data unchanged and 32-bit time wrap");
        $finish;
    end
    initial begin #2000000; $fatal(1,"UART latency timeout"); end
endmodule
