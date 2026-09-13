`timescale 1ns/1ps
module tb_feedback_trigger;
    reg source_clk=0, render_clk=0, reset_n=0;
    always #10 source_clk=~source_clk;
    always #7 render_clk=~render_clk;
    reg [31:0] sample=0, voices=1, status=32'h12345678;
    reg valid=0, release_snapshot=0, rd_en=0;
    reg [8:0] addr=0;
    wire ready;
    wire [31:0] peak, snap_voices, snap_status, sequence_word, skipped, data;
    feedback_capture dut(.source_clk(source_clk),.source_reset_n(reset_n),
        .sample_data(sample),.sample_valid(valid),.active_voices(voices),.status_data(status),
        .trigger_reference(32'd0),
        .render_clk(render_clk),.render_reset_n(reset_n),.snapshot_ready(ready),
        .snapshot_release(release_snapshot),.snapshot_peak(peak),.snapshot_voices(snap_voices),
        .snapshot_status(snap_status),.snapshot_sequence(sequence_word),.snapshot_skipped(skipped),
        .wave_read_enable(rd_en),.wave_read_addr(addr),.wave_read_data(data));

    task send_sample(input [31:0] value);
        begin
            @(negedge source_clk); sample=value; valid=1;
            @(negedge source_clk); valid=0;
        end
    endtask
    task reset_capture;
        begin
            @(negedge source_clk); reset_n=0; valid=0; release_snapshot=0; rd_en=0;
            repeat(4) @(negedge source_clk);
            reset_n=1; voices=1;
        end
    endtask
    task read_word(input integer index);
        begin
            @(negedge render_clk); addr=index; rd_en=1;
            @(posedge render_clk); #1;
            @(negedge render_clk); rd_en=0;
        end
    endtask
    task release_block;
        begin
            @(negedge render_clk); release_snapshot=1;
            @(negedge render_clk); release_snapshot=0;
            repeat(8) @(negedge source_clk);
        end
    endtask
    task check_constant(input [31:0] value, input [31:0] expected_peak);
        integer j;
        begin
            wait(ready); #1;
            if(peak!==expected_peak || snap_voices!==voices || snap_status!==status)
                $fatal(1,"constant snapshot metadata mismatch");
            for(j=0;j<512;j=j+1) begin
                read_word(j);
                if(data!==value) $fatal(1,"constant snapshot sample %0d: %h",j,data);
            end
        end
    endtask

    // Independent phase accumulator: none of these periods divides 512 or
    // the simulated renderer delays. Stored words must stay consecutive.
    reg [31:0] phase=0, phase_step;
    reg [31:0] history[0:32767];
    reg [31:0] observed[0:511];
    integer history_count, kind, frame, i, j, start_index, search_start;
    reg candidate_matches;
    reg [31:0] reference_peak, absolute_sample;
    function [31:0] waveform(input [31:0] p, input integer shape);
        real t, value;
        begin
            t=$itor(p[31:1])*2.0/4294967296.0 + p[0]/4294967296.0;
            case(shape)
                0: value=0.75*$sin(6.283185307179586*t);
                1: value=t<0.25 ? 3.0*t : t<0.75 ? 1.5-3.0*t : 3.0*t-3.0;
                default: value=t<0.5 ? 0.75 : -0.75;
            endcase
            waveform=$rtoi(value*2147483647.0);
        end
    endfunction
    task send_periodic(input integer count);
        integer j;
        begin
            for(j=0;j<count;j=j+1) begin
                history[history_count]=waveform(phase,kind);
                send_sample(history[history_count]);
                history_count=history_count+1;
                phase=phase+phase_step;
            end
        end
    endtask

    initial begin
        reset_capture();
        // A positive level at startup cannot define a rising crossing.
        for(i=0;i<600;i=i+1) send_sample(32'h20000000);
        repeat(8) @(negedge render_clk);
        if(ready) $fatal(1,"free-running snapshot published before a rising trigger");
        // Invalid-bus excursions must neither arm nor advance the timeout.
        sample=32'h80000000;
        repeat(9000) @(negedge source_clk);
        sample=0;
        repeat(9000) @(negedge source_clk);
        for(i=0;i<600;i=i+1) send_sample(i[0] ? 32'h00010000 : 32'hffff0000);
        repeat(8) @(negedge render_clk);
        if(ready) $fatal(1,"small zero chatter or invalid data armed the trigger");
        send_sample(32'hffe00000); // Arm below the negative hysteresis threshold.
        send_sample(32'hffffffff);
        send_sample(0);            // Exactly zero is a valid rising trigger.
        for(i=1;i<512;i=i+1) send_sample(i==1 ? 32'h80000000 : i);
        wait(ready); #1;
        if(peak!==32'h80000000 || skipped!==0 || sequence_word!==0)
            $fatal(1,"trigger wait changed peak/skipped/sequence semantics");
        for(i=0;i<512;i=i+1) begin
            read_word(i);
            if(data!==(i==1 ? 32'h80000000 : i))
                $fatal(1,"trigger sample omitted or 512-point window not consecutive at %0d",i);
        end

        // Silence publishes promptly and clears a formerly sounding trace.
        release_block(); voices=0;
        for(i=0;i<512;i=i+1) send_sample(0);
        check_constant(0,0);

        // No crossing (positive DC, negative full scale, active silent voice)
        // must refresh after exactly 8192 valid wait samples, not clock ticks.
        for(kind=0;kind<3;kind=kind+1) begin
            reset_capture();
            sample=kind==0 ? 32'h20000000 : kind==1 ? 32'h80000000 : 0;
            for(i=0;i<8191+511;i=i+1) send_sample(sample);
            repeat(8) @(negedge render_clk);
            if(ready) $fatal(1,"auto trigger fired early for DC case %0d",kind);
            send_sample(sample);
            check_constant(sample,kind==1 ? 32'h80000000 : sample);
        end

        for(kind=0;kind<3;kind=kind+1) begin
            reset_capture();
            history_count=0; search_start=0;
            phase=32'h24000000;
            phase_step=kind==0 ? 32'd38702809 : kind==1 ? 32'd23012345 : 32'd96543210;
            send_periodic(1800); // Fill both banks, then deliberately miss edges.
            for(frame=0;frame<6;frame=frame+1) begin
                wait(ready); #1;
                if(sequence_word!==frame || snap_voices!==1 || snap_status!==status)
                    $fatal(1,"periodic snapshot metadata mismatch");
                if(frame>0 && skipped==0) $fatal(1,"busy-bank dropping not exercised");
                reference_peak=0;
                for(i=0;i<512;i=i+1) begin
                    read_word(i);
                    observed[i]=data;
                    absolute_sample=data[31] ? (~data+1'b1) : data;
                    if(absolute_sample>reference_peak) reference_peak=absolute_sample;
                end
                // Pulse plateaus share the same first value; match the full
                // window against the input history, not just sample zero.
                start_index=-1;
                for(i=search_start+1;i<history_count-511;i=i+1) begin
                    if(start_index<0 && history[i-1][31] && !history[i][31] && history[i]===observed[0]) begin
                        candidate_matches=1;
                        for(j=0;j<512;j=j+1)
                            if(history[i+j]!==observed[j]) candidate_matches=0;
                        if(candidate_matches) start_index=i;
                    end
                end
                if(start_index<0)
                    $fatal(1,"frame %0d shape %0d is not 512 consecutive samples from a rising zero crossing",frame,kind);
                if(peak!==reference_peak) $fatal(1,"peak includes trigger-wait samples");
                search_start=start_index+511;
                // Published contents and metadata are immutable even as the
                // source keeps running through many further trigger edges.
                send_periodic(173+frame*29);
                read_word(0);
                if(data!==history[start_index] || sequence_word!==frame || peak!==reference_peak)
                    $fatal(1,"published bank changed under source pressure");
                release_block();
                send_periodic(1100+frame*31);
            end
        end

        // Reset while armed must not reuse an edge from the previous epoch.
        reset_capture(); send_sample(32'h80000000); reset_capture();
        for(i=0;i<600;i=i+1) send_sample(32'h20000000);
        repeat(8) @(negedge render_clk);
        if(ready) $fatal(1,"stale trigger survived reset");
        $display("PASS feedback trigger: rising phase across 18 sine/triangle/pulse snapshots, hysteresis, valid-only history/timeout, silence/DC, exact 512 samples, busy banks and reset");
        $finish;
    end
    initial begin #10000000; $fatal(1,"trigger test timeout"); end
endmodule
