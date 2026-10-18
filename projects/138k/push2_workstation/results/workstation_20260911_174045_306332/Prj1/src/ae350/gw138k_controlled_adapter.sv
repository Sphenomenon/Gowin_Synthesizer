`timescale 1ns/1ps
// New board boundary. Legacy audio_processing_system / G1 remain untouched.
// clk_50m handles 31,250 baud MIDI; audio_clk MUST be nominal 76.8 MHz.
// PT8211 25 clocks/half-BCK -> 1600 clocks/frame -> exactly nominal 48 kHz.
// Q1.31 L/R goes directly to the existing stereo PT8211 quantizer. Original
// Q1.15 mix controls, Q0.24 envelope and internal headroom remain unchanged.
module gw138k_controlled_adapter (
    input wire clk_50m, audio_clk, reset_n, midi_rx_i,
    input wire pc_uart_rx_i,
    output wire [127:0] held_notes_o,
    output wire [31:0] applied_events_o,pc_health_o,
    input wire cpu_event_valid_i,
    input wire [17:0] cpu_event_i,
    output wire cpu_event_ready_o,
    output wire [31:0] control_state_o,control_pitch_o,control_options_o,
    output wire hp_bck, hp_ws, hp_din, pa_en,
    output wire sample_ce_o, sample_valid_o,
    output wire signed [31:0] audio_left_o, audio_right_o,
    output wire [31:0] active_mask_o, deadline_miss_o, midi_overflow_o, note_drop_o,
    output wire [31:0] underrun_count_o, midi_cdc_drop_o, observation_drop_o,
    output wire uart_error_o,
    input wire record_enable_i, record_ready_i,
    output wire record_valid_o,
    output wire [95:0] record_packet_o,
    output wire [31:0] record_drop_o,
    output wire fft_valid_o,
    output wire [7:0] fft_bin_o,
    output wire signed [23:0] fft_real_o, fft_imag_o,
    output wire [31:0] fft_frame_o,
    input wire score_write_i,
    input wire [7:0] score_address_i,
    input wire [63:0] score_data_i,
    input wire [8:0] score_length_i,
    input wire score_start_i, score_stop_i,
    output wire score_running_o, score_done_o,
    output wire [31:0] led_mask_o, score_frame_o,
    // Entire observation tuple is atomically delivered in clk_50m domain.
    output wire display_valid_o,
    output wire [31:0] display_pcm_o, display_reference_o, display_voices_o,
    output wire [31:0] display_status_o,
    output wire [2:0] effect_mask_o,
    output wire [5:0] effect_order_o
);
    // Permit a board-level asynchronous assertion; every functional domain
    // releases locally, including UART after an audio PLL restart.
    logic [2:0] reset_50_pipe, reset_audio_pipe;
    always_ff @(posedge clk_50m or negedge reset_n)
        if(!reset_n) reset_50_pipe<=0;
        else reset_50_pipe<={reset_50_pipe[1:0],1'b1};
    always_ff @(posedge audio_clk or negedge reset_n)
        if(!reset_n) reset_audio_pipe<=0;
        else reset_audio_pipe<={reset_audio_pipe[1:0],1'b1};
    wire reset_50_n=reset_50_pipe[2];
    wire reset_audio_n=reset_audio_pipe[2];
    wire midi_valid_50, midi_valid_audio;
    wire [7:0] midi_byte_50, midi_byte_audio;
    uart_rx #(.CLOCK_HZ(50000000),.BAUD(31250)) u_midi_rx(
        .clk_i(clk_50m),.rst_ni(reset_50_n),.rx_i(midi_rx_i),
        .valid_o(midi_valid_50),.data_o(midi_byte_50),.framing_error_o(uart_error_o));
    gw138k_stream_cdc #(.WIDTH(8)) u_midi_cdc(
        .reset_n(reset_n),.source_clk(clk_50m),.destination_clk(audio_clk),
        .source_valid(midi_valid_50),.source_data(midi_byte_50),.drop_count(midi_cdc_drop_o),
        .destination_valid(midi_valid_audio),.destination_data(midi_byte_audio));
    wire pc_valid_50,pc_valid_audio,pc_frame_error;
    wire [7:0] pc_byte_50,pc_byte_audio;
    wire [31:0] pc_drop,pc_overflow;
    uart_rx #(.CLOCK_HZ(50000000),.BAUD(115200)) u_pc_rx(
        .clk_i(clk_50m),.rst_ni(reset_50_n),.rx_i(pc_uart_rx_i),
        .valid_o(pc_valid_50),.data_o(pc_byte_50),.framing_error_o(pc_frame_error));
    gw138k_stream_cdc #(.WIDTH(8)) u_pc_cdc(
        .reset_n(reset_n),.source_clk(clk_50m),.destination_clk(audio_clk),
        .source_valid(pc_valid_50),.source_data(pc_byte_50),.drop_count(pc_drop),
        .destination_valid(pc_valid_audio),.destination_data(pc_byte_audio));
    reg pc_framing_sticky;
    always @(posedge clk_50m or negedge reset_50_n)
        if(!reset_50_n)pc_framing_sticky<=0;else if(pc_frame_error)pc_framing_sticky<=1;
    (* ASYNC_REG="TRUE" *) reg [1:0] pc_health_meta,pc_health_sync;
    always @(posedge audio_clk or negedge reset_audio_n)
        if(!reset_audio_n)begin pc_health_meta<=0;pc_health_sync<=0;end
        else begin pc_health_meta<={pc_drop!=0,pc_framing_sticky};pc_health_sync<=pc_health_meta;end
    assign pc_health_o={29'd0,pc_overflow!=0,pc_health_sync};
    wire [5:0] voice_count;
    wire [1:0] mode,route;
    wire [2:0] profile;
    assign control_state_o={synth_gain,voice_count,profile,route,mode,effect_mask};
    assign control_pitch_o={10'd0,pitch};
    wire [21:0] pitch;
    wire [15:0] synth_gain, pcm_gain;
    wire [2:0] effect_mask;
    wire [5:0] effect_order;
    assign effect_mask_o=effect_mask;
    assign effect_order_o=effect_order;
    wire synth_valid, clip;
    wire signed [31:0] synth;
    gw138k_event_workstation #(.SAMPLE_RATE_HZ(48000)) u_workstation(
        .clk_i(audio_clk),.rst_ni(reset_audio_n),.midi_byte_valid_i(midi_valid_audio),
        .midi_byte_i(midi_byte_audio),.pc_byte_valid_i(pc_valid_audio),.pc_byte_i(pc_byte_audio),
        .held_notes_o(held_notes_o),.applied_events_o(applied_events_o),.pc_overflow_o(pc_overflow),.control_options_o(control_options_o),.cpu_event_valid_i(cpu_event_valid_i),
        .cpu_event_i(cpu_event_i),.cpu_event_ready_o(cpu_event_ready_o),.sample_ce_i(sample_ce_o),
        .pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
        .sample_valid_o(sample_valid_o),.left_o(audio_left_o),.right_o(audio_right_o),
        .synth_valid_o(synth_valid),.synth_o(synth),.active_mask_o(active_mask_o),
        .active_voice_count_o(voice_count),.mode_o(mode),.route_o(route),.profile_o(profile),.pitch_q20_o(pitch),
        .deadline_miss_o(deadline_miss_o),.midi_overflow_o(midi_overflow_o),.note_drop_o(note_drop_o),
        .clip_o(clip),.synth_gain_o(synth_gain),.pcm_gain_o(pcm_gain),.effect_mask_o(effect_mask),.effect_order_o(effect_order));
    audio_visual_extensions u_extensions(
        .clk_i(audio_clk),.rst_ni(reset_audio_n),.sample_valid_i(sample_valid_o),
        .left_i(audio_left_o),.right_i(audio_right_o),
        .record_enable_i(record_enable_i),.record_ready_i(record_ready_i),
        .record_valid_o(record_valid_o),.record_packet_o(record_packet_o),.record_drop_o(record_drop_o),
        .fft_valid_o(fft_valid_o),.fft_bin_o(fft_bin_o),.fft_real_o(fft_real_o),.fft_imag_o(fft_imag_o),
        .fft_frame_o(fft_frame_o),.score_write_i(score_write_i),.score_address_i(score_address_i),
        .score_data_i(score_data_i),.score_length_i(score_length_i),.score_start_i(score_start_i),
        .score_stop_i(score_stop_i),.score_running_o(score_running_o),.score_done_o(score_done_o),
        .led_mask_o(led_mask_o),.score_frame_o(score_frame_o));
    // Conservative recapture epoch: any received MIDI byte invalidates a
    // waveform template. Low reference bits = 0 selects final-PCM triggering.
    logic [23:0] revision;
    always_ff @(posedge audio_clk or negedge reset_audio_n)
        if(!reset_audio_n) revision<=0;
        else if(midi_valid_audio || pc_valid_audio || (cpu_event_valid_i && cpu_event_ready_o)) revision<=revision+1'b1;
    wire [31:0] frame_count, frame_reference, frame_voices;
    pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1)) u_pt8211(
        .clk(audio_clk),.reset_n(reset_audio_n),.sample_data(audio_left_o),.sample_right(audio_right_o),
        .sample_valid(sample_valid_o),.sample_tick(sample_ce_o),
        .hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),
        .underrun_count(underrun_count_o),.frame_count(frame_count),
        .sample_revision(revision),.sample_nonzero_voices(active_mask_o),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(frame_voices),
        .sample_trigger_reference({revision,8'd0}),.frame_trigger_reference(frame_reference));
    wire output_valid;
    wire [31:0] output_pcm, output_reference;
    pt8211_observer u_observer(
        .clk(audio_clk),.reset_n(reset_audio_n),.bck(hp_bck),.ws(hp_ws),.din(hp_din),
        .frame_reference(frame_reference),.pcm_pair(output_pcm),
        .sample_valid(output_valid),.trigger_reference(output_reference));
    // Source-domain health is a single tuple, never unsynchronized counters.
    // bits31:16 underruns; 15:0 sum of core deadline/MIDI/note-drop faults.
    wire [31:0] core_faults=deadline_miss_o+midi_overflow_o+note_drop_o;
    gw138k_stream_cdc #(.WIDTH(128)) u_display_cdc(
        .reset_n(reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(output_valid),
        .source_data({output_pcm,output_reference,frame_voices,underrun_count_o[15:0],core_faults[15:0]}),
        .drop_count(observation_drop_o),.destination_valid(display_valid_o),
        .destination_data({display_pcm_o,display_reference_o,display_voices_o,display_status_o}));
endmodule
