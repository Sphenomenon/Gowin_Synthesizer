`timescale 1ns/1ps
module tb_video_monitor;
    reg source_clk=0, pixel_clk=0;
    always #10 source_clk=~source_clk;
    always #23 pixel_clk=~pixel_clk; // intentionally unrelated phase/frequency
    reg reset_n=0;
    reg [31:0] sample_data=0, active_voices=0, status_data=0;
    reg sample_valid=0;
    wire [31:0] received_sample, received_voices, received_status;
    wire received_valid;
    video_monitor_cdc dut(source_clk,reset_n,sample_data,sample_valid,
        active_voices,status_data,pixel_clk,reset_n,
        received_sample,received_voices,received_status,received_valid);
    integer seq,received_count=0;
    reg [31:0] previous=0;
    always @(posedge pixel_clk) begin
        #1;
        if (!reset_n) begin previous=0; received_count=0; end
        else if (received_valid) begin
            if (received_voices !== (received_sample ^ 32'hcafe1234) ||
                received_status !== ~received_sample) $fatal(1,"incoherent CDC snapshot");
            if (received_sample <= previous) $fatal(1,"CDC duplicate or stale snapshot");
            previous=received_sample;
            received_count=received_count+1;
        end
    end
    task drive_observation(input integer value);
        begin
            @(negedge source_clk);
            sample_data=value;
            active_voices=value ^ 32'hcafe1234;
            status_data=~value;
            sample_valid=1;
        end
    endtask
    initial begin
        repeat(5) @(negedge source_clk);
        reset_n=1;
        // Deliberately overload observation mailbox; accepted words stay atomic.
        for (seq=1;seq<=500;seq=seq+1) drive_observation(seq);
        @(negedge source_clk); sample_valid=0;
        repeat(20) @(negedge pixel_clk);
        if (received_count<20 || received_count>=500) $fatal(1,"mailbox progress/drop policy wrong");
        // Reset during an in-flight message must not create a phantom snapshot.
        drive_observation(501);
        #3 reset_n=0; sample_valid=0;
        repeat(4) @(negedge pixel_clk);
        reset_n=1;
        repeat(8) @(negedge pixel_clk);
        if (received_count!=0) $fatal(1,"phantom data after mailbox reset");
        drive_observation(1000);
        @(negedge source_clk); sample_valid=0;
        repeat(15) @(negedge pixel_clk);
        if (received_count!=1 || previous!=1000) $fatal(1,"mailbox failed to recover after reset");
        $display("PASS tb_video_monitor: coherent asynchronous snapshots, overload, reset recovery");
        $finish;
    end
endmodule
