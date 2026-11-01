`timescale 1ns/1ps
`include "rtl/ddr_address_map.vh"
// Unselected W task owner. A bounded clip is committed and readback-CRC sealed
// before the real model/CQT/CNN/Viterbi consumes it. This port is not a realtime
// audio source: transport credits must never propagate into M's sample clock.
module workstation_cnn_task_service #(
    parameter integer CAPACITY_FRAMES=`PRJ1_DDR_TASK3_W_CNN_PCM_CAPACITY_FRAMES,
    parameter integer IO_TIMEOUT_CYCLES=50000000,
    parameter [31:0] TASK_TIMEOUT_CYCLES=32'd3600000000
) (
    input wire clk_i,reset_ni,memory_clk_i,memory_reset_ni,backend_ready_i,transport_fault_i,
    input wire start_valid_i,
    output wire start_ready_o,
    input wire [31:0] start_task_id_i,start_generation_i,start_frames_i,start_crc_i,
    input wire [7:0] start_format_i,
    output reg start_accepted_o,start_rejected_o,
    output reg [3:0] rejection_code_o,
    input wire frame_valid_i,
    output wire frame_ready_o,
    input wire [31:0] frame_task_id_i,frame_generation_i,frame_index_i,frame_pcm_i,
    input wire ingress_fault_i,
    input wire cancel_valid_i,
    input wire [31:0] cancel_task_id_i,cancel_generation_i,
    output reg seal_valid_o,
    output reg [31:0] seal_crc_o,accepted_frames_o,committed_frames_o,replayed_frames_o,
    output wire score_valid_o,
    input wire score_ready_i,
    output wire [6:0] score_note_o,
    output reg [31:0] score_index_o,
    output reg [31:0] task_id_o,generation_o,
    output wire terminal_valid_o,
    input wire terminal_ready_i,
    output reg [3:0] terminal_code_o,
    output reg first_result_valid_o,
    output reg [6:0] first_result_note_o,
    output reg [15:0] first_result_frame_o,
    output reg fatal_o,
    output wire [3:0] model_status_o,
    input wire model_serial_i,flash_miso_i,
    output wire flash_cs_n_o,flash_clk_o,flash_mosi_o,
    output wire memory_valid_o,memory_write_o,
    output wire [28:0] memory_address_o,
    output wire [255:0] memory_data_o,
    output wire [31:0] memory_mask_o,
    input wire memory_slot_ready_i,memory_native_accept_i,memory_response_i,
    input wire [255:0] memory_read_data_i
);
    localparam [3:0] IDLE=0,ARM=1,CAPTURE=2,WRITE_WAIT=3,VERIFY_REQ=4,VERIFY_WAIT=5,
        VERIFY_DATA=6,RUN_REQ=7,RUN_WAIT=8,RUN_DATA=9,ENDING=10,DRAIN=11,TERMINAL=12;
    // Terminal0 success,1 cancel,2 input identity/index/overflow,3 length,
    // 4 input CRC,5 DDR readback CRC,6 task timeout,15 transport/reset fault.
    reg [3:0] state;
    reg [31:0] expected_frames,expected_crc,last_generation,elapsed,cursor;
    reg [255:0] pack,read_beat;
    reg [3:0] pack_frames,write_frames;
    reg [2:0] beat_frame;
    reg [31:0] crc,crc_word;
    reg [1:0] crc_phase;
    reg crc_busy,stage_inflight,restart_pending,cnn_restart,previous_result;
    (* ASYNC_REG="TRUE" *) reg backend_meta,backend_sync,broker_fault_meta,broker_fault_sync;
    reg backend_seen;
    wire broker_fault;
    wire cnn_ready,cnn_score_valid,cnn_result_valid,cnn_analysis_done;
    wire [6:0] cnn_result_note;
    wire [15:0] cnn_result_frame;
    wire restart_ready,restart_busy,restart_done,restart_fault;
    wire [1:0] restart_failure;
    wire cancel_match=cancel_valid_i && cancel_task_id_i==task_id_o && cancel_generation_i==generation_o;
    wire active=state!=IDLE && state!=TERMINAL;
    wire live=reset_ni && memory_reset_ni && backend_sync && !fatal_o;
    wire running=state==RUN_REQ || state==RUN_WAIT || state==RUN_DATA || state==ENDING;
    assign start_ready_o=live && state==IDLE && model_status_o==4'd14 && restart_ready;
    assign frame_ready_o=live && state==CAPTURE && !cancel_match && !ingress_fault_i && !crc_busy &&
        pack_frames<8 && accepted_frames_o<expected_frames;
    assign score_valid_o=live && running && !cancel_match && cnn_score_valid;
    assign terminal_valid_o=state==TERMINAL;
    wire frame_fire=frame_valid_i && frame_ready_o;
    wire cnn_pcm_valid=live && state==RUN_DATA && !cancel_match;
    wire [31:0] cnn_pcm=read_beat[beat_frame*32+:32];
    wire [31:0] verify_word=read_beat[beat_frame*32+:32];
    function automatic [31:0] crc_byte(input [31:0] old_crc,input [7:0] byte_value);
        reg [31:0] c;integer k;
        begin c=old_crc^{24'd0,byte_value};for(k=0;k<8;k=k+1)c=c[0]?((c>>1)^32'hedb88320):(c>>1);crc_byte=c;end
    endfunction
    function automatic [31:0] tail_mask(input [3:0] frames);
        integer k;begin for(k=0;k<32;k=k+1)tail_mask[k]=(k>=integer'(frames)*4);end
    endfunction
    initial if(CAPACITY_FRAMES<1 || CAPACITY_FRAMES>`PRJ1_DDR_TASK3_W_CNN_PCM_CAPACITY_FRAMES ||
        IO_TIMEOUT_CYCLES<4 || TASK_TIMEOUT_CYCLES<16)$fatal(1,"invalid bounded CNN task capacity/budget");

    // At most one staging command is in flight. Native commitment/read return
    // creates the completion; enqueue into either FIFO is not commitment.
    wire flush_pack=state==CAPTURE && !crc_busy && pack_frames!=0 &&
        (pack_frames==8 || accepted_frames_o==expected_frames);
    wire command_valid=live && !cancel_match && !ingress_fault_i && !stage_inflight &&
        (flush_pack || state==VERIFY_REQ || state==RUN_REQ);
    wire command_write=flush_pack;
    wire [28:0] command_address=`PRJ1_DDR_TASK3_W_CNN_PCM_APP_BASE+
        (flush_pack?29'(committed_frames_o):{cursor[28:3],3'b000});
    wire [317:0] command_data={command_write,command_address,pack,command_write?tail_mask(pack_frames):32'd0};
    wire command_ready,command_fire=command_valid && command_ready;
    wire request_valid,request_ready;
    wire [317:0] request_data;
    music_async_fifo #(.WIDTH(318),.ADDRESS_BITS(2)) staging_requests(
        .write_clk_i(clk_i),.write_rst_ni(reset_ni),.write_valid_i(command_valid),.write_ready_o(command_ready),
        .write_data_i(command_data),.read_clk_i(memory_clk_i),.read_rst_ni(reset_ni && memory_reset_ni),
        .read_valid_o(request_valid),.read_ready_i(request_ready),.read_data_o(request_data));
    wire completion_valid,completion_ready,completion_source_ready;
    wire [256:0] completion_data;
    wire staging_native_ready,staging_response;
    wire completion_write=staging_native_ready && request_data[317];
    reg completion_overflow;
    always @(posedge memory_clk_i or negedge reset_ni)
        if(!reset_ni)completion_overflow<=0;
        else if((completion_write || staging_response) && !completion_source_ready)completion_overflow<=1;
    music_async_fifo #(.WIDTH(257),.ADDRESS_BITS(2)) staging_completions(
        .write_clk_i(memory_clk_i),.write_rst_ni(reset_ni && memory_reset_ni),
        .write_valid_i(completion_write || staging_response),.write_ready_o(completion_source_ready),
        .write_data_i({completion_write,memory_read_data_i}),
        .read_clk_i(clk_i),.read_rst_ni(reset_ni),.read_valid_o(completion_valid),
        .read_ready_i(completion_ready),.read_data_o(completion_data));
    assign completion_ready=stage_inflight &&
        (state==WRITE_WAIT || state==VERIFY_WAIT || state==RUN_WAIT || state==DRAIN);
    assign request_ready=staging_native_ready;
    wire cnn_ddr_valid,cnn_ddr_write,cnn_ddr_ready,cnn_ddr_response;
    wire [28:0] cnn_ddr_address;
    wire [255:0] cnn_ddr_data;
    wire [31:0] cnn_ddr_mask;
    workstation_cnn_ddr_broker #(.TIMEOUT_CYCLES(IO_TIMEOUT_CYCLES)) broker(
        .clk_i(memory_clk_i),.reset_ni(reset_ni && memory_reset_ni),.backend_ready_i(backend_ready_i),
        .transport_fault_i(transport_fault_i || completion_overflow),
        .cnn_valid_i(cnn_ddr_valid),.cnn_write_i(cnn_ddr_write),.cnn_address_i(cnn_ddr_address),
        .cnn_data_i(cnn_ddr_data),.cnn_mask_i(cnn_ddr_mask),.cnn_ready_o(cnn_ddr_ready),.cnn_response_o(cnn_ddr_response),
        .stage_valid_i(request_valid && completion_source_ready),.stage_write_i(request_data[317]),
        .stage_address_i(request_data[316:288]),.stage_data_i(request_data[287:32]),.stage_mask_i(request_data[31:0]),
        .stage_ready_o(staging_native_ready),.stage_response_o(staging_response),
        .slot_valid_o(memory_valid_o),.write_o(memory_write_o),.address_o(memory_address_o),
        .data_o(memory_data_o),.mask_o(memory_mask_o),.slot_ready_i(memory_slot_ready_i),
        .native_accept_i(memory_native_accept_i),.response_i(memory_response_i),.idle_o(),.fault_o(broker_fault));
    basic_pitch_workstation_link #(.USE_FLASH_WEIGHTS(1),.DRAIN_RESTART_ENABLE(1),.BOUNDED_EOF_PADDING(1),
        .RESTART_TIMEOUT_CYCLES(IO_TIMEOUT_CYCLES)) cnn(
        .clk_50m(clk_i),.reset_n(reset_ni),.memory_clk(memory_clk_i),.memory_reset_n(memory_reset_ni),
        .memory_calibrated(backend_ready_i),.model_serial(model_serial_i),.flash_miso(flash_miso_i),
        .flash_cs_n(flash_cs_n_o),.flash_clk(flash_clk_o),.flash_mosi(flash_mosi_o),
        .analysis_enable(live && running && !cancel_match),.analysis_restart(cnn_restart),
        .pcm_valid(cnn_pcm_valid),.pcm_end(state==ENDING && !cancel_match),
        .pcm_left(cnn_pcm[15:0]),.pcm_right(cnn_pcm[31:16]),.sample_rate(20'd48000),
        .format_ready(running),.source_active(running),.hotplug_debug(11'd0),.pcm_ready(cnn_ready),
        .model_status(model_status_o),.result_valid(cnn_result_valid),.result_note(cnn_result_note),.result_frame(cnn_result_frame),
        .score_valid(cnn_score_valid),.score_ready(score_ready_i && live && running && !cancel_match),.score_note(score_note_o),
        .analysis_done(cnn_analysis_done),.report_sending(),.report_serial(),
        .ddr_req(cnn_ddr_valid),.ddr_write(cnn_ddr_write),.ddr_address(cnn_ddr_address),.ddr_data(cnn_ddr_data),.ddr_mask(cnn_ddr_mask),
        .ddr_ready(cnn_ddr_ready),.ddr_response(cnn_ddr_response),.ddr_read_data(memory_read_data_i),
        .restart_ready_o(restart_ready),.restart_busy_o(restart_busy),.restart_done_o(restart_done),
        .restart_fault_o(restart_fault),.restart_failure_code_o(restart_failure));

    task automatic abort_task(input [3:0] code);
        begin
            state<=DRAIN;terminal_code_o<=code;crc_busy<=0;
            if(!restart_pending)begin cnn_restart<=1;restart_pending<=1;end
        end
    endtask
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;expected_frames<=0;expected_crc<=0;last_generation<=0;elapsed<=0;cursor<=0;
            pack<=0;read_beat<=0;pack_frames<=0;write_frames<=0;beat_frame<=0;crc<=32'hffffffff;crc_word<=0;
            crc_phase<=0;crc_busy<=0;stage_inflight<=0;restart_pending<=0;cnn_restart<=0;previous_result<=0;
            backend_meta<=0;backend_sync<=0;backend_seen<=0;broker_fault_meta<=0;broker_fault_sync<=0;
            task_id_o<=0;generation_o<=0;start_accepted_o<=0;start_rejected_o<=0;rejection_code_o<=0;
            terminal_code_o<=0;seal_valid_o<=0;seal_crc_o<=0;accepted_frames_o<=0;committed_frames_o<=0;
            replayed_frames_o<=0;score_index_o<=0;fatal_o<=0;first_result_valid_o<=0;first_result_note_o<=0;first_result_frame_o<=0;
        end else begin
            backend_meta<=backend_ready_i;backend_sync<=backend_meta;
            broker_fault_meta<=broker_fault;broker_fault_sync<=broker_fault_meta;
            if(backend_sync)backend_seen<=1;
            start_accepted_o<=0;start_rejected_o<=0;seal_valid_o<=0;cnn_restart<=0;
            previous_result<=cnn_result_valid;
            if(restart_done)restart_pending<=0;
            if(completion_valid && completion_ready)stage_inflight<=0;
            if(command_fire)stage_inflight<=1;
            if(active && elapsed<TASK_TIMEOUT_CYCLES)elapsed<=elapsed+1'b1;
            if(score_valid_o && score_ready_i)score_index_o<=score_index_o+1'b1;
            if(live && running && !cancel_match && cnn_result_valid && !previous_result && !first_result_valid_o)begin
                first_result_valid_o<=1;first_result_note_o<=cnn_result_note;first_result_frame_o<=cnn_result_frame;
            end
            if(crc_busy)begin
                crc<=crc_byte(crc,crc_word[crc_phase*8+:8]);crc_phase<=crc_phase+1'b1;
                if(crc_phase==3)crc_busy<=0;
            end
            if(broker_fault_sync || restart_fault || (backend_seen && !backend_sync))begin
                fatal_o<=1;
                if(active)begin state<=TERMINAL;terminal_code_o<=15;crc_busy<=0;end
                else if(state==TERMINAL && terminal_ready_i)state<=IDLE;
            end else if(!fatal_o)begin
                if(active && state!=DRAIN && (cancel_match || ingress_fault_i || elapsed==TASK_TIMEOUT_CYCLES))begin
                    abort_task(cancel_match?4'd1:ingress_fault_i?4'd2:4'd6);
                end else case(state)
                    IDLE:if(start_valid_i && start_ready_o)begin
                        if(start_task_id_i==0 || start_generation_i==0 || start_generation_i<=last_generation ||
                           start_format_i!=1 || start_frames_i==0 || start_frames_i>CAPACITY_FRAMES)begin
                            start_rejected_o<=1;rejection_code_o<=3;
                        end else begin
                            task_id_o<=start_task_id_i;generation_o<=start_generation_i;last_generation<=start_generation_i;
                            expected_frames<=start_frames_i;expected_crc<=start_crc_i;elapsed<=0;
                            accepted_frames_o<=0;committed_frames_o<=0;replayed_frames_o<=0;score_index_o<=0;
                            pack<=0;pack_frames<=0;crc<=32'hffffffff;crc_busy<=0;cursor<=0;beat_frame<=0;
                            terminal_code_o<=0;seal_crc_o<=0;first_result_valid_o<=0;previous_result<=0;
                            start_accepted_o<=1;cnn_restart<=1;restart_pending<=1;state<=ARM;
                        end
                    end
                    ARM:if(restart_done)state<=CAPTURE;
                    CAPTURE:begin
                        if(frame_fire)begin
                            if(frame_task_id_i!=task_id_o || frame_generation_i!=generation_o || frame_index_i!=accepted_frames_o)
                                abort_task(2);
                            else begin
                                pack[pack_frames*32+:32]<=frame_pcm_i;pack_frames<=pack_frames+1'b1;
                                accepted_frames_o<=accepted_frames_o+1'b1;crc_word<=frame_pcm_i;crc_phase<=0;crc_busy<=1;
                            end
                        end
                        if(command_fire)begin state<=WRITE_WAIT;write_frames<=pack_frames;end
                    end
                    WRITE_WAIT:if(completion_valid && completion_ready)begin
                        if(!completion_data[256])abort_task(15);
                        else begin
                            committed_frames_o<=committed_frames_o+{28'd0,write_frames};pack_frames<=0;pack<=0;
                            if(accepted_frames_o==expected_frames)begin
                                if((~crc)!=expected_crc)abort_task(4);
                                else begin crc<=32'hffffffff;cursor<=0;state<=VERIFY_REQ;end
                            end else state<=CAPTURE;
                        end
                    end
                    VERIFY_REQ:if(command_fire)state<=VERIFY_WAIT;
                    VERIFY_WAIT:if(completion_valid && completion_ready)begin
                        if(completion_data[256])abort_task(15);
                        else begin read_beat<=completion_data[255:0];beat_frame<=0;state<=VERIFY_DATA;end
                    end
                    VERIFY_DATA:begin
                        if(!crc_busy)begin crc_word<=verify_word;crc_phase<=0;crc_busy<=1;end
                        else if(crc_phase==3)begin
                            cursor<=cursor+1'b1;
                            if(cursor+1'b1==expected_frames)begin
                                seal_crc_o<=~crc_byte(crc,crc_word[31:24]);
                                if((~crc_byte(crc,crc_word[31:24]))!=expected_crc)abort_task(5);
                                else begin seal_valid_o<=1;cursor<=0;state<=RUN_REQ;end
                            end else if(beat_frame==7)state<=VERIFY_REQ;
                            else beat_frame<=beat_frame+1'b1;
                        end
                    end
                    RUN_REQ:if(command_fire)state<=RUN_WAIT;
                    RUN_WAIT:if(completion_valid && completion_ready)begin
                        if(completion_data[256])abort_task(15);
                        else begin read_beat<=completion_data[255:0];beat_frame<=0;state<=RUN_DATA;end
                    end
                    RUN_DATA:if(cnn_pcm_valid && cnn_ready)begin
                        replayed_frames_o<=replayed_frames_o+1'b1;cursor<=cursor+1'b1;
                        if(cursor+1'b1==expected_frames)state<=ENDING;
                        else if(beat_frame==7)state<=RUN_REQ;
                        else beat_frame<=beat_frame+1'b1;
                    end
                    ENDING:if(cnn_analysis_done)abort_task(0);
                    DRAIN:if(!restart_pending && !stage_inflight)state<=TERMINAL;
                    TERMINAL:if(terminal_ready_i)state<=IDLE;
                    default:state<=IDLE;
                endcase
            end
        end
    end
endmodule
