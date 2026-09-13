`timescale 1ns/1ps
module tb_audio_latency_monitor;
    reg clk=0; always #5 clk=~clk;
    reg rst_n=0;
    reg [31:0] time_cycles=0;
    reg packet_valid=0,command_commit=0,frame_start=0,sample_event=0,dac_done=0,ack_ready=0,ack_done=0;
    reg [31:0] packet_header=0,packet_start=0,packet_end=0,command_header=0;
    reg [23:0] command_revision=0,sample_revision=0,dac_revision=0;
    reg [31:0] nonzero_voices=0,dac_nonzero_voices=0;
    reg [31:0] ack_header=0,ack_ready_time=0,ack_done_header=0,ack_done_time=0;
    wire [511:0] diagnostics;
    audio_latency_monitor dut(.*);
    task step(input [31:0] now);
        begin @(negedge clk); time_cycles=now; @(posedge clk); #1; end
    endtask
    function [31:0] word(input integer n); word=diagnostics[n*32+:32]; endfunction
    task new_trace(input [31:0] first,input [31:0] last,input [31:0] commit,
                   input [7:0] seq,input [7:0] op,input [7:0] voice,input [23:0] revision);
        begin
            packet_header={seq,op,voice,8'd0}; packet_start=first; packet_end=last; packet_valid=1;
            step(last+1); packet_valid=0;
            command_header=packet_header; command_revision=revision; command_commit=1;
            step(commit); command_commit=0;
        end
    endtask
    reg [31:0] saved_id,saved_state,saved_note,saved_dac;
    initial begin
        step(0); rst_n=1; step(1);
        if(word(0)!==1 || word(1)!==0 || word(3)!==50000000) $fatal(1,"reset/schema/rate");
        new_trace(100,200,300,8'h41,1,31,24'd9);
        if(word(0)!==32'h1f014101 || word(1)!==1 || word(2)!==1 || word(4)!==100 || word(5)!==100)
            $fatal(1,"trace metadata/stage deltas");
        frame_start=1;step(300);frame_start=0;
        sample_event=1;sample_revision=8;nonzero_voices=32'hffffffff;step(526);sample_event=0;
        if(word(1)!==1 || word(12)!==226) $fatal(1,"old sample counted or compute interval");
        frame_start=1;step(1324);frame_start=0;
        sample_event=1;sample_revision=9;nonzero_voices=1;step(1550);sample_event=0;
        if(word(6)!==1250 || word(1)!==3 || word(13)!==1024) $fatal(1,"first new state/target isolation");
        dac_done=1;dac_revision=8;dac_nonzero_voices=32'h80000000;step(2000);dac_done=0;
        if(word(1)!==3) $fatal(1,"old DAC tag counted");
        dac_done=1;dac_revision=9;dac_nonzero_voices=1;step(2350);dac_done=0;
        if(word(8)!==2050 || word(1)!==11) $fatal(1,"state DAC endpoint");
        sample_event=1;nonzero_voices=32'h80000000;step(2574);sample_event=0;
        if(word(7)!==2274 || word(6)!==1250) $fatal(1,"target onset / first sample overwritten");
        dac_done=1;dac_nonzero_voices=32'h80000000;step(3374);dac_done=0;
        ack_ready=1;ack_header={8'h41,8'd0,8'd0,8'd1};ack_ready_time=530;step(3375);ack_ready=0;
        ack_done=1;ack_done_header=ack_header;ack_done_time=3300;step(3376);ack_done=0;
        if(word(1)!==127 || word(9)!==3074 || word(10)!==430 || word(11)!==3200)
            $fatal(1,"final stage timestamps/flags");
        saved_id=word(2);saved_state=word(6);saved_note=word(7);saved_dac=word(9);
        sample_event=1;dac_done=1;ack_ready=1;ack_ready_time=4000;step(4001);
        sample_event=0;dac_done=0;ack_ready=0;
        if(word(6)!==saved_state || word(7)!==saved_note || word(9)!==saved_dac || word(10)!==430)
            $fatal(1,"duplicate events overwrote first endpoints");
        // Diagnostic packet and uncommitted/semantically rejected packet do not clear history.
        packet_valid=1;packet_header=32'h420eff00;packet_start=4010;packet_end=4020;step(4021);packet_valid=0;
        command_commit=1;command_header=packet_header;step(4022);command_commit=0;
        if(word(2)!==saved_id || word(1)!==127) $fatal(1,"diagnostic reset measurement");
        packet_valid=1;packet_header=32'h43042000;step(4023);packet_valid=0;step(4024);
        if(word(2)!==saved_id) $fatal(1,"uncommitted packet reset measurement");
        // Zero is a valid measured duration. Modular deltas cross timer wrap.
        new_trace(32'hfffffff0,32'hfffffff8,32'hfffffff8,8'h44,1,31,10);
        sample_revision=10;sample_event=1;nonzero_voices=0;step(32'hfffffff8);sample_event=0;
        if((word(1)&2)==0 || word(6)!==0) $fatal(1,"zero latency seen flag");
        sample_event=1;nonzero_voices=32'h80000000;step(32'h00000008);sample_event=0;
        if(word(6)!==0 || word(7)!==16 || word(4)!==8 || word(5)!==0 || word(14)!==24)
            $fatal(1,"modular wrap/zero latency overwritten");
        new_trace(20,30,40,8'h45,2,31,11);
        if(word(15)!==1) $fatal(1,"unfinished trace replacement not counted");
        sample_event=1;sample_revision=11;nonzero_voices=32'hffffffff;step(50);sample_event=0;
        dac_done=1;dac_revision=11;dac_nonzero_voices=32'hffffffff;step(60);dac_done=0;
        if(word(1)!==11 || word(7)!==0 || word(9)!==0) $fatal(1,"non-NOTE_ON fabricated onset");
        step(32'h80000014);
        if((word(1)&128)==0) $fatal(1,"trace expiry missing");
        step(21);sample_event=1;step(22);sample_event=0;
        if((word(1)&128)==0 || word(6)!==10) $fatal(1,"expired trace revived after wrap");
        // Global output edits create a new sound revision too. Replace an
        // unfinished note trace so it cannot wait forever for an old revision.
        new_trace(1000,1010,1020,8'h46,8'h10,8'hff,12);
        sample_event=1;sample_revision=11;step(1030);sample_event=0;
        if(word(1)!==1 || word(0)!==32'hff104601) $fatal(1,"master trace association");
        sample_event=1;sample_revision=12;step(1040);sample_event=0;
        dac_done=1;dac_revision=12;step(1050);dac_done=0;
        if(word(1)!==11 || word(6)!==20 || word(8)!==30 || word(7)!==0 || word(9)!==0)
            $fatal(1,"master endpoints fabricated note onset");
        new_trace(2000,2010,2020,8'h47,8'h11,8'hff,13);
        sample_event=1;sample_revision=13;step(2025);sample_event=0;
        dac_done=1;dac_revision=13;step(2030);dac_done=0;
        if(word(0)!==32'hff114701 || word(1)!==11 || word(6)!==5 || word(8)!==10)
            $fatal(1,"balance trace endpoints");
        $display("PASS audio latency monitor: stage deltas, zero-valid, wrap/expiry, command and target association, diagnostics isolation, first-only endpoints and replacement count");
        $finish;
    end
    initial begin #100000; $fatal(1,"timeout"); end
endmodule
