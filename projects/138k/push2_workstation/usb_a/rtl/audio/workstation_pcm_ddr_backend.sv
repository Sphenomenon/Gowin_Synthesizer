`timescale 1ns/1ps
`default_nettype none
`include "src/memory/ddr_address_map.vh"
// Storage mechanism. All ports use the always-running DDR UI clock.
// The business owner supplies identity/rate/epoch; this module never generates
// recording IDs, negotiates BLE formats or controls the audio sample schedule.
module workstation_pcm_ddr_backend #(
    parameter integer CAPACITY_FRAMES=16384,
    parameter integer FIFO_ADDRESS_BITS=9,
    parameter integer DDR_BUDGET_CYCLES=10000,
    parameter integer SOURCE_GAP_CYCLES=400000,
    parameter bit TRANSPORT_FAULT_ENABLE=1'b0
) (
    input wire clk_i,rst_ni,
    input wire create_i,
    output wire create_ready_o,
    input wire [63:0] object_id_i,
    input wire rate_44k1_i,
    input wire [31:0] epoch_i,first_sequence_i,limit_frames_i,
    input wire seal_i,cancel_i,soft_reset_i,clear_i,
    output wire clear_ready_o,
    input wire pcm_valid_i,source_ready_i,source_error_i,
    input wire [31:0] pcm_pair_i,pcm_sequence_i,pcm_epoch_i,
    input wire pcm_44k1_i,
    output wire capture_o,
    output reg [3:0] state_o,
    output reg [3:0] failure_code_o,
    output reg [63:0] object_id_o,
    output reg rate_44k1_o,
    output reg [31:0] epoch_o,frames_o,committed_frames_o,
    output wire quiescent_o,
    output reg [FIFO_ADDRESS_BITS:0] fifo_peak_o,
    output reg [31:0] max_command_wait_o,max_read_wait_o,discarded_responses_o,
    // One download reference. Release closes admission immediately, then
    // drains every published native command/read before dropping the hold.
    input wire reference_acquire_i,reference_release_i,
    input wire [63:0] reference_object_id_i,
    output wire reference_ready_o,
    output reg reference_held_o,reference_granted_o,reference_error_o,reference_released_o,
    input wire download_i,
    output wire download_ready_o,
    input wire [31:0] download_offset_i,download_length_i,
    output wire download_valid_o,
    input wire download_ready_i,
    output wire [255:0] download_data_o,
    output wire [5:0] download_bytes_o,
    output wire download_last_o,
    output reg download_done_o,download_error_o,
    // ready MUST mean native command/write-data acceptance, not entry into a
    // local client slot. No write acknowledgements are invented here. Reads
    // return later, once, in order; one read is outstanding at most.
    output reg ddr_valid_o,ddr_write_o,
    output reg [28:0] ddr_address_o,
    output reg [255:0] ddr_data_o,
    output reg [31:0] ddr_mask_o,
    input wire ddr_ready_i,ddr_response_i,
    input wire [255:0] ddr_read_data_i,
    input wire transport_fault_i
);
    localparam [3:0] EMPTY=0,CAPTURE=1,SEALING=2,READY=3,ERROR=4,CANCELLED=5,RESET=6;
    localparam [3:0] OVERFLOW=1,GAP=2,CONTEXT=3,SOURCE=4,COMMAND_TIMEOUT=5,
        READ_TIMEOUT=6,UNEXPECTED_RESPONSE=7,DESCRIPTOR=8,TRANSPORT=9;
    localparam integer FIFO_DEPTH=1<<FIFO_ADDRESS_BITS;
    initial begin
        if(CAPACITY_FRAMES<1 || CAPACITY_FRAMES*4>`PRJ1_DDR_RECORDING_CPU_BYTES ||
           FIFO_ADDRESS_BITS<2 || FIFO_ADDRESS_BITS>9 || DDR_BUDGET_CYCLES<2 || SOURCE_GAP_CYCLES<2)
            $fatal(1,"invalid PCM DDR backend geometry/budget");
        if({3'd0,`PRJ1_DDR_RECORDING_CPU_APP_BASE}!=(`PRJ1_DDR_RECORDING_CPU_BYTE_BASE>>2) ||
           `PRJ1_DDR_RECORDING_CPU_BYTE_BASE!=`PRJ1_DDR_RECORDING_BYTE_BASE ||
           `PRJ1_DDR_RECORDING_CPU_BYTES!=`PRJ1_DDR_RECORDING_STAGE_BYTES ||
           `PRJ1_DDR_RECORDING_CPU_BYTE_LAST-`PRJ1_DDR_RECORDING_CPU_BYTE_BASE+1!=`PRJ1_DDR_RECORDING_CPU_BYTES ||
           {3'd0,`PRJ1_DDR_RECORDING_CPU_APP_LAST}!=(`PRJ1_DDR_RECORDING_CPU_BYTE_LAST>>2) ||
           `PRJ1_DDR_RECORDING_CPU_BYTE_LAST>=`PRJ1_DDR_RECORDING_BLE_BYTE_BASE ||
           `PRJ1_DDR_RECORDING_BLE_BYTE_LAST>`PRJ1_DDR_RECORDING_BYTE_LAST ||
           (`PRJ1_DDR_RECORDING_BYTE_BASE & 32'h000fffff)!=0 ||
           `PRJ1_DDR_RECORDING_BYTE_BASE<=`PRJ1_DDR_BP_HISTORY_BYTE_LAST ||
           `PRJ1_DDR_RECORDING_BYTE_LAST>`PRJ1_DDR_BULK_POOL_BYTE_LAST ||
           `PRJ1_DDR_RECORDING_BYTE_LAST-`PRJ1_DDR_RECORDING_BYTE_BASE+1!=`PRJ1_DDR_RECORDING_BYTES)
            $fatal(1,"PCM recording allocation overlaps/misaligns");
    end
    reg [31:0] expected_sequence,frame_limit,gap_wait,command_wait,read_wait;
    reg [31:0] generation,read_generation;
    reg [FIFO_ADDRESS_BITS-1:0] fifo_wr,fifo_rd;
    reg [FIFO_ADDRESS_BITS:0] fifo_count;
    reg fifo_forward;
    reg [31:0] fifo_forward_data;
    wire [31:0] fifo_ram_data;
    wire [31:0] fifo_head=fifo_forward ? fifo_forward_data : fifo_ram_data;
    reg [255:0] pack_data;
    reg pack_word_valid;
    reg [2:0] pack_word_index;
    reg [31:0] pack_word_data;
    wire [255:0] packed_payload;
    reg [3:0] pack_frames,command_frames;
    reg [28:0] write_address;
    reg read_outstanding,reference_closing,download_active;
    reg [31:0] issue_offset,issue_remaining;
    reg [4:0] command_skip,read_skip;
    reg [5:0] command_bytes,read_bytes;
    reg command_last,read_last;
    // Two demand-prefetch beats; deliberately registers, not another bulk RAM.
    reg [255:0] prefetched_data[0:1];
    reg [5:0] prefetched_bytes[0:1];
    reg prefetched_last[0:1];
    reg prefetch_rd,prefetch_wr;
    reg [1:0] prefetch_count;
    wire command_accept=ddr_valid_o && ddr_ready_i;
    wire terminal=state_o==ERROR || state_o==CANCELLED || state_o==RESET;
    wire command_expired=ddr_valid_o && !ddr_ready_i && command_wait>=DDR_BUDGET_CYCLES-1;
    wire read_expired=read_outstanding && !ddr_response_i && read_wait>=DDR_BUDGET_CYCLES-1;
    wire source_bad=state_o==CAPTURE && (!source_ready_i || source_error_i || gap_wait>=SOURCE_GAP_CYCLES-1);
    wire context_bad=state_o==CAPTURE && pcm_valid_i && !seal_i && (pcm_epoch_i!=epoch_o || pcm_44k1_i!=rate_44k1_o);
    wire sequence_bad=state_o==CAPTURE && pcm_valid_i && !seal_i && pcm_sequence_i!=expected_sequence;
    wire fifo_pop=(state_o==CAPTURE || state_o==SEALING) && fifo_count!=0 && pack_frames<8;
    wire overflow=state_o==CAPTURE && pcm_valid_i && !seal_i && fifo_count==(FIFO_ADDRESS_BITS+1)'(FIFO_DEPTH) && !fifo_pop;
    wire bad_response=ddr_response_i && !read_outstanding;
    wire transport_bad=TRANSPORT_FAULT_ENABLE && transport_fault_i;
    wire fault_event=!terminal && (transport_bad || source_bad || context_bad || sequence_bad || overflow || command_expired || read_expired || bad_response);
    // A sticky bus fault blocks reuse even after entering a terminal state.
    // Only the common controller/ledger/backend reset may rearm this channel.
    wire invalidate=cancel_i || soft_reset_i || transport_bad || fault_event;
    assign capture_o=rst_ni && state_o==CAPTURE && pcm_valid_i && !seal_i && !invalidate;
    wire pop=fifo_pop && !invalidate;
    wire [FIFO_ADDRESS_BITS-1:0] fifo_next_rd=fifo_rd+FIFO_ADDRESS_BITS'(pop);
    workstation_sdp #(.ADDR_WIDTH(FIFO_ADDRESS_BITS)) capture_fifo(
        .write_clk_i(clk_i),.write_enable_i(capture_o),.write_addr_i(fifo_wr),.write_data_i(pcm_pair_i),
        .read_clk_i(clk_i),.read_enable_i(1'b1),.read_addr_i(fifo_next_rd),.read_data_o(fifo_ram_data));
    assign quiescent_o=!ddr_valid_o && !read_outstanding;
    // Competing owner commands are resolved before admission, so an accepted
    // request is never silently overwritten by a later sequential assignment.
    assign create_ready_o=rst_ni && state_o==EMPTY && quiescent_o && !reference_held_o && !invalidate && !clear_i;
    assign clear_ready_o=rst_ni && state_o!=CAPTURE && state_o!=SEALING && quiescent_o && !reference_held_o && !invalidate;
    assign reference_ready_o=rst_ni && state_o==READY && !reference_held_o && !invalidate && !clear_i && !reference_release_i;
    assign download_ready_o=rst_ni && state_o==READY && reference_held_o && !reference_closing &&
        !download_active && quiescent_o && !invalidate && !reference_release_i;
    assign download_valid_o=state_o==READY && reference_held_o && !reference_closing &&
        prefetch_count!=0 && !invalidate && !reference_release_i;
    assign download_data_o=prefetched_data[prefetch_rd];
    assign download_bytes_o=prefetched_bytes[prefetch_rd];
    assign download_last_o=prefetched_last[prefetch_rd];
    wire download_pop=download_valid_o && download_ready_i;
    wire response_keep=ddr_response_i && read_outstanding && read_generation==generation &&
        state_o==READY && reference_held_o && !reference_closing && !reference_release_i && !invalidate;
    wire [5:0] next_read_bytes=(issue_remaining<32-{27'd0,issue_offset[4:0]}) ?
        issue_remaining[5:0] : 6'd32-{1'b0,issue_offset[4:0]};

    // Admission/fault feedback ends at a one-bit strobe. Retire the accepted
    // word on the next edge through a fixed lane, without clearing all 256
    // payload bits on publish/cancel. Inactive lanes are zeroed at publication.
    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin pack_word_index<=0;pack_word_data<=0;end
        else begin pack_word_index<=pack_frames[2:0];pack_word_data<=fifo_head;end
    end
    generate for(genvar lane=0;lane<8;lane=lane+1)begin:g_pack_lane
        always @(posedge clk_i or negedge rst_ni)
            if(!rst_ni)pack_data[lane*32+:32]<=0;
            else if(pack_word_valid && pack_word_index==3'(lane))
                pack_data[lane*32+:32]<=pack_word_data;
        assign packed_payload[lane*32+:32]=pack_frames>4'(lane) ? pack_data[lane*32+:32] : 32'd0;
    end endgenerate

    always @(posedge clk_i or negedge rst_ni) begin
        if(!rst_ni) begin
            state_o<=EMPTY;failure_code_o<=0;object_id_o<=0;rate_44k1_o<=0;epoch_o<=0;
            frames_o<=0;committed_frames_o<=0;frame_limit<=0;expected_sequence<=0;
            generation<=0;read_generation<=0;gap_wait<=0;command_wait<=0;read_wait<=0;
            fifo_wr<=0;fifo_rd<=0;fifo_count<=0;fifo_forward<=0;fifo_forward_data<=0;fifo_peak_o<=0;
            pack_word_valid<=0;pack_frames<=0;command_frames<=0;write_address<=`PRJ1_DDR_RECORDING_CPU_APP_BASE;
            ddr_valid_o<=0;ddr_write_o<=0;ddr_address_o<=0;ddr_data_o<=0;ddr_mask_o<=0;
            read_outstanding<=0;reference_closing<=0;reference_held_o<=0;
            reference_granted_o<=0;reference_error_o<=0;reference_released_o<=0;
            download_active<=0;issue_offset<=0;issue_remaining<=0;command_skip<=0;read_skip<=0;
            command_bytes<=0;read_bytes<=0;command_last<=0;read_last<=0;
            prefetch_rd<=0;prefetch_wr<=0;prefetch_count<=0;
            download_done_o<=0;download_error_o<=0;
            max_command_wait_o<=0;max_read_wait_o<=0;discarded_responses_o<=0;
        end else begin
            reference_granted_o<=0;reference_error_o<=0;reference_released_o<=0;
            download_done_o<=0;download_error_o<=0;
            pack_word_valid<=pop;
            fifo_forward_data<=pcm_pair_i;
            fifo_forward<=capture_o && (fifo_count==0 || (fifo_count==1 && pop));
            if(capture_o) begin
                fifo_wr<=fifo_wr+1'b1;frames_o<=frames_o+1'b1;expected_sequence<=expected_sequence+1'b1;
                if(frames_o+1'b1==frame_limit) state_o<=SEALING;
            end
            if(pop) begin
                fifo_rd<=fifo_next_rd;
                pack_frames<=pack_frames+1'b1;
            end
            case({capture_o,pop})
                2'b10:fifo_count<=fifo_count+1'b1;
                2'b01:fifo_count<=fifo_count-1'b1;
                default:begin end
            endcase
            if(capture_o && !pop && fifo_count+1'b1>fifo_peak_o) fifo_peak_o<=fifo_count+1'b1;
            if(state_o==CAPTURE) begin
                if(pcm_valid_i)gap_wait<=0;
                else if(gap_wait<SOURCE_GAP_CYCLES)gap_wait<=gap_wait+1'b1;
                if(seal_i)state_o<=SEALING;
            end
            if(ddr_valid_o && !ddr_ready_i) begin
                if(command_wait!=32'hffffffff)begin
                    command_wait<=command_wait+1'b1;
                    if(command_wait+1'b1>max_command_wait_o)max_command_wait_o<=command_wait+1'b1;
                end
            end else command_wait<=0;
            if(read_outstanding && !ddr_response_i) begin
                if(read_wait!=32'hffffffff)begin
                    read_wait<=read_wait+1'b1;
                    if(read_wait+1'b1>max_read_wait_o)max_read_wait_o<=read_wait+1'b1;
                end
            end else read_wait<=0;
            if(command_accept) begin
                ddr_valid_o<=0;
                if(ddr_write_o) begin
                    committed_frames_o<=committed_frames_o+{28'd0,command_frames};
                    write_address<=write_address+`PRJ1_DDR_APP_ADDR_STEP;
                end else begin
                    read_outstanding<=1;read_generation<=generation;
                    read_skip<=command_skip;read_bytes<=command_bytes;read_last<=command_last;
                    issue_offset<=issue_offset+{26'd0,command_bytes};
                    issue_remaining<=issue_remaining-{26'd0,command_bytes};
                end
            end
            if(ddr_response_i && read_outstanding) begin
                read_outstanding<=0;
                if(response_keep) begin
                    prefetched_data[prefetch_wr]<=ddr_read_data_i>>(read_skip*8);
                    prefetched_bytes[prefetch_wr]<=read_bytes;
                    prefetched_last[prefetch_wr]<=read_last;
                    prefetch_wr<=~prefetch_wr;
                end else discarded_responses_o<=discarded_responses_o+1'b1;
            end
            if(download_pop) begin
                prefetch_rd<=~prefetch_rd;
                if(download_last_o)begin download_active<=0;download_done_o<=1;end
            end
            case({response_keep,download_pop})
                2'b10:prefetch_count<=prefetch_count+1'b1;
                2'b01:prefetch_count<=prefetch_count-1'b1;
                default:begin end
            endcase
            if(!ddr_valid_o && !invalidate) begin
                if(!pack_word_valid && (state_o==CAPTURE || state_o==SEALING) &&
                   (pack_frames==8 || (state_o==SEALING && fifo_count==0 && pack_frames!=0))) begin
                    ddr_valid_o<=1;ddr_write_o<=1;ddr_address_o<=write_address;
                    ddr_data_o<=packed_payload;ddr_mask_o<=32'hffffffff<<(pack_frames*4);
                    command_frames<=pack_frames;pack_frames<=0;
                end else if(state_o==READY && reference_held_o && !reference_closing &&
                    !reference_release_i && download_active && issue_remaining!=0 &&
                    !read_outstanding && prefetch_count<2) begin
                    ddr_valid_o<=1;ddr_write_o<=0;ddr_mask_o<=0;ddr_data_o<=0;
                    ddr_address_o<=`PRJ1_DDR_RECORDING_CPU_APP_BASE+{2'd0,issue_offset[28:5],3'b0};
                    command_skip<=issue_offset[4:0];command_bytes<=next_read_bytes;
                    command_last<=issue_remaining=={26'd0,next_read_bytes};
                end
            end
            if(state_o==SEALING && fifo_count==0 && pack_frames==0 && quiescent_o &&
               committed_frames_o==frames_o && !invalidate)state_o<=READY;
            if(reference_acquire_i && reference_ready_o)begin
                if(reference_object_id_i==object_id_o)begin reference_held_o<=1;reference_granted_o<=1;end
                else reference_error_o<=1;
            end
            if(download_i && download_ready_o)begin
                if(download_length_i==0 || download_offset_i>frames_o*4 ||
                   download_length_i>frames_o*4-download_offset_i)download_error_o<=1;
                else begin
                    download_active<=1;issue_offset<=download_offset_i;issue_remaining<=download_length_i;
                    prefetch_rd<=0;prefetch_wr<=0;prefetch_count<=0;
                end
            end
            if(reference_release_i && reference_held_o)reference_closing<=1;
            if(reference_closing && quiescent_o)begin
                reference_held_o<=0;reference_closing<=0;reference_released_o<=1;
                download_active<=0;issue_remaining<=0;prefetch_count<=0;
            end
            if(create_i && create_ready_o)begin
                object_id_o<=object_id_i;rate_44k1_o<=rate_44k1_i;epoch_o<=epoch_i;
                expected_sequence<=first_sequence_i;frame_limit<=limit_frames_i;
                frames_o<=0;committed_frames_o<=0;gap_wait<=0;fifo_peak_o<=0;
                failure_code_o<=0;generation<=generation+1'b1;
                if(object_id_i==0 || epoch_i==0 || limit_frames_i==0 || limit_frames_i>CAPACITY_FRAMES)begin
                    state_o<=ERROR;failure_code_o<=DESCRIPTOR;
                end else state_o<=CAPTURE;
            end
            if(clear_i && clear_ready_o)begin
                state_o<=EMPTY;failure_code_o<=0;object_id_o<=0;epoch_o<=0;
                frames_o<=0;committed_frames_o<=0;generation<=generation+1'b1;
                fifo_wr<=0;fifo_rd<=0;fifo_count<=0;fifo_forward<=0;pack_frames<=0;pack_word_valid<=0;
                prefetch_count<=0;download_active<=0;issue_remaining<=0;
                write_address<=`PRJ1_DDR_RECORDING_CPU_APP_BASE;
            end
            if(invalidate)begin
                if(!terminal)begin
                    generation<=generation+1'b1;
                    if(soft_reset_i)state_o<=RESET;
                    else if(cancel_i)state_o<=CANCELLED;
                    else begin
                        state_o<=ERROR;
                        if(transport_bad)failure_code_o<=TRANSPORT;
                        else if(source_bad)failure_code_o<=SOURCE;
                        else if(context_bad)failure_code_o<=CONTEXT;
                        else if(sequence_bad)failure_code_o<=GAP;
                        else if(overflow)failure_code_o<=OVERFLOW;
                        else if(command_expired)failure_code_o<=COMMAND_TIMEOUT;
                        else if(read_expired)failure_code_o<=READ_TIMEOUT;
                        else failure_code_o<=UNEXPECTED_RESPONSE;
                    end
                end
                // A published command remains stable through invalidate. Its
                // native acceptance and any read response must still drain.
                fifo_wr<=0;fifo_rd<=0;fifo_count<=0;fifo_forward<=0;pack_frames<=0;pack_word_valid<=0;
                download_active<=0;prefetch_count<=0;
                if(reference_held_o && !reference_closing)reference_closing<=1;
            end
        end
    end
endmodule
`default_nettype wire
