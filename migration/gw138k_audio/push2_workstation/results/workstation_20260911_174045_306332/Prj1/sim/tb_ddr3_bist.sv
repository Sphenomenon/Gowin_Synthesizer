`timescale 1ns/1ps
module tb_ddr3_bist;
    localparam integer BURSTS = 31;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst_n = 0;
    wire req_valid, req_write;
    reg req_ready = 0;
    wire [28:0] req_addr;
    wire [255:0] req_wdata;
    reg rsp_valid = 0;
    reg [255:0] rsp_data = 0;
    wire done, failed;
    wire [31:0] error_count;
    wire [28:0] first_error_addr;
    ddr3_bist #(.BURSTS(BURSTS), .TIMEOUT_CYCLES(80)) dut (.*);

    reg [255:0] memory [0:BURSTS-1];
    reg [255:0] read_value;
    integer scenario = 0, writes = 0, reads = 0, responses = 0;
    integer pending = 0, delay_count = 0, cycles, seed = 27913;
    reg held = 0;
    reg [285:0] held_request;

    always @(negedge clk) begin
        rsp_valid = 0;
        if (!rst_n) begin
            req_ready = 0;
        end else begin
            req_ready = (scenario == 3) ? 0 : ($urandom_range(0, 3) != 0);
            if (pending && scenario != 2) begin
                if (delay_count == 0) begin
                    rsp_valid = 1;
                    rsp_data = read_value;
                end else delay_count = delay_count - 1;
            end
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            writes = 0;
            reads = 0;
            responses = 0;
            pending = 0;
            held = 0;
        end else begin
            if (held && req_valid && {req_write, req_addr, req_wdata} !== held_request)
                $fatal(1, "BIST changed a request under backpressure");
            held = req_valid && !req_ready;
            held_request = {req_write, req_addr, req_wdata};
            if (rsp_valid) begin
                if (!pending) $fatal(1, "unexpected model response");
                pending = 0;
                responses = responses + 1;
            end
            if (req_valid && req_ready) begin
                if (req_addr[2:0] != 0 || req_addr >= BURSTS*8)
                    $fatal(1, "BIST native address alignment/range");
                if (req_write) begin
                    if (pending) $fatal(1, "write while read pending");
                    if (req_addr !== (writes % BURSTS)*8)
                        $fatal(1, "incorrect write address progression");
                    if (writes >= BURSTS && req_wdata !== ~memory[req_addr>>3])
                        $fatal(1, "second pattern is not first pattern complement");
                    if (req_wdata[31:0] == req_wdata[63:32])
                        $fatal(1, "burst positions do not have distinct patterns");
                    memory[req_addr>>3] = req_wdata;
                    writes = writes + 1;
                end else begin
                    if (pending) $fatal(1, "more than one read pending");
                    if (writes < BURSTS || (reads >= BURSTS && writes != 2*BURSTS))
                        $fatal(1, "read before complete write pass");
                    if (req_addr !== (reads % BURSTS)*8)
                        $fatal(1, "incorrect read address progression");
                    pending = 1;
                    delay_count = $urandom_range(1, 9);
                    read_value = memory[req_addr>>3];
                    // Faults span the two 16-bit DRAM devices.
                    if (scenario == 1 && reads < BURSTS && req_addr == 24)
                        read_value[0] = !read_value[0];
                    if (scenario == 1 && reads < BURSTS && req_addr == 72)
                        read_value[16] = !read_value[16];
                    reads = reads + 1;
                end
            end
        end
    end

    task run_case(input integer next_scenario);
        begin
            @(negedge clk);
            rst_n = 0;
            scenario = next_scenario;
            repeat (4) @(negedge clk);
            rst_n = 1;
            cycles = 0;
            while (!done && cycles < 10000) begin
                @(negedge clk);
                cycles = cycles + 1;
            end
            if (!done) $fatal(1, "BIST did not finish case %0d", scenario);
            if (scenario < 2 && (writes != 2*BURSTS || reads != 2*BURSTS ||
                                responses != 2*BURSTS))
                $fatal(1, "incomplete two-pass coverage");
            if (scenario == 0 && (failed || error_count != 0))
                $fatal(1, "good memory marked failed");
            if (scenario == 1 && (!failed || error_count != 2 || first_error_addr != 24))
                $fatal(1, "data fault accounting incorrect");
            if (scenario >= 2 && (!failed || error_count != 1 || first_error_addr != 0))
                $fatal(1, "timeout not latched");
            repeat (5) @(negedge clk);
            if (!done || req_valid) $fatal(1, "finished BIST not quiescent");
        end
    endtask

    initial begin
        seed = $urandom(seed);
        run_case(0);
        run_case(1);
        run_case(2);
        run_case(3);
        $display("PASS tb_ddr3_bist: random stalls/latency, complete inverted passes, both DRAM faults, read/command timeouts");
        $finish;
    end
endmodule
