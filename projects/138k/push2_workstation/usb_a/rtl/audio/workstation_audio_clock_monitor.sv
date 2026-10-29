`timescale 1ns/1ps

// Reference-domain monitor for an independent clock. Source counter and Gray
// encoding are both registered in that source domain; restart never resets it.
module workstation_audio_clock_monitor #(
    parameter integer REFERENCE_HZ=50000000,
    parameter integer CLOCK_48_HZ=12288000,
    parameter integer CLOCK_44_HZ=16934400,
    parameter integer WINDOW_CYCLES=50000,
    parameter integer TOLERANCE_PPM=2000,
    parameter integer QUANTIZATION_EDGES=2,
    parameter integer STABLE_WINDOWS=4,
    parameter integer LOSS_TIMEOUT_CYCLES=500,
    parameter integer STOP_LOW_CYCLES=16,
    parameter integer COUNTER_BITS=32
) (
    input wire clk_i, rst_ni, source_clk_i,
    input wire restart_i, expect_44k1_i,
    output reg qualified_o, clock_present_o,
    output wire stopped_low_o,
    output reg window_valid_o, window_good_o,
    output reg [COUNTER_BITS-1:0] window_edges_o
);
    localparam integer WINDOW_BITS=$clog2(WINDOW_CYCLES+1);
    localparam integer AGE_BITS=$clog2(LOSS_TIMEOUT_CYCLES+1);
    localparam integer IDLE_BITS=$clog2(STOP_LOW_CYCLES+1);
    localparam integer STABLE_BITS=$clog2(STABLE_WINDOWS+1);
    localparam [63:0] REF_HZ_U64=64'(REFERENCE_HZ),WINDOW_U64=64'(WINDOW_CYCLES);
    localparam [63:0] PPM_U64=64'(TOLERANCE_PPM),QUANT_U64=64'(QUANTIZATION_EDGES);
    localparam [63:0] FLOOR_48=(64'(CLOCK_48_HZ)*WINDOW_U64)/REF_HZ_U64;
    localparam [63:0] FLOOR_44=(64'(CLOCK_44_HZ)*WINDOW_U64)/REF_HZ_U64;
    localparam [63:0] CEIL_48=(64'(CLOCK_48_HZ)*WINDOW_U64+REF_HZ_U64-1)/REF_HZ_U64;
    localparam [63:0] CEIL_44=(64'(CLOCK_44_HZ)*WINDOW_U64+REF_HZ_U64-1)/REF_HZ_U64;
    localparam [63:0] RAW_MIN_48=(FLOOR_48*(1000000-PPM_U64))/1000000;
    localparam [63:0] RAW_MIN_44=(FLOOR_44*(1000000-PPM_U64))/1000000;
    localparam [63:0] LIMIT_MIN_48=RAW_MIN_48>QUANT_U64 ? RAW_MIN_48-QUANT_U64 : 0;
    localparam [63:0] LIMIT_MIN_44=RAW_MIN_44>QUANT_U64 ? RAW_MIN_44-QUANT_U64 : 0;
    localparam [63:0] LIMIT_MAX_48=(CEIL_48*(1000000+PPM_U64)+999999)/1000000+QUANT_U64;
    localparam [63:0] LIMIT_MAX_44=(CEIL_44*(1000000+PPM_U64)+999999)/1000000+QUANT_U64;
    localparam [COUNTER_BITS-1:0] MIN_48=COUNTER_BITS'(LIMIT_MIN_48), MAX_48=COUNTER_BITS'(LIMIT_MAX_48);
    localparam [COUNTER_BITS-1:0] MIN_44=COUNTER_BITS'(LIMIT_MIN_44), MAX_44=COUNTER_BITS'(LIMIT_MAX_44);

    initial begin
        if (COUNTER_BITS<4 || COUNTER_BITS>32 || WINDOW_CYCLES<8 ||
            STABLE_WINDOWS<1 || LOSS_TIMEOUT_CYCLES<8 || STOP_LOW_CYCLES<4 ||
            REFERENCE_HZ<=0 || TOLERANCE_PPM<0 || TOLERANCE_PPM>=1000000 || QUANTIZATION_EDGES<0)
            $fatal(1,"invalid audio clock monitor parameters");
        if (LIMIT_MAX_48 >= (64'd1 << (COUNTER_BITS-1)) || LIMIT_MAX_44 >= (64'd1 << (COUNTER_BITS-1)))
            $fatal(1,"clock counter cannot disambiguate a measurement window");
    end

    // Global assertion works with a stopped source. Its return only releases
    // these measurement registers after three local edges; failure decisions
    // remain in clk_i and never wait for this release handshake.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] source_reset_pre;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg source_reset_n;
    always @(posedge source_clk_i or negedge rst_ni)
        if (!rst_ni) begin source_reset_pre<=0; source_reset_n<=0; end
        else begin source_reset_pre<={source_reset_pre[0],1'b1}; source_reset_n<=source_reset_pre[1]; end
    reg [COUNTER_BITS-1:0] source_binary;
    (* syn_preserve=1 *) reg [COUNTER_BITS-1:0] source_gray;
    wire [COUNTER_BITS-1:0] source_next=source_binary+1'b1;
    always @(posedge source_clk_i or negedge source_reset_n) begin
        if (!source_reset_n) begin source_binary<=0; source_gray<=0; end
        else begin source_binary<=source_next; source_gray<=(source_next>>1)^source_next; end
    end
    // Apply routed max-delay/skew constraints from source_gray to gray_meta;
    // a broad asynchronous exception alone does not preserve Gray coherence.
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [COUNTER_BITS-1:0] gray_meta,gray_sync;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg level_meta,level_sync;
    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin gray_meta<=0; gray_sync<=0; level_meta<=0; level_sync<=0; end
        else begin
            gray_meta<=source_gray; gray_sync<=gray_meta;
            level_meta<=source_clk_i; level_sync<=level_meta;
        end
    end
    function automatic [COUNTER_BITS-1:0] gray_binary(input [COUNTER_BITS-1:0] value);
        integer bit_index;
        begin
            gray_binary[COUNTER_BITS-1]=value[COUNTER_BITS-1];
            for (bit_index=COUNTER_BITS-2;bit_index>=0;bit_index=bit_index-1)
                gray_binary[bit_index]=gray_binary[bit_index+1]^value[bit_index];
        end
    endfunction
    wire [COUNTER_BITS-1:0] observed_binary=gray_binary(gray_sync);
    reg [COUNTER_BITS-1:0] previous_gray,window_baseline;
    reg previous_level,previous_mode;
    reg [2:0] primed;
    reg [WINDOW_BITS-1:0] window_timer;
    reg [AGE_BITS-1:0] loss_age;
    reg [IDLE_BITS-1:0] idle_age;
    reg [STABLE_BITS-1:0] stable_windows;
    wire gray_changed=gray_sync!=previous_gray;
    wire any_changed=gray_changed || level_sync!=previous_level;
    wire [COUNTER_BITS-1:0] delta=observed_binary-window_baseline;
    wire in_range=expect_44k1_i ? delta>=MIN_44 && delta<=MAX_44 : delta>=MIN_48 && delta<=MAX_48;
    wire alive_now=gray_changed || loss_age<AGE_BITS'(LOSS_TIMEOUT_CYCLES-1);
    assign stopped_low_o=primed[2] && !level_sync && idle_age>=IDLE_BITS'(STOP_LOW_CYCLES);

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            qualified_o<=0; clock_present_o<=0;
            window_valid_o<=0; window_good_o<=0; window_edges_o<=0;
            previous_gray<=0; window_baseline<=0; previous_level<=0; previous_mode<=0;
            primed<=0; window_timer<=0; loss_age<=0; idle_age<=0; stable_windows<=0;
        end else begin
            previous_gray<=gray_sync;
            previous_level<=level_sync;
            previous_mode<=expect_44k1_i;
            window_valid_o<=0;
            if (restart_i || previous_mode!=expect_44k1_i) begin
                qualified_o<=0; clock_present_o<=0;
                window_good_o<=0; window_edges_o<=0;
                window_baseline<=observed_binary;
                primed<=0; window_timer<=0; loss_age<=0; idle_age<=0; stable_windows<=0;
            end else if (!primed[2]) begin
                // Flush both level/Gray synchronizer histories before measuring
                // a new DCS selection; old qualification cannot leak through.
                primed<={primed[1:0],1'b1};
                window_baseline<=observed_binary;
                window_timer<=0; loss_age<=0; idle_age<=0;
            end else begin
                if (gray_changed) begin loss_age<=0; clock_present_o<=1; end
                else if (loss_age<AGE_BITS'(LOSS_TIMEOUT_CYCLES)) begin
                    loss_age<=loss_age+1'b1;
                    if (loss_age==AGE_BITS'(LOSS_TIMEOUT_CYCLES-1)) clock_present_o<=0;
                end
                if (any_changed) idle_age<=0;
                else if (idle_age<IDLE_BITS'(STOP_LOW_CYCLES)) idle_age<=idle_age+1'b1;
                if (window_timer==WINDOW_BITS'(WINDOW_CYCLES-1)) begin
                    window_timer<=0; window_baseline<=observed_binary;
                    window_valid_o<=1; window_edges_o<=delta;
                    window_good_o<=in_range && alive_now;
                    if (in_range && alive_now) begin
                        if (stable_windows<STABLE_BITS'(STABLE_WINDOWS)) stable_windows<=stable_windows+1'b1;
                        if (stable_windows>=STABLE_BITS'(STABLE_WINDOWS-1)) qualified_o<=1;
                    end else begin stable_windows<=0; qualified_o<=0; end
                end else window_timer<=window_timer+1'b1;
                // Missing clock revokes qualification without waiting for the
                // next frequency window; a returning source must qualify anew.
                if (!alive_now) begin stable_windows<=0; qualified_o<=0; end
            end
        end
    end
endmodule
