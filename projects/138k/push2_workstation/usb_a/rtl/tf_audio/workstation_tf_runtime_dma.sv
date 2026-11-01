// Runtime-only first-party DMA adaptation; see workstation_tf_runtime_storage.provenance.json.
`include "src/memory/ddr_address_map.vh"

// Streaming TF audio DDR ring.
//
// The business side remains byte addressed and 32-bit wide.  The Gowin user
// port remains its native 256-bit (32-byte BL8) interface: one accepted beat
// consumes eight native DQ words and advances app_addr by eight.  The two
// fixed 64 MiB regions form a 128 MiB circular window.  Once read data has
// been copied into the playback FIFO, the corresponding DDR beat is released
// and may be overwritten by a later part of a file larger than 128 MiB.
module workstation_tf_runtime_dma #(
    // Fixed hardware value: 64 MiB.  This parameter is exposed only so the
    // boundary/ring testbench can scale the same state machine down.
    parameter [31:0] AUDIO_BANK_BYTES = `PRJ1_DDR_AUDIO_BANK_BYTES,
    parameter [31:0] AUDIO_BANK0_BYTE_BASE =
        `PRJ1_DDR_AUDIO_BANK0_BYTE_BASE,
    parameter [31:0] AUDIO_BANK0_NATIVE_BASE =
        {3'd0, `PRJ1_DDR_AUDIO_BANK0_APP_BASE},
    parameter [31:0] AUDIO_STREAM_START_BYTES = 32'd2_048
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        mem_ready,
    input  wire        capture_done_toggle,
    input  wire        restart_toggle,
    input  wire [31:0] file_size_bytes,
    input  wire        fifo_in_empty,
    input  wire        fifo_in_rd_valid,
    input  wire [7:0]  fifo_in_rd_data,
    output reg         fifo_in_rd_en,
    output reg         playback_start_toggle,
    output reg         playback_done_toggle,
    input  wire        fifo_out_full,
    output wire        fifo_out_wr_en,
    output wire [7:0]  fifo_out_wr_data,
    output reg  [2:0]  app_cmd,
    output reg         app_en,
    output reg  [28:0] app_addr,
    output reg  [255:0] app_wdata,
    input  wire        app_rdy,
    output reg         app_wren,
    output reg         app_wend,
    input  wire        app_wrdy,
    input  wire        app_rvalid,
    input  wire [255:0] app_rdata,
    output reg         capacity_error,
    output reg         bank0_valid,
    output reg         bank1_valid,
    output reg         file_size_valid,
    output reg  [31:0] staged_file_size,
    input wire runtime_hold_i,
    output reg runtime_restart_ack_o
);
    localparam [1:0] S_STREAM = 2'd0, S_DONE = 2'd2;

    // Corrected non-overlapping map.  Video owns 0..8 MiB and the historical
    // workstation pages own 16..24 MiB, so audio starts at 24 MiB.
    // The byte/native values below are fixed for the default 64 MiB bank.
    // A reduced test parameter derives bank 1 from bank 0 while preserving
    // the same mapping equation.
    localparam [31:0] AUDIO_BANK_DQ_WORDS   = AUDIO_BANK_BYTES >> 2;
    localparam [31:0] AUDIO_BANK_BEATS      = AUDIO_BANK_BYTES >> 5;
    localparam [31:0] AUDIO_TOTAL_BYTES     = AUDIO_BANK_BYTES + AUDIO_BANK_BYTES;
    localparam [31:0] AUDIO_BANK0_BYTE_END  = AUDIO_BANK0_BYTE_BASE + AUDIO_BANK_BYTES - 1'b1;
    localparam [31:0] AUDIO_BANK1_BYTE_BASE = AUDIO_BANK0_BYTE_BASE + AUDIO_BANK_BYTES;
    localparam [31:0] AUDIO_BANK1_BYTE_END  = AUDIO_BANK1_BYTE_BASE + AUDIO_BANK_BYTES - 1'b1;
    localparam [31:0] AUDIO_BANK0_NATIVE_END  = AUDIO_BANK0_NATIVE_BASE + AUDIO_BANK_DQ_WORDS - 1'b1;
    localparam [31:0] AUDIO_BANK1_NATIVE_BASE = AUDIO_BANK0_NATIVE_BASE + AUDIO_BANK_DQ_WORDS;
    localparam [31:0] AUDIO_BANK1_NATIVE_END  = AUDIO_BANK1_NATIVE_BASE + AUDIO_BANK_DQ_WORDS - 1'b1;

    reg [1:0] state;
    reg capture_meta, capture_sync, capture_seen;
    reg restart_meta, restart_sync, restart_seen;
    reg [31:0] size_meta, size_sync;
    reg [31:0] capture_byte_count;
    reg [31:0] write_total_bytes, read_total_bytes;
    // Keep the two modulo-32-bit occupancies at the same commit boundary as
    // their total counters. Request admission no longer subtracts two wide
    // totals and then feeds that result back into the read-response update.
    reg [31:0] available_bytes, accepted_used;
    reg [31:0] write_ring_offset, read_ring_offset;
    reg [255:0] write_buf, read_buf;
    reg [5:0] write_count;
    reg [5:0] pending_bytes;
    reg [5:0] read_pending_bytes;
    reg [5:0] emit_index, emit_bytes_left;
    reg write_pending, read_pending, read_buf_valid;
    reg in_read_wait;
    reg capture_overflow;
    reg eof_seen, eof_finalized, stream_started;
    reg end_reported;

    wire capture_finished = (capture_sync != capture_seen);
    wire restart_event = (restart_sync != restart_seen);
    wire [31:0] committed_used = available_bytes;
    wire ring_has_room_for_input = accepted_used < AUDIO_TOTAL_BYTES;
    // Export the same function's intermediates to kept module-level nets.
    // Its low bit remains the sole capacity predicate used for admission.
    wire ring_upper_equal_0 /* synthesis syn_keep=1 */;
    wire ring_upper_equal_1 /* synthesis syn_keep=1 */;
    wire ring_upper_equal_2 /* synthesis syn_keep=1 */;
    wire ring_upper_equal_3 /* synthesis syn_keep=1 */;
    wire ring_upper_equal /* synthesis syn_keep=1 */;
    wire ring_can_commit;
    assign {ring_upper_equal_3, ring_upper_equal_2, ring_upper_equal_1,
            ring_upper_equal_0, ring_upper_equal, ring_can_commit} =
        pending_fits_ring(committed_used, pending_bytes);
    wire write_selected = mem_ready && !runtime_hold_i && write_pending && ring_can_commit;

    // Bound the shared full-beat/chunk zero test. These are combinational
    // groups only; admission and the sample/DDR schedules keep their cycle.
    wire available_full_group_0 /* synthesis syn_keep=1 */;
    wire available_full_group_1 /* synthesis syn_keep=1 */;
    wire available_full_group_2 /* synthesis syn_keep=1 */;
    wire available_full_group_3 /* synthesis syn_keep=1 */;
    wire available_full_binary /* synthesis syn_keep=1 */;
    assign available_full_group_0 = |available_bytes[11:5];
    assign available_full_group_1 = |available_bytes[18:12];
    assign available_full_group_2 = |available_bytes[25:19];
    assign available_full_group_3 = |available_bytes[31:26];
    assign available_full_binary = available_full_group_0 || available_full_group_1 ||
                                   available_full_group_2 || available_full_group_3;
    reg read_has_full_beat /* synthesis syn_keep=1 */;
    always @* begin
        // A relational comparison is X-pessimistic even when a known high
        // one could decide a reduction. Preserve that four-state contract.
        case (^available_bytes)
            1'b0, 1'b1: read_has_full_beat = available_full_binary;
            default: read_has_full_beat = (available_bytes >= 32'd32);
        endcase
    end
    wire read_has_partial_beat = eof_finalized && (available_bytes != 0);
    wire read_request = mem_ready && !runtime_hold_i && state == S_STREAM && stream_started &&
                        !write_selected && !read_pending && !read_buf_valid &&
                        !fifo_out_full && (read_has_full_beat || read_has_partial_beat);
    wire read_accept = read_request && app_rdy;
    wire [5:0] read_chunk_bytes = (eof_finalized && !read_has_full_beat) ?
                                  available_bytes[5:0] : 6'd32;
    wire write_accept = write_selected && app_rdy && app_wrdy;
    wire read_response = app_rvalid && (read_pending || read_accept);
    wire [5:0] read_response_bytes = read_accept ? read_chunk_bytes :
                                                   read_pending_bytes;
    // At most 32 bytes enter or leave in one cycle. Form each signed delta
    // at seven bits, then use one wide addition rather than serial add/sub.
    wire input_byte_accepted = fifo_in_rd_valid && capture_byte_count != 32'hffff_ffff;
    wire [6:0] committed_delta = {1'b0, (write_accept ? pending_bytes : 6'd0)} -
                                  {1'b0, (read_response ? read_response_bytes : 6'd0)};
    wire [6:0] accepted_delta = {6'd0, input_byte_accepted} -
                                 {1'b0, (read_response ? read_response_bytes : 6'd0)};
    // A valid response is either the registered pending read, or an accepted
    // immediate read while read_pending is clear. Select its size before the
    // late DDR permission, then precompute complete occupancy alternatives.
    wire [5:0] occupancy_response_bytes = read_pending ? read_pending_bytes : read_chunk_bytes;
    wire [6:0] occupancy_write_delta = {1'b0, pending_bytes} - 7'd0;
    wire [6:0] occupancy_read_delta = 7'd0 - {1'b0, occupancy_response_bytes};
    wire [6:0] occupancy_write_read_delta = {1'b0, pending_bytes} - {1'b0, occupancy_response_bytes};
    wire [6:0] occupancy_input_delta = 7'd1 - 7'd0;
    wire [6:0] occupancy_input_read_delta = 7'd1 - {1'b0, occupancy_response_bytes};
    wire [31:0] available_after_write = add_occupancy_delta(available_bytes, occupancy_write_delta);
    // Precompute the exact full and pending response alternatives before
    // the availability classification. Unknown controls keep the old calls.
    wire [31:0] available_read_generic = add_occupancy_delta(available_bytes, occupancy_read_delta);
    wire [31:0] available_write_read_generic = add_occupancy_delta(available_bytes, occupancy_write_read_delta);
    wire [31:0] available_full_read = add_occupancy_delta(available_bytes, 7'd96);
    wire [31:0] available_full_write_read = add_occupancy_delta(available_bytes, {1'b0, pending_bytes} - 7'd32);
    wire [31:0] available_pending_read = add_occupancy_delta(available_bytes, 7'd0 - {1'b0, read_pending_bytes});
    wire [31:0] available_pending_write_read = add_occupancy_delta(available_bytes, {1'b0, pending_bytes} - {1'b0, read_pending_bytes});
    reg [31:0] available_after_read, available_after_write_read;
    always @* begin
        available_after_read = available_read_generic;
        available_after_write_read = available_write_read_generic;
        case (read_pending)
            1'b0: begin
                case (eof_finalized && !read_has_full_beat)
                    1'b0: begin
                        available_after_read = available_full_read;
                        available_after_write_read = available_full_write_read;
                    end
                    1'b1: begin
                        // The original X-pessimistic full comparison being
                        // zero proves a known unsigned occupancy below 32.
                        available_after_read = 32'd0;
                        case (^pending_bytes)
                            1'b0, 1'b1: available_after_write_read = {26'd0, pending_bytes};
                            default: begin end
                        endcase
                    end
                    default: begin end
                endcase
            end
            1'b1: begin
                available_after_read = available_pending_read;
                available_after_write_read = available_pending_write_read;
            end
            default: begin end
        endcase
    end
    wire [31:0] accepted_after_input = add_occupancy_delta(accepted_used, occupancy_input_delta);
    // Precompute accepted-occupancy response sizes before the late full/partial
    // classification, retaining the generic result for unknown controls.
    wire [31:0] accepted_read_generic = add_occupancy_delta(accepted_used, occupancy_read_delta);
    wire [31:0] accepted_input_read_generic = add_occupancy_delta(accepted_used, occupancy_input_read_delta);
    wire [31:0] accepted_full_read = add_occupancy_delta(accepted_used, 7'd96);
    wire [31:0] accepted_full_input_read = add_occupancy_delta(accepted_used, 7'd97);
    wire [31:0] accepted_pending_read = add_occupancy_delta(accepted_used, 7'd0 - {1'b0, read_pending_bytes});
    wire [31:0] accepted_pending_input_read = add_occupancy_delta(accepted_used, 7'd1 - {1'b0, read_pending_bytes});
    wire [31:0] accepted_partial_read = add_occupancy_delta(accepted_used, 7'd0 - {1'b0, available_bytes[5:0]});
    wire [31:0] accepted_partial_input_read = add_occupancy_delta(accepted_used, 7'd1 - {1'b0, available_bytes[5:0]});
    reg [31:0] accepted_after_read, accepted_after_input_read;
    always @* begin
        accepted_after_read = accepted_read_generic;
        accepted_after_input_read = accepted_input_read_generic;
        case (read_pending)
            1'b0: begin
                case (eof_finalized && !read_has_full_beat)
                    1'b0: begin
                        accepted_after_read = accepted_full_read;
                        accepted_after_input_read = accepted_full_input_read;
                    end
                    1'b1: begin
                        accepted_after_read = accepted_partial_read;
                        accepted_after_input_read = accepted_partial_input_read;
                    end
                    default: begin end
                endcase
            end
            1'b1: begin
                accepted_after_read = accepted_pending_read;
                accepted_after_input_read = accepted_pending_input_read;
            end
            default: begin end
        endcase
    end
    // Compute both read-response cofactors before the late write admission.
    // With a selected write, no new read can be accepted; an outstanding
    // registered read may still respond in the same cycle. Unknown admission
    // retains the original selection above, including its four-state delta.
    wire read_request_without_write = mem_ready && !runtime_hold_i && state == S_STREAM && stream_started &&
                        !read_pending && !read_buf_valid &&
                        !fifo_out_full && (read_has_full_beat || read_has_partial_beat);
    wire read_accept_without_write = read_request_without_write && app_rdy;
    wire read_response_without_write = app_rvalid && (read_pending || read_accept_without_write);
    wire read_response_pending_only = app_rvalid && read_pending;
    reg [31:0] accepted_without_write /* synthesis syn_keep=1 */;
    reg [31:0] accepted_pending_only /* synthesis syn_keep=1 */;
    always @* begin
        case ({input_byte_accepted, read_response_without_write})
            2'b00: accepted_without_write = add_occupancy_delta(accepted_used, 7'd0);
            2'b01: accepted_without_write = accepted_after_read;
            2'b10: accepted_without_write = accepted_after_input;
            2'b11: accepted_without_write = accepted_after_input_read;
            default: accepted_without_write = add_occupancy_delta(accepted_used, accepted_delta);
        endcase
        case ({input_byte_accepted, read_response_pending_only})
            2'b00: accepted_pending_only = add_occupancy_delta(accepted_used, 7'd0);
            2'b01: accepted_pending_only = accepted_after_read;
            2'b10: accepted_pending_only = accepted_after_input;
            2'b11: accepted_pending_only = accepted_after_input_read;
            default: accepted_pending_only = add_occupancy_delta(accepted_used, accepted_delta);
        endcase
    end
    reg [31:0] next_available_bytes, next_accepted_used;
    always @* begin
        case ({write_accept, read_response})
            2'b00: next_available_bytes = add_occupancy_delta(available_bytes, 7'd0);
            2'b01: next_available_bytes = available_after_read;
            2'b10: next_available_bytes = available_after_write;
            2'b11: next_available_bytes = available_after_write_read;
            default: next_available_bytes = add_occupancy_delta(available_bytes, committed_delta);
        endcase
        case ({input_byte_accepted, read_response})
            2'b00: next_accepted_used = add_occupancy_delta(accepted_used, 7'd0);
            2'b01: next_accepted_used = accepted_after_read;
            2'b10: next_accepted_used = accepted_after_input;
            2'b11: next_accepted_used = accepted_after_input_read;
            default: next_accepted_used = add_occupancy_delta(accepted_used, accepted_delta);
        endcase
        case (write_selected)
            1'b0: next_accepted_used = accepted_without_write;
            1'b1: next_accepted_used = accepted_pending_only;
            default: begin end
        endcase
    end
    wire emit_byte = !runtime_hold_i && (state == S_STREAM) && read_buf_valid && !fifo_out_full &&
                     (emit_bytes_left != 0);

    wire [31:0] write_native_addr = (write_ring_offset < AUDIO_BANK_BYTES) ?
                                     AUDIO_BANK0_NATIVE_BASE + (write_ring_offset >> 2) :
                                     AUDIO_BANK1_NATIVE_BASE +
                                     ((write_ring_offset - AUDIO_BANK_BYTES) >> 2);
    wire [31:0] read_native_addr = (read_ring_offset < AUDIO_BANK_BYTES) ?
                                    AUDIO_BANK0_NATIVE_BASE + (read_ring_offset >> 2) :
                                    AUDIO_BANK1_NATIVE_BASE +
                                    ((read_ring_offset - AUDIO_BANK_BYTES) >> 2);

    // A response/admission decision is late, but its signed delta is only
    // seven bits. Compute the upper +/-1 alternatives from the current
    // occupancy alone; the late delta selects them after a six-bit sum.
    // Preserve modulo-2^32 arithmetic, including borrow and wrap at zero.
    function [31:0] add_occupancy_delta;
        input [31:0] occupancy;
        input [6:0] delta;
        reg [6:0] low_sum;
        reg [25:0] upper, upper_plus, upper_minus;
        begin
            low_sum = {1'b0, occupancy[5:0]} + {1'b0, delta[5:0]};
            upper_plus = occupancy[31:6] + 26'd1;
            upper_minus = occupancy[31:6] - 26'd1;
            if (delta[6])
                upper = low_sum[6] ? occupancy[31:6] : upper_minus;
            else
                upper = low_sum[6] ? upper_plus : occupancy[31:6];
            add_occupancy_delta = {upper, low_sum[5:0]};
        end
    endfunction

    // Decide the modulo-32-bit sum against the capacity without sending the
    // late pending count through a full-width carry chain. The two upper
    // comparisons depend only on the current occupancy; a six-bit sum then
    // selects between them. This also preserves the old wrap-at-2^32 case.
    // Return the original predicate at bit 0; the other five bits expose
    // exactly the equality intermediates used by that same computation.
    function [5:0] pending_fits_ring;
        input [31:0] occupancy;
        input [5:0] pending;
        reg [6:0] low_sum;
        reg [25:0] upper_plus;
        reg upper_less, incremented_less, incremented_equal;
        reg upper_equal, upper_equal_0, upper_equal_1, upper_equal_2, upper_equal_3;
        begin
            low_sum = {1'b0, occupancy[5:0]} + {1'b0, pending};
            upper_plus = occupancy[31:6] + 26'd1;
            upper_less = occupancy[31:6] < AUDIO_TOTAL_BYTES[31:6];
            // This same-cycle equality also feeds the full-ring admission
            // cofactor. Keep balanced groups instead of a shared serial
            // zero chain; grouping == preserves mismatch-dominant X/Z logic.
            upper_equal_0 = occupancy[11:6] == AUDIO_TOTAL_BYTES[11:6];
            upper_equal_1 = occupancy[18:12] == AUDIO_TOTAL_BYTES[18:12];
            upper_equal_2 = occupancy[25:19] == AUDIO_TOTAL_BYTES[25:19];
            upper_equal_3 = occupancy[31:26] == AUDIO_TOTAL_BYTES[31:26];
            upper_equal = upper_equal_0 && upper_equal_1 && upper_equal_2 && upper_equal_3;
            incremented_less = upper_plus < AUDIO_TOTAL_BYTES[31:6];
            incremented_equal = upper_plus == AUDIO_TOTAL_BYTES[31:6];
            pending_fits_ring = {upper_equal_3, upper_equal_2, upper_equal_1,
                upper_equal_0, upper_equal,
                (low_sum[6] ?
                    (incremented_less || (incremented_equal && low_sum[5:0] <= AUDIO_TOTAL_BYTES[5:0])) :
                    (upper_less || (upper_equal && low_sum[5:0] <= AUDIO_TOTAL_BYTES[5:0])))};
        end
    endfunction

    function [31:0] advance_ring;
        input [31:0] offset;
        begin
            if (offset + 32'd32 >= AUDIO_TOTAL_BYTES)
                advance_ring = offset + 32'd32 - AUDIO_TOTAL_BYTES;
            else
                advance_ring = offset + 32'd32;
        end
    endfunction

    // Bank valid means that committed, not-yet-read bytes currently occupy
    // some part of that bank.  The read buffer is already a private copy and
    // is therefore freeable in DDR as soon as the read response is captured.
    always @(*) begin
        bank0_valid = 1'b0;
        bank1_valid = 1'b0;
        if (available_bytes != 0) begin
            if (available_bytes > AUDIO_BANK_BYTES) begin
                bank0_valid = 1'b1;
                bank1_valid = 1'b1;
            end else if (available_bytes == AUDIO_BANK_BYTES) begin
                // Exactly one bank is occupied only when the read pointer is
                // exactly bank-aligned; an unaligned 64 MiB interval spans
                // both banks.
                if (read_ring_offset == 0)
                    bank0_valid = 1'b1;
                else if (read_ring_offset == AUDIO_BANK_BYTES)
                    bank1_valid = 1'b1;
                else begin
                    bank0_valid = 1'b1;
                    bank1_valid = 1'b1;
                end
            end else if (read_ring_offset < AUDIO_BANK_BYTES) begin
                bank0_valid = 1'b1;
                if (read_ring_offset + available_bytes > AUDIO_BANK_BYTES)
                    bank1_valid = 1'b1;
            end else begin
                bank1_valid = 1'b1;
                if (read_ring_offset + available_bytes > AUDIO_TOTAL_BYTES)
                    bank0_valid = 1'b1;
            end
        end
    end

    assign fifo_out_wr_en = emit_byte;
    assign fifo_out_wr_data = read_buf[emit_index*8 +: 8];

    always @(*) begin
        app_cmd   = 3'b000;
        app_en    = 1'b0;
        app_addr  = 29'd0;
        app_wdata = write_buf;
        app_wren  = 1'b0;
        app_wend  = 1'b0;
        if (write_selected) begin
            app_cmd  = 3'b000;
            // Keep the request asserted until the external arbiter returns
            // ready.  app_en must not depend combinationally on app_rdy;
            // the top-level audio adapter feeds its accepted pulse back as
            // the DMA-side ready signal.
            app_en   = 1'b1;
            app_addr = write_native_addr[28:0];
            app_wren = app_en;
            app_wend = app_en;
        end else if (read_request) begin
            app_cmd  = 3'b001;
            app_en   = 1'b1;
            app_addr = read_native_addr[28:0];
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_STREAM;
            capture_meta <= 1'b0;
            capture_sync <= 1'b0;
            capture_seen <= 1'b0;
            restart_meta <= 1'b0;
            restart_sync <= 1'b0;
            restart_seen <= 1'b0;
            size_meta <= 32'd0;
            size_sync <= 32'd0;
            capture_byte_count <= 32'd0;
            write_total_bytes <= 32'd0;
            read_total_bytes <= 32'd0;
            available_bytes <= 32'd0;
            accepted_used <= 32'd0;
            write_ring_offset <= 32'd0;
            read_ring_offset <= 32'd0;
            write_buf <= 256'd0;
            read_buf <= 256'd0;
            write_count <= 6'd0;
            pending_bytes <= 6'd0;
            read_pending_bytes <= 6'd0;
            emit_index <= 6'd0;
            emit_bytes_left <= 6'd0;
            write_pending <= 1'b0;
            read_pending <= 1'b0;
            read_buf_valid <= 1'b0;
            in_read_wait <= 1'b0;
            capture_overflow <= 1'b0;
            eof_seen <= 1'b0;
            eof_finalized <= 1'b0;
            stream_started <= 1'b0;
            end_reported <= 1'b0;
            capacity_error <= 1'b0;
            file_size_valid <= 1'b0;
            staged_file_size <= 32'd0;
            fifo_in_rd_en <= 1'b0;
            playback_start_toggle <= 1'b0;
            playback_done_toggle <= 1'b0;
        end else begin
            capture_meta <= capture_done_toggle;
            capture_sync <= capture_meta;
            restart_meta <= restart_toggle;
            restart_sync <= restart_meta;
            size_meta <= file_size_bytes;
            size_sync <= size_meta;
            fifo_in_rd_en <= 1'b0;

            // A restart/track change starts a new ring epoch.  The physical
            // DDR contents need not be erased because no old pointer survives.
            if (restart_event) begin
                restart_seen <= restart_sync;
                capture_seen <= capture_sync;
                state <= S_STREAM;
                capture_byte_count <= 32'd0;
                write_total_bytes <= 32'd0;
                read_total_bytes <= 32'd0;
                available_bytes <= 32'd0;
                accepted_used <= 32'd0;
                write_ring_offset <= 32'd0;
                read_ring_offset <= 32'd0;
                write_count <= 6'd0;
                pending_bytes <= 6'd0;
                read_pending_bytes <= 6'd0;
                emit_index <= 6'd0;
                emit_bytes_left <= 6'd0;
                write_pending <= 1'b0;
                read_pending <= 1'b0;
                read_buf_valid <= 1'b0;
                in_read_wait <= 1'b0;
                capture_overflow <= 1'b0;
                eof_seen <= 1'b0;
                eof_finalized <= 1'b0;
                stream_started <= 1'b0;
                end_reported <= 1'b0;
                capacity_error <= 1'b0;
                file_size_valid <= 1'b0;
                staged_file_size <= 32'd0;
                write_buf <= 256'd0;
                read_buf <= 256'd0;
            end else if (runtime_hold_i) begin
                // The canceled epoch may retire its accepted response, but
                // cannot emit or refill a byte after admission has closed.
                if (app_rvalid) read_pending <= 1'b0;
            end else if (state == S_DONE) begin
                // A new capture toggle is accepted as a fresh epoch for
                // simple test harnesses that do not send restart first.
                if (capture_finished) begin
                    capture_seen <= capture_sync;
                    state <= S_STREAM;
                    capture_byte_count <= 32'd0;
                    write_total_bytes <= 32'd0;
                    read_total_bytes <= 32'd0;
                    available_bytes <= 32'd0;
                    accepted_used <= 32'd0;
                    write_ring_offset <= 32'd0;
                    read_ring_offset <= 32'd0;
                    write_count <= 6'd0;
                    pending_bytes <= 6'd0;
                    read_pending_bytes <= 6'd0;
                    emit_index <= 6'd0;
                    emit_bytes_left <= 6'd0;
                    write_pending <= 1'b0;
                    read_pending <= 1'b0;
                    read_buf_valid <= 1'b0;
                    in_read_wait <= 1'b0;
                    capture_overflow <= 1'b0;
                    eof_seen <= 1'b0;
                    eof_finalized <= 1'b0;
                    stream_started <= 1'b0;
                    end_reported <= 1'b0;
                    capacity_error <= 1'b0;
                    file_size_valid <= 1'b0;
                    staged_file_size <= 32'd0;
                    write_buf <= 256'd0;
                end
            end else begin
                available_bytes <= next_available_bytes;
                accepted_used <= next_accepted_used;
                // Input is throttled by ring occupancy as well as the
                // asynchronous FIFO.  This is the key no-overwrite rule.
                if (!write_pending && !in_read_wait && !fifo_in_empty &&
                    ring_has_room_for_input && !capture_overflow) begin
                    fifo_in_rd_en <= 1'b1;
                    in_read_wait <= 1'b1;
                end

                if (fifo_in_rd_valid) begin
                    in_read_wait <= 1'b0;
                    if (capture_byte_count == 32'hffff_ffff) begin
                        // The business counters are deliberately 32-bit;
                        // a file beyond that representable range is the only
                        // capacity error in streaming mode.
                        capture_overflow <= 1'b1;
                        capacity_error <= 1'b1;
                    end else begin
                        capture_byte_count <= capture_byte_count + 32'd1;
                        write_buf[write_count*8 +: 8] <= fifo_in_rd_data;
                        if (write_count == 6'd31) begin
                            write_count <= 6'd0;
                            pending_bytes <= 6'd32;
                            write_pending <= 1'b1;
                        end else begin
                            write_count <= write_count + 1'b1;
                        end
                    end
                end

                if (capture_finished) begin
                    capture_seen <= capture_sync;
                    eof_seen <= 1'b1;
                end

                if ((eof_seen || capture_finished) && !write_pending &&
                    !in_read_wait && fifo_in_empty && write_count != 0) begin
                    // The final short beat is padded by write_buf; only
                    // pending_bytes are later emitted to the decoder.
                    pending_bytes <= write_count;
                    write_count <= 6'd0;
                    write_pending <= 1'b1;
                end

                if (write_accept) begin
                    write_pending <= 1'b0;
                    write_total_bytes <= write_total_bytes + {26'd0, pending_bytes};
                    write_ring_offset <= advance_ring(write_ring_offset);
                    write_buf <= 256'd0;
                end

                if ((eof_seen || capture_finished) && !write_pending &&
                    !in_read_wait && fifo_in_empty && write_count == 0 &&
                    !eof_finalized) begin
                    eof_finalized <= 1'b1;
                    if (capture_overflow) begin
                        // A 32-bit business counter cannot represent a
                        // fifth gigabyte.  Report that explicit error and
                        // terminate instead of waiting forever for an
                        // unrepresentable final byte count.
                        capacity_error <= 1'b1;
                        file_size_valid <= 1'b0;
                        staged_file_size <= 32'd0;
                        end_reported <= 1'b1;
                        playback_done_toggle <= ~playback_done_toggle;
                        state <= S_DONE;
                    end else begin
                        file_size_valid <= 1'b1;
                        staged_file_size <= capture_byte_count;
                    end
                end

                if (!stream_started &&
                    ((write_total_bytes >= AUDIO_STREAM_START_BYTES &&
                      write_total_bytes != 0) ||
                     (eof_finalized && write_total_bytes != 0))) begin
                    stream_started <= 1'b1;
                    playback_start_toggle <= ~playback_start_toggle;
                end

                // Data is private until the unchanged response publishes it.
                // A valid beat stays fixed while the byte FIFO consumes it.
                // Keep the original procedural behavior for unknown validity.
                case (read_buf_valid)
                    1'b0: read_buf <= app_rdata;
                    1'b1: begin end
                    default: if (read_response) read_buf <= app_rdata;
                endcase
                if (read_accept) begin
                    read_pending <= 1'b1;
                    read_pending_bytes <= read_chunk_bytes;
                end
                if (read_response) begin
                    read_pending <= 1'b0;
                    read_buf_valid <= 1'b1;
                    emit_index <= 6'd0;
                    emit_bytes_left <= read_response_bytes;
                    read_total_bytes <= read_total_bytes +
                                        {26'd0, read_response_bytes};
                    read_ring_offset <= advance_ring(read_ring_offset);
                end
                if (emit_byte) begin
                    emit_bytes_left <= emit_bytes_left - 1'b1;
                    if (emit_bytes_left == 6'd1) begin
                        emit_index <= 6'd0;
                        read_buf_valid <= 1'b0;
                    end else begin
                        emit_index <= emit_index + 1'b1;
                    end
                end

                if (eof_finalized && !end_reported &&
                    read_total_bytes >= staged_file_size &&
                    !read_pending && !read_buf_valid &&
                    emit_bytes_left == 0) begin
                    end_reported <= 1'b1;
                    playback_done_toggle <= ~playback_done_toggle;
                    state <= S_DONE;
                end
            end
        end
    end

    // ACK follows processing THIS synchronized token and two stable memory
    // edges with private state empty. A paused memory clock cannot ACK.
    reg [1:0] restart_zero_count;
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin runtime_restart_ack_o<=0;restart_zero_count<=0;end
        else begin
            restart_zero_count<=0;
            if(runtime_hold_i && restart_seen==restart_sync &&
               runtime_restart_ack_o!=restart_seen && !write_pending && !read_pending &&
               !read_buf_valid && !in_read_wait && !fifo_in_rd_en && !fifo_in_rd_valid &&
               write_count==0 && emit_bytes_left==0)begin
                if(restart_zero_count==1)begin runtime_restart_ack_o<=restart_seen;restart_zero_count<=0;end
                else restart_zero_count<=restart_zero_count+1'b1;
            end
        end
    end
endmodule
