`timescale 1ns / 1ps
`include "sim/tb_touch_i2c_model.v"
`timescale 1ns / 1ps

module tb_touch_diagnostics;
    reg clk = 0;
    always #10 clk = ~clk;
    reg reset = 1, change_n = 0, slider_scan_pause = 0, slider_nack = 0;
    tri1 k_scl, k_sda, s_scl, s_sda;
    wire [15:0] keys, errors;
    wire key_update, slider_valid, slider_touch, keypad_ready, slider_ready;
    wire slider_scan_paused, slider_overrun;
    wire [7:0] slider_position, slider_raw_position, slider_general_status, slider_sample_count;
    wire [255:0] diagnostics;
    wire [31:0] word0 = diagnostics[31:0];
    wire [31:0] word1 = diagnostics[63:32];
    wire [31:0] word2 = diagnostics[95:64];
    wire [31:0] word3 = diagnostics[127:96];
    wire [31:0] word4 = diagnostics[159:128];
    wire [31:0] word5 = diagnostics[191:160];
    wire [31:0] word6 = diagnostics[223:192];
    wire [31:0] word7 = diagnostics[255:224];
    reg monitor_frames = 0, previous_valid = 0, was_paused = 0;
    reg forbid_ack = 0;
    reg [127:0] previous_frame;
    reg [31:0] previous_sequence;
    integer pause_verifications = 0, resume_verifications = 0, pause_acks = 0;
    integer pause_starts = 0, pause_count_before, resume_count_before;
    integer cycle = 0, coherent_frames = 0;
    reg [31:0] sequence_before;

    midi_touch_frontend #(
        .STARTUP_CYCLES(20), .CALIBRATION_CYCLES(100),
        .MIN_SCAN_CYCLES(30000), .POLL_CYCLES(40000),
        .HALF_CYCLES(5), .BUS_FREE_CYCLES(8), .TIMEOUT_CYCLES(200)
    ) dut (
        .clk(clk), .reset(reset), .change_n(change_n),
        .slider_scan_pause(slider_scan_pause), .slider_scan_paused(slider_scan_paused),
        .touch_diagnostics(diagnostics),
        .touch1_scl(k_scl), .touch1_sda(k_sda), .touch2_scl(s_scl), .touch2_sda(s_sda),
        .key_bitmap(keys), .key_update(key_update),
        .slider_valid(slider_valid), .slider_position(slider_position),
        .slider_touch(slider_touch), .keypad_ready(keypad_ready), .slider_ready(slider_ready),
        .errors(errors), .slider_raw_position(slider_raw_position),
        .slider_general_status(slider_general_status), .slider_overrun(slider_overrun),
        .slider_sample_count(slider_sample_count)
    );
    midi_i2c_slave_model key_device (.scl(k_scl), .sda(k_sda), .nack_all(1'b0));
    midi_i2c_slave_model slider_device (.scl(s_scl), .sda(s_sda), .nack_all(slider_nack));

    // Observe completed real transactions before the client's NBA consumes
    // done, then inspect published state after that edge has settled.
    always @(posedge clk) begin
        cycle = cycle + 1;
        if (!reset && dut.slider.state == 14 && dut.slider.waiting &&
            dut.slider.transaction_done && dut.slider.bus_error == 0) begin
            if (dut.slider.requested_pause && dut.slider.read_data[7:0] == 0)
                pause_verifications = pause_verifications + 1;
            if (!dut.slider.requested_pause && dut.slider.read_data[7:0] == 1)
                resume_verifications = resume_verifications + 1;
        end
        #1;
        if (!reset) begin
            if (word7 !== 32'h54430101) $fatal(1,"Bad touch diagnostics format tag");
            if (word4 !== {slider_sample_count,slider_general_status,slider_position,slider_raw_position})
                $fatal(1,"Slider diagnostic word does not match its published outputs");
            if (word5[31:24] !== 0 || word5[23:8] !== errors ||
                word5[5:0] !== {slider_overrun,slider_scan_paused,slider_scan_pause,
                                slider_touch,slider_ready,keypad_ready})
                $fatal(1,"Touch diagnostic status/error bit layout is wrong: %h",word5);
            if (forbid_ack && slider_scan_paused)
                $fatal(1,"Failed LP write/readback acknowledged a pause");
            if (slider_scan_paused && !was_paused) begin
                if (pause_verifications <= pause_acks || slider_device.mem[12] !== 0)
                    $fatal(1,"Pause ack preceded successful LP=0 readback");
                pause_acks = pause_acks + 1;
                pause_starts = slider_device.starts;
            end
            if (slider_scan_paused && slider_scan_pause) begin
                if (slider_device.starts != pause_starts || dut.slider.request ||
                    s_scl !== 1'b1 || s_sda !== 1'b1 || slider_ready)
                    $fatal(1,"U2 generated traffic or remained ready after verified pause");
            end
            was_paused = slider_scan_paused;
            if (monitor_frames) begin
                if (previous_valid) begin
                    if (word6 == previous_sequence && diagnostics[127:0] !== previous_frame)
                        $fatal(1,"U1 diagnostic words changed outside a completed frame seq=%0d old=%h new=%h",
                               word6,previous_frame,diagnostics[127:0]);
                    if (word6 != previous_sequence) begin
                        if (word6 !== previous_sequence + 1 || !key_update)
                            $fatal(1,"U1 diagnostic sequence is not a successful frame counter");
                        coherent_frames = coherent_frames + 1;
                    end
                end
                previous_valid = 1;
                previous_sequence = word6;
                previous_frame = diagnostics[127:0];
            end
        end
    end

    task wait_keys(input [15:0] expected);
        integer attempts;
        begin : awaiting
            for (attempts = 0; attempts < 5; attempts = attempts + 1) begin
                @(posedge key_update); #1;
                if (keys === expected) disable awaiting;
            end
            $fatal(1,"Keys %h expected %h",keys,expected);
        end
    endtask
    task wait_frame(input [15:0] before_keys, input [15:0] after_keys, input [15:0] filtered_keys);
        integer attempts;
        begin : awaiting
            for (attempts = 0; attempts < 5; attempts = attempts + 1) begin
                @(posedge key_update); #1;
                if (word1 === {after_keys,before_keys}) begin
                    if (word0 !== {8'h41,word6[7:0],filtered_keys} ||
                        word2 !== 32'h12481234 || word3 !== 32'h34743456 || word6 == 0)
                        $fatal(1,"Wrong coherent G/H diagnostics w0=%h w1=%h G=%h H=%h seq=%0d",
                               word0,word1,word2,word3,word6);
                    disable awaiting;
                end
            end
            $fatal(1,"Missing G/H frame before=%h after=%h current=%h",before_keys,after_keys,word1);
        end
    endtask
    task verify_paused;
        begin
            wait(slider_scan_paused);
            repeat (5) @(negedge clk);
            if (slider_device.mem[12] !== 0 || slider_ready || slider_touch ||
                !word5[3] || !word5[4] || errors[15:8])
                $fatal(1,"Invalid verified paused state flags=%h LP=%h",word5,slider_device.mem[12]);
        end
    endtask
    task resume_slider;
        begin
            resume_count_before = resume_verifications;
            @(negedge clk); slider_scan_pause = 0;
            wait(!slider_scan_paused);
            #1;
            if (resume_verifications != resume_count_before+1 || slider_device.mem[12] !== 1)
                $fatal(1,"Resume did not write and verify LP=1");
            wait(slider_ready);
            @(posedge slider_valid); #1;
            if (errors[15:8] || slider_raw_position !== 8'd96)
                $fatal(1,"Slider did not resume normal acquisition");
        end
    endtask

    initial begin
        repeat (5) @(negedge clk); reset = 0;
        wait(keypad_ready && slider_ready);
        @(negedge clk); monitor_frames = 1;
        wait(dut.keypad.state == 10);
        @(negedge clk);
        key_device.mem[2] = 8'h41;
        key_device.mem[4] = 8'h82;
        key_device.mem[118] = 8'h34; key_device.mem[119] = 8'h12;
        key_device.mem[150] = 8'h48; key_device.mem[151] = 8'h12;
        key_device.mem[130] = 8'h56; key_device.mem[131] = 8'h34;
        key_device.mem[162] = 8'h74; key_device.mem[163] = 8'h34;
        slider_device.mem[2] = 8'h41; slider_device.mem[5] = 8'd96;
        wait_frame(16'h8200,16'h8200,16'h8200);
        if (!word5[6]) $fatal(1,"U1 overrun history missing from diagnostic flags");

        // Preserve the distinct bracketing status words, while rejecting a
        // key released between the first status and final status read.
        wait(dut.keypad.state == 10);
        @(negedge clk); key_device.mem[4] = 8'h82;
        wait(dut.keypad.state == 5);
        @(negedge clk); key_device.mem[4] = 8'h02;
        wait_frame(16'h8200,16'h0200,16'h0200);
        @(negedge clk); key_device.mem[4] = 8'h82;
        wait_frame(16'h8200,16'h8200,16'h8200);

        // A verified hardware pause produces no further U2 transactions,
        // while complete U1 scans and actual G/H releases/presses continue.
        @(negedge clk); slider_scan_pause = 1;
        verify_paused();
        sequence_before = word6;
        repeat (4) begin @(posedge key_update); #1; end
        if (word6 < sequence_before+4 || keys !== 16'h8200)
            $fatal(1,"Pausing U2 stopped U1 acquisition");
        @(negedge clk); key_device.mem[4] = 0; wait_keys(0);
        @(negedge clk); key_device.mem[4] = 8'h82; wait_keys(16'h8200);
        resume_slider();

        // NACK the actual LP write, rather than an earlier status read.
        @(negedge clk); slider_scan_pause = 1; forbid_ack = 1;
        wait(dut.slider.state == 13);
        @(negedge clk); slider_nack = 1;
        wait(errors[15:8] != 0);
        #1;
        if (slider_scan_paused || slider_ready || word5[23:16] == 0)
            $fatal(1,"Pause write NACK was not published as an error");
        @(negedge clk); forbid_ack = 0; slider_nack = 0;
        verify_paused(); resume_slider();

        // Corrupt only the completed LP write's readback. A fresh retry
        // reconfigures U2 and eventually performs a new verified pause.
        @(negedge clk); slider_scan_pause = 1; forbid_ack = 1;
        wait(dut.slider.state == 14 && !dut.slider.waiting);
        @(negedge clk); slider_device.mem[12] = 8'h7f;
        wait(errors[15:8] == 8'h06);
        #1;
        if (slider_scan_paused || slider_ready || word5[23:16] !== 8'h06)
            $fatal(1,"Bad LP readback acknowledged pause or hid mismatch error");
        @(negedge clk); forbid_ack = 0;
        verify_paused(); resume_slider();
        if (pause_acks != 3 || pause_verifications != 3 || resume_verifications != 3 || coherent_frames < 12)
            $fatal(1,"Incomplete diagnostics/pause coverage ack=%0d pause=%0d resume=%0d frames=%0d",
                   pause_acks,pause_verifications,resume_verifications,coherent_frames);
        $display("PASS touch diagnostics: exact G/H/status/sequence words, completed-frame coherence, flags/errors, verified LP pause with silent U2 and functional U1, verified resume, write NACK and readback mismatch recovery; frames=%0d pause/resume=%0d/%0d",
                 coherent_frames,pause_verifications,resume_verifications);
        $finish;
    end
    initial begin
        #40_000_000;
        $fatal(1,"Touch diagnostics timeout U1=%0d U2=%0d pause=%b ack=%b err=%h seq=%0d",
               dut.keypad.state,dut.slider.state,slider_scan_pause,slider_scan_paused,errors,word6);
    end
endmodule
