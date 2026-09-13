`timescale 1ns/1ps
module tb_feedback_renderer;
    reg clk=0, source_clk=0, reset_n=0;
    always #5 clk=~clk;
    always #10 source_clk=~source_clk;
    reg start=0, pixel_ready=0, sample_valid=0;
    reg [31:0] sample_data=32'h40000000;
    reg [31:0] trigger_reference=1;
    reg [31:0] memory_status=3, underruns=0, frame_count=17;
    reg [31:0] active_voices=32'h80010005;
    wire ready,busy,done,valid;
    wire [63:0] pixels;
    feedback_renderer #(.WIDTH(1088),.HEIGHT(970)) dut(
        .clk(clk),.rst_n(reset_n),.start(start),.frame_ready(ready),.busy(busy),.frame_done(done),
        .pixel_valid(valid),.pixel_ready(pixel_ready),.pixel_data(pixels),
        .source_clk(source_clk),.source_reset_n(reset_n),.sample_data(sample_data),.sample_valid(sample_valid),
        .trigger_reference(trigger_reference),
        .active_voices(active_voices),.status_data(32'h10203040),.memory_status(memory_status),.underruns(underruns),.frame_count(frame_count));
    integer i,count=0,done_count=0,cycles=0,trace_hits=0,tile_hits=0,voice_index;
    reg [31:0] expected_tile;
    reg stalled=0;
    reg [63:0] held;
    reg [31:0] rng=32'h12345678;
    always @(negedge clk) begin
        if (reset_n) begin
            rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
            pixel_ready=rng[0] | rng[1];
        end
    end
    always @(posedge clk) begin
        if (reset_n) begin
            if (stalled && (!valid || pixels!==held)) $fatal(1,"stream changed under backpressure");
            stalled=valid && !pixel_ready;
            held=pixels;
            if (valid && pixel_ready) begin
                if (dut.output_x!==((count%544)*2) || dut.output_y!==(count/544))
                    $fatal(1,"raster position mismatch beat %d",count);
                if (dut.output_x>=64 && dut.output_y>=351 && dut.output_y<=353) begin
                    if (pixels!==64'h003cdbab003cdbab) $fatal(1,"wave trace does not match real +0.5 Q1.31 sample");
                    trace_hits=trace_hits+1;
                end
                if (dut.frame_memory_status!==3 || dut.frame_underruns!==0 || dut.frame_framecount!==17)
                    $fatal(1,"frame metadata tore");
                if (dut.snapshot_voices!==32'h80010005) $fatal(1,"32-voice metadata truncated or tore");
                if (dut.output_x>=68 && (dut.output_x-68)%64==0 &&
                    (dut.output_y==910 || dut.output_y==958)) begin
                    voice_index=(dut.output_x-68)/64+(dut.output_y==958 ? 16 : 0);
                    expected_tile=(32'h80010005 & (32'h1 << voice_index)) ? 32'h00157d70 : 32'h00263a4f;
                    if (pixels!=={expected_tile,expected_tile}) $fatal(1,"voice %0d tile not aligned to its captured activity bit",voice_index);
                    tile_hits=tile_hits+1;
                end
                count=count+1;
            end
            if (done) begin
                done_count=done_count+1;
                if (count!==527680 || busy || valid || trace_hits!==1536 || tile_hits!==32)
                    $fatal(1,"frame length/completion incorrect count=%0d trace=%0d tiles=%0d",count,trace_hits,tile_hits);
            end
            cycles=cycles+1;
        end
    end
    initial begin
        #31; reset_n=1;
        // A mixed rising crossing must be ignored while the DDS reference
        // is valid. Exercise its connection through the actual renderer.
        @(negedge source_clk); sample_data=32'hffe00000; sample_valid=1;
        @(negedge source_clk); sample_data=32'h40000000; sample_valid=0;
        for(i=0;i<600;i=i+1) begin @(negedge source_clk); sample_valid=1; end
        @(negedge source_clk); sample_valid=0;
        repeat(8) @(negedge clk);
        if(ready) $fatal(1,"renderer ignored the external DDS reference");
        for(i=0;i<1024;i=i+1) begin
            @(negedge source_clk); sample_valid=1; trigger_reference=i==0 ? 3 : 1;
        end
        @(negedge source_clk); sample_valid=0;
        wait(ready);
        @(negedge clk); start=1;
        @(negedge clk); start=0;
        repeat(50) @(negedge clk);
        memory_status=4; underruns=99; frame_count=200; active_voices=32'h7ffefffa;
        start=1; // Busy start must not restart the frame.
        repeat(3) @(negedge clk);
        start=0;
        wait(done); repeat(4) @(negedge clk);
        if(done_count!==1) $fatal(1,"done must pulse exactly once");
        $display("PASS feedback renderer: DDS reference connection, two pixels/beat, raster ordering, waveform alignment, all 32 captured activity tiles, random stalls, coherent full-width metadata and final handshake");
        $finish;
    end
    initial begin #15000000; $fatal(1,"timeout"); end
endmodule
