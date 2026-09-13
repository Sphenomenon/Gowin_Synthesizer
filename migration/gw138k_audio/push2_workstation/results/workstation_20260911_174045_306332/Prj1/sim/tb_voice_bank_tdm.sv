`timescale 1ns/1ps
// The independent, previously shipped parallel voice is the numerical
// oracle. Compare every state bit as well as signed mixed audio each frame.
module tb_voice_bank_tdm;
    localparam integer N = 32;
    localparam integer LATENCY = 7*N+1;
    reg clk=0; always #10 clk=~clk;
    reg rst_n=0, sample_tick=0, command_apply=0;
    reg [31:0] command_header=0, command_value=0;
    wire signed [31:0] sample_data;
    wire signed [39:0] mix_sum;
    wire signed [31:0] voice_sample_data;
    wire [4:0] voice_sample_index;
    wire sample_valid, busy, ready, reference_valid, voice_sample_event;
    wire [31:0] active_voices, nonzero_voices, reference_phase;
    wire [5:0] reference_voice;
    synth_voice_bank #(.VOICE_COUNT(N)) dut(.*);

    wire signed [31:0] parallel_sample [0:N-1];
    wire [N-1:0] parallel_valid, parallel_active, parallel_display_active;
    wire [31:0] parallel_phase [0:N-1], parallel_step [0:N-1];
    wire [261:0] parallel_state [0:N-1];
    genvar g;
    generate for(g=0;g<N;g=g+1) begin: oracle
        synth_voice #(.VOICE_ID(g)) voice(
            .clk(clk),.rst_n(rst_n),.sample_tick(sample_tick),
            .command_header(command_header),.command_value(command_value),.command_apply(command_apply),
            .sample_data(parallel_sample[g]),.sample_valid(parallel_valid[g]),.active(parallel_active[g]),
            .display_phase(parallel_phase[g]),.display_step(parallel_step[g]),
            .display_active(parallel_display_active[g]));
        assign parallel_state[g] = {
            voice.phase,voice.phase_step,voice.envelope,voice.velocity,
            voice.attack_step,voice.decay_step,voice.sustain_level,voice.release_step,
            voice.waveform,voice.envelope_stage,voice.retrigger_smooth
        };
    end endgenerate

    integer verified=0, n, k, seed=32'h237be219;
    reg [31:0] random_word;
    task frame;
        integer cycle_number, v, streamed;
        reg signed [39:0] sum, held_sum;
        reg signed [31:0] expected_sample;
        reg [31:0] held_active, held_nonzero, expected_nonzero, expected_phase, best_step;
        reg [5:0] expected_voice;
        reg expected_reference;
        begin
            if(!ready || busy) $fatal(1,"frame launched before bank ready");
            @(negedge clk);
            held_active=active_voices; held_nonzero=nonzero_voices;
            held_sum=mix_sum; streamed=0; expected_reference=0;
            expected_voice=0; expected_phase=0; best_step=32'hffffffff;
            for(v=0;v<N;v=v+1) begin
                if(parallel_display_active[v] && parallel_step[v] != 0 && parallel_step[v] < best_step) begin
                    expected_reference=1; expected_voice=v;
                    expected_phase=parallel_phase[v]; best_step=parallel_step[v];
                end
            end
            sample_tick=1;
            @(negedge clk); sample_tick=0;
            // Poison the live command bus immediately after acceptance.
            // Every voice must still observe the same latched command.
            command_header=32'h000aff00; command_value=32'h12345678;
            command_apply=0;
            if(sample_valid || !busy || ready) $fatal(1,"incorrect frame acceptance handshake");
            for(cycle_number=1;cycle_number<=LATENCY+8;cycle_number=cycle_number+1) begin
                @(negedge clk);
                if(cycle_number == 4) begin
                    if(!(&parallel_valid)) $fatal(1,"parallel oracle latency changed");
                    sum=0; expected_nonzero=0;
                    for(v=0;v<N;v=v+1) begin
                        sum=sum+{{8{parallel_sample[v][31]}},parallel_sample[v]};
                        expected_nonzero[v]=parallel_sample[v] >= 32'sd32768 || parallel_sample[v] <= -32'sd32768;
                    end
                    if(sum > 40'sd2147483647) expected_sample=32'sh7fffffff;
                    else if(sum < -40'sd2147483648) expected_sample=32'sh80000000;
                    else expected_sample=sum[31:0];
                end
                if(voice_sample_event) begin
                    if(cycle_number != 7*streamed+6 || voice_sample_index !== streamed[4:0])
                        $fatal(1,"frame %0d voice diagnostic stream index/timing mismatch",verified);
                    if(voice_sample_data !== parallel_sample[streamed])
                        $fatal(1,"frame %0d voice %0d raw diagnostic mismatch",verified,streamed);
                    streamed=streamed+1;
                end
                if(sample_valid !== (cycle_number == LATENCY))
                    $fatal(1,"frame %0d valid wrong at cycle %0d",verified,cycle_number);
                if(cycle_number < LATENCY) begin
                    if(!busy || ready || active_voices !== held_active ||
                       nonzero_voices !== held_nonzero || mix_sum !== held_sum)
                        $fatal(1,"voice mask/ready changed before atomic frame commit");
                end
                if(sample_valid) begin
                    if(!ready || busy) $fatal(1,"completion did not release bank");
                    if(sample_data !== expected_sample)
                        $fatal(1,"frame %0d sample mismatch: got %h expected %h",verified,sample_data,expected_sample);
                    if(mix_sum !== sum || streamed != N)
                        $fatal(1,"frame %0d unscaled mix/stream mismatch: got %h expected %h events %0d",verified,mix_sum,sum,streamed);
                    if(nonzero_voices !== expected_nonzero)
                        $fatal(1,"frame %0d unscaled PCM16 onset mask mismatch",verified);
                    if(active_voices !== parallel_active)
                        $fatal(1,"frame %0d active mask mismatch: got %h expected %h",verified,active_voices,parallel_active);
                    if(reference_valid !== expected_reference || reference_voice !== expected_voice || reference_phase !== expected_phase)
                        $fatal(1,"frame %0d pre-update reference mismatch",verified);
                    for(v=0;v<N;v=v+1) begin
                        if(dut.state_memory[v] !== parallel_state[v])
                            $fatal(1,"frame %0d voice %0d state mismatch: got %h expected %h",verified,v,dut.state_memory[v],parallel_state[v]);
                    end
                    verified=verified+1;
                end
            end
        end
    endtask

    task command(input [7:0] opcode,input [7:0] voice_id,input [31:0] value,input apply);
        begin
            command_header={8'ha5,opcode,voice_id,8'd0}; command_value=value; command_apply=apply;
            frame;
        end
    endtask

    task reset_and_wait;
        integer init_cycles;
        begin
            rst_n=0; sample_tick=0; command_apply=0;
            repeat(3) @(negedge clk); rst_n=1;
            init_cycles=0;
            while(!ready) begin
                @(negedge clk); init_cycles=init_cycles+1;
                if(sample_valid || active_voices != 0 || !busy && !ready)
                    $fatal(1,"unexpected output during state RAM initialization");
                if(init_cycles>N+1) $fatal(1,"state RAM initialization stalled");
            end
            if(init_cycles != N) $fatal(1,"initialization should write exactly one voice per clock");
        end
    endtask

    initial begin
        if(LATENCY>=512) $fatal(1,"32-voice schedule exceeds half of 1024-clock audio period");
        reset_and_wait;
        frame;
        // A single full-scale voice must retain full scale in a 32-slot
        // bank. The wide sum must also hold all 32 coherent voices before
        // the external master gain, with no wrap or per-slot division.
        command(6,0,0,1); command(7,0,0,1); command(8,0,32'h80000000,1);
        command(4,0,32'h80000000,1); command(5,0,1,1); command(1,0,0,1);
        repeat(3) frame;
        if(mix_sum !== 40'sd2147483647 || sample_data !== 32'sh7fffffff || nonzero_voices !== 1)
            $fatal(1,"one full-scale voice was attenuated by the number of slots");
        // PCM16 rounding-to-nearest onset threshold, before master gain.
        command(4,0,32768,1); frame;
        if(mix_sum !== 32767 || nonzero_voices !== 0)
            $fatal(1,"below-half-LSB unscaled onset threshold changed");
        command(4,0,32769,1); frame;
        if(mix_sum !== 32768 || nonzero_voices !== 1)
            $fatal(1,"half-LSB unscaled onset threshold changed");
        command(4,0,32'h80000000,1);
        for(n=1;n<N;n=n+1) begin
            command(6,n,0,1); command(7,n,0,1); command(8,n,32'h80000000,1);
            command(4,n,32'h80000000,1); command(5,n,1,1); command(1,n,0,1);
        end
        repeat(3) frame;
        if(mix_sum !== 40'sd68719476704 || sample_data !== 32'sh7fffffff || nonzero_voices !== 32'hffffffff)
            $fatal(1,"32 coherent positive voices overflowed or were normalized");
        for(n=0;n<N;n=n+1) begin
            command(3,n,32'h80000000,1); command(3,n,0,1);
        end
        frame;
        if(mix_sum !== -40'sd68719476704 || sample_data !== 32'sh80000000 || nonzero_voices !== 32'hffffffff)
            $fatal(1,"32 coherent negative voices overflowed or were normalized");
        reset_and_wait;
        // All 32 voices concurrently sustain nonzero sound. Cover all three
        // oscillators and both fast/slow envelope paths with unique pitches.
        for(n=0;n<N;n=n+1) begin
            command(6,n,n%2 == 0 ? 32'h20000000 : 32'h08000000,1);
            command(7,n,n%2 == 0 ? 32'h10000000 : 32'h02000000,1);
            command(8,n,32'h30000000+n*32'h01000000,1);
            command(9,n,32'h04000000,1);
            command(4,n,32'h40000000+n*32'h01000000,1);
            command(5,n,n%3,1);
            command(1,n,32'h01123457+n*32'h00987651,1);
        end
        repeat(128) frame;
        if(active_voices !== 32'hffffffff) $fatal(1,"not all 32 voices are active");
        // Rejected commands must be inert, including an apparently valid
        // PANIC opcode, unsupported waveform, high voice ID and high gain.
        command(10,255,0,0); command(5,31,3,0);
        command(1,255,32'h10000000,0); command(4,31,32'hffffffff,0);
        // Preserve current phase/level on retrigger, including release's
        // final boundary and zero/large ADSR steps capped by smoothing.
        command(6,31,0,1); command(7,31,0,1); command(9,31,32'h80000000,1);
        command(2,31,0,1); command(1,31,32'h00123456,1);
        repeat(150) frame;
        command(1,0,32'h00123456,1); // equal pitch reference chooses slot 0
        repeat(150) frame;
        command(4,0,0,1); // reference excludes a silent velocity
        command(3,31,0,1); // reference excludes a stopped phase
        repeat(8) frame;

        // Deterministic randomized legal traffic exercises every parameter
        // and repeated voice stealing while bit-exactly checking all states.
        for(k=0;k<384;k=k+1) begin
            random_word=$random(seed);
            case(k%12)
                0,1: command(1,random_word[4:0],{1'b0,random_word[30:0]},1);
                2: command(2,random_word[4:0],0,1);
                3: command(3,random_word[4:0],{1'b0,random_word[30:0]},1);
                4: command(4,random_word[4:0],{1'b0,random_word[30:0]},1);
                5: command(5,random_word[4:0],random_word%3,1);
                6: command(6,random_word[4:0],{1'b0,random_word[30:0]},1);
                7: command(7,random_word[4:0],{1'b0,random_word[30:0]},1);
                8: command(8,random_word[4:0],{1'b0,random_word[30:0]},1);
                9: command(9,random_word[4:0],{1'b0,random_word[30:0]},1);
                default: frame;
            endcase
        end
        command(10,255,0,1);
        if(active_voices !== 0) $fatal(1,"panic failed to clear all 32 voices atomically");
        frame;
        if(sample_data !== 0 || reference_valid) $fatal(1,"panic did not silence next frame");
        // Reinitialize RAM after sound has been active, including reset in
        // the middle of processing a frame.
        command(1,31,32'h07000000,1);
        @(negedge clk); sample_tick=1;
        @(negedge clk); sample_tick=0;
        repeat(60) @(negedge clk);
        reset_and_wait;
        frame;
        if(active_voices !== 0 || sample_data !== 0) $fatal(1,"warm reset left stale state");
        $display("PASS tb_voice_bank_tdm: %0d bit-exact 32-voice frames, full-scale single voice, unscaled +/-32-voice sums/saturation, raw voice stream and PCM16 masks, state RAM/reset, command snapshot, retrigger/ADSR/all waves, reference, atomic mask, one valid per %0d-clock frame",verified,LATENCY);
        $finish;
    end
    initial begin #20000000; $fatal(1,"voice bank TDM test timeout"); end
endmodule
