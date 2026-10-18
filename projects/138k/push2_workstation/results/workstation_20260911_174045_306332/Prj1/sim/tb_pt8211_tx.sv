`timescale 1ns/1ps
module tb_pt8211_tx;
    reg clk=0;
    always #10 clk=~clk;
    reg reset_n=0, sample_valid=0;
    reg signed [31:0] sample_data=0;
    wire tick,bck,ws,din,pa;
    wire [31:0] underruns,frames;
    pt8211_tx dut(.clk(clk),.reset_n(reset_n),.sample_data(sample_data),.sample_valid(sample_valid),
        .sample_tick(tick),.hp_bck(bck),.hp_ws(ws),.hp_din(din),.pa_en(pa),
        .underrun_count(underruns),.frame_count(frames),.sample_revision(24'd0),
        .sample_nonzero_voices(32'd0),.trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices());
    reg producing=1;
    integer samples_seen=0, ticks=0;
    time last_tick=0, last_bck=0;
    reg [15:0] decoded, expect_word;
    integer bit_no;

    // independent bit receiver: align at WS falling, sample on each BCK rise.
    initial begin
        #65 reset_n=1;
        repeat (12) begin
            @(negedge ws);
            expect_word = (samples_seen == 0) ? 0 : 16'h1234;
            for(bit_no=15;bit_no>=0;bit_no=bit_no-1) begin
                @(posedge bck); #1;
                if (ws !== 0) $fatal(1,"right slot length/polarity");
                decoded[bit_no]=din;
            end
            if(decoded !== expect_word) $fatal(1,"right %h expected %h",decoded,expect_word);
            for(bit_no=15;bit_no>=0;bit_no=bit_no-1) begin
                @(posedge bck); #1;
                if (ws !== 1) $fatal(1,"left slot length/polarity");
                decoded[bit_no]=din;
            end
            if(decoded !== expect_word) $fatal(1,"left %h expected %h",decoded,expect_word);
            samples_seen=samples_seen+1;
        end
        producing=0;
        repeat(3) @(posedge tick);
        #1;
        if(underruns == 0 || dut.frame_sample !== 0) $fatal(1,"underrun must count and mute");
        if(dut.quantize16(32'h7fffffff) !== 16'h7fff) $fatal(1,"positive saturation");
        if(dut.quantize16(32'h80000000) !== 16'h8000) $fatal(1,"negative full scale");
        if(dut.quantize16(32'h00008000) !== 16'h0001) $fatal(1,"positive half rounding");
        if(dut.quantize16(32'hffff8000) !== 16'hffff) $fatal(1,"negative half rounding");
        if(dut.quantize16(32'hffffffff) !== 16'h0000) $fatal(1,"negative near zero rounding");
        repeat(510) @(posedge tick);
        #1;
        if(pa !== 0) $fatal(1,"amplifier must enable after warmup");
        reset_n=0; #1;
        if(pa !== 1) $fatal(1,"reset must shut amplifier down");
        $display("PASS tb_pt8211_tx: serial PCM, period, rounding, underrun, amplifier");
        $finish;
    end
    initial begin
        wait(reset_n);
        forever begin
            @(posedge tick);
            if(last_tick && $time-last_tick != 20480) $fatal(1,"sample period");
            last_tick=$time;
            if(producing) begin
                repeat(8) @(negedge clk);
                sample_data=32'h12340000; sample_valid=1;
                @(negedge clk); sample_valid=0;
            end
        end
    end
    always @(posedge bck) if(reset_n) begin
        if(last_bck && $time-last_bck != 640) $fatal(1,"BCK period");
        last_bck=$time;
    end
    initial begin #20000000; $fatal(1,"timeout"); end
endmodule
