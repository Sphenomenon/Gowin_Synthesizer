`default_nettype none
// Explicit native-profile display composition. Physical observations cross as
// one held tuple; analysis/export is independent of the raster. Only a current,
// fully validated local cache may start a new raster. Audio never waits.
module workstation_display_runtime (
    input wire source_clk_i,source_reset_ni,clk_i,rst_ni,enabled_i,
    input wire frame_valid_i,frame_44k1_i,frame_error_i,observation_trusted_i,
    input wire [31:0] frame_epoch_i,frame_sequence_i,frame_pcm_i,
    input wire [31:0] trigger_reference_i,active_voices_i,status_i,
    input wire [2:0] effect_mask_i,
    input wire [5:0] effect_order_i,
    output wire [31:0] observation_drop_o,
    input wire [31:0] memory_status_i,
    input wire raster_busy_i,raster_start_i,
    output wire raster_allowed_o,current_image_o,summary_publish_o,
    output wire writer_busy_o,writer_done_o,writer_initialized_o,
    output wire writer_req_o,
    input wire writer_ready_i,
    output wire [28:0] writer_address_o,
    output wire [255:0] writer_data_o,
    output wire reader_busy_o,reader_done_o,reader_valid_o,reader_fault_o,
    output wire reader_req_o,
    input wire reader_ready_i,
    output wire [28:0] reader_address_o,
    input wire reader_response_i,
    input wire [255:0] reader_data_i,
    input wire render_read_enable_i,
    input wire [8:0] render_wave_address_i,render_spectrum_column_i,
    input wire [15:0] render_image_address_i,
    output wire [31:0] render_wave_data_o,
    output wire render_image_hit_o,
    output wire [7:0] render_spectrum_left_o,render_spectrum_right_o,
    output wire [255:0] render_meta_o,
    output wire [31:0] render_analysis_sequence_o,render_analysis_skipped_o,render_stereo_peaks_o,
    output wire [2:0] render_image_gain_o,
    output wire render_analysis_valid_o,
    output wire [31:0] render_frame_sequence_o,render_sample_rate_o,render_epoch_o,
    output wire [2:0] writer_diagnostic_o,
    output wire [3:0] reader_diagnostic_o
);
    wire common_reset_n=source_reset_ni && rst_ni;
    // Either domain may revoke the whole display immediately. Each owner's
    // release must nevertheless wait for its own clock, including a stopped
    // DDR clock; a 50MHz release must not drive the cache's asynchronous reset.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] source_release,memory_release;
    always @(posedge source_clk_i or negedge common_reset_n)
        if(!common_reset_n)source_release<=0;
        else source_release<={source_release[1:0],1'b1};
    always @(posedge clk_i or negedge common_reset_n)
        if(!common_reset_n)memory_release<=0;
        else memory_release<={memory_release[1:0],1'b1};
    wire source_reset_n=source_release[2];
    wire memory_reset_n=memory_release[2];
    wire memory_enabled=enabled_i && memory_reset_n;
    wire tuple_valid,tuple_rate,tuple_error,tuple_trusted;
    wire [31:0] tuple_epoch,tuple_sequence,tuple_pcm,tuple_reference,tuple_voices,tuple_status;
    wire [2:0] tuple_mask;
    wire [5:0] tuple_order;
    // Every multibit field that came from the 50MHz completed-frame snapshot
    // stays in the same held-word CDC, including its receipt-time trust bit.
    gw138k_stream_cdc #(.WIDTH(204)) observation(
        .reset_n(common_reset_n),.source_clk(source_clk_i),.destination_clk(clk_i),
        .source_valid(frame_valid_i),
        .source_data({observation_trusted_i,frame_44k1_i,frame_epoch_i,frame_sequence_i,frame_error_i,
            frame_pcm_i,trigger_reference_i,active_voices_i,status_i,effect_mask_i,effect_order_i}),
        .drop_count(observation_drop_o),.destination_valid(tuple_valid),
        .destination_data({tuple_trusted,tuple_rate,tuple_epoch,tuple_sequence,tuple_error,
            tuple_pcm,tuple_reference,tuple_voices,tuple_status,tuple_mask,tuple_order}));
    wire [31:0] destination_drop,destination_drop_gray;
    gw138k_counter_cdc drops(
        .reset_n(common_reset_n),.source_clk(source_clk_i),.destination_clk(clk_i),
        .source_count(observation_drop_o),.destination_count(destination_drop),
        .destination_gray(destination_drop_gray));
    reg [31:0] previous_drop_gray;
    reg drop_wrap_fault;
    // The reused mailbox counter wraps. Reaching its maximum permanently
    // revokes this observation path until common reset, before wrap can hide
    // loss. The 50MHz source clock is independent of the audio clock switch.
    always @(posedge source_clk_i or negedge source_reset_n)
        if(!source_reset_n)drop_wrap_fault<=0;
        else if(observation_drop_o==32'hffff_ffff)drop_wrap_fault<=1;
    (* ASYNC_REG="TRUE" *) reg [1:0] trusted_sync;
    always @(posedge clk_i or negedge memory_reset_n)
        if(!memory_reset_n)trusted_sync<=0;
        else trusted_sync<={trusted_sync[0],observation_trusted_i && !drop_wrap_fault};
    always @(posedge clk_i or negedge memory_reset_n)
        if(!memory_reset_n)previous_drop_gray<=0;else previous_drop_gray<=destination_drop_gray;
    // Gray is bijective, so change detection has the same cycle and wrap
    // behavior without putting the binary decode on immediate revocation.
    // Keep the small reductions explicit to avoid an ALU carry comparator.
    (* syn_keep=1 *) wire [7:0] drop_changed_groups;
    for(genvar group_index=0;group_index<8;group_index=group_index+1)begin:drop_change
        assign drop_changed_groups[group_index]=
            |(destination_drop_gray[group_index*4+:4]^previous_drop_gray[group_index*4+:4]);
    end
    wire observation_loss=|drop_changed_groups;
    wire trusted=trusted_sync[1] && (!tuple_valid || tuple_trusted);
    reg [31:0] reference_q,voices_q,status_q;
    reg [2:0] mask_q;
    reg [5:0] order_q;
    always @(posedge clk_i or negedge memory_reset_n)begin
        if(!memory_reset_n)begin reference_q<=0;voices_q<=0;status_q<=0;mask_q<=0;order_q<=6'b10_01_00;end
        else if(tuple_valid)begin
            reference_q<=tuple_reference;voices_q<=tuple_voices;status_q<=tuple_status;
            mask_q<=tuple_mask;order_q<=tuple_order;
        end
    end
    wire source_valid,wave_valid,analysis_context,analysis_valid,source_ready;
    wire [31:0] source_rate,source_epoch,source_generation,wave_rate,wave_epoch,wave_generation;
    wire [31:0] analysis_rate,analysis_epoch,analysis_generation,analysis_sequence,analysis_skipped,peaks;
    wire [2:0] gain;
    wire [255:0] metadata;
    wire read_enable;
    wire [1:0] read_kind;
    wire [15:0] read_address;
    wire [31:0] read_data;
    reg pending,loading,have_image,publish,load_request,export_live;
    reg [31:0] export_rate,export_epoch,export_generation,image_generation;
    wire unavailable;
    wire export_current=source_valid && export_rate==source_rate && export_epoch==source_epoch &&
        export_generation==source_generation;
    wire export_start=enabled_i && source_ready && writer_initialized_o && !writer_busy_o &&
        !reader_busy_o && !pending && !loading;
    // Context qualification ends at this request register. A context break
    // on its acceptance edge may start one obsolete private-cache read; the
    // current-image path revokes immediately and completion must still pass
    // the live export/current-context guards below. Do not reconnect the long
    // loss/context comparator cone to the reader state transition.
    wire load_start=load_request && enabled_i && export_live && !loading &&
        !reader_busy_o && !raster_busy_i && !raster_start_i;
    display_data_analysis_source producer(
        .clk(clk_i),.rst_ni(memory_reset_n),.frame_valid_i(tuple_valid),.frame_error_i(tuple_error),
        .frame_44k1_i(tuple_rate),.frame_epoch_i(tuple_epoch),.frame_sequence_i(tuple_sequence),.frame_pcm_i(tuple_pcm),
        .observation_trusted_i(trusted),.observation_loss_i(observation_loss),
        .trigger_reference_i(tuple_valid ? tuple_reference:reference_q),
        .active_voices_i(tuple_valid ? tuple_voices:voices_q),.status_i(tuple_valid ? tuple_status:status_q),
        .memory_status_i(memory_status_i),.effect_mask_i(mask_q),.effect_order_i(order_q),
        .start_i(export_start),.export_done_i(writer_done_o),.start_ready_o(source_ready),
        .source_context_valid_o(source_valid),.source_sample_rate_o(source_rate),.source_epoch_o(source_epoch),
        .source_generation_o(source_generation),.waveform_context_valid_o(wave_valid),
        .analysis_context_valid_o(analysis_context),.waveform_sample_rate_o(wave_rate),.waveform_epoch_o(wave_epoch),
        .waveform_generation_o(wave_generation),.analysis_sample_rate_o(analysis_rate),.analysis_epoch_o(analysis_epoch),
        .analysis_generation_o(analysis_generation),.effect_meta_o(metadata),.analysis_sequence_o(analysis_sequence),
        .analysis_skipped_o(analysis_skipped),.stereo_peaks_o(peaks),.analysis_valid_o(analysis_valid),.image_gain_o(gain),
        .discarded_contexts_o(),.read_enable_i(read_enable),.read_kind_i(read_kind),.read_addr_i(read_address),.read_data_o(read_data));
    display_data_writer #(.METADATA_MINOR(1)) writer(
        .clk(clk_i),.rst_n(memory_reset_n),.enabled(memory_enabled),.start(export_start),.effect_meta(metadata),
        .analysis_sequence(analysis_sequence),.analysis_skipped(analysis_skipped),.stereo_peaks(peaks),
        .analysis_valid(analysis_valid),.image_gain(gain),
        .source_context_valid_i(source_valid),.source_sample_rate_i(source_rate),.source_epoch_i(source_epoch),
        .source_generation_i(source_generation),.waveform_context_valid_i(wave_valid),.waveform_sample_rate_i(wave_rate),
        .waveform_epoch_i(wave_epoch),.waveform_generation_i(wave_generation),.analysis_context_valid_i(analysis_context),
        .analysis_sample_rate_i(analysis_rate),.analysis_epoch_i(analysis_epoch),.analysis_generation_i(analysis_generation),
        .context_rejected_o(),.context_aborted_o(),.context_unavailable_o(unavailable),.context_diagnostic_o(writer_diagnostic_o),
        .busy(writer_busy_o),.done(writer_done_o),.initialized(writer_initialized_o),.req_valid(writer_req_o),
        .req_ready(writer_ready_i),.req_addr(writer_address_o),.req_wdata(writer_data_o),
        .read_enable(read_enable),.read_kind(read_kind),.read_addr(read_address),.read_data(read_data));
    display_data_reader #(.METADATA_MINOR(1)) reader(
        .clk(clk_i),.rst_n(memory_reset_n),.enabled(memory_enabled),.start(load_start),
        .busy(reader_busy_o),.done(reader_done_o),.valid(reader_valid_o),.fault(reader_fault_o),
        .req_valid(reader_req_o),.req_ready(reader_ready_i),.req_addr(reader_address_o),
        .rsp_valid(reader_response_i),.rsp_data(reader_data_i),.render_read_enable(render_read_enable_i),
        .render_wave_addr(render_wave_address_i),.render_image_addr(render_image_address_i),
        .render_spectrum_column(render_spectrum_column_i),.render_wave_data(render_wave_data_o),
        .render_image_hit(render_image_hit_o),.render_spectrum_left(render_spectrum_left_o),
        .render_spectrum_right(render_spectrum_right_o),.render_meta(render_meta_o),
        .render_analysis_sequence(render_analysis_sequence_o),.render_analysis_skipped(render_analysis_skipped_o),
        .render_stereo_peaks(render_stereo_peaks_o),.render_image_gain(render_image_gain_o),
        .render_analysis_valid(render_analysis_valid_o),.render_frame_sequence(render_frame_sequence_o),
        .render_sample_rate_o(render_sample_rate_o),.render_epoch_o(render_epoch_o),.render_generation_o(),
        .render_context_changed_o(),.incompatible_o(),.diagnostic_code_o(reader_diagnostic_o));
    assign current_image_o=have_image && reader_valid_o && source_valid &&
        image_generation==source_generation && render_sample_rate_o==source_rate && render_epoch_o==source_epoch;
    assign raster_allowed_o=enabled_i && current_image_o && !pending && !loading && !reader_busy_o;
    assign summary_publish_o=enabled_i && publish && current_image_o;
    always @(posedge clk_i or negedge memory_reset_n)begin
        if(!memory_reset_n)begin
            pending<=0;loading<=0;have_image<=0;publish<=0;load_request<=0;export_live<=0;
            export_rate<=0;export_epoch<=0;export_generation<=0;image_generation<=0;
        end else begin
            publish<=0;
            load_request<=enabled_i && pending && export_live && export_current &&
                !loading && !reader_busy_o;
            if(export_start)begin
                export_rate<=source_rate;export_epoch<=source_epoch;export_generation<=source_generation;
                export_live<=1;
            end else if(!enabled_i || !export_current)export_live<=0;
            if(writer_done_o)pending<=enabled_i && export_live && !unavailable && export_current;
            if(pending && (!export_current || !export_live))pending<=0;
            if(load_start)begin pending<=0;loading<=1;end
            if(reader_done_o)begin
                loading<=0;
                if(loading && enabled_i && export_live && !reader_fault_o && reader_valid_o && export_current &&
                   render_sample_rate_o==export_rate && render_epoch_o==export_epoch)begin
                    have_image<=1;image_generation<=export_generation;publish<=1;
                end
            end
            // Disabling revokes the complete export/load transaction, even
            // if the real writer/reader later drains after re-enable. Their
            // existing outstanding DDR handshake remains under its owner.
            if(!enabled_i)begin
                pending<=0;loading<=0;load_request<=0;have_image<=0;
            end
        end
    end
endmodule
`default_nettype wire
