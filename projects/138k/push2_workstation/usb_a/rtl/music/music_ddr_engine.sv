`timescale 1ns/1ps
// Writes uploaded 256-bit beats into the reserved 64-MiB song region and,
// later, reads exactly one aligned detector window at a time.  One stereo PCM
// frame is one native 32-bit DDR word, so source frame offsets map directly to
// native addresses. No parsed note sequence exists in this block.
module music_ddr_engine #(
    parameter logic [28:0] MUSIC_BASE=29'h00800000,
    parameter integer WINDOW_LOG2=12
)(
    input  logic clk_i,rst_ni,
    input  logic upload_valid_i,
    output logic upload_ready_o,
    input  logic [20:0] upload_beat_index_i,
    input  logic [255:0] upload_data_i,
    input  logic [31:0] upload_keep_i,
    input  logic window_request_i,
    input  logic [31:0] window_frame_i,
    output logic detector_start_o,
    output logic [31:0] detector_frame_o,
    input  logic detector_sample_ready_i,
    output logic detector_sample_valid_o,
    output logic signed [15:0] detector_sample_o,
    output logic music_req_o,
    output logic music_write_o,
    output logic [28:0] music_address_o,
    output logic [255:0] music_data_o,
    output logic [31:0] music_mask_o,
    input  logic music_ready_i,
    input  logic music_response_i,
    input  logic [255:0] music_read_data_i,
    output logic busy_o,
    output logic [31:0] windows_loaded_o
);
    localparam integer BEATS_PER_WINDOW=(1<<WINDOW_LOG2)/8;
    localparam integer BEAT_COUNT_BITS=$clog2(BEATS_PER_WINDOW);
    localparam logic [2:0] IDLE=0,ISSUE_UPLOAD=1,ISSUE_READ=2,WAIT_READ=3,STREAM_BEAT=4;
    logic [2:0] state;
    logic [20:0] upload_beat_index;
    logic [255:0] upload_data;
    logic [31:0] upload_keep;
    logic [28:0] read_address;
    logic [BEAT_COUNT_BITS-1:0] beat_count;
    logic [2:0] sample_lane;
    logic [255:0] read_data;
    logic signed [15:0] left_sample,right_sample;
    logic signed [16:0] sample_sum;

    always_comb begin
        left_sample=$signed(read_data[sample_lane*32+:16]);
        right_sample=$signed(read_data[sample_lane*32+16+:16]);
        sample_sum={left_sample[15],left_sample}+{right_sample[15],right_sample};
        detector_sample_o=sample_sum[16:1];
        detector_sample_valid_o=state==STREAM_BEAT;
        music_req_o=0;music_write_o=0;music_address_o=0;music_data_o=0;music_mask_o=0;
        // Accept the FIFO beat into local registers before requesting DDR.  In
        // particular, neither upload_ready_o nor the FIFO pointer update may
        // depend combinationally on app_ready from the DDR arbiter.
        upload_ready_o=state==IDLE && !window_request_i;
        if(state==ISSUE_UPLOAD)begin
            music_req_o=1;music_write_o=1;
            music_address_o=MUSIC_BASE+{5'd0,upload_beat_index,3'b000};
            music_data_o=upload_data;music_mask_o=~upload_keep;
        end else if(state==ISSUE_READ)begin
            music_req_o=1;music_address_o=read_address;
        end
        busy_o=state!=IDLE;
    end

    always_ff @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin
            state<=IDLE;upload_beat_index<=0;upload_data<=0;upload_keep<=0;
            read_address<=0;beat_count<=0;sample_lane<=0;read_data<=0;
            detector_start_o<=0;detector_frame_o<=0;windows_loaded_o<=0;
        end else begin
            detector_start_o<=0;
            case(state)
                IDLE:begin
                    if(window_request_i)begin
                        // Search advances in 1024-frame hops, hence all requests
                        // are naturally aligned to the eight frames in one beat.
                        read_address<=MUSIC_BASE+window_frame_i[28:0];
                        beat_count<=0;sample_lane<=0;detector_frame_o<=window_frame_i;
                        detector_start_o<=1;state<=ISSUE_READ;
                    end else if(upload_valid_i)begin
                        upload_beat_index<=upload_beat_index_i;
                        upload_data<=upload_data_i;upload_keep<=upload_keep_i;
                        state<=ISSUE_UPLOAD;
                    end
                end
                ISSUE_UPLOAD:if(music_ready_i)state<=IDLE;
                ISSUE_READ:if(music_ready_i)state<=WAIT_READ;
                WAIT_READ:if(music_response_i)begin
                    read_data<=music_read_data_i;sample_lane<=0;state<=STREAM_BEAT;
                end
                STREAM_BEAT:if(detector_sample_ready_i)begin
                    if(sample_lane==7)begin
                        if(&beat_count)begin
                            windows_loaded_o<=windows_loaded_o+1'b1;state<=IDLE;
                        end else begin
                            beat_count<=beat_count+1'b1;read_address<=read_address+29'd8;state<=ISSUE_READ;
                        end
                    end else sample_lane<=sample_lane+1'b1;
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
