// Test-only SPI/FAT/decoder endpoint replacement; no model arithmetic claim.
// Streaming audio path: TF stream -> DDR ring -> selected decoder -> PCM16.
// This path is intentionally single-track for bring-up; the top-level default
// selects track 0, while restart/track_index are available for clean recapture.
module tf_audio_ddr_path #(
    parameter [23:0] FILE_EXT = "WAV",
    parameter integer AUDIO_KIND = 2       // 1=MP3, 2=WAV, 3=FLAC
) (
    input  wire        clk_50m,
    input  wire        reset_n,
    input  wire        restart,
    input  wire [3:0]  track_index,
    input  wire        memory_clk,
    input  wire        memory_reset_n,
    input  wire        memory_ready,
    input  wire        sample_tick,
    input  wire        sd_miso,
    output wire        sd_cs_n,
    output wire        sd_sck,
    output wire        sd_mosi,
    output wire [1:0]  card_type,
    output wire [3:0]  card_stat,
    output wire [1:0]  filesystem_type,
    output wire [2:0]  filesystem_stat,
    output wire        scan_done,
    output wire        card_ready,
    output wire        playing,
    output wire        eof,
    output wire [4:0]  track_count,
    output wire        format_ready,
    output wire        unsupported,
    output wire        audio_ddr_error,
    output wire        audio_bank0_valid,
    output wire        audio_bank1_valid,
    output wire [31:0] audio_file_size,
    output wire [19:0] sample_rate_hz,
    output wire        stereo,
    output wire [5:0]  bits_per_sample,
    output wire        pcm_valid,
    input  wire        pcm_ready,
    output wire signed [15:0] pcm_left,
    output wire signed [15:0] pcm_right,
    output wire [15:0] frame_count,
    output wire [15:0] resync_count,
    output wire [15:0] skipped_frames,
    output wire [15:0] stuck_frames,
    output wire [15:0] pcm_fifo_parity_errors,
    output wire [7:0]  debug_cmdrsp,
    output wire [7:0]  debug_rwrsp,
    output wire [3:0]  debug_cardstate,
    output wire        debug_spidone,
    output wire        debug_rvalid_session,
    output wire [2:0]  app_cmd,
    output wire        app_en,
    output wire [28:0] app_addr,
    output wire [255:0] app_wdata,
    input  wire        app_rdy,
    output wire        app_wren,
    output wire        app_wend,
    input  wire        app_wrdy,
    input  wire        app_rvalid,
    input  wire [255:0] app_rdata
);

    reg [15:0] index;
    reg [7:0] gate;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin index<=0;gate<=0;end
        else begin gate<=gate+1'b1;if(pcm_valid && pcm_ready)index<=index+1'b1;end
    end
    assign pcm_valid=reset_n && gate[2:0]!=3'd0;
    assign pcm_left=$signed(index);
    assign pcm_right=$signed(~index);
    assign sample_rate_hz=20'd48000;
    assign format_ready=1'b1;
    assign unsupported=1'b0;
    assign sd_cs_n=1'b1;assign sd_sck=1'b0;assign sd_mosi=1'b0;
    assign card_type=2'd2;assign card_stat=4'd8;assign filesystem_type=2'd2;
    assign filesystem_stat=3'd4;assign scan_done=1'b1;assign card_ready=1'b1;
    assign playing=1'b1;assign eof=1'b0;assign track_count=5'd1;
    assign audio_ddr_error=1'b0;assign audio_bank0_valid=1'b1;assign audio_bank1_valid=1'b0;
    assign audio_file_size=32'd0;assign stereo=1'b1;assign bits_per_sample=6'd16;
    assign frame_count=index;assign resync_count=0;assign skipped_frames=0;
    assign stuck_frames=0;assign pcm_fifo_parity_errors=0;
    assign debug_cmdrsp=0;assign debug_rwrsp=0;assign debug_cardstate=0;
    assign debug_spidone=0;assign debug_rvalid_session=0;
    assign app_cmd=3'b001;assign app_en=0;assign app_addr=0;assign app_wdata=0;
    assign app_wren=0;assign app_wend=0;
endmodule
