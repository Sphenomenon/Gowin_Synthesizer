`default_nettype none
// Optional A07 producer, after an atomic physical-frame CDC into clk. Reuses
// the maintained waveform capture and actual 2048-point stereo analysis. This
// module owns only observation-window cancellation, never the stream epoch.
module display_data_analysis_source (
    input wire clk,rst_ni,
    input wire frame_valid_i,frame_error_i,frame_44k1_i,
    input wire [31:0] frame_epoch_i,frame_sequence_i,frame_pcm_i,
    input wire observation_trusted_i,observation_loss_i,
    input wire [31:0] trigger_reference_i,active_voices_i,status_i,memory_status_i,
    input wire [2:0] effect_mask_i,
    input wire [5:0] effect_order_i,
    input wire start_i,export_done_i,
    output wire start_ready_o,
    output wire source_context_valid_o,
    output wire [31:0] source_sample_rate_o,source_epoch_o,source_generation_o,
    output wire waveform_context_valid_o,analysis_context_valid_o,
    output reg [31:0] waveform_sample_rate_o,waveform_epoch_o,waveform_generation_o,
    output reg [31:0] analysis_sample_rate_o,analysis_epoch_o,analysis_generation_o,
    output wire [255:0] effect_meta_o,
    output wire [31:0] analysis_sequence_o,analysis_skipped_o,stereo_peaks_o,
    output wire analysis_valid_o,
    output wire [2:0] image_gain_o,
    output reg [31:0] discarded_contexts_o,
    input wire read_enable_i,
    input wire [1:0] read_kind_i,
    input wire [15:0] read_addr_i,
    output wire [31:0] read_data_o
);
    reg have_context,rate_q,have_previous,break_previous,local_reset_n,aligned,exporting;
    reg [31:0] epoch_q,expected_sequence,generation_q,memory_status_q;
    reg [2:0] effect_mask_q;
    reg [5:0] effect_order_q;
    // These identities revoke raster/export admission in the same cycle. Keep
    // their equality reductions balanced instead of a 32-bit carry comparator
    // followed by the complete admission cone. Predict the following sequence
    // on receipt of each frame, outside the immediate loss/revocation path;
    // the addition keeps the original modulo-2^32 continuity rule.
    // A pair needs four LUT inputs. The former four-bit groups still mapped
    // to short ALU carry chains in M25; expose the XOR pairs and both OR
    // levels without changing any same-cycle revocation or four-state rule.
    (* syn_keep=1 *) wire [15:0] epoch_changed_pairs,sequence_changed_pairs;
    (* syn_keep=1 *) wire [3:0] epoch_changed_groups,sequence_changed_groups;
    (* syn_keep=1 *) wire [7:0] waveform_changed_groups,analysis_changed_groups;
    for(genvar identity_pair=0;identity_pair<16;identity_pair=identity_pair+1)begin:context_identity_pair
        assign epoch_changed_pairs[identity_pair]=
            (frame_epoch_i[identity_pair*2]^epoch_q[identity_pair*2]) |
            (frame_epoch_i[identity_pair*2+1]^epoch_q[identity_pair*2+1]);
        assign sequence_changed_pairs[identity_pair]=
            (frame_sequence_i[identity_pair*2]^expected_sequence[identity_pair*2]) |
            (frame_sequence_i[identity_pair*2+1]^expected_sequence[identity_pair*2+1]);
    end
    for(genvar identity_group=0;identity_group<4;identity_group=identity_group+1)begin:context_identity
        assign epoch_changed_groups[identity_group]=
            |epoch_changed_pairs[identity_group*4+:4];
        assign sequence_changed_groups[identity_group]=
            |sequence_changed_pairs[identity_group*4+:4];
    end
    for(genvar snapshot_group=0;snapshot_group<8;snapshot_group=snapshot_group+1)begin:snapshot_identity
        assign waveform_changed_groups[snapshot_group]=
            |(waveform_epoch_o[snapshot_group*4+:4]^epoch_q[snapshot_group*4+:4]) |
            |(waveform_generation_o[snapshot_group*4+:4]^generation_q[snapshot_group*4+:4]);
        assign analysis_changed_groups[snapshot_group]=
            |(analysis_epoch_o[snapshot_group*4+:4]^epoch_q[snapshot_group*4+:4]) |
            |(analysis_generation_o[snapshot_group*4+:4]^generation_q[snapshot_group*4+:4]);
    end
    wire context_changed=frame_valid_i && (!have_context || frame_44k1_i!=rate_q || |epoch_changed_groups);
    // context_changed already independently revokes the same sample below;
    // its negation need not sit in series with the sequence comparator.
    wire sequence_gap=frame_valid_i && have_previous && |sequence_changed_groups;
    wire context_break=!observation_trusted_i || observation_loss_i ||
        (frame_valid_i && (frame_error_i || frame_epoch_i==0 || context_changed || sequence_gap));
    assign source_sample_rate_o=rate_q ? 32'd44100:32'd48000;
    assign source_epoch_o=epoch_q;
    assign source_generation_o=generation_q;
    assign source_context_valid_o=have_context && epoch_q!=0 && observation_trusted_i && local_reset_n && !context_break;
    wire good_sample=frame_valid_i && source_context_valid_o;
    wire wave_ready,align_busy,align_done,capture_read_enable,analysis_ready,front_valid;
    wire [31:0] wave_peak,wave_voices,wave_status,wave_sequence,wave_skipped,wave_revision,capture_data,wave_data;
    wire [8:0] capture_read_addr;
    wire [15:0] peak_left,peak_right;
    wire [7:0] spectrum_left,spectrum_right;
    wire image_hit;
    wire accept_start=start_i && start_ready_o;
    wire signed [16:0] mono_sum=$signed({frame_pcm_i[31],frame_pcm_i[31:16]})+
        $signed({frame_pcm_i[15],frame_pcm_i[15:0]});
    wire signed [31:0] mono_sample=$signed({{15{mono_sum[16]}},mono_sum}) <<< 15;
    feedback_capture #(.INPUT_REGISTERED(1),.CAPTURE_SAMPLES(512),
        .TRIGGER_TIMEOUT_SAMPLES(8192),.SMOOTH_TRIGGER(1)) waveform(
        .source_clk(clk),.source_reset_n(local_reset_n),.sample_data(mono_sample),.sample_valid(good_sample),
        .trigger_reference(trigger_reference_i),.active_voices(active_voices_i),.status_data(status_i),
        .render_clk(clk),.render_reset_n(local_reset_n),.snapshot_ready(wave_ready),.snapshot_release(export_done_i),
        .snapshot_peak(wave_peak),.snapshot_voices(wave_voices),.snapshot_status(wave_status),
        .snapshot_sequence(wave_sequence),.snapshot_skipped(wave_skipped),.snapshot_revision(wave_revision),
        .wave_read_enable(capture_read_enable),.wave_read_addr(capture_read_addr),.wave_read_data(capture_data));
    feedback_wave_align aligner(
        .clk,.reset_n(local_reset_n),.start(wave_ready && !aligned && !align_busy && !align_done && !exporting),
        .snapshot_revision(wave_revision),.snapshot_peak(wave_peak),.busy(align_busy),.done(align_done),.waveform_held(),
        .capture_read_enable,.capture_read_addr,.capture_read_data(capture_data),
        .wave_read_enable(read_enable_i && read_kind_i==0),.wave_read_addr(read_addr_i[8:0]),.wave_read_data(wave_data));
    output_audio_analysis #(.ASYNC_DISPLAY(1),.XY_DIRECT(1)) analysis(
        .clk,.reset_n(local_reset_n),.source_clk(clk),.source_reset_n(local_reset_n),
        .pcm_pair(frame_pcm_i),.sample_valid(good_sample),.release_frame(accept_start && analysis_ready),
        .ready(analysis_ready),.peak_left,.peak_right,.image_gain(image_gain_o),
        .sequence_data(analysis_sequence_o),.skipped_data(analysis_skipped_o),
        .display_read_enable(read_enable_i && read_kind_i!=0),.spectrum_column(read_addr_i[8:0]),.image_addr(read_addr_i),
        .spectrum_left,.spectrum_right,.image_hit,.display_valid(front_valid));
    assign waveform_context_valid_o=aligned && source_context_valid_o &&
        waveform_sample_rate_o==source_sample_rate_o && !(|waveform_changed_groups);
    assign analysis_context_valid_o=front_valid && source_context_valid_o &&
        analysis_sample_rate_o==source_sample_rate_o && !(|analysis_changed_groups);
    assign analysis_valid_o=analysis_context_valid_o;
    // A newly finished analysis swaps on accept_start, then writer SNAPSHOT
    // reads its new immutable front and tags on the following clk edge.
    assign start_ready_o=waveform_context_valid_o && !exporting && (analysis_ready || analysis_context_valid_o);
    assign stereo_peaks_o={peak_left,peak_right};
    assign effect_meta_o={32'h44495350,23'd0,effect_order_q,effect_mask_q,
        wave_peak,wave_voices,wave_status,wave_sequence,wave_skipped,memory_status_q};
    assign read_data_o=read_kind_i==0 ? wave_data : read_kind_i==1 ? {31'd0,image_hit} :
        {16'd0,spectrum_right,spectrum_left};
    always @(posedge clk or negedge rst_ni)begin
        if(!rst_ni)begin
            have_context<=0;rate_q<=0;epoch_q<=0;have_previous<=0;expected_sequence<=0;
            generation_q<=1;break_previous<=0;local_reset_n<=0;aligned<=0;exporting<=0;
            waveform_sample_rate_o<=0;waveform_epoch_o<=0;waveform_generation_o<=0;
            analysis_sample_rate_o<=0;analysis_epoch_o<=0;analysis_generation_o<=0;
            memory_status_q<=0;effect_mask_q<=0;effect_order_q<=6'b10_01_00;discarded_contexts_o<=0;
        end else begin
            local_reset_n<=!context_break;break_previous<=context_break;
            if(frame_valid_i)begin
                have_context<=1;rate_q<=frame_44k1_i;epoch_q<=frame_epoch_i;
                expected_sequence<=frame_sequence_i+1'b1;have_previous<=1;
            end
            if(context_break)begin
                aligned<=0;exporting<=0;
                if(!break_previous)begin
                    generation_q<=generation_q==32'hffff_ffff ? 32'd1:generation_q+1'b1;
                    if(discarded_contexts_o!=32'hffff_ffff)discarded_contexts_o<=discarded_contexts_o+1'b1;
                end
            end else begin
                if(align_done)begin
                    aligned<=1;waveform_sample_rate_o<=source_sample_rate_o;
                    waveform_epoch_o<=epoch_q;waveform_generation_o<=generation_q;
                end
                if(accept_start)begin
                    exporting<=1;memory_status_q<=memory_status_i;
                    effect_mask_q<=effect_mask_i;effect_order_q<=effect_order_i;
                    if(analysis_ready)begin
                        analysis_sample_rate_o<=source_sample_rate_o;
                        analysis_epoch_o<=epoch_q;analysis_generation_o<=generation_q;
                    end
                end
                if(export_done_i)begin exporting<=0;aligned<=0;end
            end
        end
    end
endmodule
`default_nettype wire
