`timescale 1ps/1ps
module tb_workstation_input_fifo;
    parameter integer CPU_HALF_PERIOD_PS = 10417;
    reg usb_clk = 0, audio_clk = 0, usb_running = 1, audio_running = 1;
    reg usb_rst = 1, checking = 0, writes_enabled = 0, reads_enabled = 1, randomized = 0;
    reg [17:0] expected [0:32767];
    reg [15:0] write_random = 16'hace1, read_random = 16'h5173;
    reg [6:0] previous_write_gray = 0, previous_read_gray = 0, write_difference, read_difference;
    integer written = 0, consumed = 0, checks = 0, full_cycles = 0, epochs = 0;
    reg [17:0] epoch_seed = 0;
    wire [17:0] write_data = epoch_seed ^ written[17:0];
    wire write_enable = writes_enabled && (!randomized || write_random[1:0] != 0);
    wire read_enable = reads_enabled && (!randomized || read_random[1:0] != 0);
    wire write_ready, read_ready;
    wire [17:0] read_data;
    always #(CPU_HALF_PERIOD_PS) if (usb_running) usb_clk = !usb_clk; else usb_clk = 0;
    always #6510 if (audio_running) audio_clk = !audio_clk; else audio_clk = 0;
    gw138k_usb_event_fifo dut (.usb_rst(usb_rst), .usb_clk(usb_clk), .audio_clk(audio_clk),
        .w_data(write_data), .w_en(write_enable), .w_rdy(write_ready),
        .r_en(read_enable), .r_data(read_data), .r_rdy(read_ready));

    always @(negedge usb_clk) begin
        write_random <= {write_random[14:0], write_random[15] ^ write_random[13] ^ write_random[12] ^ write_random[10]};
        if (checking) begin
            write_difference = previous_write_gray ^ dut.fifo.unbuffered.produce_w_gry;
            if ((^write_difference) === 1'bx || (write_difference & (write_difference - 7'd1)) != 0)
                $fatal(1, "write Gray pointer changed more than one bit");
            if (dut.fifo.unbuffered.produce_w_gry !== ((dut.fifo.unbuffered.produce_w_bin >> 1) ^ dut.fifo.unbuffered.produce_w_bin))
                $fatal(1, "write Gray pointer does not encode binary pointer");
        end
        previous_write_gray = dut.fifo.unbuffered.produce_w_gry;
    end
    always @(negedge audio_clk) begin
        read_random <= {read_random[14:0], read_random[15] ^ read_random[13] ^ read_random[12] ^ read_random[10]};
        if (checking) begin
            read_difference = previous_read_gray ^ dut.fifo.unbuffered.consume_r_gry;
            if ((^read_difference) === 1'bx || (read_difference & (read_difference - 7'd1)) != 0)
                $fatal(1, "read Gray pointer changed more than one bit");
            if (dut.fifo.unbuffered.consume_r_gry !== ((dut.fifo.unbuffered.consume_r_bin >> 1) ^ dut.fifo.unbuffered.consume_r_bin))
                $fatal(1, "read Gray pointer does not encode binary pointer");
        end
        previous_read_gray = dut.fifo.unbuffered.consume_r_gry;
    end
    always @(posedge usb_clk) begin
        if (!checking) written = 0;
        else if (!usb_rst && write_enable) begin
            if (write_ready) begin
                if (written >= 32768) $fatal(1, "scoreboard capacity exceeded");
                expected[written] = write_data;
                written = written + 1;
            end else full_cycles = full_cycles + 1;
        end
    end
    always @(posedge audio_clk) begin
        if (!checking) consumed = 0;
        else if (read_enable && read_ready) begin
            if (consumed >= written || read_data !== expected[consumed])
                $fatal(1, "event FIFO lost ordering or retained stale data: epoch=%0d index=%0d word=%h", epochs, consumed, read_data);
            consumed = consumed + 1;
            checks = checks + 1;
        end
    end
    task clear_fifo;
        begin
            checking = 0;
            writes_enabled = 0;
            reads_enabled = 1;
            randomized = 0;
            usb_running = 1;
            audio_running = 1;
            usb_rst = 1;
            repeat (12) @(negedge usb_clk);
            repeat (12) @(negedge audio_clk);
            usb_rst = 0;
            repeat (24) @(negedge audio_clk);
            repeat (8) @(negedge usb_clk);
            if (read_ready) $fatal(1, "output buffer did not flush after reset");
            epochs = epochs + 1;
            epoch_seed = epoch_seed + 18'h08001;
            checking = 1;
        end
    endtask
    task drain_fifo;
        integer waited;
        begin
            writes_enabled = 0;
            reads_enabled = 1;
            randomized = 0;
            waited = 0;
            while ((consumed != written || read_ready) && waited < 1000) begin
                @(negedge audio_clk);
                waited = waited + 1;
            end
            repeat (16) @(negedge audio_clk);
            if (consumed != written || read_ready) $fatal(1, "event FIFO did not drain");
        end
    endtask
    integer held_count;
    initial begin
        clear_fifo();
        reads_enabled = 0;
        writes_enabled = 1;
        repeat (200) @(negedge usb_clk);
        if (write_ready || written < 64 || written > 65) $fatal(1, "full FIFO did not backpressure");
        held_count = written;
        repeat (80) @(negedge usb_clk);
        if (written != held_count) $fatal(1, "full FIFO overwrote unread events");
        reads_enabled = 1;
        randomized = 1;
        repeat (6000) @(negedge usb_clk);
        drain_fifo();
        if (written < 1000) $fatal(1, "insufficient wraparound coverage");
        audio_running = 0;
        writes_enabled = 1;
        repeat (300) @(negedge usb_clk);
        held_count = written;
        repeat (200) @(negedge usb_clk);
        if (written != held_count || write_ready) $fatal(1, "stopped audio consumer did not backpressure");
        audio_running = 1;
        drain_fifo();
        writes_enabled = 1;
        repeat (600) @(negedge usb_clk);
        @(negedge usb_clk);
        usb_running = 0;
        repeat (300) @(negedge audio_clk);
        if (consumed != written || read_ready) $fatal(1, "stopped USB producer retained phantom events");
        usb_running = 1;
        repeat (300) @(negedge usb_clk);
        reads_enabled = 0;
        repeat (100) @(negedge usb_clk);
        audio_running = 0;
        checking = 0;
        writes_enabled = 0;
        usb_rst = 1;
        repeat (80) @(negedge usb_clk);
        clear_fifo();
        writes_enabled = 1;
        reads_enabled = 1;
        randomized = 1;
        repeat (3000) @(negedge usb_clk);
        drain_fifo();
        if (checks < 3000 || full_cycles < 100 || epochs != 2) $fatal(1, "insufficient event FIFO coverage");
        $display("PASS workstation_input_fifo: half=%0d events=%0d full=%0d epochs=%0d registered Gray, wrap, full, stopped clocks, reset flush", CPU_HALF_PERIOD_PS, checks, full_cycles, epochs);
        $finish;
    end
    initial begin
        #2000000000;
        $fatal(1, "event FIFO test timed out");
    end
endmodule
