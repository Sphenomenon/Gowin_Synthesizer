// Board-level TF audio integration for the workstation.
//
// The SD/FAT reader and decoder run at 50 MHz.  File bytes cross into the DDR
// user clock through tf_audio_ddr_path's byte FIFOs; decoded PCM16 crosses into
// the audio clock through a shallow stereo FIFO.  Only one decoder kind is
// elaborated, so MP3/WAV/FLAC are build-time profiles rather than three
// simultaneous BSRAM consumers.
module tf_workstation_audio_bridge #(
    parameter integer AUDIO_KIND = 2,
    parameter [23:0] FILE_EXT = "WAV",
    parameter integer CAPTURE_ON_ANALYSIS = 0
) (
    input  wire               clk_50m,
    input  wire               reset_n,
    input  wire               audio_clk,
    input  wire               audio_reset_n,
    input  wire               memory_clk,
    input  wire               memory_reset_n,
    input  wire               memory_ready,
    input  wire               restart,
    input  wire [3:0]         track_index,
    input  wire               sd_miso,
    output wire               sd_cs_n,
    output wire               sd_sck,
    output wire               sd_mosi,

    input  wire               sample_ce,
    output reg  signed [31:0] pcm_left,
    output reg  signed [31:0] pcm_right,
    output reg                pcm_active,
    output reg                source_active,
    output wire [19:0]        sample_rate_hz,
    output wire               format_ready,
    output wire               unsupported,
    output wire               ddr_error,
    output wire [31:0]        file_size,
    output wire [4:0]         track_count,
    output wire               playlist_ready,
    output wire               card_lost,
    output wire [10:0]        hotplug_debug,
    input  wire [7:0]         playlist_name_addr,
    output wire [7:0]         playlist_name_data,
    input  wire               playback_hold_i,
    input  wire               analysis_hold_i,
    input  wire               analysis_enable_i,
    input  wire               analysis_pcm_ready_i,
    output wire               analysis_pcm_valid,
    output wire               analysis_pcm_end,
    output wire signed [15:0] analysis_pcm_left,
    output wire signed [15:0] analysis_pcm_right,
    output wire [19:0]        analysis_sample_rate,

    output wire               ddr_valid,
    output wire               ddr_write,
    output wire [28:0]        ddr_address,
    output wire [255:0]       ddr_data,
    input  wire               ddr_ready,
    input  wire               ddr_response,
    input  wire [255:0]       ddr_response_data
);
    wire path_pcm_valid,path_pcm_ready,path_pcm_end;
    wire signed [15:0] path_pcm_left,path_pcm_right;
    assign analysis_pcm_valid = path_pcm_valid && path_pcm_ready && analysis_enable_i;
    assign analysis_pcm_end = path_pcm_end;
    assign analysis_pcm_left = path_pcm_left;
    assign analysis_pcm_right = path_pcm_right;
    wire path_app_wren,path_app_wend;
    wire [2:0] path_app_cmd;
    wire [1:0] card_type,filesystem_type;
    wire [3:0] card_stat;
    wire [2:0] filesystem_stat;
    wire scan_done,card_ready,playing,eof,stereo;
    wire [5:0] bits_per_sample;
    wire [19:0] path_sample_rate;
    assign analysis_sample_rate = path_sample_rate;
    wire path_format_ready,path_unsupported;
    wire bank0_valid,bank1_valid;
    wire [15:0] frame_count,resync_count,skipped_frames,stuck_frames,parity_errors;

    // Toggle a transport epoch for both the decoder path and PCM CDC FIFO.
    reg restart_q,pcm_clear_toggle;
    reg [3:0] track_index_q;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin restart_q<=0;pcm_clear_toggle<=0;track_index_q<=4'd0;end
        else begin
            restart_q<=restart;track_index_q<=track_index;
            if((restart && !restart_q) || track_index!=track_index_q || card_lost)
                pcm_clear_toggle<=~pcm_clear_toggle;
        end
    end

    wire pcm_fifo_full,pcm_fifo_empty,pcm_fifo_valid;
    wire signed [15:0] pcm_fifo_left,pcm_fifo_right;
    // The score analyzer must keep receiving decoded PCM while TF playback is
    // hidden from the workstation audio output.
    assign path_pcm_ready=(!playback_hold_i || analysis_enable_i) &&
        (playback_hold_i || !pcm_fifo_full) &&
        (!analysis_hold_i || (analysis_enable_i && analysis_pcm_ready_i));
    reg hold_meta,hold_sync;
    tf_async_pcm_fifo #(.ADDR_WIDTH(4)) u_pcm_cdc(
        .wr_clk(clk_50m),.wr_rst_n(reset_n),.clear_toggle(pcm_clear_toggle),
        .wr_en(path_pcm_valid && path_pcm_ready && !playback_hold_i),.wr_left(path_pcm_left),
        .wr_right(path_pcm_right),.wr_full(pcm_fifo_full),
        .rd_clk(audio_clk),.rd_rst_n(audio_reset_n),.rd_en(sample_ce && !hold_sync && !pcm_fifo_empty),
        .rd_valid(pcm_fifo_valid),.rd_left(pcm_fifo_left),.rd_right(pcm_fifo_right),
        .rd_empty(pcm_fifo_empty));

    reg [19:0] rate_meta,rate_sync;
    reg format_meta,format_sync,unsupported_meta,unsupported_sync;
    reg clear_meta,clear_sync,clear_seen;
    reg [12:0] idle_frames;
    assign sample_rate_hz=rate_sync;
    assign format_ready=format_sync;
    assign unsupported=unsupported_sync;
    always @(posedge audio_clk or negedge audio_reset_n) begin
        if(!audio_reset_n) begin
            pcm_left<=0;pcm_right<=0;pcm_active<=0;source_active<=0;
            rate_meta<=0;rate_sync<=0;format_meta<=0;format_sync<=0;
            unsupported_meta<=0;unsupported_sync<=0;idle_frames<=0;
            clear_meta<=0;clear_sync<=0;clear_seen<=0;hold_meta<=0;hold_sync<=0;
        end
        else begin
            clear_meta<=pcm_clear_toggle;clear_sync<=clear_meta;
            hold_meta<=playback_hold_i;hold_sync<=hold_meta;
            rate_meta<=path_sample_rate;rate_sync<=rate_meta;
            format_meta<=path_format_ready;format_sync<=format_meta;
            unsupported_meta<=path_unsupported || (scan_done && {1'b0,track_index}>=track_count);unsupported_sync<=unsupported_meta;
            pcm_active<=0;
            if(clear_sync!=clear_seen) begin
                clear_seen<=clear_sync;pcm_left<=0;pcm_right<=0;
                source_active<=0;idle_frames<=0;
            end else if(pcm_fifo_valid) begin
                pcm_left<=$signed({pcm_fifo_left,16'd0});
                pcm_right<=$signed({pcm_fifo_right,16'd0});
                pcm_active<=1;source_active<=1;idle_frames<=0;
            end else if(sample_ce && source_active) begin
                // Return the headphone pins to the synth after about 85 ms
                // without decoded PCM (4096 frames at 48 kHz).  This keeps a
                // missing/finished card from muting the workstation.
                if(idle_frames==13'd4095) begin
                    source_active<=0;idle_frames<=0;
                end else idle_frames<=idle_frames+1'b1;
            end
        end
    end

    tf_audio_ddr_path #(.FILE_EXT(FILE_EXT),.AUDIO_KIND(AUDIO_KIND),
        .CAPTURE_ON_ANALYSIS(CAPTURE_ON_ANALYSIS)) u_path(
        .clk_50m(clk_50m),.reset_n(reset_n),.restart(restart),.track_index(track_index),
        .capture_enable_i(analysis_enable_i),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),.memory_ready(memory_ready),
        .sample_tick(sample_ce),.sd_miso(sd_miso),.sd_cs_n(sd_cs_n),.sd_sck(sd_sck),.sd_mosi(sd_mosi),
        .card_type(card_type),.card_stat(card_stat),.filesystem_type(filesystem_type),
        .filesystem_stat(filesystem_stat),.scan_done(scan_done),.card_lost(card_lost),
        .hotplug_debug(hotplug_debug),.card_ready(card_ready),
        .playing(playing),.eof(eof),.track_count(track_count),
        .playlist_ready(playlist_ready),.playlist_name_addr(playlist_name_addr),
        .playlist_name_data(playlist_name_data),.format_ready(path_format_ready),
        .unsupported(path_unsupported),.audio_ddr_error(ddr_error),.audio_bank0_valid(bank0_valid),
        .audio_bank1_valid(bank1_valid),.audio_file_size(file_size),.sample_rate_hz(path_sample_rate),
        .stereo(stereo),.bits_per_sample(bits_per_sample),.pcm_valid(path_pcm_valid),
        .pcm_end(path_pcm_end),
        .pcm_ready(path_pcm_ready),.pcm_left(path_pcm_left),.pcm_right(path_pcm_right),
        .frame_count(frame_count),.resync_count(resync_count),.skipped_frames(skipped_frames),
        .stuck_frames(stuck_frames),.pcm_fifo_parity_errors(parity_errors),
        .debug_cmdrsp(),.debug_rwrsp(),.debug_cardstate(),.debug_spidone(),.debug_rvalid_session(),
        .app_cmd(path_app_cmd),.app_en(ddr_valid),.app_addr(ddr_address),.app_wdata(ddr_data),
        .app_rdy(ddr_ready),.app_wren(path_app_wren),.app_wend(path_app_wend),
        .app_wrdy(ddr_ready),.app_rvalid(ddr_response),.app_rdata(ddr_response_data));

    assign ddr_write=ddr_valid && path_app_wren && path_app_wend && (path_app_cmd==3'b000);
endmodule
