`timescale 1ns/1ps
module feedback_fence_case #(parameter integer DIRECT = 0)(
    input wire clk_cpu, clk_ref, clk_audio, reset_n,
    output reg done = 0
);
    reg selected = 0, writing = 0;
    reg [7:0] address = 0;
    reg [31:0] write_data = 0;
    wire ready, audio_valid, lifecycle, cancel;
    wire [17:0] event_data;
    reg [9:0] epoch = 0;
    reg [127:0] core_held = 0;
    reg [447:0] performance = 0;
    wire [447:0] delayed_performance;
    reg [15:0] telemetry_divider = 0;
    integer notes = 0, stores = 0, attaches = 0;
    always @(posedge clk_audio) begin
        if (!reset_n) begin epoch <= 0; core_held <= 0; telemetry_divider <= 0; end
        else begin
            telemetry_divider <= telemetry_divider + 1'b1;
            performance <= {32'h43545231, 32'd0, 32'd0, 32'd0, 32'd0,
                            epoch, 22'd1048576, 32'd0, core_held, 32'd0, 32'h80000410, 32'd13};
            if (audio_valid) begin
                if (lifecycle && event_data[6:0] < 3) begin
                    epoch <= epoch + 1'b1; core_held <= 0;
                    if (event_data[6:0] == 1) attaches <= attaches + 1;
                end else if (!lifecycle) begin
                    if (notes == 0 && event_data != {4'd1,7'd36,7'd30})
                        $fatal(1, "feedback first mapped note changed");
                    if (notes == 1 && event_data != {4'd0,7'd36,7'd0})
                        $fatal(1, "feedback release mapping changed");
                    notes <= notes + 1;
                    core_held[event_data[13:7]] <= event_data[17:14] == 1;
                end
            end
        end
    end
    gw138k_stream_cdc #(.WIDTH(448)) telemetry (
        .reset_n(reset_n), .source_clk(clk_audio), .destination_clk(clk_ref),
        .source_valid(&telemetry_divider), .source_data(performance), .drop_count(),
        .destination_valid(), .destination_data(delayed_performance)
    );
    push2_usb_a_control owner (
        .clk(clk_cpu), .reset_n(reset_n), .audio_clk(clk_audio), .audio_reset_n(reset_n),
        .feedback_clk(DIRECT != 0 ? clk_audio : clk_ref), .feedback_reset_n(reset_n),
        .performance_words(DIRECT != 0 ? performance : delayed_performance),
        .display_meta_data(64'd0), .display_meta_valid(1'b0),
        .service_state_data(34'd0), .service_state_valid(1'b0), .score_valid(1'b0),
        .analysis_done(1'b0), .score_ready(), .score_note(7'd0), .playlist_valid(1'b0),
        .playlist_ready(), .playlist_word(16'd0), .track_launch(), .track_index(),
        .select(selected), .write(writing), .address(address), .wdata(write_data), .ready(ready), .rdata(),
        .audio_valid(audio_valid), .audio_ready(1'b1), .audio_event(event_data),
        .audio_lifecycle(lifecycle), .audio_cancel(cancel), .telemetry()
    );
    task automatic store(input [7:0] target, input [31:0] data);
        begin
            @(negedge clk_cpu); selected = 1; writing = 1; address = target; write_data = data;
            do @(posedge clk_cpu); while (!ready);
            stores = stores + 1;
            @(negedge clk_cpu); selected = 0; writing = 0;
        end
    endtask
    initial begin
        wait(reset_n);
        store(8'h00,32'd1);
        #250000;
        store(8'h04,32'h02249009);
        wait(notes == 1);
        #800000;
        store(8'h04,32'h00248008);
        #100000;
        if (stores != 3 || attaches != 1 || epoch != 1) $fatal(1, "feedback fence coverage missing");
        if (DIRECT != 0) begin
            if (notes != 2 || core_held != 0 || owner.held != 0)
                $fatal(1, "direct audio feedback lost release notes=%0d core=%x mapper=%x", notes, core_held, owner.held);
        end else if (notes != 1 || !core_held[36] || owner.held != 0)
            $fatal(1, "old cascaded feedback no longer reproduces stale epoch failure");
        $display("feedback fence DIRECT=%0d stores=%0d mapped_notes=%0d core_held=%x mapper_held=%x",
                 DIRECT, stores, notes, core_held, owner.held);
        done = 1;
    end
endmodule

module tb_workstation_usb2_feedback_fence;
    reg clk_cpu = 0, clk_ref = 0, clk_audio = 0, reset_n = 0;
    always #10.417 clk_cpu = !clk_cpu;
    always #10 clk_ref = !clk_ref;
    always #6.510417 clk_audio = !clk_audio;
    wire old_done, direct_done;
    feedback_fence_case #(.DIRECT(0)) old_path(clk_cpu,clk_ref,clk_audio,reset_n,old_done);
    feedback_fence_case #(.DIRECT(1)) direct_path(clk_cpu,clk_ref,clk_audio,reset_n,direct_done);
    initial begin repeat (10) @(negedge clk_cpu); reset_n = 1; end
    initial begin
        wait(old_done && direct_done);
        $display("PASS feedback fence: old chain loses release; direct audio snapshot preserves On/Off; real owner/CDC, modeled audio state");
        $finish;
    end
    initial begin #2000000; $fatal(1, "feedback fence timeout"); end
endmodule
