`timescale 1ns/1ps
// One M SD/FAT/WAV owner, with an exclusive playback OR offline-analysis
// cursor. Analysis backpressure never reaches the independent synth clock.
// This composition has no physical-output completion authority: playback's
// final serializer/EOS barrier remains in the maintained runtime service.
module workstation_task3_tf_route #(
    parameter integer SPI_CLK_DIV=100,SPI_CLK_DIV_FAST=12,
    parameter integer VERIFY_DATA_CRC=1,FAT_SECTOR_CACHE=1,
    parameter integer BYTE_DEPTH=4096,PCM_DEPTH=4096,PREFILL_FRAMES=3072
)(
    input wire clk_i,reset_ni,cancel_i,panic_i,
    input wire open_valid_i,
    output wire open_ready_o,
    input wire open_analysis_i,
    input wire [3:0] open_track_i,
    input wire [31:0] open_generation_i,
    input wire [19:0] playback_rate_i,
    output reg open_accepted_o,open_rejected_o,
    // Atomic with native file acceptance; connect to the M analysis producer.
    output wire analysis_start_valid_o,
    input wire analysis_start_ready_i,
    output wire analysis_pcm_valid_o,
    input wire analysis_pcm_ready_i,
    output wire [31:0] analysis_pcm_o,
    output wire analysis_pcm_last_o,
    output wire analysis_cancel_o,
    // Connect playback to the existing TF frame ingress/output scheduler.
    input wire playback_pause_i,playback_sample_request_i,
    output wire playback_pcm_valid_o,
    input wire playback_pcm_ready_i,
    output wire signed [15:0] playback_left_o,playback_right_o,
    output wire playback_last_o,
    output wire [31:0] playback_generation_o,
    output wire [19:0] playback_session_rate_o,
    output wire busy_o,analysis_selected_o,
    output reg file_consumed_o,failed_o,
    output reg [3:0] failure_code_o,
    output wire stop_completed_o,stop_failed_o,
    output wire scan_done_o,
    output wire [4:0] track_count_o,
    input wire [7:0] name_address_i,
    output wire [7:0] name_data_o,
    output wire sd_cs_no,sd_sck_o,sd_mosi_o,
    input wire sd_miso_i
);
    localparam [2:0] IDLE=0,WAIT_APPLY=1,OPEN=2,DRAIN=3,STOP=4;
    reg [2:0] state;
    reg analysis;
    wire native_ready,native_applied,native_failed,native_cancelled,native_pending;
    wire ingress_failed,file_error,sector_busy,native_empty,tail_drained;
    wire [3:0] native_failure,ingress_failure,file_failure;
    wire pcm_valid,pcm_ready,pcm_last;
    wire signed [15:0] pcm_left,pcm_right;
    wire abort=cancel_i || panic_i;
    wire fault=native_failed || file_error || ((state==OPEN || state==DRAIN) && ingress_failed);
    wire stop=abort || state==STOP || (state!=IDLE && fault);
    assign open_ready_o=reset_ni && state==IDLE && native_ready && !abort &&
        (!open_analysis_i || analysis_start_ready_i);
    wire open_fire=open_valid_i && open_ready_o && open_generation_i!=0;
    assign analysis_start_valid_o=open_fire && open_analysis_i;
    assign busy_o=state!=IDLE;
    assign analysis_selected_o=state!=IDLE && analysis;
    assign analysis_cancel_o=analysis_selected_o && (stop || (state==OPEN && native_empty));
    assign analysis_pcm_valid_o=pcm_valid && state==OPEN && analysis && !stop;
    assign analysis_pcm_o={pcm_right,pcm_left};
    assign analysis_pcm_last_o=pcm_last;
    assign playback_pcm_valid_o=pcm_valid && state==OPEN && !analysis && !stop;
    assign playback_left_o=pcm_left;
    assign playback_right_o=pcm_right;
    assign playback_last_o=pcm_last;
    assign pcm_ready=state==OPEN && !stop &&
        (analysis?analysis_pcm_ready_i:playback_pcm_ready_i);
    workstation_tf_direct_native_v1 #(
        .SPI_CLK_DIV(SPI_CLK_DIV),.SPI_CLK_DIV_FAST(SPI_CLK_DIV_FAST),
        .VERIFY_DATA_CRC(VERIFY_DATA_CRC),.FAT_SECTOR_CACHE(FAT_SECTOR_CACHE),
        .BYTE_DEPTH(BYTE_DEPTH),.PCM_DEPTH(PCM_DEPTH),.PREFILL_FRAMES(PREFILL_FRAMES)
    ) file_owner(
        .clk_i(clk_i),.rst_ni(reset_ni),.spi_ssn_o(sd_cs_no),.spi_sck_o(sd_sck_o),
        .spi_mosi_o(sd_mosi_o),.spi_miso_i(sd_miso_i),
        .request_valid_i(open_fire),.request_ready_o(native_ready),
        .track_index_i(open_track_i),.generation_i(open_generation_i),
        .expected_rate_i(open_analysis_i?20'd48000:playback_rate_i),
        .stop_i(stop),.pause_i(!analysis && playback_pause_i),
        .sample_request_i(state==OPEN && !analysis && playback_sample_request_i),
        .request_accepted_o(),.request_applied_o(native_applied),.request_failed_o(native_failed),
        .request_cancelled_o(native_cancelled),.request_failure_code_o(native_failure),
        .request_pending_o(native_pending),.cancelled_o(),
        .stop_completed_o(stop_completed_o),.stop_failed_o(stop_failed_o),
        .pcm_valid_o(pcm_valid),.pcm_ready_i(pcm_ready),
        .pcm_left_o(pcm_left),.pcm_right_o(pcm_right),.pcm_last_o(pcm_last),
        .generation_o(playback_generation_o),.session_rate_o(playback_session_rate_o),
        .active_o(),.prefill_ready_o(),.decoded_eos_o(),.local_tail_drained_o(tail_drained),
        .empty_o(native_empty),.ingress_failed_o(ingress_failed),.ingress_failure_code_o(ingress_failure),
        .file_error_o(file_error),.file_error_code_o(file_failure),
        .scan_done_o(scan_done_o),.playing_o(),.sector_busy_o(sector_busy),
        .track_count_o(track_count_o),.name_raddr_i(name_address_i),.name_rdata_o(name_data_o),
        .card_type_o(),.filesystem_type_o(),.card_stat_o(),.filesystem_stat_o(),
        .byte_level_o(),.pcm_level_o(),.byte_high_water_o(),.pcm_high_water_o(),
        .file_byte_valid_o(),.data_sector_start_o(),.file_eof_o());
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;analysis<=0;open_accepted_o<=0;open_rejected_o<=0;
            file_consumed_o<=0;failed_o<=0;failure_code_o<=0;
        end else begin
            open_accepted_o<=0;open_rejected_o<=0;file_consumed_o<=0;
            if(open_valid_i && open_ready_o)begin
                if(open_generation_i==0)begin open_rejected_o<=1;failure_code_o<=4'd15;end
                else begin
                    state<=WAIT_APPLY;analysis<=open_analysis_i;open_accepted_o<=1;
                    failed_o<=0;failure_code_o<=0;
                end
            end
            if(state!=IDLE)begin
                if(abort || fault || native_cancelled || (state==OPEN && native_empty))begin
                    state<=STOP;failed_o<=1;
                    failure_code_o<=panic_i?4'd14:cancel_i?4'd13:
                        file_error?file_failure:ingress_failed?ingress_failure:
                        native_failed?native_failure:4'd12;
                end else if(state==WAIT_APPLY && native_applied)state<=OPEN;
                else if(state==OPEN && pcm_valid && pcm_ready && pcm_last)state<=DRAIN;
                else if(state==DRAIN && tail_drained && !sector_busy && !native_pending)begin
                    state<=IDLE;file_consumed_o<=1;
                end
                // The real SD owner acknowledges cancellation only after its
                // outstanding sector has drained. Never reopen on local flush.
                if(state==STOP && (stop_completed_o || stop_failed_o))state<=IDLE;
            end
        end
    end
endmodule
