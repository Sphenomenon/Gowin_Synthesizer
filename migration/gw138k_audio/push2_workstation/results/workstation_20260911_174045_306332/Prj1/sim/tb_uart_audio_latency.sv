`timescale 1ns/1ps
// Full digital measurement chain. UART uses 16 clocks/bit for test speed;
// the real 50MHz timebase, 32-voice compute and 1024-clock DAC period remain.
module tb_uart_audio_latency;
    localparam integer BIT_CLKS=16;
    localparam [7:0] NOTE_SEQUENCE=8'h51;
    localparam [31:0] NOTE_HEADER={NOTE_SEQUENCE,8'h01,8'h1f,8'h00};
    reg clk=0;
    always #10 clk=~clk;
    reg rst_n=0,serial_rx=1;
    reg [31:0] time_cycles=0;
    always @(posedge clk or negedge rst_n)
        if(!rst_n) time_cycles<=0; else time_cycles<=time_cycles+1'b1;
    wire serial_tx;
    wire [31:0] cmd_data,rsp_data,uart_errors;
    wire cmd_valid,cmd_ready,cmd_first,cmd_last,rsp_valid,rsp_ready;
    wire trace_packet_valid,trace_ack_ready,trace_ack_done;
    wire [31:0] trace_packet_header,trace_packet_start,trace_packet_end;
    wire [31:0] trace_ack_header,trace_ack_ready_time,trace_ack_done_header,trace_ack_done_time;
    uart_control #(.CLK_HZ(1843200),.BAUD(115200)) link(
        .clk(clk),.rst_n(rst_n),.uart_rx(serial_rx),.uart_tx(serial_tx),.time_cycles(time_cycles),
        .cmd_data(cmd_data),.cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_first(cmd_first),.cmd_last(cmd_last),
        .rsp_data(rsp_data),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.error_count(uart_errors),
        .trace_packet_valid(trace_packet_valid),.trace_packet_header(trace_packet_header),
        .trace_packet_start(trace_packet_start),.trace_packet_end(trace_packet_end),
        .trace_ack_ready(trace_ack_ready),.trace_ack_header(trace_ack_header),.trace_ack_ready_time(trace_ack_ready_time),
        .trace_ack_done(trace_ack_done),.trace_ack_done_header(trace_ack_done_header),.trace_ack_done_time(trace_ack_done_time));
    wire signed [31:0] sample_data;
    wire sample_valid,sample_tick;
    wire [31:0] active_voices,trigger_reference,sample_nonzero_voices;
    wire trace_commit,trace_frame_start,trace_sample_event;
    wire [31:0] trace_header,trace_nonzero_voices;
    wire [23:0] trace_revision,trace_sample_revision;
    wire [511:0] latency_diagnostics;
    synth_engine #(.VOICE_COUNT(32)) engine(.onset_query_request(),.onset_query_voice(),
        .onset_query_done(1'b0),.onset_query_data(256'd0),
        .clk(clk),.rst_n(rst_n),.sample_tick(sample_tick),
        .cmd_data(cmd_data),.cmd_valid(cmd_valid),.cmd_ready(cmd_ready),.cmd_first(cmd_first),.cmd_last(cmd_last),
        .rsp_data(rsp_data),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),
        .sample_data(sample_data),.sample_valid(sample_valid),.active_voices(active_voices),.trigger_reference(trigger_reference),
        .memory_flags(8'd0),.video_diagnostics(128'd0),.latency_diagnostics(latency_diagnostics),
        .trace_commit(trace_commit),.trace_header(trace_header),.trace_revision(trace_revision),
        .trace_frame_start(trace_frame_start),.trace_sample_event(trace_sample_event),
        .trace_sample_revision(trace_sample_revision),.trace_nonzero_voices(trace_nonzero_voices),
        .sample_nonzero_voices(sample_nonzero_voices));
    wire hp_bck,hp_ws,hp_din,pa_en,trace_dac_done;
    wire [31:0] underrun_count,frame_count,trace_dac_nonzero_voices;
    wire [23:0] trace_dac_revision;
    pt8211_tx audio_output(
        .clk(clk),.reset_n(rst_n),.sample_data(sample_data),.sample_valid(sample_valid),
        .sample_tick(sample_tick),.hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),
        .underrun_count(underrun_count),.frame_count(frame_count),
        .sample_revision(trigger_reference[31:8]),.sample_nonzero_voices(sample_nonzero_voices),
        .trace_dac_done(trace_dac_done),.trace_dac_revision(trace_dac_revision),
        .trace_dac_nonzero_voices(trace_dac_nonzero_voices));
    audio_latency_monitor monitor(
        .clk(clk),.rst_n(rst_n),.time_cycles(time_cycles),
        .packet_valid(trace_packet_valid),.packet_header(trace_packet_header),
        .packet_start(trace_packet_start),.packet_end(trace_packet_end),
        .command_commit(trace_commit),.command_header(trace_header),.command_revision(trace_revision),
        .frame_start(trace_frame_start),.sample_event(trace_sample_event),
        .sample_revision(trace_sample_revision),.nonzero_voices(trace_nonzero_voices),
        .dac_done(trace_dac_done),.dac_revision(trace_dac_revision),.dac_nonzero_voices(trace_dac_nonzero_voices),
        .ack_ready(trace_ack_ready),.ack_header(trace_ack_header),.ack_ready_time(trace_ack_ready_time),
        .ack_done(trace_ack_done),.ack_done_header(trace_ack_done_header),.ack_done_time(trace_ack_done_time),
        .diagnostics(latency_diagnostics));

    function [15:0] crc_byte(input [15:0] initial_crc,input [7:0] value);
        reg [15:0] result;
        integer b;
        begin
            result=initial_crc^{value,8'b0};
            for(b=0;b<8;b=b+1) result=result[15] ? (result<<1)^16'h1021 : result<<1;
            crc_byte=result;
        end
    endfunction
    function [31:0] live_word(input integer index);
        live_word=latency_diagnostics[index*32+:32];
    endfunction
    reg [7:0] snapshot[0:63];
    function [31:0] snap_word(input integer index);
        snap_word={snapshot[index*4+3],snapshot[index*4+2],snapshot[index*4+1],snapshot[index*4]};
    endfunction

    task byte_out(input [7:0] value);
        integer b;
        begin
            serial_rx=0; repeat(BIT_CLKS) @(negedge clk);
            for(b=0;b<8;b=b+1) begin serial_rx=value[b]; repeat(BIT_CLKS) @(negedge clk); end
            serial_rx=1; repeat(BIT_CLKS) @(negedge clk);
        end
    endtask
    reg [31:0] note_pin_detect_expected;
    task packet(input [7:0] seq,input [7:0] opcode,input [7:0] voice,input [31:0] value,input bad_crc);
        integer b;
        reg [7:0] octet;
        reg [15:0] crc;
        begin
            @(negedge clk);
            if(seq==NOTE_SEQUENCE && !bad_crc) note_pin_detect_expected=time_cycles+2;
            byte_out(8'ha5); byte_out(8'h5a); crc=16'hffff;
            for(b=0;b<8;b=b+1) begin
                case(b)
                    0:octet=seq; 1:octet=opcode; 2:octet=voice; 3:octet=0;
                    4:octet=value[7:0]; 5:octet=value[15:8]; 6:octet=value[23:16]; 7:octet=value[31:24];
                endcase
                byte_out(octet); crc=crc_byte(crc,octet);
            end
            byte_out(crc[7:0]^{7'd0,bad_crc}); byte_out(crc[15:8]);
        end
    endtask

    // Full ACK decoder uses only the FPGA TX pin, including its complete
    // final stop bit. No internal transmitter state is used to find the end.
    integer ack_count=0,ack_index=0,ack_bit,j;
    reg [7:0] ack_bytes[0:7],ack_octet;
    reg [31:0] latest_ack,ack_first_time,note_ack_wire_start,note_ack_wire_done;
    reg [15:0] ack_crc;
    initial begin
        forever begin
            @(negedge serial_tx);
            if(rst_n) begin
                #1;
                if(ack_index==0) ack_first_time=time_cycles-1'b1;
                repeat(BIT_CLKS/2) @(posedge clk);
                #1; if(serial_tx!==0) $fatal(1,"bad UART ACK start");
                for(ack_bit=0;ack_bit<8;ack_bit=ack_bit+1) begin
                    repeat(BIT_CLKS) @(posedge clk);
                    #1; ack_octet[ack_bit]=serial_tx;
                end
                repeat(BIT_CLKS) @(posedge clk);
                #1; if(serial_tx!==1) $fatal(1,"bad UART ACK stop");
                ack_bytes[ack_index]=ack_octet;
                repeat(BIT_CLKS/2) @(posedge clk);
                #1; if(serial_tx!==1) $fatal(1,"shortened UART ACK stop");
                if(ack_index==7) begin
                    if(ack_bytes[0]!==8'ha5 || ack_bytes[1]!==8'h5a) $fatal(1,"bad UART ACK sync");
                    ack_crc=16'hffff;
                    for(j=2;j<6;j=j+1) ack_crc=crc_byte(ack_crc,ack_bytes[j]);
                    if({ack_bytes[7],ack_bytes[6]}!==ack_crc) $fatal(1,"bad UART ACK CRC");
                    latest_ack={ack_bytes[2],ack_bytes[3],ack_bytes[4],ack_bytes[5]};
                    if(latest_ack[31:24]==NOTE_SEQUENCE && latest_ack[7:0]==1) begin
                        note_ack_wire_start=ack_first_time; note_ack_wire_done=time_cycles-1'b1;
                    end
                    ack_count=ack_count+1; ack_index=0;
                end else ack_index=ack_index+1;
            end
        end
    end
    task transact(input [7:0] seq,input [7:0] opcode,input [7:0] voice,input [31:0] value,input [7:0] status);
        integer before_ack,deadline;
        begin
            before_ack=ack_count;
            packet(seq,opcode,voice,value,0);
            deadline=0;
            while(ack_count==before_ack && deadline<5000) begin @(negedge clk); deadline=deadline+1; end
            if(ack_count!=before_ack+1 || latest_ack[31:24]!==seq || latest_ack[7:0]!==opcode || latest_ack[23:16]!==status)
                $fatal(1,"unexpected/missing ACK seq=%h op=%h got=%h count=%0d",seq,opcode,latest_ack,ack_count-before_ack);
            repeat(2) @(negedge clk);
        end
    endtask

    // Observe source events at their actual 50MHz edges. The endpoint is
    // independently decoded below from the complete physical stereo words.
    reg target_committed=0,old_frame_seen=0,state_sample_seen=0,note_sample_seen=0,dac_state_seen=0;
    reg [31:0] target_start,target_packet_end,target_commit,state_sample_time,note_sample_time,dac_state_time;
    reg [31:0] target_ack_ready,target_raw_ack_ready,target_ack_done,committed_count=0,target_trace_id;
    reg [23:0] target_revision;
    reg [31:0] last_frame_time=0;
    reg frame_seen=0;
    reg [31:0] pending_header=0;
    reg pending_snapshot=0,snapshot_captured=0;
    reg [511:0] expected_snapshot;
    always @(posedge clk) begin
        if(rst_n) begin
            if(rsp_valid && rsp_ready && rsp_data[31:24]==NOTE_SEQUENCE && rsp_data[7:0]==1)
                target_raw_ack_ready=time_cycles;
            if(trace_packet_valid && trace_packet_header==NOTE_HEADER) begin
                target_start=trace_packet_start; target_packet_end=trace_packet_end;
                if(target_start!==note_pin_detect_expected) $fatal(1,"packet origin does not match synchronized physical start");
            end
            if(trace_commit) begin
                committed_count=committed_count+1;
                if(trace_header==NOTE_HEADER) begin
                    target_committed=1; target_commit=time_cycles; target_revision=trace_revision;
                    target_trace_id=committed_count;
                end
            end
            if(trace_frame_start) begin
                if(frame_seen && frame_count>3 && time_cycles-last_frame_time!=1024)
                    $fatal(1,"DAC-driven sample cadence changed");
                last_frame_time=time_cycles; frame_seen=1;
                if(pending_snapshot) begin
                    expected_snapshot=latency_diagnostics; snapshot_captured=1; pending_snapshot=0;
                end
            end
            if(cmd_valid && cmd_ready) begin
                if(cmd_first) pending_header=cmd_data;
                if(cmd_last && pending_header[23:16]==8'h0e && cmd_data==0) pending_snapshot=1;
            end
            if(target_committed && trace_sample_event) begin
                if(time_cycles-target_commit==226) begin
                    if(trace_sample_revision==target_revision || trace_nonzero_voices[31])
                        $fatal(1,"NOTE_ON commit frame's old state was labeled as the new note");
                    old_frame_seen=1;
                end
                if(trace_sample_revision==target_revision && !state_sample_seen) begin
                    state_sample_seen=1; state_sample_time=time_cycles;
                    if(trace_nonzero_voices[31]) $fatal(1,"zero-envelope first new-state sample fabricated onset");
                end
                if(trace_sample_revision==target_revision && trace_nonzero_voices[31] && !note_sample_seen) begin
                    note_sample_seen=1; note_sample_time=time_cycles;
                end
            end
            if(target_committed && trace_dac_done && trace_dac_revision==target_revision && !dac_state_seen) begin
                dac_state_seen=1; dac_state_time=time_cycles;
            end
            if(trace_ack_ready && trace_ack_header[31:24]==NOTE_SEQUENCE && trace_ack_header[7:0]==1)
                target_ack_ready=trace_ack_ready_time;
            if(trace_ack_done && trace_ack_done_header[31:24]==NOTE_SEQUENCE && trace_ack_done_header[7:0]==1)
                target_ack_done=trace_ack_done_time;
        end
    end

    integer pcm_bit=0,pcm_frames=0;
    reg [15:0] pcm_shift=0,right_pcm=0;
    reg physical_note_seen=0;
    reg [31:0] physical_note_done;
    always @(posedge hp_bck) begin
        if(rst_n) begin
            #1;
            if(hp_ws!==(pcm_bit>=16)) $fatal(1,"PT8211 WS does not match independent stereo bit count");
            pcm_shift={pcm_shift[14:0],hp_din};
            if(pcm_bit==15) right_pcm=pcm_shift;
            if(pcm_bit==31) begin
                if(pcm_shift!==right_pcm) $fatal(1,"PT8211 stereo words disagree");
                pcm_frames=pcm_frames+1;
                if(pcm_shift!=0 && !physical_note_seen) begin
                    if(!target_committed || pa_en) $fatal(1,"nonzero PCM before target note or amplifier warmup complete");
                    if(pcm_shift!==16'h7fff) $fatal(1,"first pulse sample not expected single-voice full-scale PCM: %h",pcm_shift);
                    physical_note_seen=1; physical_note_done=time_cycles-1'b1;
                end
            end
            pcm_bit=(pcm_bit+1)%32;
        end
    end

    reg [447:0] completed_target;
    integer previous_acks,previous_errors,k;
    initial begin
        repeat(4) @(negedge clk); rst_n=1;
        // Let the actual 512-frame amplifier startup guard complete. This
        // remains a digital transport test, not an analog onset measurement.
        wait(frame_count>=520);
        transact(1,5,31,1,0);                  // positive pulse at phase zero
        transact(2,4,31,32'h80000000,0);       // unity velocity
        transact(3,6,31,0,0);                  // immediate attack
        transact(4,7,31,0,0);                  // immediate decay
        transact(5,8,31,32'h80000000,0);       // unity sustain
        transact(6,9,31,0,0);                  // immediate release
        transact(NOTE_SEQUENCE,1,31,32'h01000000,0);
        wait(physical_note_seen && live_word(1)==127);
        repeat(2) @(negedge clk);
        if(!old_frame_seen || !state_sample_seen || !note_sample_seen || !dac_state_seen)
            $fatal(1,"missing old-state or first-state/nonzero endpoint coverage");
        if(state_sample_time-target_commit!=1250 || note_sample_time-target_commit!=2274)
            $fatal(1,"unexpected 32-voice state/onset latency state=%0d note=%0d",state_sample_time-target_commit,note_sample_time-target_commit);
        if(target_packet_end-target_start!=119*BIT_CLKS+BIT_CLKS/2+1 ||
           target_ack_ready!==target_raw_ack_ready || target_raw_ack_ready-target_commit!=227)
            $fatal(1,"UART receive/ACK-acceptance timestamps do not match physical receive length or raw response handshake");
        if(target_ack_done!==note_ack_wire_done || note_ack_wire_done-note_ack_wire_start!=80*BIT_CLKS+7)
            $fatal(1,"ACK completion does not match independently decoded full stop bit");
        if(live_word(0)!==32'h1f015101 || live_word(1)!==127 || live_word(2)!==target_trace_id || target_trace_id!=7 ||
           live_word(3)!==50000000 || live_word(4)!==target_packet_end-target_start ||
           live_word(5)!==target_commit-target_packet_end || live_word(6)!==state_sample_time-target_commit ||
           live_word(7)!==note_sample_time-target_commit || live_word(8)!==dac_state_time-target_commit ||
           live_word(9)!==physical_note_done-target_commit || live_word(10)!==target_ack_ready-target_start ||
           live_word(11)!==note_ack_wire_done-target_start || live_word(12)!==226 || live_word(13)!==1024)
            $fatal(1,"live telemetry differs from independent observed stage events");
        completed_target=latency_diagnostics[447:0];

        // Corrupt input and valid-CRC illegal notes never replace this sound
        // record. PING and all 0E queries also remain observation-only.
        previous_acks=ack_count; previous_errors=uart_errors;
        packet(8'h52,1,31,32'h02000000,1);
        repeat(3500) @(negedge clk);
        if(ack_count!=previous_acks || uart_errors!=previous_errors+1 || latency_diagnostics[447:0]!==completed_target)
            $fatal(1,"bad CRC replaced target latency record or produced ACK");
        transact(8'h53,1,32,32'h01000000,2);
        transact(8'h54,1,31,32'h80000000,3);
        transact(8'h55,0,255,0,0);
        if(latency_diagnostics[447:0]!==completed_target || committed_count!=7)
            $fatal(1,"invalid note or PING replaced target latency record");

        transact(8'h90,14,255,0,0);
        snapshot[0]=latest_ack[15:8];
        if(!snapshot_captured || latency_diagnostics[447:0]!==completed_target)
            $fatal(1,"0E byte zero did not create a passive snapshot");
        // Change the live sound/diagnostic record after snapshot byte zero.
        // Remaining 63 serial replies must still describe the old NOTE_ON.
        transact(8'h80,10,255,0,0);
        if(live_word(2)!==target_trace_id+1 || live_word(0)!==32'hff0a8001)
            $fatal(1,"PANIC failed to replace the live sound record");
        for(k=1;k<64;k=k+1) begin
            transact(8'h90+k,14,255,k,0);
            snapshot[k]=latest_ack[15:8];
            if(live_word(2)!==target_trace_id+1) $fatal(1,"diagnostic query incremented sound trace ID");
        end
        for(k=0;k<64;k=k+1)
            if(snapshot[k]!==expected_snapshot[k*8+:8]) $fatal(1,"torn 0E snapshot byte %0d got %h expected %h",k,snapshot[k],expected_snapshot[k*8+:8]);
        if(snap_word(0)!==32'h1f015101 || snap_word(1)!==127 || snap_word(2)!==7 || snap_word(3)!==50000000 ||
           snap_word(9)!==physical_note_done-target_commit || snap_word(12)!==226 || snap_word(13)!==1024)
            $fatal(1,"serial 0E schema, metadata or digital endpoint mismatch");
        if(underrun_count!==0 || active_voices!==0) $fatal(1,"measurement/query traffic disturbed audio transport");
        $display("UART_AUDIO_LATENCY ticks@50MHz: start=%0d crc=%0d commit=%0d first_state=%0d first_note=%0d first_pcm_stereo_done=%0d ack_ready=%0d ack_full_stop=%0d",
            target_start,target_packet_end,target_commit,state_sample_time,note_sample_time,physical_note_done,target_ack_ready,target_ack_done);
        $display("UART_AUDIO_LATENCY stage ticks: rx=%0d commit_wait=%0d state=%0d note=%0d dac_state=%0d dac_note=%0d ack_ready_from_start=%0d ack_done_from_start=%0d compute=%0d period=%0d snapshot_age=%0d",
            snap_word(4),snap_word(5),snap_word(6),snap_word(7),snap_word(8),snap_word(9),snap_word(10),snap_word(11),snap_word(12),snap_word(13),snap_word(14));
        $display("PASS UART audio latency integration: actual serial command/ACK CRC, engine32 old-state exclusion, independently decoded positive PCM16 stereo endpoint, complete atomic 64-byte 0E snapshot across PANIC, invalid-input/query isolation and zero DAC underruns; %0d PCM frames",pcm_frames);
        $finish;
    end
    initial begin #40000000; $fatal(1,"UART audio latency timeout"); end
endmodule
