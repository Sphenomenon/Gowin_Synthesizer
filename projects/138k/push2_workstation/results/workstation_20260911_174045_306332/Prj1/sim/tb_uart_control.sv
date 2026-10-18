`timescale 1ns/1ps
// UART -> committed command -> synth -> PT8211 serial PCM, with UART ACK decoding.
// Dividers are accelerated for functional simulation, not a board latency measurement.
module tb_uart_control;
    wire [7:0] memory_flags=8'hc3;
    wire [127:0] video_diagnostics=128'hffeeddccbbaa99887766554433221101;
    localparam integer BIT_CLKS=16;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0, serial_rx=1;
    wire serial_tx;
    wire [31:0] cmd_data,rsp_data,error_count,active_voices;
    wire cmd_valid,cmd_ready,cmd_first,cmd_last,rsp_valid,rsp_ready;
    wire signed [31:0] sample_data;
    wire [31:0] trigger_reference;
    wire sample_valid;
    wire sample_tick, hp_bck, hp_ws, hp_din, pa_en;
    wire [31:0] underrun_count, frame_count;
    pt8211_tx #(.BCK_HALF_CYCLES(1)) audio_output(
        .clk(clk),.reset_n(rst_n),.sample_data(sample_data),.sample_valid(sample_valid),
        .sample_tick(sample_tick),.hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),
        .pa_en(pa_en),.underrun_count(underrun_count),.frame_count(frame_count));
    uart_control #(.CLK_HZ(1843200),.BAUD(115200)) link(
        .clk(clk),.rst_n(rst_n),.uart_rx(serial_rx),.uart_tx(serial_tx),
        .time_cycles(32'd0),
        .cmd_data(cmd_data),.cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_first(cmd_first),.cmd_last(cmd_last),
        .rsp_data(rsp_data),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.error_count(error_count));
    synth_engine #(.VOICE_COUNT(4)) engine(.onset_query_request(),.onset_query_voice(),
        .onset_query_done(1'b0),.onset_query_data(256'd0),.latency_diagnostics(512'd0),.trace_commit(),.trace_header(),.trace_revision(),
        .trace_frame_start(),.trace_sample_event(),.trace_sample_revision(),.trace_nonzero_voices(),
        .sample_nonzero_voices(),.mix_sum(),.voice_sample_event(),.voice_sample_data(),
        .voice_sample_index(),.master_volume(),.lr_balance(),.*);
    wire [31:0] reply_byte;
    wire reply_valid,reply_error;
    uart_rx #(.CLK_HZ(1843200),.BAUD(115200)) host_rx(
        .clk(clk),.rst_n(rst_n),.serial_in(serial_tx),.time_cycles(32'd0),
        .byte_start_time(),.data(reply_byte),.valid(reply_valid),.framing_error(reply_error));
    function [15:0] crc_byte(input [15:0] c0,input [7:0] b);
        reg [15:0] c; integer k;
        begin c=c0^{b,8'b0}; for(k=0;k<8;k=k+1) c=c[15]?(c<<1)^16'h1021:c<<1; crc_byte=c; end
    endfunction
    task byte_out(input [7:0] b);
        integer k;
        begin
            serial_rx=0; repeat(BIT_CLKS) @(negedge clk);
            for(k=0;k<8;k=k+1) begin serial_rx=b[k]; repeat(BIT_CLKS) @(negedge clk); end
            serial_rx=1; repeat(BIT_CLKS) @(negedge clk);
        end
    endtask
    task packet(input [7:0] seq,input [7:0] op,input [7:0] voice,input [31:0] value,input bad_crc);
        reg [15:0] c; integer k; reg [7:0] b;
        begin
            c=16'hffff; @(negedge clk); byte_out(8'ha5); byte_out(8'h5a);
            for(k=0;k<8;k=k+1) begin
                case(k)
                    0:b=seq; 1:b=op; 2:b=voice; 3:b=0;
                    4:b=value[7:0];5:b=value[15:8];6:b=value[23:16];7:b=value[31:24];
                endcase
                byte_out(b); c=crc_byte(c,b);
            end
            byte_out(c[7:0]^{7'b0,bad_crc}); byte_out(c[15:8]);
        end
    endtask
    integer ack_count=0, reply_index=0, command_words=0;
    reg [7:0] reply [0:7];
    reg [31:0] latest_ack;
    reg heard_sample=0;
    reg heard_pcm=0;
    reg [15:0] reference_latest=0, expected_frame=0, pcm_shift=0, latest_right=0, latest_left=0;
    integer pcm_bit=0, decoded_slots=0;
    // Independent sign/magnitude reference for nearest PCM16, ties away from zero.
    function [15:0] reference_pcm16(input signed [31:0] value);
        longint signed magnitude, rounded;
        begin
            magnitude=value;
            if(magnitude<0) magnitude=-magnitude;
            rounded=(magnitude+32768)/65536;
            if(value<0) rounded=-rounded;
            if(rounded>32767) rounded=32767;
            if(rounded< -32768) rounded=-32768;
            reference_pcm16=rounded[15:0];
        end
    endfunction
    always @(posedge clk) if(rst_n && sample_valid) reference_latest=reference_pcm16(sample_data);
    always @(negedge hp_bck) begin
        #1;
        if(rst_n && pcm_bit==0) expected_frame=reference_latest;
    end
    // Decode only physical serial pins: no serializer state is inspected.
    always @(posedge hp_bck) begin
        if(rst_n) begin
            if(hp_ws !== (pcm_bit>=16)) $fatal(1,"PT8211 WS slot alignment");
            pcm_shift={pcm_shift[14:0],hp_din};
            if(pcm_bit==15 || pcm_bit==31) begin
                if(pcm_shift !== expected_frame) $fatal(1,"UART-to-PCM mismatch actual=%h expected=%h",pcm_shift,expected_frame);
                if(pcm_shift != 0) heard_pcm=1;
                if(pcm_bit==15) latest_right=pcm_shift; else latest_left=pcm_shift;
                decoded_slots=decoded_slots+1;
            end
            pcm_bit=(pcm_bit+1)%32;
        end
    end
    reg [15:0] check_crc;
    integer k;
    always @(posedge clk) begin
        if(rst_n) begin
            if(reply_error) $fatal(1,"invalid UART stop bit on FPGA reply");
            if(sample_valid && sample_data != 0) heard_sample<=1;
            if(cmd_valid && cmd_ready) begin
                if((command_words%2 == 0 && (!cmd_first || cmd_last)) ||
                   (command_words%2 == 1 && (cmd_first || !cmd_last))) $fatal(1,"command word boundaries");
                command_words=command_words+1;
            end
            if(reply_valid) begin
                reply[reply_index]=reply_byte[7:0];
                if(reply_index == 7) begin
                    if(reply[0] != 8'ha5 || reply[1] != 8'h5a) $fatal(1,"reply sync");
                    check_crc=16'hffff;
                    for(k=2;k<6;k=k+1) check_crc=crc_byte(check_crc,reply[k]);
                    if({reply[7],reply[6]} !== check_crc) $fatal(1,"reply CRC");
                    latest_ack={reply[2],reply[3],reply[4],reply[5]};
                    ack_count=ack_count+1; reply_index=0;
                end else reply_index=reply_index+1;
            end
        end
    end
    task expect_ack(input integer number,input [7:0] seq,input [7:0] status,input [7:0] op);
        begin
            while(ack_count<number) @(negedge clk);
            if(latest_ack[31:24] !== seq || latest_ack[23:16] !== status || latest_ack[7:0] !== op)
                $fatal(1,"unexpected ACK %h",latest_ack);
        end
    endtask
    initial begin
        repeat(5) @(negedge clk); rst_n=1;
        packet(1,1,2,32'h10000000,1);
        repeat(600) @(negedge clk);
        if(command_words != 0 || ack_count != 0 || error_count != 1 || active_voices != 0)
            $fatal(1,"bad CRC executed or failed to count");
        // An abandoned packet times out; repeated sync bytes also recover.
        byte_out(8'ha5); byte_out(8'h5a); byte_out(8'h77);
        repeat(600) @(negedge clk);
        if(error_count != 2) $fatal(1,"partial packet did not time out");
        byte_out(8'ha5);
        packet(2,1,2,32'h10000000,0); expect_ack(1,2,0,1);
        if(latest_ack[15:8] != 4 || active_voices != 4 || command_words != 2) $fatal(1,"note-on not committed");
        if(!heard_sample || !heard_pcm) $fatal(1,"valid serial note-on produced no synthesized/serialized audio");
        packet(3,3,2,32'h0f000000,0); expect_ack(2,3,0,3);
        if(engine.bank.state_memory[2][229:198] !== 32'h0f000000 || engine.bank.state_memory[0][229:198] !== 0)
            $fatal(1,"serial per-note pitch independence");
        packet(4,4,2,32'hffffffff,0); expect_ack(3,4,3,4);
        if(engine.bank.state_memory[2][165:134] !== 32'h60000000) $fatal(1,"invalid gain applied");
        packet(5,10,8'hff,0,0); expect_ack(4,5,0,10);
        repeat(200) @(negedge clk);
        if(active_voices != 0 || sample_data != 0 || latest_right != 0 || latest_left != 0) $fatal(1,"serial panic failed");
        if(underrun_count != 0 || decoded_slots<20) $fatal(1,"PCM underrun or missing frames");
        packet(6,12,8'hff,0,0); expect_ack(5,6,0,12);
        if(latest_ack[15:8] !== 1) $fatal(1,"serial video schema byte");
        packet(7,12,8'hff,15,0); expect_ack(6,7,0,12);
        if(latest_ack[15:8] !== 8'hff) $fatal(1,"serial video last byte/CRC");
        packet(8,12,8'hff,16,0); expect_ack(7,8,3,12);
        if(active_voices != 0 || underrun_count != 0) $fatal(1,"video query affected audio");
        $display("PASS tb_uart_control: UART CRC/recovery -> independent synth -> matched PT8211 stereo PCM; ACK CRC, panic, no underruns");
        $finish;
    end
    initial begin #2000000; $fatal(1,"UART integration timeout"); end
endmodule
