`timescale 1ns/1ps

// Standalone digital experiment only. It is never a production source profile.
// The DAC's physical SMUTE stays asserted even while internal frames run.
module workstation_audio_probe_top #(
    parameter integer HOLD_REFERENCE_CYCLES=2500000,
    parameter integer SNAPSHOT_REFERENCE_CYCLES=5000,
    parameter integer MONITOR_WINDOW_CYCLES=50000,
    parameter integer MONITOR_STABLE_WINDOWS=4,
    parameter integer SERIAL_STARTUP_FRAMES=1028
) (
    input wire clk_50mhz,clk_12m288,clk_16m9344,restart_n,
    output wire ak_pdn,ak_mclk,ak_bick,ak_lrck,ak_sdata,ak_smute
);
    reg [9:0] power_on_count=0;
    reg power_ready=0;
    always @(posedge clk_50mhz or negedge restart_n)
        if(!restart_n)begin power_on_count<=0;power_ready<=0;end
        else if(!power_ready)begin
            if(&power_on_count)power_ready<=1;
            else power_on_count<=power_on_count+1'b1;
        end
    wire reset_n=restart_n && power_ready;
    wire selected_clk,audio_reset_n,ready,busy,fault,accepted,applied,rejected,failed;
    wire [2:0] reject_code;
    wire [3:0] fault_code,clock_select;
    wire quiesce,mute,flush,active44,active_valid,staged44;
    wire [31:0] epoch,staged_epoch,measured48,measured44,measured_selected;
    wire [1:0] raw_qualified,raw_present;
    wire selected_qualified,selected_low;
    reg request=0,target44=0;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] quiesce_sync,resume_sync;
    always @(posedge selected_clk or negedge audio_reset_n)
        if(!audio_reset_n)begin quiesce_sync<=3;resume_sync<=0;end
        else begin quiesce_sync<={quiesce_sync[0],quiesce};resume_sync<={resume_sync[0],!mute};end
    wire quiet_audio,prefill_audio,running_audio,response_idle;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] quiet_sync,prefill_sync,running_sync,idle_sync;
    always @(posedge clk_50mhz or negedge reset_n)
        if(!reset_n)begin quiet_sync<=0;prefill_sync<=0;running_sync<=0;idle_sync<=0;end
        else if(flush)begin quiet_sync<=0;prefill_sync<=0;running_sync<=0;idle_sync<=0;end
        else begin
            quiet_sync<={quiet_sync[0],quiet_audio};prefill_sync<={prefill_sync[0],prefill_audio};
            running_sync<={running_sync[0],running_audio};idle_sync<={idle_sync[0],response_idle};
        end
    workstation_audio_clock_domain #(
        .WINDOW_CYCLES(MONITOR_WINDOW_CYCLES),.STABLE_WINDOWS(MONITOR_STABLE_WINDOWS)
    ) audio_domain (
        .clk_50m_i(clk_50mhz),.rst_ni(reset_n),.reference_48_i(clk_12m288),.reference_44_i(clk_16m9344),
        .request_i(request),.request_44k1_i(target44),.recover_i(1'b0),
        .frame_quiescent_i(quiet_sync[1] && idle_sync[1]),.prefill_ready_i(prefill_sync[1]),.output_running_i(running_sync[1]),
        .selected_clock_o(selected_clk),.audio_reset_no(audio_reset_n),.request_ready_o(ready),.busy_o(busy),.fault_o(fault),
        .accepted_o(accepted),.applied_o(applied),.rejected_o(rejected),.failed_o(failed),.reject_code_o(reject_code),
        .fault_code_o(fault_code),.clock_select_o(clock_select),.quiesce_o(quiesce),.dac_mute_o(mute),.stream_flush_o(flush),
        .active_44k1_o(active44),.active_valid_o(active_valid),.staged_44k1_o(staged44),.stream_epoch_o(epoch),
        .staged_epoch_o(staged_epoch),.source_qualified_o(raw_qualified),.source_present_o(raw_present),
        .selected_qualified_o(selected_qualified),.selected_stopped_low_o(selected_low),
        .measured_48_o(measured48),.measured_44_o(measured44),.measured_selected_o(measured_selected)
    );
    wire render_request,render_ready,render44;
    wire [31:0] render_epoch,render_sequence;
    reg response_valid,response44;
    reg [31:0] response_epoch,response_sequence;
    // One selected-clock register of latency, zero PCM, no independent render
    // clock or artificial high ACK. This is explicitly not the future DSP bridge.
    always @(posedge selected_clk or negedge audio_reset_n)
        if(!audio_reset_n)begin response_valid<=0;response44<=0;response_epoch<=0;response_sequence<=0;end
        else begin
            response_valid<=render_request && !quiesce_sync[1];
            if(render_request)begin response44<=render44;response_epoch<=render_epoch;response_sequence<=render_sequence;end
        end
    assign response_idle=!response_valid && !render_request;
    wire serializer_mute,frame_valid,frame_error,frame44;
    wire [31:0] frame_pcm,frame_sequence,frame_epoch,underruns,rejections;
    workstation_i2s_serializer #(.STARTUP_MUTE_FRAMES(SERIAL_STARTUP_FRAMES)) serializer (
        .clk_i(selected_clk),.rst_ni(audio_reset_n),.rate_44k1_i(staged44),.epoch_i(staged_epoch),
        .quiesce_i(quiesce_sync[1]),.resume_i(resume_sync[1]),.serial_quiescent_o(quiet_audio),
        .output_running_o(running_audio),.prefill_ready_o(prefill_audio),.request_o(render_request),
        .request_sequence_o(render_sequence),.request_44k1_o(render44),.request_epoch_o(render_epoch),
        .sample_valid_i(response_valid),.sample_ready_o(render_ready),.sample_44k1_i(response44),
        .sample_epoch_i(response_epoch),.sample_sequence_i(response_sequence),.sample_pcm_i(32'd0),
        .mclk_o(ak_mclk),.bck_o(ak_bick),.lrck_o(ak_lrck),.data_o(ak_sdata),.pdn_no(ak_pdn),.smute_o(serializer_mute),
        .frame_valid_o(frame_valid),.frame_error_o(frame_error),.frame_pcm_o(frame_pcm),
        .frame_sequence_o(frame_sequence),.frame_44k1_o(frame44),.frame_epoch_o(frame_epoch),
        .underrun_count_o(underruns),.rejected_sample_count_o(rejections)
    );
    assign ak_smute=1'b1;

    // Atomic bundled snapshot: the selected domain registers and holds all
    // fields before acknowledging. 50MHz synchronizes both payload and ACK,
    // then captures the stable payload; no wide live audio bus reaches GAO.
    reg snapshot_request;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] snapshot_request_sync;
    reg snapshot_ack;
    (* syn_preserve=1 *) reg [191:0] snapshot_hold;
    reg [31:0] serial_count,last_sequence,last_epoch;
    reg last_error,last_mode;
    always @(posedge selected_clk or negedge audio_reset_n)
        if(!audio_reset_n)begin
            snapshot_request_sync<=0;snapshot_ack<=0;snapshot_hold<=0;
            serial_count<=0;last_sequence<=0;last_epoch<=0;last_error<=0;last_mode<=0;
        end else begin
            snapshot_request_sync<={snapshot_request_sync[0],snapshot_request};
            if(frame_valid)begin
                serial_count<=serial_count+1'b1;last_sequence<=frame_sequence;last_epoch<=frame_epoch;
                last_error<=frame_error || frame_pcm!=0;last_mode<=frame44;
            end
            if(snapshot_request_sync[1]!=snapshot_ack)begin
                snapshot_hold<={{24'd0,render_ready,serializer_mute,(serial_count!=0),last_error,last_mode,running_audio,prefill_audio,quiet_audio},
                    rejections,underruns,last_epoch,last_sequence,serial_count};
                snapshot_ack<=snapshot_request_sync[1];
            end
        end
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] snapshot_ack_sync;
    (* syn_preserve=1 *) reg [191:0] snapshot_payload_meta,snapshot_payload_sync;
    reg [191:0] snapshot_value;
    reg snapshot_seen,snapshot_valid;
    reg [31:0] snapshot_timer,snapshots_completed;
    always @(posedge clk_50mhz or negedge reset_n)
        if(!reset_n)begin
            snapshot_request<=0;snapshot_ack_sync<=0;snapshot_payload_meta<=0;snapshot_payload_sync<=0;
            snapshot_seen<=0;snapshot_value<=0;snapshot_valid<=0;snapshot_timer<=0;snapshots_completed<=0;
        end else if(flush)begin
            snapshot_request<=0;snapshot_ack_sync<=0;snapshot_payload_meta<=0;snapshot_payload_sync<=0;
            snapshot_seen<=0;snapshot_value<=0;snapshot_valid<=0;snapshot_timer<=0;
        end else begin
            snapshot_ack_sync<={snapshot_ack_sync[0],snapshot_ack};
            snapshot_payload_meta<=snapshot_hold;snapshot_payload_sync<=snapshot_payload_meta;
            if(snapshot_ack_sync[1]!=snapshot_seen)begin
                snapshot_value<=snapshot_payload_sync;snapshot_seen<=snapshot_ack_sync[1];snapshot_valid<=1;
                snapshots_completed<=snapshots_completed+1'b1;
            end
            if(snapshot_timer==SNAPSHOT_REFERENCE_CYCLES-1)begin
                snapshot_timer<=0;
                if(snapshot_request==snapshot_seen)snapshot_request<=!snapshot_request;
            end else snapshot_timer<=snapshot_timer+1'b1;
        end

    localparam [3:0] WAIT_BOOT=0,HOLD_48=1,SEND_44=2,WAIT_44=3,HOLD_44=4,
        SEND_48=5,WAIT_48=6,HOLD_FINAL=7,COMPLETE=8,ERROR=15;
    reg [3:0] probe_state;
    reg [31:0] hold_timer,heartbeat,completed_cycles,accepted_count,applied_count,rejected_count,failed_count;
    reg [31:0] boot48_frames,rate44_frames,final48_frames,selected48_history,selected44_history;
    always @(posedge clk_50mhz or negedge reset_n)
        if(!reset_n)begin
            boot48_frames<=0;rate44_frames<=0;final48_frames<=0;selected48_history<=0;selected44_history<=0;
        end else begin
            if(ready && active_valid)begin
                if(active44)selected44_history<=measured_selected;
                else selected48_history<=measured_selected;
            end
            if(snapshot_valid && !flush && snapshot_value[165] && !snapshot_value[164])begin
                case(snapshot_value[95:64])
                    0:boot48_frames<=snapshot_value[31:0];
                    1:rate44_frames<=snapshot_value[31:0];
                    2:final48_frames<=snapshot_value[31:0];
                    default:begin end
                endcase
            end
        end
    always @(posedge clk_50mhz or negedge reset_n)
        if(!reset_n)begin
            probe_state<=WAIT_BOOT;hold_timer<=0;request<=0;target44<=0;heartbeat<=0;
            completed_cycles<=0;accepted_count<=0;applied_count<=0;rejected_count<=0;failed_count<=0;
        end else begin
            heartbeat<=heartbeat+1'b1;request<=0;
            if(accepted)accepted_count<=accepted_count+1'b1;
            if(applied)applied_count<=applied_count+1'b1;
            if(rejected)rejected_count<=rejected_count+1'b1;
            if(failed)failed_count<=failed_count+1'b1;
            if(fault || rejected || failed)probe_state<=ERROR;
            else case(probe_state)
                WAIT_BOOT:if(ready && !active44 && epoch==0)begin probe_state<=HOLD_48;hold_timer<=0;end
                HOLD_48,HOLD_44,HOLD_FINAL:begin
                    if(hold_timer==HOLD_REFERENCE_CYCLES-1)begin
                        hold_timer<=0;
                        if(probe_state==HOLD_48)probe_state<=SEND_44;
                        else if(probe_state==HOLD_44)probe_state<=SEND_48;
                        else begin probe_state<=COMPLETE;completed_cycles<=completed_cycles+1'b1;end
                    end else hold_timer<=hold_timer+1'b1;
                end
                SEND_44:if(ready)begin target44<=1;request<=1;probe_state<=WAIT_44;end
                WAIT_44:if(ready && active44 && epoch==1)begin probe_state<=HOLD_44;hold_timer<=0;end
                SEND_48:if(ready)begin target44<=0;request<=1;probe_state<=WAIT_48;end
                WAIT_48:if(ready && !active44 && epoch==2)begin probe_state<=HOLD_FINAL;hold_timer<=0;end
                COMPLETE,ERROR:begin end
                default:probe_state<=ERROR;
            endcase
        end
    wire [31:0] status={4'd0,probe_state,3'd0,(probe_state==ERROR),(probe_state==COMPLETE),snapshot_valid,
        running_sync[1],prefill_sync[1],quiet_sync[1],selected_low,selected_qualified,
        raw_present[1],raw_present[0],raw_qualified[1],raw_qualified[0],audio_reset_n,flush,mute,quiesce,
        active44,active_valid,fault,busy,ready};
    (* syn_keep=1,syn_preserve=1 *) reg [799:0] audio_probe_debug;
    always @(posedge clk_50mhz or negedge reset_n)
        if(!reset_n)audio_probe_debug<=0;
        else audio_probe_debug<={selected44_history,selected48_history,final48_frames,rate44_frames,boot48_frames,
            {16'd0,5'd0,reject_code,fault_code,clock_select},snapshots_completed,
            snapshot_value,failed_count,rejected_count,applied_count,accepted_count,completed_cycles,
            measured_selected,measured44,measured48,epoch,status,heartbeat,32'h41504231};
endmodule
