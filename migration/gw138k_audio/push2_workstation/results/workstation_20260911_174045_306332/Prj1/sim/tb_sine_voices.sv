`timescale 1ns/1ps
module tb_sine_voices;
    wire [127:0] video_diagnostics=0;
    wire [7:0] memory_flags=8'hc3;
    reg clk=0; always #10 clk=~clk;
    reg rst_n=0, sample_tick=0, cmd_valid=0, cmd_first=0, cmd_last=0, rsp_ready=0;
    reg [31:0] cmd_data=0;
    wire cmd_ready, rsp_valid, sample_valid;
    wire [31:0] rsp_data, active_voices;
    wire signed [31:0] sample_data;
    wire signed [39:0] mix_sum;
    wire [31:0] trigger_reference;
    synth_engine #(.VOICE_COUNT(4)) dut(.onset_query_request(),.onset_query_voice(),
        .onset_query_done(1'b0),.onset_query_data(256'd0),.latency_diagnostics(512'd0),.trace_commit(),.trace_header(),.trace_revision(),
        .trace_frame_start(),.trace_sample_event(),.trace_sample_revision(),.trace_nonzero_voices(),
        .sample_nonzero_voices(),.voice_sample_event(),.voice_sample_data(),.voice_sample_index(),
        .master_volume(),.lr_balance(),.*);

    // Independent DDS model. Its phase advances only at sample boundaries;
    // reference sine coefficients are calculated with real-valued trig.
    reg [31:0] model_phase [0:3];
    reg [31:0] model_step [0:3];
    reg [3:0] model_active=0;
    reg check_samples=0;
    integer seq=0, j, n, verified=0;
    localparam real PI = 3.14159265358979323846;

    task frame;
        integer v, cycle_number, reference_wave;
        real ideal;
        reg signed [63:0] reference_sum, reference_mix, error;
        begin
            reference_sum=0;
            for(v=0;v<4;v=v+1) begin
                if(model_active[v]) begin
                    ideal=2147483647.0*$sin(2.0*PI*model_phase[v][31:22]/1024.0);
                    reference_wave=ideal < 0.0 ? $rtoi(ideal-0.5) : $rtoi(ideal+0.5);
                    reference_sum=reference_sum+reference_wave;
                end
            end
            if(reference_sum > 64'sd2147483647) reference_mix=64'sd2147483647;
            else if(reference_sum < -64'sd2147483648) reference_mix=-64'sd2147483648;
            else reference_mix=reference_sum;
            while(!dut.bank_ready) @(negedge clk);
            @(negedge clk); sample_tick=1;
            for(v=0;v<4;v=v+1)
                if(model_active[v]) model_phase[v]=model_phase[v]+model_step[v];
            @(negedge clk); sample_tick=0;
            if(sample_valid) $fatal(1,"unexpected sample at input boundary");
            for(cycle_number=1;cycle_number<=33;cycle_number=cycle_number+1) begin
                @(negedge clk);
                if(sample_valid !== (cycle_number == 30))
                    $fatal(1,"engine valid latency changed at cycle %0d",cycle_number);
                if(check_samples && sample_valid) begin
                    error=$signed(mix_sum)-reference_sum;
                    if(error < -1 || error > 1)
                        $fatal(1,"four-voice raw sine sum mismatch actual=%0d expected=%0d",$signed(mix_sum),reference_sum);
                    error=$signed(sample_data)-reference_mix;
                    if(error < -1 || error > 1)
                        $fatal(1,"four-voice sine mismatch actual=%0d expected=%0d",$signed(sample_data),reference_mix);
                    verified=verified+1;
                end
            end
        end
    endtask

    task command(input [7:0] op,input [7:0] voice,input [31:0] value,input [7:0] status);
        begin
            @(negedge clk);
            while(!cmd_ready) @(negedge clk);
            cmd_valid=1; cmd_first=1; cmd_last=0; cmd_data={seq[7:0],op,voice,8'b0};
            @(negedge clk); cmd_first=0; cmd_last=1; cmd_data=value;
            @(negedge clk); cmd_valid=0; cmd_last=0;
            frame;
            if(!rsp_valid || rsp_data[23:16] !== status || rsp_data[31:24] !== seq[7:0])
                $fatal(1,"unexpected command ACK: %h op=%h status=%h",rsp_data,op,status);
            if(status == 0) begin
                if(op == 1) begin model_phase[voice]=0; model_step[voice]=value; model_active[voice]=1; end
                if(op == 3) model_step[voice]=value;
                if(op == 10) begin
                    model_active=0;
                    for(j=0;j<4;j=j+1) model_phase[j]=0;
                end
            end
            rsp_ready=1; @(negedge clk); rsp_ready=0; seq=seq+1;
        end
    endtask

    initial begin
        for(j=0;j<4;j=j+1) begin model_phase[j]=0; model_step[j]=0; end
        repeat(4) @(negedge clk); rst_n=1;
        frame;
        for(n=0;n<4;n=n+1) begin
            command(6,n,0,0); command(7,n,0,0); command(8,n,32'h80000000,0);
            command(4,n,32'h80000000,0); command(5,n,2,0);
            command(1,n,32'h02345679+n*32'h01531423,0);
        end
        repeat(4) frame;
        if(active_voices !== 32'hf) $fatal(1,"sine four-voice activation failed");
        check_samples=1;
        repeat(1024) frame;
        command(3,1,32'h07654321,0); // frequency change must preserve every phase
        repeat(128) frame;
        command(5,2,3,3); // a rejected enum must preserve the selected sine
        command(5,2,32'h10000002,3); // high bits must not be silently truncated
        repeat(128) frame;
        command(3,3,32'h7fffffff,0); // valid DDS pitch immediately below Nyquist
        repeat(128) frame;
        command(10,8'hff,0,0);
        repeat(4) frame;
        if(active_voices !== 0 || sample_data !== 0) $fatal(1,"sine panic did not become silent");
        $display("PASS tb_sine_voices: %0d reference samples, four independent DDS phases, pitch continuity, enum rejection, unchanged valid latency, panic",verified);
        $finish;
    end
    initial begin #20000000; $fatal(1,"sine voice test timeout"); end
endmodule
