`timescale 1ns/1ps
module tb_synth_engine;
    reg [7:0] memory_flags=8'hc3;
    reg [127:0] video_diagnostics=128'hffeeddccbbaa99887766554433221101;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0, sample_tick=0, cmd_valid=0, cmd_first=0, cmd_last=0, rsp_ready=0;
    reg [31:0] cmd_data=0;
    wire cmd_ready, rsp_valid, sample_valid;
    wire [31:0] rsp_data, active_voices;
    wire signed [31:0] sample_data;
    wire [31:0] trigger_reference;
    synth_engine #(.VOICE_COUNT(4)) dut(.onset_query_request(),.onset_query_voice(),
        .onset_query_done(1'b0),.onset_query_data(256'd0),.latency_diagnostics(512'd0),.trace_commit(),.trace_header(),.trace_revision(),
        .trace_frame_start(),.trace_sample_event(),.trace_sample_revision(),.trace_nonzero_voices(),
        .sample_nonzero_voices(),.mix_sum(),.voice_sample_event(),.voice_sample_data(),
        .voice_sample_index(),.master_volume(),.lr_balance(),.*);
    integer seq=0, j, n;
    reg [31:0] p0,p1,p2,p3, held_response;
    task frame;
        begin
            while(!dut.bank_ready) @(negedge clk);
            @(negedge clk); sample_tick=1;
            @(negedge clk); sample_tick=0;
            repeat(33) @(negedge clk);
        end
    endtask
    task send_words(input [7:0] op,input [7:0] voice,input [31:0] value,input [7:0] flags=0);
        begin
            @(negedge clk);
            while(!cmd_ready) @(negedge clk);
            cmd_valid=1; cmd_first=1; cmd_last=0; cmd_data={seq[7:0],op,voice,flags};
            @(negedge clk); cmd_first=0; cmd_last=1; cmd_data=value;
            @(negedge clk); cmd_valid=0; cmd_last=0;
        end
    endtask
    task ack(input [7:0] status);
        begin
            if(!rsp_valid || rsp_data[23:16] != status || rsp_data[31:24] != seq[7:0])
                $fatal(1,"unexpected response %h, seq=%0d status=%0d",rsp_data,seq,status);
            held_response=rsp_data;
            repeat(3) begin @(negedge clk); if(rsp_data !== held_response || !rsp_valid || cmd_ready)
                $fatal(1,"response not stable under backpressure"); end
            rsp_ready=1; @(negedge clk); rsp_ready=0; seq=seq+1;
        end
    endtask
    task command(input [7:0] op,input [7:0] voice,input [31:0] value,input [7:0] status);
        begin send_words(op,voice,value); frame; ack(status); end
    endtask
    initial begin
        repeat(4) @(negedge clk); rst_n=1;
        frame;
        if(sample_data !== 0 || active_voices !== 0) $fatal(1,"reset must be silent");
        for(j=0;j<4;j=j+1) begin
            command(6,j,0,0); command(7,j,0,0); command(8,j,32'h80000000,0);
            command(9,j,32'h40000000,0); command(4,j,32'h80000000,0);
        end
        send_words(1,0,32'h10000000);
        repeat(12) @(negedge clk);
        if(active_voices != 0) $fatal(1,"note committed outside frame boundary");
        frame; ack(0);
        for(j=1;j<4;j=j+1) command(1,j,32'h10000000+j*32'h01000000,0);
        repeat(4) frame;
        if(active_voices !== 32'hf) $fatal(1,"four voices did not activate");
        // Memory diagnostics occupy ACK byte 4 without changing voice state.
        p0=dut.bank.state_memory[0][261:230];
        send_words(8'h0b,8'hff,0); frame;
        if(rsp_data[15:8] !== 8'hc3 || rsp_data[7:0] !== 8'h0b)
            $fatal(1,"memory-status ACK payload incorrect: %h",rsp_data);
        if(active_voices !== 32'hf || dut.bank.state_memory[0][261:230] !== p0+32'h10000000)
            $fatal(1,"memory query affected voices/phase continuity");
        // Changing live flags while the ACK is backpressured must not change it.
        memory_flags=8'h3c; ack(0);
        send_words(8'h0b,8'hff,0); frame;
        if(rsp_data[15:8] !== 8'h3c) $fatal(1,"memory status was not refreshed");
        ack(0);
        command(8'h0b,0,0,2);
        command(8'h0b,8'hff,1,3);
        if(active_voices !== 32'hf) $fatal(1,"invalid memory query affected active voices");
        command(8'h0c,8'hff,1,3); // No snapshot until byte zero is accepted.
        send_words(8'h0c,8'hff,0);
        repeat(3) @(negedge clk);
        if(dut.video_snapshot_valid) $fatal(1,"video snapshot committed outside sample boundary");
        video_diagnostics=128'hffeeddccbbaa99887766554433221101;
        p0=dut.bank.state_memory[0][261:230];
        frame;
        if(rsp_data[15:8] !== 1 || rsp_data[7:0] !== 8'h0c)
            $fatal(1,"video schema ACK incorrect");
        if(active_voices !== 32'hf || dut.bank.state_memory[0][261:230] !== p0+32'h10000000)
            $fatal(1,"video query affected voices/phase continuity");
        video_diagnostics=0; ack(0);
        for(j=1;j<16;j=j+1) begin
            send_words(8'h0c,8'hff,j); frame;
            if(rsp_data[15:8] !== j*17) $fatal(1,"torn video snapshot index %0d: %h",j,rsp_data);
            ack(0);
        end
        command(8'h0c,0,0,2);
        command(8'h0c,8'hff,16,3);
        command(8'h0c,8'hff,32'h80000000,3);
        send_words(8'h0c,8'hff,0,1); frame; ack(3);
        send_words(8'h0c,8'hff,15); frame;
        if(rsp_data[15:8] !== 8'hff) $fatal(1,"rejected video query corrupted snapshot");
        ack(0);
        send_words(8'h0c,8'hff,0); frame;
        if(rsp_data[15:8] !== 0) $fatal(1,"video snapshot did not refresh");
        ack(0);
        send_words(0,8'hff,0); frame;
        if(rsp_data[15:8] !== 8'h0f || rsp_data[7:0] !== 0)
            $fatal(1,"PING stopped reporting active voices");
        ack(0);
        p0=dut.bank.state_memory[0][261:230]; p1=dut.bank.state_memory[1][261:230];
        p2=dut.bank.state_memory[2][261:230]; p3=dut.bank.state_memory[3][261:230];
        send_words(3,0,32'h07000000);
        if(dut.bank.state_memory[0][261:230] !== p0) $fatal(1,"phase moved between ticks");
        frame; ack(0);
        if(dut.bank.state_memory[0][261:230] !== p0+32'h10000000) $fatal(1,"pitch reset phase");
        if(dut.bank.state_memory[1][261:230] !== p1+32'h11000000 ||
           dut.bank.state_memory[2][261:230] !== p2+32'h12000000 ||
           dut.bank.state_memory[3][261:230] !== p3+32'h13000000) $fatal(1,"pitch affected other voices");
        if(dut.bank.state_memory[0][229:198] !== 32'h07000000) $fatal(1,"pitch was not applied");
        command(2,1,0,0); repeat(3) frame;
        if(active_voices !== 32'hd || dut.bank.state_memory[1][197:166] !== 0) $fatal(1,"independent release failed");
        command(4,4,32'h10000000,2); command(4,0,32'h80000001,3);
        command(8'hfe,0,0,1);
        command(10,8'hff,0,0); repeat(2) frame;
        if(active_voices !== 0 || sample_data !== 0) $fatal(1,"panic did not silence engine");
        // Four coherent full-scale voices must not wrap the signed mixer.
        for(j=0;j<4;j=j+1) begin command(5,j,1,0); command(1,j,0,0); end
        repeat(4) frame;
        if(sample_data !== 32'h7fffffff) $fatal(1,"positive full-scale mix incorrect: %h",sample_data);
        // Bring the coherent sum below clipping before checking one voice's
        // gain independently. Each 1/8-gain pulse is exactly 0x0fffffff.
        for(j=0;j<4;j=j+1) command(4,j,32'h10000000,0);
        repeat(2) frame;
        if(sample_data !== 32'h3ffffffc) $fatal(1,"unscaled low-level mix incorrect: %h",sample_data);
        command(4,0,0,0); repeat(2) frame;
        if(sample_data !== 32'h2ffffffd) $fatal(1,"independent velocity gain incorrect: %h",sample_data);
        command(10,8'hff,0,0); repeat(2) frame;
        // Nonzero attack/decay, bounded sustain and release endpoint.
        command(4,0,32'h80000000,0); command(6,0,32'h40000000,0);
        command(7,0,32'h20000000,0); command(8,0,32'h40000000,0);
        command(1,0,0,0);
        frame; if(dut.bank.state_memory[0][197:166] !== 32'h40000000) $fatal(1,"attack step");
        frame; if(dut.bank.state_memory[0][197:166] !== 32'h80000000) $fatal(1,"attack endpoint");
        frame; if(dut.bank.state_memory[0][197:166] !== 32'h60000000) $fatal(1,"decay step");
        frame; if(dut.bank.state_memory[0][197:166] !== 32'h40000000) $fatal(1,"sustain endpoint");
        command(2,0,0,0); frame;
        if(active_voices !== 0) $fatal(1,"release endpoint");
        $display("PASS tb_synth_engine: 4 voices, frame commits, independent pitch/ADSR/velocity, mixer, memory/video snapshots, rejection, ACK backpressure");
        $finish;
    end
    initial begin #20000000; $fatal(1,"test timeout"); end
endmodule
