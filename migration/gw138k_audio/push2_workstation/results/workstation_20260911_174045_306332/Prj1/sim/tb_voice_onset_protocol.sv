`timescale 1ns/1ps
// Exercise the engine/observer handshake independently of the observer's RAM.
module tb_voice_onset_protocol;
    reg clk=0; always #10 clk=~clk;
    reg rst_n=0, sample_tick=0;
    reg [31:0] cmd_data=0;
    reg cmd_valid=0,cmd_first=0,cmd_last=0,rsp_ready=1;
    wire cmd_ready,rsp_valid,sample_valid;
    wire [31:0] rsp_data,active_voices,trigger_reference;
    wire signed [31:0] sample_data;
    wire onset_query_request;
    wire [4:0] onset_query_voice;
    reg onset_query_done=0;
    reg [255:0] onset_query_data=0;
    reg [511:0] latency_diagnostics=0;
    synth_engine dut (
        .clk(clk),.rst_n(rst_n),.sample_tick(sample_tick),
        .cmd_data(cmd_data),.cmd_valid(cmd_valid),.cmd_ready(cmd_ready),
        .cmd_first(cmd_first),.cmd_last(cmd_last),.rsp_data(rsp_data),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.sample_data(sample_data),
        .sample_valid(sample_valid),.active_voices(active_voices),
        .trigger_reference(trigger_reference),.memory_flags(8'd0),.video_diagnostics(128'd0),
        .latency_diagnostics(latency_diagnostics),.onset_query_request(onset_query_request),
        .onset_query_voice(onset_query_voice),.onset_query_done(onset_query_done),
        .onset_query_data(onset_query_data),.trace_commit(),.trace_header(),.trace_revision(),
        .trace_frame_start(),.trace_sample_event(),.trace_sample_revision(),
        .trace_nonzero_voices(),.sample_nonzero_voices());

    integer divider=0,samples=0,query_count=0,wait_clocks=0,query_delay=7;
    integer i,j;
    reg [7:0] pattern=8'h40;
    reg [255:0] pending_data;
    always @(negedge clk) begin
        if (!rst_n) begin sample_tick=0; divider=0; end
        else begin
            sample_tick=(divider==0);
            divider=(divider+1)%1024;
        end
    end
    always @(posedge clk) begin
        if (rst_n && sample_valid) samples=samples+1;
        onset_query_done<=0;
        if (onset_query_request) begin
            if (wait_clocks) $fatal(1,"duplicate in-flight query");
            query_count=query_count+1;
            wait_clocks=query_delay;
            for (j=0;j<32;j=j+1) pending_data[j*8+:8]=pattern+j;
            pending_data[15:8]=onset_query_voice;
        end else if (wait_clocks>0) begin
            wait_clocks=wait_clocks-1;
            if (wait_clocks==0) begin
                onset_query_data<=pending_data;
                onset_query_done<=1;
            end
        end
    end
    task word(input [31:0] data,input first,input last);
        begin
            @(negedge clk);
            while (!cmd_ready) @(negedge clk);
            cmd_data=data;cmd_first=first;cmd_last=last;cmd_valid=1;
            @(negedge clk);cmd_valid=0;
        end
    endtask
    reg [7:0] seq=0;
    reg [31:0] reply;
    task request(input [7:0] op,input [7:0] voice,input [7:0] flags,
                 input [31:0] value,input [7:0] status);
        integer timeout;
        begin
            seq=seq+1;
            word({seq,op,voice,flags},1,0);word(value,0,1);
            timeout=0;
            while (!rsp_valid) begin
                @(negedge clk);timeout=timeout+1;
                if (timeout>6000) $fatal(1,"query ACK timeout");
            end
            reply=rsp_data;
            if (reply[31:24]!==seq || reply[23:16]!==status || reply[7:0]!==op)
                $fatal(1,"bad reply %h expected seq=%h op=%h status=%h",reply,seq,op,status);
            @(negedge clk);
        end
    endtask
    integer before_samples,before_queries;
    initial begin
        for (i=0;i<64;i=i+1) latency_diagnostics[i*8+:8]=8'h80+i;
        repeat(5) @(negedge clk);rst_n=1;
        request(8'h0f,31,0,1,3); // Requires index zero first.
        request(8'h0f,32,0,0,2);
        request(8'h0f,31,1,0,3);
        request(8'h0f,31,0,32,3);
        if (query_count) $fatal(1,"invalid input launched RAM query");
        before_samples=samples;
        request(8'h0f,31,0,0,0);
        if (reply[15:8]!==8'h40 || samples<=before_samples || query_count!=1)
            $fatal(1,"early query reply did not wait for bank commit");
        pattern=8'h60;onset_query_data=0;
        for (i=1;i<32;i=i+1) begin
            request(8'h0f,31,0,i,0);
            if (reply[15:8] !== (i==1 ? 8'd31 : (8'h40+i)&255))
                $fatal(1,"snapshot changed byte %0d",i);
        end
        request(8'h0f,30,0,1,3);
        if (query_count!=1) $fatal(1,"nonzero index requested new query");
        query_delay=1400;before_samples=samples;
        request(8'h0f,30,0,0,0);
        if (reply[15:8]!==8'h60 || samples-before_samples<2 || query_count!=2)
            $fatal(1,"late observer stalled audio or read stale data");
        request(8'h0f,31,0,1,3);
        request(8'h0f,30,0,1,0);
        if (reply[15:8]!==30) $fatal(1,"snapshot voice mismatch");
        request(8'h0e,8'hff,0,0,0);
        if (reply[15:8]!==8'h80) $fatal(1,"0E snapshot affected");
        latency_diagnostics=0;
        request(8'h0e,8'hff,0,63,0);
        if (reply[15:8]!==8'hbf) $fatal(1,"0E snapshot torn");
        request(8'h0f,30,0,31,0);
        if (reply[15:8]!==8'h7f) $fatal(1,"0E query replaced 0F snapshot");
        rsp_ready=0;
        request(8'h0f,30,0,4,0);
        before_queries=query_count;
        repeat(1500) begin
            @(negedge clk);
            if (!rsp_valid || rsp_data!==reply || cmd_ready)
                $fatal(1,"ACK backpressure corrupted response");
        end
        if (dut.sound_revision!=0 || query_count!=before_queries || active_voices!=0)
            $fatal(1,"diagnostics changed audio/queried twice");
        rsp_ready=1;
        $display("PASS voice onset protocol: short/long RAM read handshake, uninterrupted audio, atomic voice-specific 32-byte snapshot, validation, 0E isolation and ACK backpressure");
        $finish;
    end
    initial begin #5000000; $fatal(1,"test timeout"); end
endmodule
