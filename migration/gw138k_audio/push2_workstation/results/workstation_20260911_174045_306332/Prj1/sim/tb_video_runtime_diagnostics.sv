`timescale 1ns/1ps
module tb_video_runtime_diagnostics;
    localparam integer WINDOW = 4096;
    reg clk_50m=0, pixel_clk=0, ui_clk=0;
    reg pixel_clock_running=1, ui_clock_running=1;
    always #10 clk_50m=~clk_50m;
    // Deliberately unrelated clocks, nominally 148.5 MHz and 100 MHz.
    always #3.367 pixel_clk=pixel_clock_running ? ~pixel_clk : 1'b0;
    always #5 ui_clk=ui_clock_running ? ~ui_clk : 1'b0;
    reg reset_n=0, pixel_reset_request_n=0, ui_reset_request_n=0;
    wire pixel_reset_n, ui_reset_n;
    wire pixel_release_request=reset_n & pixel_reset_request_n;
    wire ui_release_request=reset_n & ui_reset_request_n;
    reg [1:0] pixel_input_reset_pipe=0, ui_input_reset_pipe=0;
    // Match the integration contract: global reset asserts every input-domain
    // reset even with stopped clocks; release traverses that domain's flops.
    always @(posedge pixel_clk or negedge pixel_release_request) begin
        if (!pixel_release_request) pixel_input_reset_pipe <= 0;
        else pixel_input_reset_pipe <= {pixel_input_reset_pipe[0],1'b1};
    end
    always @(posedge ui_clk or negedge ui_release_request) begin
        if (!ui_release_request) ui_input_reset_pipe <= 0;
        else ui_input_reset_pipe <= {ui_input_reset_pipe[0],1'b1};
    end
    assign pixel_reset_n=pixel_input_reset_pipe[1];
    assign ui_reset_n=ui_input_reset_pipe[1];
    always @(posedge pixel_reset_n)
        if (!reset_n || pixel_clk !== 1'b1) $fatal(1,"pixel reset contract violated");
    always @(posedge ui_reset_n)
        if (!reset_n || ui_clk !== 1'b1) $fatal(1,"UI reset contract violated");
    always @(negedge reset_n) begin
        #0.001;
        if (pixel_reset_n || ui_reset_n) $fatal(1,"global reset did not assert domain resets");
    end
    reg hdmi_hpd=1, video_locked=0, scanout_reset_n=0, serializer_reset=1;
    reg vblank_start=0, drive_ui_counts=0;
    reg [31:0] rendered_frames=0, underruns=0;
    wire [127:0] diagnostics;
    video_runtime_diagnostics #(.WINDOW_CYCLES(WINDOW)) dut (
        .clk_50m(clk_50m), .reset_n(reset_n),
        .pixel_clk(pixel_clk), .pixel_reset_n(pixel_reset_n),
        .ui_clk(ui_clk), .ui_reset_n(ui_reset_n),
        .hdmi_hpd(hdmi_hpd), .video_locked(video_locked),
        .scanout_reset_n(scanout_reset_n), .serializer_reset(serializer_reset),
        .vblank_start(vblank_start), .rendered_frames(rendered_frames),
        .underruns(underruns), .diagnostics(diagnostics)
    );
    integer ui_tick=0;
    reg [31:0] expected_frames=0;
    always @(posedge pixel_clk or negedge reset_n or negedge pixel_reset_n) begin
        if (!reset_n || !pixel_reset_n) expected_frames <= 0;
        else if (vblank_start) expected_frames <= expected_frames+1'b1;
    end
    always @(negedge ui_clk or negedge reset_n or negedge ui_reset_n) begin
        if (!reset_n || !ui_reset_n) begin
            rendered_frames <= 0; underruns <= 0; ui_tick <= 0;
        end else if (drive_ui_counts) begin
            rendered_frames <= rendered_frames+1'b1;
            if ((ui_tick % 2) == 0) underruns <= underruns+1'b1;
            ui_tick <= ui_tick+1;
        end
    end

    function bit single_gray_step(input [31:0] delta);
        single_gray_step = ((delta & (delta-1'b1)) == 0);
    endfunction
    reg [31:0] last_frame_gray=0, last_block_gray=0;
    reg [31:0] last_render_gray=0, last_under_gray=0;
    // Verify the actual source registers, including the low-half rollover.
    always @(posedge pixel_clk) begin
        #0.001;
        if (reset_n && pixel_reset_n &&
            !single_gray_step(dut.pixel_frame_gray ^ last_frame_gray))
            $fatal(1,"pixel frame Gray changed more than one bit");
        if (reset_n &&
            !single_gray_step({16'd0,dut.pixel_block_gray} ^ last_block_gray))
            $fatal(1,"pixel block Gray changed more than one bit");
        last_frame_gray=dut.pixel_frame_gray;
        last_block_gray={16'd0,dut.pixel_block_gray};
    end
    always @(posedge ui_clk) begin
        #0.001;
        if (reset_n && ui_reset_n &&
            (!single_gray_step(dut.memory_rendered_gray ^ last_render_gray) ||
             !single_gray_step(dut.memory_underrun_gray ^ last_under_gray)))
            $fatal(1,"UI Gray changed more than one bit");
        last_render_gray=dut.memory_rendered_gray;
        last_under_gray=dut.memory_underrun_gray;
    end
    always @(negedge reset_n or negedge pixel_reset_n) last_frame_gray=0;
    always @(negedge reset_n) last_block_gray=0;
    always @(negedge reset_n or negedge ui_reset_n) begin
        last_render_gray=0; last_under_gray=0;
    end

    task tick_reference(input integer cycles);
        repeat(cycles) @(negedge clk_50m);
    endtask
    task require_valid_frequency;
        begin
            if (!diagnostics[13]) $fatal(1,"complete window not marked valid");
            // 4096*20 ns/(6.734 ns*1024) = 11.88 blocks, quantized to 11/12.
            if (diagnostics[31:16] < 11 || diagnostics[31:16] > 12)
                $fatal(1,"wrong pixel frequency: %0d blocks",diagnostics[31:16]);
        end
    endtask
    task require_full_first_window;
        integer index;
        begin
            // Release occurs on a reference falling edge. No earlier valid
            // result may survive a reset or appear before a complete window.
            for(index=0;index<WINDOW;index=index+1) begin
                @(negedge clk_50m);
                if(diagnostics[13]) $fatal(1,"partial first window marked valid");
            end
            tick_reference(12);
            require_valid_frequency();
        end
    endtask
    task require_settled_counters;
        begin
            tick_reference(12);
            if(diagnostics[63:32] !== expected_frames ||
               diagnostics[95:64] !== rendered_frames ||
               diagnostics[127:96] !== underruns)
                $fatal(1,"counter mapping/CDC mismatch: got %h expected %h %h %h",
                       diagnostics[127:32],underruns,rendered_frames,expected_frames);
            if(diagnostics[7:0] !== 8'd1 || diagnostics[15:14] !== 2'd0)
                $fatal(1,"version or reserved bits incorrect");
        end
    endtask

    initial begin
        tick_reference(10);
        reset_n=1; ui_reset_request_n=1;
        tick_reference(WINDOW+10);
        if(diagnostics[15:8] !== 8'h11 || diagnostics[31:16] !== 16'd0)
            $fatal(1,"reset flags or initial invalid measurement incorrect");
        if(dut.pixel_block_count == 0)
            $fatal(1,"physical pixel count incorrectly gated by video reset");
        pixel_reset_request_n=1; video_locked=1; scanout_reset_n=1; serializer_reset=0;
        require_full_first_window();
        if(diagnostics[15:8] !== 8'h2f) $fatal(1,"running status bit map incorrect");

        // Count enough events to exercise a 16-bit carry and both 32-bit CDC
        // words. Events are intentionally faster than a real video frame.
        @(negedge pixel_clk); vblank_start=1;
        @(posedge ui_clk); drive_ui_counts=1;
        repeat(70000) @(posedge ui_clk);
        drive_ui_counts=0;
        @(negedge pixel_clk); vblank_start=0;
        require_settled_counters();
        if(expected_frames < 65536 || rendered_frames < 65536)
            $fatal(1,"test did not exercise counter low-half rollover");
        require_valid_frequency();

        // HPD is only an observation; unplugging must not stop measurement.
        hdmi_hpd=0; tick_reference(8);
        if(diagnostics[8] || !diagnostics[13]) $fatal(1,"HPD status/independence incorrect");
        hdmi_hpd=1;

        // A silent clock stall with lock/reset held high must be observable as
        // valid zero blocks. DDR-domain counters continue while vblank freezes.
        @(negedge pixel_clk); pixel_clock_running=0;
        @(posedge ui_clk); drive_ui_counts=1;
        tick_reference(2*WINDOW+12);
        drive_ui_counts=0;
        if(!diagnostics[13] || diagnostics[31:16] !== 16'd0)
            $fatal(1,"stopped pixel clock not reported as valid zero");
        require_settled_counters();
        pixel_clock_running=1;
        tick_reference(2*WINDOW+12);
        require_valid_frequency();

        // Reset while the source clock is stopped must still invalidate the
        // measurement and clear its frame counter in the reference domain.
        @(negedge pixel_clk); pixel_clock_running=0;
        @(negedge clk_50m);
        pixel_reset_request_n=0; scanout_reset_n=0; serializer_reset=1;
        tick_reference(8);
        if(diagnostics[13] || diagnostics[63:32] !== 32'd0 ||
           diagnostics[15:8] !== 8'h13)
            $fatal(1,"pixel reset with stopped clock was not observed");
        pixel_clock_running=1;
        tick_reference(WINDOW/2);
        if(diagnostics[13]) $fatal(1,"measurement valid while pixel reset active");
        pixel_reset_request_n=1; scanout_reset_n=1; serializer_reset=0;
        require_full_first_window();
        @(negedge pixel_clk); vblank_start=1;
        repeat(17) @(negedge pixel_clk);
        vblank_start=0;
        require_settled_counters();

        // A lock glitch shorter than one 50 MHz cycle invalidates the window.
        @(negedge clk_50m); #2 video_locked=0; #2 video_locked=1;
        tick_reference(2);
        if(diagnostics[13]) $fatal(1,"short lock-loss event left stale measurement valid");
        require_full_first_window();
        require_settled_counters();

        // A UI reset is observable even without a UI clock; independent pixel
        // frequency and frame diagnostics must remain available.
        @(negedge ui_clk); ui_clock_running=0;
        #1 ui_reset_request_n=0;
        tick_reference(8);
        if(diagnostics[127:64] !== 64'd0 || !diagnostics[13])
            $fatal(1,"UI reset masking or pixel independence failed");
        ui_clock_running=1;
        @(posedge ui_clk); ui_reset_request_n=1; drive_ui_counts=1;
        repeat(33) @(posedge ui_clk);
        drive_ui_counts=0;
        require_settled_counters();

        // Global reset/recovery also works with both observed clocks stopped.
        @(negedge pixel_clk); pixel_clock_running=0;
        @(negedge ui_clk); ui_clock_running=0;
        reset_n=0; pixel_reset_request_n=0; ui_reset_request_n=0; video_locked=0;
        tick_reference(8);
        if(diagnostics !== 128'd1) $fatal(1,"global reset record incorrect");
        reset_n=1;
        tick_reference(12);
        if(diagnostics[13]) $fatal(1,"stopped clocks after global reset marked valid");
        pixel_clock_running=1; ui_clock_running=1;
        tick_reference(12);
        pixel_reset_request_n=1; ui_reset_request_n=1; video_locked=1;
        require_full_first_window();
        require_settled_counters();
        $display("PASS tb_video_runtime_diagnostics: byte map, Gray CDC/rollover, full windows, clock stall, reset/lock recovery");
        $finish;
    end
    initial begin
        #10000000;
        $fatal(1,"diagnostics test timeout");
    end
endmodule
