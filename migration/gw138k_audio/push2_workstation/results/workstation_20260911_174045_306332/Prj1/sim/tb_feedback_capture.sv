`timescale 1ns/1ps
module tb_feedback_capture;
    reg source_clk=0, render_clk=0, reset_n=0;
    always #10 source_clk=~source_clk;
    always #7 render_clk=~render_clk;
    reg [31:0] sample=0, voices=0, status=0;
    reg valid=0, release_snapshot=0, rd_en=0;
    reg [8:0] addr=0;
    wire ready;
    wire [31:0] peak, snap_voices, snap_status, sequence_word, skipped, data;
    // Immediate auto-trigger isolates RAM ownership/metadata checks; phase
    // triggering with the production timeout is covered by tb_feedback_trigger.
    feedback_capture #(.TRIGGER_TIMEOUT_SAMPLES(1)) dut(.source_clk(source_clk),.source_reset_n(reset_n),
        .sample_data(sample),.sample_valid(valid),.active_voices(voices),.status_data(status),
        .trigger_reference(32'd0),
        .render_clk(render_clk),.render_reset_n(reset_n),.snapshot_ready(ready),
        .snapshot_release(release_snapshot),.snapshot_peak(peak),.snapshot_voices(snap_voices),
        .snapshot_status(snap_status),.snapshot_sequence(sequence_word),.snapshot_skipped(skipped),
        .wave_read_enable(rd_en),.wave_read_addr(addr),.wave_read_data(data));
    task send_block(input [31:0] base, input [31:0] v, input [31:0] s);
        integer i;
        begin
            for (i=0;i<512;i=i+1) begin
                @(negedge source_clk); sample=base+i; voices=v; status=s; valid=1;
            end
            @(negedge source_clk); valid=0;
        end
    endtask
    task check_word(input [8:0] a, input [31:0] expected);
        begin
            @(negedge render_clk); rd_en=1; addr=a;
            @(posedge render_clk); #1;
            if (data !== expected) $fatal(1,"sample %0d: %h expected %h",a,data,expected);
            @(negedge render_clk); rd_en=0;
        end
    endtask
    task release_block;
        begin
            @(negedge render_clk); release_snapshot=1;
            @(negedge render_clk); release_snapshot=0;
        end
    endtask
    initial begin
        #39; reset_n=1;
        send_block(32'h80000000,32'h80010003,32'h12345678);
        wait(ready); #1;
        if (peak!==32'h80000000 || snap_voices!==32'h80010003 || snap_status!==32'h12345678 || sequence_word!==0)
            $fatal(1,"first snapshot metadata incorrect");
        // The next bank captures while the displayed bank stays unchanged.
        send_block(32'h10000000,32'h7ffefffc,32'habcdef01);
        repeat(30) begin
            @(negedge source_clk); sample=32'hdeadbeef; valid=1;
        end
        @(negedge source_clk); valid=0;
        check_word(0,32'h80000000);
        check_word(511,32'h800001ff);
        if (sequence_word!==0 || snap_voices!==32'h80010003) $fatal(1,"snapshot changed before release");
        release_block();
        wait(ready); #1;
        if (sequence_word!==1 || peak!==32'h100001ff || snap_voices!==32'h7ffefffc || snap_status!==32'habcdef01 || skipped<30)
            $fatal(1,"second snapshot metadata incorrect seq=%d peak=%h skipped=%d",sequence_word,peak,skipped);
        check_word(0,32'h10000000);
        check_word(511,32'h100001ff);
        // Reset cancels ownership; the following publication must be fresh.
        @(negedge source_clk); reset_n=0;
        #60; reset_n=1;
        send_block(32'h20000000,4,7);
        wait(ready); #1;
        if (sequence_word!==0 || snap_status!==7) $fatal(1,"stale metadata after reset");
        check_word(511,32'h200001ff);
        $display("PASS feedback capture: async clocks, complete 512-point blocks, double buffering, signed peak, dropped observations and reset");
        $finish;
    end
    initial begin #200000; $fatal(1,"timeout"); end
endmodule
