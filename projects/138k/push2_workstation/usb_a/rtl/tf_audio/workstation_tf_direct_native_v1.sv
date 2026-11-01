`timescale 1ns/1ps
// Unselected same-clock composition. Exactly one native file/sector/SPI owner.
// No DDR interface, source selector, clock owner, physical EOS ACK or CDC.
module workstation_tf_direct_native_v1 #(
    parameter integer SPI_CLK_DIV=100,SPI_CLK_DIV_FAST=12,
    parameter integer VERIFY_DATA_CRC=0,
    parameter integer FAT_SECTOR_CACHE=0,
    parameter integer TOKEN_WAIT_CLOCKS=8320000,WATCHDOG_CLOCKS=250000000,
    parameter [25:0] PROBE_INTERVAL_CYCLES=26'd50000000,
    parameter integer BYTE_DEPTH=4096,PCM_DEPTH=4096,PREFILL_FRAMES=3072
)(
    input wire clk_i,rst_ni,
    output wire spi_ssn_o,spi_sck_o,spi_mosi_o,
    input wire spi_miso_i,
    input wire request_valid_i,
    output wire request_ready_o,
    input wire [3:0] track_index_i,
    input wire [31:0] generation_i,
    input wire [19:0] expected_rate_i,
    input wire stop_i,pause_i,sample_request_i,
    output wire request_accepted_o,request_applied_o,
    output reg request_failed_o,request_cancelled_o,
    output reg [3:0] request_failure_code_o,
    output wire request_pending_o,cancelled_o,
    output reg stop_completed_o,stop_failed_o,
    output wire pcm_valid_o,
    input wire pcm_ready_i,
    output wire signed [15:0] pcm_left_o,pcm_right_o,
    output wire pcm_last_o,
    output wire [31:0] generation_o,
    output wire [19:0] session_rate_o,
    output wire active_o,prefill_ready_o,decoded_eos_o,local_tail_drained_o,empty_o,
    output wire ingress_failed_o,
    output wire [3:0] ingress_failure_code_o,
    output wire file_error_o,
    output wire [3:0] file_error_code_o,
    output wire scan_done_o,playing_o,sector_busy_o,
    output wire [4:0] track_count_o,
    input wire [7:0] name_raddr_i,
    output wire [7:0] name_rdata_o,
    output wire [1:0] card_type_o,filesystem_type_o,
    output wire [3:0] card_stat_o,
    output wire [2:0] filesystem_stat_o,
    output wire [31:0] byte_level_o,pcm_level_o,byte_high_water_o,pcm_high_water_o,
    output wire file_byte_valid_o,data_sector_start_o,file_eof_o
);
    reg slot_pending,reader_start,failure_hold,failure_seen,quiet,stop_wait,stop_q;
    reg [3:0] held_track;
    reg [31:0] held_generation;
    reg [19:0] held_rate;
    wire reader_applied,reader_cancelled,reader_eof,sector_allow;
    wire [7:0] file_byte;
    wire reader_stop=stop_i || failure_hold;
    wire apply_fire=reader_applied && slot_pending && !stop_i && !file_error_o;
    wire accept_fire=request_valid_i && request_ready_o;
    wire stop_new=stop_i && !stop_q;
    assign request_ready_o=scan_done_o && !file_error_o && !slot_pending &&
        !stop_i && !stop_wait && (!failure_hold || quiet) && !reader_applied;
    assign file_eof_o=reader_eof && !reader_stop && !file_error_o;
    assign request_accepted_o=accept_fire;
    assign request_applied_o=apply_fire;
    assign request_pending_o=slot_pending;
    // This ACK is the actual file-owner payload/CRC drain, after local queues
    // have already been revoked; it is unrelated to physical audio completion.
    assign cancelled_o=reader_cancelled;
    workstation_tf_file_reader #(.EXT("WAV"),.SPI_CLK_DIV(SPI_CLK_DIV),
        .SPI_CLK_DIV_FAST(SPI_CLK_DIV_FAST),.TOKEN_WAIT_CLOCKS(TOKEN_WAIT_CLOCKS),
        .VERIFY_DATA_CRC(VERIFY_DATA_CRC),.FAT_SECTOR_CACHE(FAT_SECTOR_CACHE),
        .WATCHDOG_CLOCKS(WATCHDOG_CLOCKS),.PROBE_INTERVAL_CYCLES(PROBE_INTERVAL_CYCLES)) file_owner(
        .rstn(rst_ni),.clk(clk_i),.spi_ssn(spi_ssn_o),.spi_sck(spi_sck_o),.spi_mosi(spi_mosi_o),.spi_miso(spi_miso_i),
        .card_type(card_type_o),.card_stat(card_stat_o),.filesystem_type(filesystem_type_o),.filesystem_stat(filesystem_stat_o),
        .scan_done(scan_done_o),.sector_busy(sector_busy_o),.track_count(track_count_o),
        .track_index(held_track),.track_start(reader_start && !stop_i),.stop(reader_stop),
        .cancelled(reader_cancelled),.track_applied(reader_applied),.data_sector_start(data_sector_start_o),
        .file_error(file_error_o),.file_error_code(file_error_code_o),.playing(playing_o),.eof(reader_eof),
        .sector_allow(sector_allow),.outen(file_byte_valid_o),.outbyte(file_byte),
        .name_raddr(name_raddr_i),.name_rdata(name_rdata_o),.debug_cmdrsp(),.debug_rwrsp(),
        .debug_cardstate(),.debug_spidone(),.debug_rvalid_session());
    workstation_tf_direct_ingress_v1 #(.BYTE_DEPTH(BYTE_DEPTH),.PCM_DEPTH(PCM_DEPTH),
        .PREFILL_FRAMES(PREFILL_FRAMES)) ingress(
        .clk_i(clk_i),.rst_ni(rst_ni),.start_i(apply_fire),.cancel_i(reader_stop),.pause_i(pause_i),
        .generation_i(held_generation),.expected_rate_i(held_rate),
        .data_sector_start_i(data_sector_start_o),.sector_allow_o(sector_allow),
        .file_byte_valid_i(file_byte_valid_o),.file_byte_i(file_byte),.file_eof_i(file_eof_o),
        .file_error_i(file_error_o),.file_error_code_i(file_error_code_o),
        .sample_request_i(sample_request_i),.pcm_valid_o(pcm_valid_o),.pcm_ready_i(pcm_ready_i),
        .pcm_left_o(pcm_left_o),.pcm_right_o(pcm_right_o),.pcm_last_o(pcm_last_o),
        .generation_o(generation_o),.session_rate_o(session_rate_o),.active_o(active_o),
        .prefill_ready_o(prefill_ready_o),.decoded_eos_o(decoded_eos_o),
        .local_tail_drained_o(local_tail_drained_o),.empty_o(empty_o),
        .failed_o(ingress_failed_o),.failure_code_o(ingress_failure_code_o),.file_failure_code_o(),
        .byte_level_o(byte_level_o),.pcm_level_o(pcm_level_o),.byte_high_water_o(byte_high_water_o),
        .pcm_high_water_o(pcm_high_water_o),.format_ready_o(),.file_rate_o(),.file_bits_o(),.file_stereo_o());
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            slot_pending<=0;reader_start<=0;failure_hold<=0;failure_seen<=0;quiet<=1;stop_wait<=0;stop_q<=0;
            held_track<=0;held_generation<=0;held_rate<=0;
            request_failed_o<=0;request_cancelled_o<=0;request_failure_code_o<=0;
            stop_completed_o<=0;stop_failed_o<=0;
        end else begin
            reader_start<=0;request_failed_o<=0;request_cancelled_o<=0;stop_q<=stop_i;
            stop_completed_o<=0;stop_failed_o<=0;
            if(reader_cancelled)begin
                quiet<=1;stop_wait<=0;
                if(stop_wait || stop_new)stop_completed_o<=1;
            end
            if(file_error_o && stop_wait)begin
                stop_wait<=0;stop_failed_o<=1;stop_completed_o<=0;
            end
            if(data_sector_start_o)quiet<=0;
            if(accept_fire)begin
                slot_pending<=1;reader_start<=1;held_track<=track_index_i;
                held_generation<=generation_i;held_rate<=expected_rate_i;
                failure_hold<=0;quiet<=0;request_failure_code_o<=0;
            end
            if(apply_fire)begin slot_pending<=0;failure_seen<=0;end
            // No track_applied exists for an invalid track or mount failure.
            // A pending accepted command still gets one explicit terminal result.
            if(file_error_o && slot_pending)begin
                slot_pending<=0;request_failed_o<=1;request_failure_code_o<=file_error_code_o;
            end
            if(ingress_failed_o && !failure_seen && !slot_pending && !apply_fire &&
                !accept_fire && !stop_i)begin failure_hold<=1;failure_seen<=1;end
            if(stop_i)begin
                reader_start<=0;
                // A local failure may already hold native stop high AFTER
                // its real drain ACK. A later external stop cannot require a
                // second edge/ACK which that held owner will never produce.
                // A coincident actual ACK also wins arming this wait latch.
                if(!stop_q && !reader_cancelled && !(failure_hold && quiet) && !file_error_o)stop_wait<=1;
                if(stop_new)begin
                    if(file_error_o)begin stop_wait<=0;stop_failed_o<=1;stop_completed_o<=0;end
                    else if(reader_cancelled || (failure_hold && quiet))stop_completed_o<=1;
                end
                // Keep the same native stop asserted if failure and external
                // stop overlap; releasing the external pin cannot create a
                // falling/rising stop pair or a second transport transaction.
                if(ingress_failed_o)begin failure_hold<=1;failure_seen<=1;end
                if(slot_pending)begin request_cancelled_o<=1;request_failure_code_o<=0;end
                request_failed_o<=0;
                slot_pending<=0;
            end
        end
    end
endmodule
