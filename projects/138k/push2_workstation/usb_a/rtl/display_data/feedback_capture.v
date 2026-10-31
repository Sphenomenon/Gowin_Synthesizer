`default_nettype none

// Derivative: optional six-pole Xilinx trigger with bounded live capture.
// Two-bank observation RAM. Start each 512-sample Q1.31 block on the synth's
// sample-aligned reference cycle. Without a reference, use a rising zero
// crossing armed by a negative excursion below the hysteresis level.
// Silence and a bounded auto-trigger keep status/flat traces refreshing.
// The published bank is immutable until the renderer releases it. Meanwhile
// the other bank captures the next block; if both are occupied, only display
// observations are discarded. There is deliberately no audio ready signal.
// Both resets must assert together; release is synchronized in each domain.
module feedback_capture #(
    // 167.77216 ms at 48,828.125 Hz: longer than a MIDI note 0 period.
    // A value of 1 gives immediate auto capture (also useful for RAM tests).
    parameter integer TRIGGER_TIMEOUT_SAMPLES = 8192,
    // Renderer uses 1024 points so it can choose a matched 512-point window.
    parameter integer CAPTURE_SAMPLES = 512,
    parameter integer INPUT_REGISTERED = 0,
    parameter integer SMOOTH_TRIGGER = 0
) (
    input wire source_clk,
    input wire source_reset_n,
    input wire [31:0] sample_data,
    input wire sample_valid,
    input wire [31:0] trigger_reference,
    input wire [31:0] active_voices,
    input wire [31:0] status_data,
    input wire render_clk,
    input wire render_reset_n,
    output reg snapshot_ready,
    input wire snapshot_release,
    output reg [31:0] snapshot_peak,
    output reg [31:0] snapshot_voices,
    output reg [31:0] snapshot_status,
    output reg [31:0] snapshot_sequence,
    output reg [31:0] snapshot_skipped,
    output reg [31:0] snapshot_revision,
    input wire wave_read_enable,
    input wire [$clog2(CAPTURE_SAMPLES)-1:0] wave_read_addr,
    output reg [31:0] wave_read_data
);
    // Only observation data is delayed; no audio backpressure or new memory.
    reg valid_q;
    reg [31:0] sample_q,reference_q,voices_q,status_q,magnitude_q;
    always @(posedge source_clk or negedge source_reset_n) begin
        if(!source_reset_n) begin
            valid_q<=0;sample_q<=0;reference_q<=0;voices_q<=0;status_q<=0;magnitude_q<=0;
        end else begin
            valid_q<=sample_valid;
            sample_q<=sample_data;reference_q<=trigger_reference;
            voices_q<=active_voices;status_q<=status_data;
            magnitude_q<=sample_data[31] ? -sample_data : sample_data;
        end
    end
    wire sample_valid_local=INPUT_REGISTERED ? valid_q : sample_valid;
    wire [31:0] sample_data_local=INPUT_REGISTERED ? sample_q : sample_data;
    wire [31:0] trigger_reference_local=INPUT_REGISTERED ? reference_q : trigger_reference;
    wire [31:0] active_voices_local=INPUT_REGISTERED ? voices_q : active_voices;
    wire [31:0] status_data_local=INPUT_REGISTERED ? status_q : status_data;
    // No reset on the memory or its read register, to infer dual-clock BSRAM.
    // Consumers may read only after snapshot_ready; all block words exist.
    localparam integer ADDRESS_BITS = $clog2(CAPTURE_SAMPLES);
    localparam [ADDRESS_BITS-1:0] LAST_SAMPLE = CAPTURE_SAMPLES - 1;
    reg [31:0] samples [0:2*CAPTURE_SAMPLES-1];
    reg write_bank, render_bank;
    reg [ADDRESS_BITS-1:0] write_index;
    reg block_complete, published_pending;
    localparam integer WAIT_BITS = TRIGGER_TIMEOUT_SAMPLES > 1 ? $clog2(TRIGGER_TIMEOUT_SAMPLES) : 1;
    localparam [WAIT_BITS-1:0] WAIT_LAST = TRIGGER_TIMEOUT_SAMPLES - 1;
    // 1/2048 full scale, below one vertical display pixel (1/256).
    localparam [31:0] TRIGGER_HYSTERESIS = 32'h00100000;
    reg trigger_armed, capturing;
    reg [WAIT_BITS-1:0] trigger_wait;
    reg [31:0] capture_peak, capture_voices, capture_status;
    reg [31:0] capture_revision, held_revision;
    reg [31:0] sequence_count, skipped_count;
    reg held_bank;
    reg [31:0] held_peak, held_voices, held_status, held_sequence, held_skipped;
    reg request_toggle, acknowledge_toggle;
    (* ASYNC_REG = "TRUE" *) reg ack_meta, ack_sync;
    (* ASYNC_REG = "TRUE" *) reg req_meta, req_sync;
    reg req_settled;
    wire [31:0] magnitude = INPUT_REGISTERED ? magnitude_q : sample_data_local[31] ? (~sample_data_local + 1'b1) : sample_data_local;
    wire [31:0] next_peak = magnitude > capture_peak ? magnitude : capture_peak;
    wire rising_trigger = trigger_armed && !sample_data_local[31];
    wire smooth_trigger;
    generate if(SMOOTH_TRIGGER) begin : g_smooth
        reg signed [31:0] poles[0:5];
        reg signed [31:0] previous;
        reg armed;
        integer k;
        wire signed [32:0] slope=$signed({poles[5][31],poles[5]})-$signed({previous[31],previous});
        function signed [31:0] smooth(input signed [31:0] value,old_value);
            reg [6:0] low_sum;
            reg [31:0] value_upper,old_upper_complement,round_carry,overflow_correction;
            reg [31:0] sum1,carry1,sum2,carry2,sum3,carry3;
            begin
                // Preserve the signed 33-bit subtract/round wrap, then form
                // the update with one final carry-propagating addition.
                low_sum={2'b00,value[4:0]}+{2'b00,~old_value[4:0]}+7'd17;
                value_upper={{5{value[31]}},value[31:5]};
                old_upper_complement=~{{5{old_value[31]}},old_value[31:5]};
                round_carry={30'd0,low_sum[6:5]};
                overflow_correction=(value[31:5]==27'h3ffffff &&
                    old_value[31:5]==27'h4000000 && low_sum[6:5]==2'd2) ? 32'hf0000000 : 32'd0;
                sum1=old_value^value_upper^old_upper_complement;
                carry1=((old_value&value_upper)|(old_value&old_upper_complement)|
                    (value_upper&old_upper_complement))<<1;
                sum2=sum1^carry1^round_carry;
                carry2=((sum1&carry1)|(sum1&round_carry)|(carry1&round_carry))<<1;
                sum3=sum2^carry2^overflow_correction;
                carry3=((sum2&carry2)|(sum2&overflow_correction)|(carry2&overflow_correction))<<1;
                smooth=sum3+carry3;
            end
        endfunction
        assign smooth_trigger=armed && !slope[32];
        always @(posedge source_clk or negedge source_reset_n) begin
            if(!source_reset_n) begin
                previous<=0;armed<=0;
                for(k=0;k<6;k=k+1)poles[k]<=0;
            end else if(sample_valid_local) begin
                previous<=poles[5];poles[0]<=smooth($signed(sample_data_local),poles[0]);
                for(k=1;k<6;k=k+1)poles[k]<=smooth(poles[k-1],poles[k]);
                if(slope < -33'sd64)armed<=1;
                else if(!slope[32])armed<=0;
            end
        end
    end else begin : g_raw
        assign smooth_trigger=rising_trigger;
    end endgenerate
    wire phase_trigger = trigger_reference_local[0] ? trigger_reference_local[1] : smooth_trigger;
    wire idle_silence = active_voices_local == 0 && sample_data_local == 0;
    wire [31:0] source_revision = {8'd0,trigger_reference_local[31:8]};
    wire revision_changed = source_revision != capture_revision;
    wire capture_sample = !block_complete && (!revision_changed || SMOOTH_TRIGGER) &&
                          (capturing || phase_trigger || idle_silence || trigger_wait == WAIT_LAST);

    always @(posedge source_clk) begin
        if (source_reset_n && sample_valid_local && capture_sample)
            samples[{write_bank, write_index}] <= sample_data_local;
    end
    always @(posedge render_clk) begin
        if (wave_read_enable) wave_read_data <= samples[{render_bank, wave_read_addr}];
    end

    always @(posedge source_clk or negedge source_reset_n) begin
        if (!source_reset_n) begin
            write_bank <= 0; write_index <= 0;
            block_complete <= 0; published_pending <= 0;
            trigger_armed <= 0; capturing <= 0; trigger_wait <= 0;
            capture_peak <= 0; capture_voices <= 0; capture_status <= 0;
            capture_revision <= 0; held_revision <= 0;
            sequence_count <= 0; skipped_count <= 0;
            held_bank <= 0; held_peak <= 0; held_voices <= 0; held_status <= 0;
            held_sequence <= 0; held_skipped <= 0;
            request_toggle <= 0; ack_meta <= 0; ack_sync <= 0;
        end else begin
            ack_meta <= acknowledge_toggle;
            ack_sync <= ack_meta;
            if (published_pending && ack_sync == request_toggle)
                published_pending <= 0;
            if (sample_valid_local) begin
                // Track/consume edges even while both banks are busy. A
                // crossing missed there cannot become a stale trigger later.
                // Invalid bus values between sample strobes do not count.
                if (sample_data_local[31] && magnitude >= TRIGGER_HYSTERESIS)
                    trigger_armed <= 1;
                else if (!sample_data_local[31]) trigger_armed <= 0;
                if (block_complete) skipped_count <= skipped_count + 1'b1;
                else if (revision_changed && !SMOOTH_TRIGGER) begin
                    // Never compare a template against a half-old/half-new
                    // sound after a command. Published banks stay immutable.
                    capturing <= 0; write_index <= 0; capture_peak <= 0;
                    trigger_wait <= 0; capture_revision <= source_revision;
                end
                else if (capture_sample) begin
                    // Live waveforms include transients; MIDI traffic cannot
                    // restart a capture indefinitely. Metadata tracks its end.
                    if(SMOOTH_TRIGGER) capture_revision<=source_revision;
                    capturing <= 1;
                    trigger_wait <= 0;
                    capture_peak <= next_peak;
                    capture_voices <= active_voices_local;
                    capture_status <= status_data_local;
                    if (write_index == LAST_SAMPLE) begin
                        block_complete <= 1;
                        capturing <= 0;
                    end
                    else write_index <= write_index + 1'b1;
                end else trigger_wait <= trigger_wait + 1'b1;
            end
            if (block_complete && !published_pending) begin
                held_bank <= write_bank;
                held_peak <= capture_peak;
                held_voices <= capture_voices;
                held_status <= capture_status;
                held_revision <= capture_revision;
                held_sequence <= sequence_count;
                held_skipped <= skipped_count;
                sequence_count <= sequence_count + 1'b1;
                request_toggle <= ~request_toggle;
                published_pending <= 1;
                write_bank <= ~write_bank;
                write_index <= 0;
                capture_peak <= 0;
                block_complete <= 0;
                capturing <= 0;
                trigger_wait <= 0;
            end
        end
    end

    always @(posedge render_clk or negedge render_reset_n) begin
        if (!render_reset_n) begin
            req_meta <= 0; req_sync <= 0; req_settled <= 0;
            acknowledge_toggle <= 0; snapshot_ready <= 0; render_bank <= 0;
            snapshot_peak <= 0; snapshot_voices <= 0; snapshot_status <= 0;
            snapshot_sequence <= 0; snapshot_skipped <= 0;
            snapshot_revision <= 0;
        end else begin
            req_meta <= request_toggle;
            req_sync <= req_meta;
            // Extra cycle allows the held 32-bit metadata buses to settle.
            req_settled <= req_sync;
            if (!snapshot_ready && req_settled != acknowledge_toggle) begin
                render_bank <= held_bank;
                snapshot_peak <= held_peak;
                snapshot_voices <= held_voices;
                snapshot_status <= held_status;
                snapshot_revision <= held_revision;
                snapshot_sequence <= held_sequence;
                snapshot_skipped <= held_skipped;
                snapshot_ready <= 1;
            end
            if (snapshot_ready && snapshot_release) begin
                snapshot_ready <= 0;
                acknowledge_toggle <= req_settled;
            end
        end
    end
endmodule

`default_nettype wire
