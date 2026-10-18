`timescale 1ns/1ps
module tb_feedback_wave_align;
    reg clk=0, reset_n=0, start=0, rd_en=0;
    always #5 clk=~clk;
    reg [31:0] revision=1, peak=32'h40000000;
    reg [8:0] addr=0;
    wire busy, done, held, cap_en;
    wire [9:0] cap_addr;
    reg [31:0] cap_data;
    wire [31:0] data;
    reg [31:0] source[0:1023], expected[0:511];
    feedback_wave_align dut(.clk(clk),.reset_n(reset_n),.start(start),
        .snapshot_revision(revision),.snapshot_peak(peak),.busy(busy),.done(done),.waveform_held(held),
        .capture_read_enable(cap_en),.capture_read_addr(cap_addr),.capture_read_data(cap_data),
        .wave_read_enable(rd_en),.wave_read_addr(addr),.wave_read_data(data));
    always @(posedge clk) if(cap_en) cap_data<=source[cap_addr];
    function [31:0] pattern(input integer n,input integer generation);
        integer height;
        begin
            // An odd period prevents accidental alignment at the block boundary.
            height=((n%257)*73)%257-128;
            pattern=(height*8388608)+generation;
        end
    endfunction
    integer i, cycles;
    task run_alignment(input bit expect_hold);
        begin
            @(negedge clk); start=1;
            @(negedge clk); start=0; cycles=0;
            while(!done) begin
                @(negedge clk); cycles=cycles+1;
                if(cycles>530000) $fatal(1,"alignment exceeded bounded search time");
            end
            if(busy || held!==expect_hold) $fatal(1,"incorrect match/HOLD result");
            for(i=0;i<512;i=i+1) begin
                @(negedge clk); rd_en=1; addr=i;
                @(posedge clk); #1;
                if(data!==expected[i]) $fatal(1,"trace sample %0d corrupted: %h expected %h",i,data,expected[i]);
                @(negedge clk); rd_en=0;
            end
            if(done) $fatal(1,"done did not pulse");
        end
    endtask
    initial begin
        #17; reset_n=1;
        for(i=0;i<1024;i=i+1) source[i]=pattern(i,11);
        for(i=0;i<512;i=i+1) expected[i]=source[i];
        run_alignment(0); // First complete trace seeds the template.

        for(i=0;i<1024;i=i+1) source[i]=pattern(i+73,29);
        for(i=0;i<512;i=i+1) expected[i]=source[i+184];
        run_alignment(0); // Exact shape at a nonzero offset; preserve all low bits.

        for(i=0;i<1024;i=i+1) source[i]=32'h30000000;
        run_alignment(1); // Unrelated fresh signal must leave every old word intact.
        revision=2;
        for(i=0;i<512;i=i+1) expected[i]=source[i];
        run_alignment(0); // Sound revision reacquires without matching old shape.

        // The mean full-window error threshold is inclusive at four pixels.
        for(i=0;i<1024;i=i+1) source[i]=32'h32000000;
        for(i=0;i<512;i=i+1) expected[i]=source[i];
        run_alignment(0);
        for(i=0;i<1024;i=i+1) source[i]=32'h34800000;
        run_alignment(1); // Five pixels of error per sample must hold.

        // Differences on points skipped by a sparse signature must count.
        for(i=0;i<1024;i=i+1) source[i]=i%8==0 ? 32'h32000000 : 32'h3a000000;
        run_alignment(1);

        peak=0;
        for(i=0;i<1024;i=i+1) source[i]=0;
        for(i=0;i<512;i=i+1) expected[i]=0;
        run_alignment(0); // Silence never leaves an old sounding trace frozen.
        reset_n=0; repeat(4) @(negedge clk); reset_n=1;
        peak=32'h80000000;
        for(i=0;i<1024;i=i+1) source[i]=i[0] ? 32'h7fffffff : 32'h80000000;
        for(i=0;i<512;i=i+1) expected[i]=source[i];
        run_alignment(0);
        for(i=0;i<1024;i=i+1) source[i]=32'h7fffffff;
        run_alignment(1); // Full negative-to-positive difference cannot overflow.
        $display("PASS waveform match: all 513 windows/all 512 points, shifted real data, exact threshold, HOLD immutability, revision rearm, silence, signed extremes and bounded latency");
        $finish;
    end
    initial begin #40000000; $fatal(1,"wave align test timeout"); end
endmodule
