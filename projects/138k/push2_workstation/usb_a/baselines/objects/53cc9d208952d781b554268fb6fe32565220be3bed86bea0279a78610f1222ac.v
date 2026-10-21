// Small, synthesizable FLAC stream decoder.
//
// Supported subset (the subset used by the TF audio path):
//   fLaC marker, STREAMINFO metadata, fixed-block frames, constant/verbatim
//   and fixed-order (0..4) subframes with Rice residuals, mono and
//   independent stereo.
//
// LPC, variable-block frames, partitioned streams with unsupported coding,
// side/mid stereo and blocks above MAX_BLOCK_SAMPLES are reported through
// unsupported_o.  CRC
// bytes are consumed to preserve stream framing; this small implementation
// does not claim CRC validation.  The byte stream is held whenever a PCM
// pair is back-pressured, so no input byte is lost.
module tf_flac_pcm_decoder #(
    parameter integer MAX_BLOCK_SAMPLES = 8192
) (
    input  wire               clk,
    input  wire               rst_n,
    input  wire               restart,
    input  wire               in_valid,
    input  wire [7:0]         in_byte,
    output wire               in_ready,
    output wire               format_ready,
    output wire [19:0]        sample_rate_hz,
    output wire               stereo,
    output wire [5:0]         bits_per_sample,
    output wire               pcm_valid,
    input  wire               pcm_ready,
    output wire signed [15:0] pcm_left,
    output wire signed [15:0] pcm_right,
    output wire               unsupported,
    output wire               error,
    output wire [15:0]        frame_count
);
    localparam [7:0] S_MARK0       = 8'd0;
    localparam [7:0] S_MARK1       = 8'd1;
    localparam [7:0] S_MARK2       = 8'd2;
    localparam [7:0] S_MARK3       = 8'd3;
    localparam [7:0] S_META_H0     = 8'd4;
    localparam [7:0] S_META_H1     = 8'd5;
    localparam [7:0] S_META_H2     = 8'd6;
    localparam [7:0] S_META_STREAM = 8'd7;
    localparam [7:0] S_META_SKIP   = 8'd8;
    localparam [7:0] S_BITS        = 8'd9;
    localparam [7:0] S_HDR_CRC     = 8'd10;
    localparam [7:0] S_SF_ZERO     = 8'd11;
    localparam [7:0] S_SF_TYPE     = 8'd12;
    localparam [7:0] S_SF_WASTE    = 8'd13;
    localparam [7:0] S_SAMPLE      = 8'd14;
    localparam [7:0] S_CONST_EMIT  = 8'd15;
    localparam [7:0] S_RES_METHOD  = 8'd16;
    localparam [7:0] S_PART_ORDER  = 8'd17;
    localparam [7:0] S_RICE_PARAM  = 8'd18;
    localparam [7:0] S_RICE_UNARY  = 8'd19;
    localparam [7:0] S_RICE_REM    = 8'd20;
    localparam [7:0] S_RAW_BITS    = 8'd21;
    localparam [7:0] S_CRC16       = 8'd22;
    localparam [7:0] S_FAIL        = 8'd23;
    localparam [7:0] S_META_H3     = 8'd24;
    localparam [7:0] S_HDR_FRAME   = 8'd25;
    localparam [7:0] S_HDR_BLOCK6  = 8'd26;
    localparam [7:0] S_HDR_BLOCK7H = 8'd27;
    localparam [7:0] S_HDR_BLOCK7L = 8'd28;

    // Four bits are intentional: subframe and residual fields must not alias
    // frame-header fields.
    localparam [3:0] T_SYNC        = 4'd0;
    localparam [3:0] T_HDR_RES     = 4'd1;
    localparam [3:0] T_HDR_BLOCK   = 4'd2;
    localparam [3:0] T_BLOCK       = 4'd3;
    localparam [3:0] T_SRATE       = 4'd4;
    localparam [3:0] T_CHAN        = 4'd5;
    localparam [3:0] T_SSIZE       = 4'd6;
    localparam [3:0] T_SF_TYPE     = 4'd7;
    localparam [3:0] T_SAMPLE      = 4'd8;
    localparam [3:0] T_RES_METHOD  = 4'd9;
    localparam [3:0] T_PART_ORDER  = 4'd10;
    localparam [3:0] T_RICE_PARAM  = 4'd11;
    localparam [3:0] T_RICE_REM    = 4'd12;
    localparam [3:0] T_RAW_BITS    = 4'd13;
    localparam [3:0] T_FRAME_RES   = 4'd14;

    reg [7:0] state;
    reg [7:0] cur_byte;
    reg [3:0] bits_left;
    reg [31:0] field_acc;
    reg [6:0] field_need;
    reg [6:0] field_count;
    reg [3:0] field_target;

    reg [1:0] meta_last;
    reg [6:0] meta_type;
    reg [23:0] meta_length;
    reg [23:0] meta_remaining;
    reg [7:0] meta_index;
    reg [15:0] si_min_block, si_max_block;
    reg [19:0] sample_rate_r;
    reg [3:0] channels_r;
    reg [5:0] bits_per_sample_r;
    reg       bps_msb;

    reg format_ready_r;
    reg unsupported_r;
    reg error_r;
    reg [15:0] frame_count_r;

    // Code 7 encodes blocksize-1 in 16 bits, so 65,536 needs 17 bits.
    reg [16:0] block_size;
    reg [3:0] block_code;
    reg [3:0] sample_rate_code;
    reg [3:0] channel_assignment;
    reg [2:0] sample_size_code;
    reg [5:0] frame_bps;
    reg [1:0] subframe_index;
    reg [5:0] subframe_kind;
    reg [2:0] fixed_order;
    reg [16:0] sample_index;
    reg [31:0] warmup_left;
    reg [31:0] partition_index;
    reg [31:0] partition_order;
    reg [31:0] residual_left;
    reg [31:0] residual_count;
    reg [4:0] rice_param;
    reg [1:0] rice_method;
    reg [31:0] rice_quotient;
    reg [31:0] rice_unsigned;
    reg [5:0] raw_bits_left;
    reg signed [31:0] const_value;
    reg signed [31:0] pending_sample;
    reg wasted_flag;

    // Fixed prediction needs only the four most recent samples.  Independent
    // stereo retains channel 0 while channel 1 is decoded.  Registered reads
    // are required here: an asynchronous read makes Gowin expand the array
    // into registers/muxes and can exhaust host memory during synthesis.
    localparam integer BLOCK_ADDR_BITS =
        (MAX_BLOCK_SAMPLES <= 2) ? 1 : $clog2(MAX_BLOCK_SAMPLES);
    (* ram_style = "block" *) reg signed [31:0] ch0_mem [0:MAX_BLOCK_SAMPLES-1];
    reg                         ch0_write_en;
    reg [BLOCK_ADDR_BITS-1:0]   ch0_write_addr;
    reg signed [31:0]           ch0_write_data;
    reg signed [31:0]           ch0_read_data;
    reg signed [31:0] prev0, prev1, prev2, prev3;

    reg pcm_valid_r;
    reg signed [15:0] pcm_left_r, pcm_right_r;

    wire bit_in = (bits_left != 0) ? cur_byte[bits_left-1] : 1'b0;
    wire flow_stall = pcm_valid_r && !pcm_ready;
    // Constant subframes can emit one sample per cycle.  Prefetch channel 0
    // for the next sample only when the current PCM pair can advance; while
    // back-pressured, keep the current index selected.
    wire [16:0] ch0_read_index =
        (!flow_stall && state == S_CONST_EMIT && channel_assignment == 1 &&
         subframe_index != 0) ? sample_index + 17'd1 : sample_index;
    wire byte_state = (state == S_MARK0) || (state == S_MARK1) ||
                      (state == S_MARK2) || (state == S_MARK3) ||
                      (state == S_META_H0) || (state == S_META_H1) ||
                      (state == S_META_H2) || (state == S_META_H3) ||
                      (state == S_META_STREAM) ||
                      (state == S_META_SKIP) || (state == S_HDR_FRAME) ||
                      (state == S_HDR_BLOCK6) || (state == S_HDR_BLOCK7H) ||
                      (state == S_HDR_BLOCK7L);
    // A byte handshake is only a refill operation.  Bit-consuming states must
    // not advertise ready while a previously loaded byte still has bits left.
    assign in_ready = !flow_stall && (state != S_FAIL) && (bits_left == 0);

    function signed [31:0] sx_sample(input [31:0] value, input [5:0] width);
        reg signed [31:0] t;
        begin
            t = value[31:0];
            if (width < 32 && value[width-1])
                t = t | (~32'd0 << width);
            sx_sample = t;
        end
    endfunction

    function signed [31:0] predict_fixed(input [2:0] order);
        begin
            case (order)
                3'd0: predict_fixed = 0;
                3'd1: predict_fixed = prev0;
                3'd2: predict_fixed = (prev0 <<< 1) - prev1;
                3'd3: predict_fixed = (prev0 * 3) - (prev1 * 3) + prev2;
                3'd4: predict_fixed = (prev0 * 4) - (prev1 * 6) + (prev2 * 4) - prev3;
                default: predict_fixed = 0;
            endcase
        end
    endfunction

    function [15:0] to_pcm16(input signed [31:0] sample, input [5:0] width);
        reg signed [31:0] scaled;
        begin
            // FLAC PCM is signed.  Reduce wider samples by dropping LSBs and
            // expand narrow samples to the PCM16 full-scale convention.
            if (width > 16)
                scaled = sample >>> (width - 16);
            else if (width < 16)
                scaled = sample <<< (16 - width);
            else
                scaled = sample;
            to_pcm16 = scaled[15:0];
        end
    endfunction

    function signed [31:0] rice_to_signed(input [31:0] value);
        begin
            if (value[0])
                rice_to_signed = -$signed({1'b0, value[31:1]}) - 1;
            else
                rice_to_signed = $signed({1'b0, value[31:1]});
        end
    endfunction

    function [16:0] fixed_block_samples(input [3:0] code);
        begin
            case (code)
                4'd1: fixed_block_samples = 17'd192;
                4'd2: fixed_block_samples = 17'd576;
                4'd3: fixed_block_samples = 17'd1152;
                4'd4: fixed_block_samples = 17'd2304;
                4'd5: fixed_block_samples = 17'd4608;
                4'd8: fixed_block_samples = 17'd256;
                4'd9: fixed_block_samples = 17'd512;
                4'd10: fixed_block_samples = 17'd1024;
                4'd11: fixed_block_samples = 17'd2048;
                4'd12: fixed_block_samples = 17'd4096;
                4'd13: fixed_block_samples = 17'd8192;
                4'd14: fixed_block_samples = 17'd16384;
                4'd15: fixed_block_samples = 17'd32768;
                default: fixed_block_samples = 17'd0;
            endcase
        end
    endfunction

    wire [31:0] field_value = {field_acc[30:0], bit_in};
    wire [31:0] decoded_rice = rice_to_signed(rice_unsigned);

    // Set up a new bit field.  The helper is only used in sequential cases;
    // keeping the assignments explicit makes the generated logic portable to
    // the Gowin Verilog synthesizer.
    task automatic begin_field(input [6:0] width, input [3:0] target);
        begin
            field_acc <= 32'd0;
            field_need <= width;
            field_count <= 0;
            field_target <= target;
            state <= S_BITS;
        end
    endtask

    task automatic enter_subframe;
        begin
            subframe_kind <= 0;
            fixed_order <= 0;
            sample_index <= 0;
            warmup_left <= 0;
            partition_index <= 0;
            residual_left <= 0;
            prev0 <= 0;
            prev1 <= 0;
            prev2 <= 0;
            prev3 <= 0;
            state <= S_SF_ZERO;
        end
    endtask

    // Complete one decoded sample.  The task writes predictor storage and,
    // when the channel assignment permits it, publishes the stereo pair.
    task automatic accept_sample(input signed [31:0] sample_value);
        reg signed [31:0] right_value;
        reg signed [31:0] left_value;
        begin
            if ((channel_assignment == 1) && (subframe_index == 0)) begin
                ch0_write_en <= 1'b1;
                ch0_write_addr <= sample_index[BLOCK_ADDR_BITS-1:0];
                ch0_write_data <= sample_value;
            end
            if ((channel_assignment == 0) || (subframe_index != 0)) begin
                if (channel_assignment == 0) begin
                    left_value = sample_value;
                    right_value = sample_value;
                end else begin
                    left_value = ch0_read_data;
                    right_value = sample_value;
                end
                pcm_left_r <= to_pcm16(left_value, frame_bps);
                pcm_right_r <= to_pcm16(right_value, frame_bps);
                pcm_valid_r <= 1'b1;
            end
            if (sample_index + 17'd1 >= block_size) begin
                sample_index <= 0;
                if ((channel_assignment != 0) && (subframe_index == 0)) begin
                    subframe_index <= 1;
                    state <= S_SF_ZERO;
                end else begin
                    state <= S_CRC16;
                    field_acc <= 0;
                    field_need <= 16;
                    field_count <= 0;
                    field_target <= T_SYNC;
                end
            end else begin
                sample_index <= sample_index + 17'd1;
                if (subframe_kind == 1) begin
                    field_need <= frame_bps;
                    field_count <= 0;
                    field_acc <= 0;
                    field_target <= T_SAMPLE;
                    state <= S_BITS;
                end
                else if (subframe_kind >= 8)
                    state <= (residual_left != 0) ? S_RICE_UNARY : S_PART_ORDER;
            end
            prev3 <= prev2;
            prev2 <= prev1;
            prev1 <= prev0;
            prev0 <= sample_value;
        end
    endtask

    task automatic accept_residual(input signed [31:0] sample_value);
        begin
            accept_sample(sample_value);
            if (residual_left <= 1) begin
                residual_left <= 0;
                if (sample_index + 17'd1 < block_size && partition_index + 32'd1 < (32'd1 << partition_order)) begin
                    partition_index <= partition_index + 1;
                    residual_left <= block_size >> partition_order;
                    field_need <= (rice_method == 0) ? 4 : 5;
                    field_count <= 0;
                    field_acc <= 0;
                    field_target <= T_RICE_PARAM;
                    state <= S_BITS;
                // At the end of a block accept_sample selects either the
                // second stereo subframe or the frame CRC state.
                end
            end else begin
                residual_left <= residual_left - 1;
                rice_quotient <= 0;
                state <= S_RICE_UNARY;
            end
        end
    endtask

    always @(posedge clk) begin
        if (ch0_write_en)
            ch0_mem[ch0_write_addr] <= ch0_write_data;
        ch0_read_data <= ch0_mem[ch0_read_index[BLOCK_ADDR_BITS-1:0]];
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_MARK0;
            cur_byte <= 0;
            bits_left <= 0;
            field_acc <= 0;
            field_need <= 0;
            field_count <= 0;
            field_target <= 0;
            meta_last <= 0;
            meta_type <= 0;
            meta_length <= 0;
            meta_remaining <= 0;
            meta_index <= 0;
            si_min_block <= 0;
            si_max_block <= 0;
            sample_rate_r <= 0;
            channels_r <= 0;
            bits_per_sample_r <= 0;
            bps_msb <= 0;
            format_ready_r <= 0;
            unsupported_r <= 0;
            error_r <= 0;
            frame_count_r <= 0;
            block_size <= 0;
            block_code <= 0;
            sample_rate_code <= 0;
            channel_assignment <= 0;
            sample_size_code <= 0;
            frame_bps <= 0;
            subframe_index <= 0;
            subframe_kind <= 0;
            fixed_order <= 0;
            sample_index <= 0;
            warmup_left <= 0;
            partition_index <= 0;
            partition_order <= 0;
            residual_left <= 0;
            residual_count <= 0;
            rice_param <= 0;
            rice_method <= 0;
            rice_quotient <= 0;
            rice_unsigned <= 0;
            raw_bits_left <= 0;
            const_value <= 0;
            pending_sample <= 0;
            wasted_flag <= 0;
            pcm_valid_r <= 0;
            pcm_left_r <= 0;
            pcm_right_r <= 0;
            ch0_write_en <= 0;
            ch0_write_addr <= 0;
            ch0_write_data <= 0;
            prev0 <= 0;
            prev1 <= 0;
            prev2 <= 0;
            prev3 <= 0;
        end else if (restart) begin
            state <= S_MARK0;
            bits_left <= 0;
            format_ready_r <= 0;
            unsupported_r <= 0;
            error_r <= 0;
            frame_count_r <= 0;
            pcm_valid_r <= 0;
            sample_rate_r <= 0;
            channels_r <= 0;
            bits_per_sample_r <= 0;
            ch0_write_en <= 0;
            prev0 <= 0;
            prev1 <= 0;
            prev2 <= 0;
            prev3 <= 0;
        end else begin
            ch0_write_en <= 0;
            if (pcm_valid_r && pcm_ready)
                pcm_valid_r <= 0;

            if (!flow_stall) begin
                // A byte is loaded only when no previous bits remain.  Bit parser
                // states consume the loaded byte MSB first in following cycles.
                if (in_valid && in_ready && (bits_left == 0) && !byte_state)
                    begin cur_byte <= in_byte; bits_left <= 4'd8; end

            case (state)
                S_MARK0: if (in_valid && in_ready) begin
                    if (in_byte == 8'h66) state <= S_MARK1; else begin state <= S_FAIL; error_r <= 1; end
                end
                S_MARK1: if (in_valid && in_ready) begin
                    if (in_byte == 8'h4c) state <= S_MARK2; else begin state <= S_FAIL; error_r <= 1; end
                end
                S_MARK2: if (in_valid && in_ready) begin
                    if (in_byte == 8'h61) state <= S_MARK3; else begin state <= S_FAIL; error_r <= 1; end
                end
                S_MARK3: if (in_valid && in_ready) begin
                    if (in_byte == 8'h43) state <= S_META_H0; else begin state <= S_FAIL; error_r <= 1; end
                end
                S_META_H0: if (in_valid && in_ready) begin
                    meta_last <= in_byte[7];
                    meta_type <= in_byte[6:0];
                    state <= S_META_H1;
                end
                S_META_H1: if (in_valid && in_ready) begin
                    meta_length[23:16] <= in_byte;
                    state <= S_META_H2;
                end
                S_META_H2: if (in_valid && in_ready) begin
                    meta_length[15:8] <= in_byte;
                    state <= S_META_H3;
                end
                S_META_H3: if (in_valid && in_ready) begin
                    meta_length[7:0] <= in_byte;
                    meta_remaining <= {meta_length[23:16], meta_length[15:8], in_byte};
                    meta_index <= 0;
                    if (meta_type == 0 && {meta_length[23:16], meta_length[15:8], in_byte} >= 24'd34)
                        state <= S_META_STREAM;
                    else if ({meta_length[23:16], meta_length[15:8], in_byte} != 0)
                        state <= S_META_SKIP;
                    else if (meta_last)
                        state <= S_BITS;
                    else
                        state <= S_META_H0;
                end
                S_META_STREAM: if (in_valid && in_ready) begin
                    meta_remaining <= meta_remaining - 24'd1;
                    meta_index <= meta_index + 8'd1;
                    case (meta_index)
                        0: si_min_block[15:8] <= in_byte;
                        1: si_min_block[7:0] <= in_byte;
                        2: si_max_block[15:8] <= in_byte;
                        3: si_max_block[7:0] <= in_byte;
                        10: sample_rate_r[19:12] <= in_byte;
                        11: sample_rate_r[11:4] <= in_byte;
                        12: begin
                            sample_rate_r[3:0] <= in_byte[7:4];
                            channels_r <= {1'b0, in_byte[3:1]} + 4'd1;
                            bps_msb <= in_byte[0];
                        end
                        13: begin
                            bits_per_sample_r <= {bps_msb, in_byte[7:4]} + 1'b1;
                        end
                        default: ;
                    endcase
                    if (meta_remaining == 1) begin
                        if (meta_length != 34) begin
                            unsupported_r <= 1;
                            state <= S_FAIL;
                        end else if (si_max_block > MAX_BLOCK_SAMPLES) begin
                            unsupported_r <= 1;
                            state <= S_FAIL;
                        end else if (meta_last) begin
                            format_ready_r <= 1;
                            state <= S_BITS;
                            field_acc <= 0;
                            field_need <= 14;
                            field_count <= 0;
                            field_target <= T_SYNC;
                        end else begin
                            state <= S_META_H0;
                        end
                    end
                end
                S_META_SKIP: if (in_valid && in_ready) begin
                    meta_remaining <= meta_remaining - 24'd1;
                    if (meta_remaining == 1) begin
                        if (meta_last) begin
                            format_ready_r <= 1;
                            state <= S_BITS;
                            field_acc <= 0;
                            field_need <= 14;
                            field_count <= 0;
                            field_target <= T_SYNC;
                        end else state <= S_META_H0;
                    end
                end
                S_BITS: if (bits_left != 0) begin
                    bits_left <= bits_left - 4'd1;
                    field_acc <= field_value;
                    if (field_count + 7'd1 >= field_need) begin
                        field_count <= 0;
                        case (field_target)
                            T_SYNC: begin
                                if (field_value[13:0] != 14'h3ffe) begin
                                    error_r <= 1; state <= S_FAIL;
                                end else begin
                                    field_need <= 1; field_target <= T_HDR_RES; state <= S_BITS;
                                end
                            end
                            T_HDR_RES: begin
                                if (field_value[0]) begin error_r <= 1; state <= S_FAIL; end
                                else begin field_need <= 1; field_target <= T_HDR_BLOCK; end
                            end
                            T_HDR_BLOCK: begin
                                // Only fixed-block frames are accepted here.
                                if (field_value[0]) begin unsupported_r <= 1; state <= S_FAIL; end
                                else begin field_need <= 4; field_target <= T_BLOCK; end
                            end
                            T_BLOCK: begin
                                block_code <= field_value[3:0];
                                field_need <= 4; field_target <= T_SRATE;
                            end
                            T_SRATE: begin
                                sample_rate_code <= field_value[3:0];
                                field_need <= 4; field_target <= T_CHAN;
                            end
                            T_CHAN: begin
                                channel_assignment <= field_value[3:0];
                                field_need <= 3; field_target <= T_SSIZE;
                            end
                            T_SSIZE: begin
                                sample_size_code <= field_value[2:0];
                                field_need <= 1; field_target <= T_FRAME_RES;
                                state <= S_BITS;
                                if ((block_code == 0) ||
                                    !((channel_assignment == 0) || (channel_assignment == 1)) ||
                                    (field_value[2:0] == 3) ||
                                    (field_value[2:0] == 7) || (sample_rate_code >= 12) ||
                                    (((block_code != 6) && (block_code != 7)) &&
                                     (fixed_block_samples(block_code) > MAX_BLOCK_SAMPLES))) begin
                                    unsupported_r <= 1; state <= S_FAIL;
                                end else begin
                                    // Codes 6/7 receive their explicit block
                                    // size after the frame-number field.
                                    block_size <= fixed_block_samples(block_code);
                                    case (field_value[2:0])
                                        1: frame_bps <= 8;
                                        2: frame_bps <= 12;
                                        4: frame_bps <= 16;
                                        5: frame_bps <= 20;
                                        6: frame_bps <= 24;
                                        default: frame_bps <= bits_per_sample_r;
                                    endcase
                                end
                            end
                            default: ;
                        endcase
                    end else field_count <= field_count + 7'd1;
                end else if (in_valid && in_ready) begin
                    cur_byte <= in_byte;
                    bits_left <= 8;
                end
                S_HDR_FRAME: if (in_valid && in_ready) begin
                    // UTF-8 encoded frame number (or sample number for a
                    // variable-block frame).  The common one-byte form is
                    // enough for the streaming path; continuation bytes are
                    // consumed by treating them as an opaque header field.
                    if (block_code == 6) state <= S_HDR_BLOCK6;
                    else if (block_code == 7) state <= S_HDR_BLOCK7H;
                    else state <= S_HDR_CRC;
                end
                S_HDR_BLOCK6: if (in_valid && in_ready) begin
                    block_size <= {9'd0, in_byte} + 17'd1;
                    if (({9'd0, in_byte} + 17'd1) > MAX_BLOCK_SAMPLES) begin unsupported_r <= 1; state <= S_FAIL; end
                    else state <= S_HDR_CRC;
                end
                S_HDR_BLOCK7H: if (in_valid && in_ready) begin
                    field_acc[15:8] <= in_byte;
                    state <= S_HDR_BLOCK7L;
                end
                S_HDR_BLOCK7L: if (in_valid && in_ready) begin
                    block_size <= {1'b0, field_acc[15:8], in_byte} + 17'd1;
                    if (({1'b0, field_acc[15:8], in_byte} + 17'd1) > MAX_BLOCK_SAMPLES) begin unsupported_r <= 1; state <= S_FAIL; end
                    else state <= S_HDR_CRC;
                end
                S_HDR_CRC: if (bits_left != 0) begin
                    bits_left <= bits_left - 4'd1;
                    if (field_count + 7'd1 >= 7'd8) begin
                        field_count <= 0;
                        subframe_index <= 0;
                        enter_subframe();
                    end else field_count <= field_count + 7'd1;
                end else if (in_valid && in_ready) begin
                    cur_byte <= in_byte; bits_left <= 8;
                end
                S_SF_ZERO: if (bits_left != 0) begin
                    bits_left <= bits_left - 4'd1;
                    if (bit_in != 0) begin unsupported_r <= 1; state <= S_FAIL; end
                    else begin field_need <= 6; field_count <= 0; field_acc <= 0; field_target <= T_SF_TYPE; state <= S_BITS; end
                end else if (in_valid && in_ready) begin cur_byte <= in_byte; bits_left <= 8; end
                S_SF_TYPE: ; // retained for state-map readability; type uses S_BITS
                S_SF_WASTE: if (bits_left != 0) begin
                    bits_left <= bits_left - 4'd1;
                    if (bit_in) begin unsupported_r <= 1; wasted_flag <= 1; state <= S_FAIL; end
                    else begin
                        if (subframe_kind == 0) begin
                            field_need <= frame_bps; field_count <= 0; field_acc <= 0; field_target <= T_SAMPLE; state <= S_BITS;
                        end else if (subframe_kind == 1) begin
                            field_need <= frame_bps; field_count <= 0; field_acc <= 0; field_target <= T_SAMPLE; state <= S_BITS;
                        end else begin
                            warmup_left <= fixed_order;
                            if (fixed_order != 0) begin field_need <= frame_bps; field_count <= 0; field_acc <= 0; field_target <= T_SAMPLE; state <= S_BITS; end
                            else begin field_need <= 2; field_count <= 0; field_acc <= 0; field_target <= T_RES_METHOD; state <= S_BITS; end
                        end
                    end
                end else if (in_valid && in_ready) begin cur_byte <= in_byte; bits_left <= 8; end
                S_SAMPLE: begin
                    // Sample fields are completed by S_BITS target T_SAMPLE.
                end
                S_CONST_EMIT: if (!flow_stall) begin
                    accept_sample(const_value);
                end
                S_RES_METHOD: ;
                S_PART_ORDER: ;
                S_RICE_PARAM: ;
                S_RICE_UNARY: if (bits_left != 0) begin
                    bits_left <= bits_left - 4'd1;
                    if (bit_in) begin
                        if (rice_param == 0) begin
                            rice_unsigned <= rice_quotient;
                            pending_sample <= predict_fixed(fixed_order) + rice_to_signed(rice_quotient);
                            accept_residual(predict_fixed(fixed_order) + rice_to_signed(rice_quotient));
                        end else begin
                            field_need <= rice_param; field_count <= 0; field_acc <= 0; field_target <= T_RICE_REM; state <= S_BITS;
                        end
                    end else rice_quotient <= rice_quotient + 1;
                end else if (in_valid && in_ready) begin cur_byte <= in_byte; bits_left <= 8; end
                S_RICE_REM: ;
                S_RAW_BITS: ;
                S_CRC16: if (bits_left != 0) begin
                    bits_left <= bits_left - 4'd1;
                    if (field_count + 7'd1 >= 7'd16) begin
                        field_count <= 0;
                        frame_count_r <= frame_count_r + 16'd1;
                        field_need <= 14; field_count <= 0; field_acc <= 0; field_target <= T_SYNC; state <= S_BITS;
                    end else field_count <= field_count + 7'd1;
                end else if (in_valid && in_ready) begin cur_byte <= in_byte; bits_left <= 8; end
                S_FAIL: begin
                    bits_left <= 0;
                end
                default: state <= S_FAIL;
            endcase

            // Actions associated with fields that finish in S_BITS are kept
            // here so all variable-width fields share one bit reader.
            if (state == S_BITS && bits_left != 0 && field_count + 7'd1 >= field_need) begin
                case (field_target)
                    T_SF_TYPE: begin
                        subframe_kind <= field_value[5:0];
                        if (field_value[5:0] == 0) subframe_kind <= 0;
                        else if (field_value[5:0] == 1) subframe_kind <= 1;
                        else if (field_value[5:0] >= 8 && field_value[5:0] <= 12) begin
                            subframe_kind <= field_value[5:0];
                            fixed_order <= field_value[2:0];
                        end else begin unsupported_r <= 1; state <= S_FAIL; end
                        field_need <= 1; field_count <= 0; field_target <= T_SYNC; state <= S_SF_WASTE;
                    end
                    T_SAMPLE: begin
                        if (subframe_kind == 0 && sample_index == 0) begin
                            const_value <= sx_sample(field_value, frame_bps);
                            sample_index <= 0;
                            state <= S_CONST_EMIT;
                        end else if (subframe_kind == 0) begin
                            accept_sample(const_value);
                        end else if (subframe_kind == 1 || warmup_left != 0) begin
                            pending_sample <= sx_sample(field_value, frame_bps);
                            accept_sample(sx_sample(field_value, frame_bps));
                            if (warmup_left != 0) warmup_left <= warmup_left - 1;
                            if (warmup_left == 1) begin
                                field_need <= 2; field_count <= 0; field_acc <= 0; field_target <= T_RES_METHOD; state <= S_BITS;
                            end else if (warmup_left > 1) begin
                                field_need <= frame_bps; field_count <= 0; field_acc <= 0; field_target <= T_SAMPLE; state <= S_BITS;
                            end
                        end
                    end
                    T_RES_METHOD: begin
                        rice_method <= field_value[1:0];
                        if (field_value[1:0] > 1) begin unsupported_r <= 1; state <= S_FAIL; end
                        else begin field_need <= 4; field_count <= 0; field_acc <= 0; field_target <= T_PART_ORDER; state <= S_BITS; end
                    end
                    T_PART_ORDER: begin
                        partition_order <= field_value[3:0];
                        partition_index <= 0;
                        residual_count <= (block_size >> field_value[3:0]) - fixed_order;
                        residual_left <= (block_size >> field_value[3:0]) - fixed_order;
                        field_need <= (rice_method == 0) ? 4 : 5;
                        field_count <= 0; field_acc <= 0; field_target <= T_RICE_PARAM; state <= S_BITS;
                    end
                    T_RICE_PARAM: begin
                        rice_param <= field_value[4:0];
                        rice_quotient <= 0;
                        if ((rice_method == 0 && field_value[3:0] == 15) ||
                            (rice_method == 1 && field_value[4:0] == 31)) begin
                            unsupported_r <= 1; state <= S_FAIL;
                        end else if (residual_left == 0) begin
                            if (partition_index + 1 < (32'd1 << partition_order)) begin
                                partition_index <= partition_index + 1;
                                residual_left <= block_size >> partition_order;
                                field_need <= (rice_method == 0) ? 4 : 5;
                                field_count <= 0; field_acc <= 0; field_target <= T_RICE_PARAM; state <= S_BITS;
                            end else state <= S_CRC16;
                        end else state <= S_RICE_UNARY;
                    end
                    T_FRAME_RES: begin
                        if (field_value[0]) begin error_r <= 1; state <= S_FAIL; end
                        else begin
                            field_count <= 0;
                            state <= S_HDR_FRAME;
                        end
                    end
                    T_RICE_REM: begin
                        rice_unsigned <= (rice_quotient << rice_param) | field_value[31:0];
                        accept_residual(predict_fixed(fixed_order) + rice_to_signed((rice_quotient << rice_param) | field_value[31:0]));
                    end
                    default: ;
                endcase
            end
            end
        end
    end

    assign format_ready = format_ready_r;
    assign sample_rate_hz = sample_rate_r;
    assign stereo = (channels_r == 2);
    assign bits_per_sample = bits_per_sample_r;
    assign pcm_valid = pcm_valid_r;
    assign pcm_left = pcm_left_r;
    assign pcm_right = pcm_right_r;
    assign unsupported = unsupported_r;
    assign error = error_r;
    assign frame_count = frame_count_r;
endmodule
