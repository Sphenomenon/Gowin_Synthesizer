`timescale 1ns/1ps
// Native composition fixture only. The explicit zero renderer below is not
// the workstation DSP; the production audio owner is not duplicated/selected.
module tb_workstation_tf_physical_native #(
    parameter integer RATE=48000,MODE=0,FRAMES0=97,FRAMES1=97,FAST_DIV=2
);
    reg source_clk=0,compute_clk=0,serial_clk=0,rst=0;
    always #10 source_clk=!source_clk;
    realtime compute_next=1.7,serial_next=3.1;
    localparam real COMPUTE_HALF=1000000000.0/153600000.0;
    localparam real SERIAL_HALF=RATE==48000 ? 1000000000.0/24576000.0:1000000000.0/33868800.0;
    initial forever begin compute_next=compute_next+COMPUTE_HALF;#(compute_next-$realtime);compute_clk=!compute_clk;end
    initial forever begin serial_next=serial_next+SERIAL_HALF;#(serial_next-$realtime);serial_clk=!serial_clk;end
    reg request=0,stop=0,pause=0,observation_ready=1;
    reg [3:0] track=0;
    reg [31:0] command_generation=32'hffffffff;
    wire request_ready,applied,native_cancelled,native_stop_completed,native_stop_failed;
    wire ssn,sck,mosi,miso,scan,file_error,native_failed,native_valid,native_last,native_active,native_drained,sector_busy;
    wire [3:0] file_code,native_code;
    wire [15:0] native_left,native_right;
    wire [19:0] native_rate;
    wire [31:0] native_generation,byte_level,pcm_level,byte_high,pcm_high;
    wire [4:0] tracks;
    wire source_ready,source_quiet,media_quiet,generation_pending,tf_valid,tf_error,tf_last,generation_valid,generation_change,tf_ready;
    wire [15:0] tf_left,tf_right;
    wire [19:0] tf_rate;
    wire [31:0] tf_generation,tf_session,expected_generation,source_generation;
    reg source_stop_q=0,applied_toggle=0;
    wire invalidate=applied || (stop && !source_stop_q);
    always @(posedge source_clk or negedge rst)
        if(!rst)begin source_stop_q<=0;applied_toggle<=0;end
        else begin source_stop_q<=stop;if(applied)applied_toggle<=!applied_toggle;end
    workstation_tf_direct_native_v1 #(.SPI_CLK_DIV(2),.SPI_CLK_DIV_FAST(FAST_DIV),
        .TOKEN_WAIT_CLOCKS(1000),.WATCHDOG_CLOCKS(500000)) native(
        .clk_i(source_clk),.rst_ni(rst),.spi_ssn_o(ssn),.spi_sck_o(sck),.spi_mosi_o(mosi),.spi_miso_i(miso),
        .request_valid_i(request),.request_ready_o(request_ready),.track_index_i(track),.generation_i(command_generation),
        .expected_rate_i(20'(RATE)),.stop_i(stop),.pause_i(pause),
        // Producer-only path here. ACTUAL serial/router requests own deadlines.
        .sample_request_i(1'b0),.request_applied_o(applied),.cancelled_o(native_cancelled),
        .stop_completed_o(native_stop_completed),.stop_failed_o(native_stop_failed),
        .pcm_valid_o(native_valid),.pcm_ready_i(source_ready),.pcm_left_o(native_left),.pcm_right_o(native_right),
        .pcm_last_o(native_last),.generation_o(native_generation),.session_rate_o(native_rate),.active_o(native_active),
        .local_tail_drained_o(native_drained),.ingress_failed_o(native_failed),.ingress_failure_code_o(native_code),
        .file_error_o(file_error),.file_error_code_o(file_code),.scan_done_o(scan),.sector_busy_o(sector_busy),
        .track_count_o(tracks),.name_raddr_i(8'd0),.byte_level_o(byte_level),.pcm_level_o(pcm_level),
        .byte_high_water_o(byte_high),.pcm_high_water_o(pcm_high));
    workstation_tf_frame_bridge_v2 #(.FIFO_ADDRESS_BITS(2),.INITIAL_GENERATION(32'hfffffffd)) transport(
        .rst_ni(rst),.source_clk_i(source_clk),.compute_clk_i(compute_clk),.invalidate_i(invalidate),.source_quiesce_i(stop),
        .source_valid_i(native_valid),.source_error_i(1'b0),.source_last_i(native_last),.source_session_generation_i(native_generation),
        .source_sample_rate_i(native_rate),.source_left_i(native_left),.source_right_i(native_right),.source_ready_o(source_ready),
        .source_generation_o(source_generation),.source_generation_pending_o(generation_pending),.source_quiescent_o(source_quiet),
        .tf_valid_o(tf_valid),.tf_ready_i(tf_ready),.tf_error_o(tf_error),.tf_last_o(tf_last),.tf_session_generation_o(tf_session),
        .tf_sample_rate_o(tf_rate),.tf_left_o(tf_left),.tf_right_o(tf_right),.tf_generation_o(tf_generation),
        .expected_generation_o(expected_generation),.expected_generation_valid_o(generation_valid),.generation_change_o(generation_change),
        .media_quiescent_o(media_quiet));
    wire integer commands,payload_bytes,crc_bytes,post_crc_bytes,cs_releases,high_clocks;
    workstation_tf_file_wire_card card(.ssn(ssn),.sck(sck),.mosi(mosi),.miso(miso),.token_delay_bytes(2),
        .hold_init(1'b0),.fault_lba(32'hffffffff),.fault_kind(0),.suppress_token(1'b0),.command_error(1'b0),.suppress_r1(1'b0),
        .cmd17_count(commands),.payload_bytes(payload_bytes),.crc_bytes(crc_bytes),.post_crc_bytes(post_crc_bytes),
        .cs_releases(cs_releases),.high_clocks(high_clocks));
    (* ASYNC_REG="TRUE" *) reg [1:0] stop_sync=0,pause_sync=0,applied_sync=0;
    reg applied_seen=0,arm_needed=0,previous_stop=0;
    wire arm_ready,armed,tail_pending,tail_closed,tail_admit,tail_quiet,physical_eos,tail_cancelled,tail_failed,mailbox_busy;
    wire [3:0] tail_failure;
    wire [31:0] tail_epoch,tail_sequence,baseline_drops,tail_drops;
    wire arm_valid=arm_needed && tf_valid && generation_valid && !stop_sync[1];
    wire tail_fence=generation_change || (stop_sync[1] && !previous_stop);
    always @(posedge compute_clk or negedge rst)
        if(!rst)begin stop_sync<=0;pause_sync<=0;applied_sync<=0;applied_seen<=0;arm_needed<=0;previous_stop<=0;end
        else begin
            stop_sync<={stop_sync[0],stop};pause_sync<={pause_sync[0],pause};applied_sync<={applied_sync[0],applied_toggle};
            previous_stop<=stop_sync[1];
            if(applied_sync[1]!=applied_seen)begin applied_seen<=applied_sync[1];arm_needed<=1;end
            if(arm_valid && arm_ready)arm_needed<=0;
            if(stop_sync[1])arm_needed<=0;
        end
    reg [4:0] serial_guard=0;
    wire serial_reset=rst && serial_guard==20;
    (* ASYNC_REG="TRUE" *) reg [1:0] serial_quiesce=3;
    always @(posedge serial_clk or negedge rst)
        if(!rst)begin serial_guard<=0;serial_quiesce<=3;end
        else begin if(serial_guard<20)serial_guard<=serial_guard+1'b1;serial_quiesce<={serial_quiesce[0],stop};end
    wire serial_request,serial_request_rate,sample_valid,sample_ready,sample_rate,sample_error,serial_quiet;
    wire [31:0] serial_request_epoch,serial_request_sequence,sample_epoch,sample_sequence,sample_pcm;
    wire bridge_request,bridge_rate,router_ready,router_done,router_error,router_source_tf,router_rate,router_quiet,bridge_quiet;
    wire [31:0] bridge_epoch,bridge_sequence,router_epoch,router_sequence,router_pcm;
    wire [15:0] router_gain;
    wire [7:0] router_error_bits;
    wire [31:0] request_drops,return_discards,unexpected_renders,request_drops_compute,return_discards_compute;
    wire tf_selected=tail_admit && !pause_sync[1] && !stop_sync[1] && !tail_failed;
    wire router_tf_ready;
    assign tf_ready=router_tf_ready && tf_selected;
    wire tf_fire=tf_valid && tf_ready;
    wire render_request;
    reg silence_done=0;
    // Explicit non-consuming silence render for prefill, pause and post-tail.
    // This does NOT claim the full synth/effect service is in this fixture.
    always @(posedge compute_clk or negedge rst)if(!rst)silence_done<=0;else silence_done<=render_request;
    workstation_final_pcm_router router(.clk_i(compute_clk),.rst_ni(rst),.request_i(bridge_request),.request_44k1_i(bridge_rate),
        .request_epoch_i(bridge_epoch),.request_sequence_i(bridge_sequence),.request_ready_o(router_ready),
        .active_44k1_i(1'(RATE==44100)),.active_epoch_i(32'hffffffff),.cancel_epoch_i(expected_generation),
        .scope_enable_i(1'b0),.tf_active_i(tf_selected),.master_volume_i(16'h8000),.mute_i(1'b0),
        .tf_valid_i(tf_valid),.tf_error_i(tf_error),.tf_left_i(tf_left),.tf_right_i(tf_right),.tf_sample_rate_i(tf_rate),
        .tf_generation_i(tf_generation),.expected_tf_generation_i(expected_generation),.tf_ready_o(router_tf_ready),
        .render_ready_i(1'b1),.render_done_i(silence_done),.render_error_i(1'b0),.render_left_i(32'sd0),.render_right_i(32'sd0),
        .render_request_o(render_request),.frame_valid_o(router_done),.frame_error_o(router_error),.frame_44k1_o(router_rate),
        .frame_source_tf_o(router_source_tf),.frame_epoch_o(router_epoch),.frame_sequence_o(router_sequence),
        .frame_pcm_o(router_pcm),.frame_error_bits_o(router_error_bits),.frame_gain_o(router_gain),.quiescent_o(router_quiet));
    wire drop_return=MODE==8 && tail_pending && sample_sequence==tail_sequence;
    workstation_pcm_frame_bridge pcm_bridge(.reset_ni(rst),.serial_clk_i(serial_clk),.compute_clk_i(compute_clk),
        .serial_reset_ni(serial_reset),.serial_quiet_i(serial_quiet),.quiesce_i(stop),
        .request_i(serial_request),.request_44k1_i(serial_request_rate),.request_epoch_i(serial_request_epoch),
        .request_sequence_i(serial_request_sequence),.request_ready_o(),.sample_valid_o(sample_valid),
        .sample_ready_i(sample_ready && !drop_return),.sample_44k1_o(sample_rate),.sample_error_o(sample_error),
        .sample_epoch_o(sample_epoch),.sample_sequence_o(sample_sequence),.sample_pcm_o(sample_pcm),
        .render_ready_i(router_ready),.render_done_i(router_done),.rendered_pcm_i(router_pcm),.rendered_error_i(router_error),
        .render_request_o(bridge_request),.render_44k1_o(bridge_rate),.render_epoch_o(bridge_epoch),.render_sequence_o(bridge_sequence),
        .quiescent_o(bridge_quiet),.request_drop_count_o(request_drops),.return_discard_count_o(return_discards),
        .unexpected_render_count_o(unexpected_renders));
    wire mclk,bck,lrck,data,pdn,smute,physical_valid,physical_error,physical_rate;
    wire [31:0] physical_epoch,physical_sequence,physical_pcm,underruns,source_errors,rejected_samples;
    workstation_i2s_serializer #(.PDN_HOLD_FRAMES(1),.STARTUP_MUTE_FRAMES(5),.SAMPLE_ERROR_ENABLE(1)) serializer(
        .clk_i(serial_clk),.rst_ni(serial_reset),.rate_44k1_i(1'(RATE==44100)),.epoch_i(32'hffffffff),
        .quiesce_i(serial_quiesce[1]),.resume_i(1'b1),.serial_quiescent_o(serial_quiet),
        .request_o(serial_request),.request_sequence_o(serial_request_sequence),.request_44k1_o(serial_request_rate),
        .request_epoch_o(serial_request_epoch),.sample_valid_i(sample_valid && !drop_return),.sample_ready_o(sample_ready),
        .sample_44k1_i(sample_rate),.sample_error_i(sample_error),.sample_epoch_i(sample_epoch),.sample_sequence_i(sample_sequence),
        .sample_pcm_i(sample_pcm),.mclk_o(mclk),.bck_o(bck),.lrck_o(lrck),.data_o(data),.pdn_no(pdn),.smute_o(smute),
        .frame_valid_o(physical_valid),.frame_error_o(physical_error),.frame_pcm_o(physical_pcm),.frame_sequence_o(physical_sequence),
        .frame_44k1_o(physical_rate),.frame_epoch_o(physical_epoch),.underrun_count_o(underruns),
        .source_error_count_o(source_errors),.rejected_sample_count_o(rejected_samples));
    wire observed_valid,observed_error,observed_rate,observed_gap,drop_event;
    wire [31:0] observed_epoch,observed_sequence,observed_pcm,source_observation_drops,destination_observation_drops;
    workstation_pcm_observation_bridge #(.FIFO_ADDRESS_BITS(2)) observation(.reset_ni(rst),.source_clk_i(serial_clk),
        .destination_clk_i(compute_clk),.frame_valid_i(physical_valid),.frame_44k1_i(physical_rate),.frame_error_i(physical_error),
        .frame_epoch_i(physical_epoch),.frame_sequence_i(physical_sequence),.frame_pcm_i(physical_pcm),
        .source_drop_count_o(source_observation_drops),.destination_drop_count_o(destination_observation_drops),
        .destination_drop_event_o(drop_event),.frame_valid_o(observed_valid),.frame_ready_i(observation_ready),
        .frame_44k1_o(observed_rate),.frame_error_o(observed_error),.frame_epoch_o(observed_epoch),
        .frame_sequence_o(observed_sequence),.frame_pcm_o(observed_pcm),.sequence_gap_o(observed_gap));
    gw138k_counter_cdc request_drop_crossing(.reset_n(rst),.source_clk(serial_clk),.destination_clk(compute_clk),
        .source_count(request_drops),.destination_count(request_drops_compute));
    gw138k_counter_cdc return_discard_crossing(.reset_n(rst),.source_clk(serial_clk),.destination_clk(compute_clk),
        .source_count(return_discards),.destination_count(return_discards_compute));
    reg [31:0] previous_request_drops=0,previous_return_discards=0,previous_unexpected=0;
    wire transport_fault=request_drops_compute!=previous_request_drops || return_discards_compute!=previous_return_discards ||
        unexpected_renders!=previous_unexpected;
    always @(posedge compute_clk or negedge rst)
        if(!rst)begin previous_request_drops<=0;previous_return_discards<=0;previous_unexpected<=0;end
        else begin previous_request_drops<=request_drops_compute;previous_return_discards<=return_discards_compute;previous_unexpected<=unexpected_renders;end
    workstation_tf_physical_tail_v1 tail(.rst_ni(rst),.compute_clk_i(compute_clk),.serial_clk_i(serial_clk),.fence_i(tail_fence),
        .arm_valid_i(arm_valid),.arm_ready_o(arm_ready),.arm_44k1_i(1'(RATE==44100)),.arm_generation_i(tf_generation),
        .arm_session_i(tf_session),.arm_epoch_i(32'hffffffff),.armed_o(armed),.tail_pending_o(tail_pending),.tail_closed_o(tail_closed),
        .tf_admit_o(tail_admit),.quiescent_o(tail_quiet),.tf_fire_i(tf_fire),.tf_last_i(tf_last),.tf_error_i(tf_error),
        .tf_44k1_i(1'(tf_rate==44100)),.tf_generation_i(tf_generation),.tf_session_i(tf_session),
        .render_epoch_i(bridge_epoch),.render_sequence_i(bridge_sequence),.router_valid_i(router_done),.router_error_i(router_error),
        .router_source_tf_i(router_source_tf),.router_44k1_i(router_rate),.router_epoch_i(router_epoch),.router_sequence_i(router_sequence),
        .transport_fault_i(transport_fault),.observation_valid_i(observed_valid && observation_ready),.observation_error_i(observed_error),
        // MODE7 isolates the source-prefix proof by losing only the two
        // destination notices; the actual observation FIFO/counter still drop.
        .observation_44k1_i(observed_rate),.observation_gap_i(MODE==7 ? 1'b0:observed_gap),
        .observation_drop_event_i(MODE==7 ? 1'b0:drop_event),
        .observation_epoch_i(observed_epoch),.observation_sequence_i(observed_sequence),.physical_valid_i(physical_valid),
        .physical_error_i(physical_error),.physical_44k1_i(physical_rate),.physical_epoch_i(physical_epoch),.physical_sequence_i(physical_sequence),
        .observation_source_drops_i(source_observation_drops),.physical_eos_o(physical_eos),.tail_cancelled_o(tail_cancelled),
        .failed_o(tail_failed),.failure_code_o(tail_failure),.tail_epoch_o(tail_epoch),.tail_sequence_o(tail_sequence),
        .baseline_drops_o(baseline_drops),.tail_drops_o(tail_drops),.mailbox_busy_o(mailbox_busy));

    reg [31:0] oracle0[0:12000],oracle1[0:12000];
    reg [2047:0] path0,path1;
    reg [31:0] expected_pcm[0:19999];
    reg [31:0] expected_cancel[0:19999];
    reg expected_error[0:19999],expected_tf[0:19999];
    integer source_cycles=0,render_requests=0,physical_frames=0,physical_tf_frames=0,delivered0=0,delivered1=0;
    integer eos_count=0,cancel_count=0,checks=0,byte_peak=0,pcm_peak=0,raw_cancels=0,stop_completions=0,arm_accepts=0,desired_arm=0;
    integer serial_position=0;
    integer bck_checks=0,frame_period_checks=0,physical_deadlines=0;
    realtime previous_bck_edge=0,previous_frame_edge=0;
    reg [31:0] decoded=0,last_decoded=0;
    reg [31:0] gold;
    always @(posedge source_clk)if(rst)begin
        source_cycles=source_cycles+1;
        if(source_cycles>30000000)$fatal(1,"native physical watchdog mode=%0d d0=%0d d1=%0d eos=%0d fail=%0d",MODE,delivered0,delivered1,eos_count,tail_failure);
        if(native_cancelled)raw_cancels=raw_cancels+1;if(native_stop_completed)stop_completions=stop_completions+1;
        if(byte_high>byte_peak)byte_peak=byte_high;if(pcm_high>pcm_peak)pcm_peak=pcm_high;
        if(file_error || native_failed)$fatal(1,"unexpected producer failure file=%0d native=%0d",file_code,native_code);
    end
    always @(posedge compute_clk)if(rst)begin
        if(arm_valid && arm_ready)arm_accepts=arm_accepts+1;
        if(bridge_request && router_ready)begin
            if(bridge_sequence>=20000)$fatal(1,"fixture expected queue capacity");
            render_requests=render_requests+1;expected_pcm[bridge_sequence]=0;expected_error[bridge_sequence]=0;expected_tf[bridge_sequence]=0;
            expected_cancel[bridge_sequence]=expected_generation;
            if(tf_selected)begin
                if(!tf_valid || tf_error)expected_error[bridge_sequence]=1;
                else begin
                    if(tf_session==32'hffffffff)begin gold=oracle0[delivered0];delivered0=delivered0+1;end
                    else if(tf_session==0)begin gold=oracle1[delivered1];delivered1=delivered1+1;end
                    else $fatal(1,"unexpected TF command identity");
                    if({tf_right,tf_left}!==gold)$fatal(1,"actual wire-to-router PCM oracle mismatch");
                    if(tf_last!==((tf_session==32'hffffffff ? delivered0:delivered1)==(tf_session==32'hffffffff ? FRAMES0:FRAMES1)))$fatal(1,"atomic real LAST mismatch");
                    expected_pcm[bridge_sequence]={gold[15:0],gold[31:16]};expected_tf[bridge_sequence]=1;
                    if(MODE==8 && tf_last)begin expected_pcm[bridge_sequence]=0;expected_error[bridge_sequence]=1;end
                end
            end
        end
        // Cancellation is an explicit zero/error completion of the pending
        // router slot. Predict it from the independently captured request
        // context, rather than copying the router's PCM/error outputs.
        if(router_done && expected_cancel[router_sequence]!=expected_generation)begin
            expected_pcm[router_sequence]=0;expected_error[router_sequence]=1;expected_tf[router_sequence]=0;
        end
        if(router_done && router_source_tf && !router_error && router_gain!==16'h8000)$fatal(1,"fixture did not finish master-gain warmup");
        if(physical_eos)begin
            if(tail_failed || stop_sync[1] || !native_drained || baseline_drops!=tail_drops || tail_drops==32'hffffffff)
                $fatal(1,"false physical EOF success");
            eos_count=eos_count+1;
        end
        if(tail_cancelled)cancel_count=cancel_count+1;
    end
    always @(posedge bck)begin
        #0.1;
        if(serial_reset)begin
            if(lrck!==(serial_position>=32))$fatal(1,"physical LRCK slot mismatch");
            if(serial_position>=1 && serial_position<=16)decoded[32-serial_position]=data;
            else if(serial_position>=33 && serial_position<=48)decoded[48-serial_position]=data;
            else if(data!==0)$fatal(1,"physical nonzero I2S delay/padding");
            if(serial_position==63)begin last_decoded=decoded;decoded=0;serial_position=0;end
            else serial_position=serial_position+1;
        end
    end
    always @(bck)if(serial_reset)begin
        if(previous_bck_edge!=0 && (($realtime-previous_bck_edge)<(RATE==48000 ? 4.0:6.0)*SERIAL_HALF-0.003 ||
            ($realtime-previous_bck_edge)>(RATE==48000 ? 4.0:6.0)*SERIAL_HALF+0.003))$fatal(1,"real BCK cadence mismatch");
        previous_bck_edge=$realtime;bck_checks=bck_checks+1;
    end
    always @(posedge lrck)if(serial_reset)begin
        if(previous_frame_edge!=0 && (($realtime-previous_frame_edge)<(RATE==48000 ? 512.0:768.0)*SERIAL_HALF-0.003 ||
            ($realtime-previous_frame_edge)>(RATE==48000 ? 512.0:768.0)*SERIAL_HALF+0.003))$fatal(1,"real LRCK cadence mismatch");
        previous_frame_edge=$realtime;frame_period_checks=frame_period_checks+1;
    end
    always @(posedge serial_clk)begin
        if(serial_reset && serial_request)physical_deadlines=physical_deadlines+1;
        #0.2;
        if(serial_reset && physical_valid)begin
            if(physical_rate!==(RATE==44100) || physical_epoch!==32'hffffffff || physical_sequence>=20000)
                $fatal(1,"physical completed identity mismatch");
            if(physical_pcm!==last_decoded)$fatal(1,"real pins differ from completed frame");
            if(physical_pcm!==expected_pcm[physical_sequence] || physical_error!==expected_error[physical_sequence])
                $fatal(1,"physical PCM/error oracle seq=%0d got=%08x err=%b expected=%08x err=%b",physical_sequence,physical_pcm,physical_error,expected_pcm[physical_sequence],expected_error[physical_sequence]);
            physical_frames=physical_frames+1;if(expected_tf[physical_sequence])physical_tf_frames=physical_tf_frames+1;
        end
    end
    task clocks(input integer n);repeat(n)@(negedge source_clk);endtask
    task check(input bit ok,input string why);begin checks=checks+1;if(!ok)$fatal(1,"%s",why);end endtask
    task request_track(input integer index,input [31:0] identity);
        begin desired_arm=arm_accepts+1;@(negedge source_clk);while(!request_ready)@(negedge source_clk);track=4'(index);command_generation=identity;request=1;clocks(1);request=0;end
    endtask
    task complete_track(input integer target);
        begin wait(arm_accepts>=desired_arm);clocks(2);wait(eos_count==target || tail_failed);clocks(3);check(!tail_failed && eos_count==target,"physical tail did not complete");end
    endtask
    integer before_eos,before_frames,before_raw,before_stop;
    reg [117:0] pause_head;
    initial begin
        if(!$value$plusargs("ORACLE0=%s",path0) || !$value$plusargs("ORACLE1=%s",path1))$fatal(1,"missing real PCM oracle");
        $readmemh(path0,oracle0,0,FRAMES0-1);$readmemh(path1,oracle1,0,FRAMES1-1);
        for(integer n=0;n<20000;n=n+1)begin expected_pcm[n]=0;expected_cancel[n]=0;expected_error[n]=0;expected_tf[n]=0;end
        clocks(10);rst=1;wait(scan);check(tracks==2,"real SPI mount failed");
        wait(physical_frames>=140);request_track(0,32'hffffffff);
        if(MODE==0 || MODE==1)begin
            if(MODE==1)begin
                wait(delivered0>=5);@(negedge source_clk);pause=1;wait(pause_sync[1]);@(negedge compute_clk);
                pause_head={tf_generation,tf_session,tf_rate,tf_error,tf_last,tf_left,tf_right};before_stop=delivered0;before_frames=physical_frames;
                wait(physical_frames>=before_frames+200);@(negedge compute_clk);
                check(tf_valid && {tf_generation,tf_session,tf_rate,tf_error,tf_last,tf_left,tf_right}===pause_head &&
                    delivered0==before_stop && !tail_failed,"physical pause consumed/changed next TF head or stopped cadence");
                @(negedge source_clk);pause=0;
            end
            complete_track(1);request_track(1,0);complete_track(2);
        end
        else if(MODE==8)begin
            wait(tail_failed);clocks(2);check(eos_count==0 && underruns>0,"missing real return did not fail physical tail");
        end else begin
            if(MODE==2)wait(native_drained && !tail_pending);
            else if(MODE==3)wait(tail_pending);
            else if(MODE==4)wait(router_done && router_source_tf && router_sequence==tail_sequence && tail_pending);
            else if(MODE==5)begin wait(tail_pending);wait(physical_valid && physical_sequence+1==tail_sequence);wait(serial_position==8);end
            else if(MODE==7)begin
                wait(delivered0>=10);observation_ready=0;before_frames=physical_frames;wait(physical_frames>=before_frames+6);observation_ready=1;
                wait(tail_failed || eos_count>0);check(tail_failed && tail_failure==6 && eos_count==0 && source_observation_drops>0,
                    "actual source-drop prefix failed to revoke physical EOF");
            end else if(MODE==9)begin
                wait(tail_failed || eos_count>0);check(tail_failed && eos_count==0 && delivered0<FRAMES0 && !native_failed,
                    "actual router supply deadline failed to terminate FAST12 stream");
            end
            else $fatal(1,"unimplemented physical mode");
            before_eos=eos_count;before_raw=raw_cancels;before_stop=stop_completions;
            @(negedge source_clk);stop=1;
            wait(raw_cancels>before_raw);wait(source_quiet && media_quiet && tail_quiet && bridge_quiet && serial_quiet);
            clocks(20);check(eos_count==before_eos && !sector_busy && ssn && stop_completions==before_stop+1,"cancelled physical tail or false quiet");
            stop=0;clocks(100);request_track(1,0);complete_track(before_eos+1);
        end
        clocks(100);check(commands>0 && payload_bytes>0 && crc_bytes>0 && physical_tf_frames>0 && bck_checks>1000 && frame_period_checks>100,"real chain not exercised");
        $display("PASS tf_physical_native mode=%0d rate=%0d commands=%0d PCM0=%0d PCM1=%0d physical_frames=%0d physical_TF=%0d requests=%0d EOS=%0d checks=%0d raw_cancels=%0d tail_cancels=%0d byte_peak=%0d pcm_peak=%0d underruns=%0d drops=%0d physical_deadlines=%0d BCK_checks=%0d LRCK_checks=%0d",MODE,RATE,commands,delivered0,delivered1,physical_frames,physical_tf_frames,render_requests,eos_count,checks,raw_cancels,cancel_count,byte_peak,pcm_peak,underruns,source_observation_drops,physical_deadlines,bck_checks,frame_period_checks);
        $finish;
    end
endmodule
