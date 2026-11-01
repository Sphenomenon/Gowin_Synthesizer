`timescale 1ns/1ps
module tb_push_rate_control;
    localparam integer RELEASE_QUIET=8;
    reg clk=0,aclk=0,audio_run=1,rn=0,arn=0;
    always #10 clk=~clk;
    always #6.5 if(audio_run)aclk=~aclk;
    reg sel=0,wr=0;reg[7:0]addr=0;reg[31:0]wd=0;
    reg consume=1,source_gate=1;
    wire usb_ready,rate_pulse,source_reject,service_ready,service_reject;
    wire[31:0]generation;reg[31:0]source_tag=0,manual_tag=0;
    reg manual=0,manual_pulse=0;
    reg cv=0,cw=1;reg[11:0]ca=12'h008;reg[31:0]cd=0;reg[3:0]cs=15;
    wire cr,re;wire[31:0]rd;
    reg permit=1,dsp_fault=0,inject_fault=0,inject_busy=0,frame_quiet=1;
    reg[1:0]qualified=3;
    wire request,target,recover,core_ready,core_busy,core_fault,accepted,applied,rejected,failed;
    wire active_rate,active_valid;wire[31:0]epoch;wire[2:0]reject_code;wire[3:0]fault_code;
    wire service_busy,service_fault;
    push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0),.MEDIA_CONTROLS_ENABLE(0),.PUSH_RATE_CONTROL_ENABLE(1),.RATE_RELEASE_QUIET_CYCLES(RELEASE_QUIET)) usb(
        .clk,.reset_n(rn),.audio_clk(aclk),.audio_reset_n(arn),.feedback_clk(clk),.feedback_reset_n(rn),
        .performance_words(448'd0),.display_meta_data(64'd0),.display_meta_valid(1'b0),
        .service_state_data(34'd0),.service_state_valid(1'b0),.score_valid(1'b0),.analysis_done(1'b0),
        .score_ready(),.score_note(7'd0),.playlist_valid(1'b0),.playlist_ready(),.playlist_word(16'd0),
        .track_launch(),.track_index(),.select(sel),.write(wr),.address(addr),.wdata(wd),
        .ready(usb_ready),.rdata(),.audio_valid(),.audio_ready(consume),.audio_event(),.telemetry(),
        .rate_control_ready_i(service_ready && source_gate),.rate_toggle_o(rate_pulse),.rate_rejected_o(source_reject));
    workstation_sample_rate_switch #(.TIMEOUT_CYCLES(256),.RESERVE_ZERO_EPOCH(1),.INITIAL_STREAM_EPOCH(1)) core(
        .clk_i(clk),.rst_ni(rn),.request_i(request),.request_44k1_i(target),.recover_i(recover),
        .source_qualified_i(qualified),.frame_quiescent_i(frame_quiet),
        .selected_clock_stopped_low_i(1'b1),.selected_clock_qualified_i(1'b1),.prefill_ready_i(1'b1),.output_running_i(1'b1),
        .request_ready_o(core_ready),.busy_o(core_busy),.fault_o(core_fault),.accepted_o(accepted),.applied_o(applied),
        .rejected_o(rejected),.failed_o(failed),.reject_code_o(reject_code),.fault_code_o(fault_code),
        .quiesce_o(),.dac_mute_o(),.stream_flush_o(),.audio_reset_no(),.clock_monitor_restart_o(),.clock_select_o(),
        .active_44k1_o(active_rate),.active_valid_o(active_valid),.stream_epoch_o(epoch),.staged_44k1_o(),.staged_epoch_o());
    workstation_audio_clock_service #(.ENABLE_PUSH_RATE_CONTROL(1),.ACCEPT_TIMEOUT_CYCLES(16),
        .RESULT_TIMEOUT_CYCLES(512),.RESERVE_ZERO_EPOCH(1)) service(
        .clk_i(clk),.reset_ni(rn),.command_valid_i(cv),.command_write_i(cw),.command_address_i(ca),
        .command_data_i(cd),.command_strobes_i(cs),.command_ready_o(cr),.response_data_o(rd),.response_error_o(re),
        .push_toggle_i(manual ? manual_pulse : rate_pulse),.push_generation_i(manual ? manual_tag : source_tag),
        .push_ready_o(service_ready),.push_generation_o(generation),.push_rejected_o(service_reject),
        .service_busy_o(service_busy),.service_fault_o(service_fault),.switch_permit_i(permit),
        .core_request_ready_i(core_ready),.core_busy_i(core_busy || inject_busy),.core_fault_i(core_fault || inject_fault),
        .core_dsp_fault_i(dsp_fault),.core_accepted_i(accepted),.core_applied_i(applied),.core_rejected_i(rejected),
        .core_policy_rejected_i(1'b0),.core_failed_i(failed),.core_reject_code_i(reject_code),.core_fault_code_i(fault_code),
        .core_active_44k1_i(active_rate),.core_active_valid_i(active_valid),.core_stream_epoch_i(epoch),
        .core_source_qualified_i(qualified),.request_o(request),.request_44k1_o(target),.recover_o(recover),
        .media_stop_request_o(),.media_stop_hold_o(),.media_stop_ready_i(1'b1),.media_stop_done_i(1'b0),
        .media_stop_failed_i(1'b0),.media_stop_failure_code_i(4'd0));
    integer usb_pulses=0,usb_rejects=0,service_rejects=0,requests=0,applies=0,fifo_writes=0,tests=0;
    wire raw_rate_selected=sel && wr && addr==4 && wd[15:0]==16'hb00b && wd[23:16]==51;
    always @(posedge clk)begin
        if(rn)begin
            if(rate_pulse)usb_pulses++;
            if(source_reject)usb_rejects++;
            if(service_reject)service_rejects++;
            if(request)requests++;
            if(applied)applies++;
            if(recover)$fatal(1,"Push introduced fault recovery semantics");
            if(raw_rate_selected && (usb.midi.usb_valid || usb.events.w_en))
                $fatal(1,"CC51 entered normal decoder/audio FIFO");
            if(usb.events.w_en)fifo_writes++;
            if(raw_rate_selected && usb_ready)source_tag<=generation;
        end
    end
    task tick(input integer n);repeat(n)@(negedge clk);endtask
    task put(input[7:0]a,input[31:0]d);
        integer n;
        begin
            @(negedge clk);sel=1;wr=1;addr=a;wd=d;n=0;
            do begin @(posedge clk);n++;if(n>8)$fatal(1,"MMIO rate/connection store blocked by audio addr=%h",a);end while(!usb_ready);
            @(negedge clk);sel=0;wr=0;
        end
    endtask
    task cc(input[6:0]n,input[6:0]v);put(4,{1'b0,v,1'b0,n,16'hb00b});endtask
    task release_rate;begin cc(51,0);tick(RELEASE_QUIET+1);end endtask
    task ready_wait;
        integer n;
        begin n=0;while(!service_ready)begin tick(1);n++;if(n>100)$fatal(1,"service never ready phase=%d core=%d",service.phase,core.state);end end
    endtask
    task reset_all;
        begin
            @(negedge clk);rn=0;arn=0;sel=0;wr=0;cv=0;manual=0;manual_pulse=0;
            permit=1;dsp_fault=0;inject_fault=0;inject_busy=0;qualified=3;source_gate=1;frame_quiet=1;
            consume=1;audio_run=1;tick(5);rn=1;ready_wait();put(0,1);tick(2);
        end
    endtask
    task applied_rate(input bit rate,input integer expected_requests);
        begin
            tick(2);ready_wait();tick(3);
            if(active_rate!==rate || !active_valid || requests!=expected_requests || service.result_code!=1)
                $fatal(1,"rate transaction mismatch actual=%b want=%b requests=%0d expected=%0d result=%d",active_rate,rate,requests,expected_requests,service.result_code);
        end
    endtask
    task delayed(input[31:0]tag);
        begin @(negedge clk);manual=1;manual_tag=tag;manual_pulse=1;@(negedge clk);manual_pulse=0;tick(2);manual=0;end
    endtask
    integer p0,r0,s0,q0,w0,fill,n;reg[31:0]g0;reg full_seen;
    initial begin
        reset_all();p0=usb_pulses;q0=requests;
        // Real raw MMIO ingress remains live before any audio reset release,
        // feedback warmup, queue release, or ordinary decoder admission.
        audio_run=0;cc(51,127);applied_rate(1,q0+1);
        if(usb_pulses!=p0+1 || arn || usb.queue_write_ready || usb.push_warmup==0)$fatal(1,"stopped audio bypass witness missing");
        cc(51,127);cc(51,1);tick(5);if(usb_pulses!=p0+1)$fatal(1,"held press repeated");
        // A release shorter than the configured quiet interval is consumed
        // and rejected. Expiry while held must not queue another request.
        cc(51,0);r0=usb_rejects;cc(51,127);tick(2);
        if(usb_rejects!=r0+1 || requests!=q0+1)$fatal(1,"short release/repress escaped debounce");
        tick(RELEASE_QUIET+4);cc(51,127);tick(3);
        if(requests!=q0+1)$fatal(1,"bounce replayed after quiet expiry");tests++;
        release_rate();cc(51,127);applied_rate(0,q0+2);tests++;
        // A physically denied press is consumed and remains held after ready
        // returns; neither service nor FIFO may replay it.
        release_rate();source_gate=0;r0=usb_rejects;cc(51,127);tick(3);
        if(usb_rejects!=r0+1)$fatal(1,"source denial not reported");source_gate=1;
        cc(51,127);tick(12);if(requests!=q0+2)$fatal(1,"denied press replayed");tests++;
        // Busy: reject a new physical press immediately and retain no work.
        release_rate();frame_quiet=0;cc(51,127);tick(5);
        if(!service_busy || service_ready)$fatal(1,"service did not expose busy");
        release_rate();r0=usb_rejects;cc(51,127);tick(3);
        if(usb_rejects!=r0+1)$fatal(1,"busy press not consumed/rejected");
        g0=generation;tick(8);if(generation!=g0)$fatal(1,"closed window generation oscillates");
        frame_quiet=1;applied_rate(1,q0+3);cc(51,127);tick(10);
        if(requests!=q0+3)$fatal(1,"busy press queued beyond completion");tests++;
        // Stale generation still rejects after busy has ended. Even a direct
        // transport race must be checked again by the sole service owner.
        s0=service_rejects;delayed(g0-1);if(service_rejects!=s0+1 || requests!=q0+3)$fatal(1,"stale generation entered reopened admission");tests++;
        // Closure without submit changes generation once, then reopening is
        // stable. Fault/DSP/no-permit/unqualified requests do not change rate.
        release_rate();g0=generation;inject_fault=1;tick(5);
        if(service_ready || !service_fault || generation!=g0+1)$fatal(1,"fault admission/status/generation");
        g0=generation;tick(12);if(generation!=g0)$fatal(1,"fault generation oscillates");
        r0=usb_rejects;cc(51,127);tick(2);if(usb_rejects!=r0+1)$fatal(1,"fault press not rejected");
        inject_fault=0;ready_wait();if(generation!=g0)$fatal(1,"reopen changed generation");
        s0=service_rejects;manual_tag=generation;inject_busy=1;delayed(manual_tag);inject_busy=0;ready_wait();
        if(service_rejects!=s0+1)$fatal(1,"destination busy admission bypassed");
        s0=service_rejects;permit=0;delayed(generation);permit=1;ready_wait();
        if(service_rejects!=s0+1)$fatal(1,"permit admission bypassed");
        s0=service_rejects;dsp_fault=1;delayed(generation);dsp_fault=0;ready_wait();
        if(service_rejects!=s0+1)$fatal(1,"DSP fault admission bypassed");
        s0=service_rejects;qualified[!active_rate]=0;delayed(generation);qualified=3;ready_wait();
        if(service_rejects!=s0+1 || requests!=q0+3)$fatal(1,"source qualification admission bypassed");tests++;
        // APB accepting write has priority over the simultaneous transported
        // physical press, through the SAME service transaction FSM.
        reset_all();q0=requests;s0=service_rejects;cd=0;ca=8;tick(2);
        cc(51,127);cv=1;tick(1);cv=0;tick(3);
        if(service_rejects!=s0+1)$fatal(1,"APB write did not reject simultaneous Push");
        applied_rate(0,q0+1);tests++;
        // APB read can coincide with a valid physical press.
        release_rate();cw=0;ca=12'h02c;tick(2);cc(51,127);cv=1;tick(1);cv=0;cw=1;ca=8;
        applied_rate(1,q0+2);tests++;
        // Connection boundaries and PANIC clear physical held identity.
        put(0,0);tick(3);put(0,1);cc(51,127);applied_rate(0,q0+3);tests++;
        arn=1;audio_run=1;tick(30);cc(27,127);tick(5);cc(51,127);applied_rate(1,q0+4);tests++;
        // Fill the actual generated asynchronous FIFO with ordinary mapped
        // controls. No force/stub creates its real write backpressure.
        tick(13000);if(usb.push_warmup!=0)$fatal(1,"real feedback warmup never completed");
        consume=0;full_seen=0;fill=0;
        begin:fill_loop
            for(integer k=0;k<160;k=k+1)begin
                @(negedge clk);sel=1;wr=1;addr=4;wd={1'b0,7'd1,1'b0,7'd71,16'hb00b};n=0;
                begin:wait_normal
                    forever begin
                        @(posedge clk);n++;
                        if(usb_ready)begin fill++;disable wait_normal;end
                        if(n==30)begin full_seen=1;disable wait_normal;end
                    end
                end
                @(negedge clk);sel=0;wr=0;
                if(full_seen)disable fill_loop;
            end
        end
        tick(3);if(!full_seen || usb.fifo_ready || fill<32)$fatal(1,"actual FIFO did not backpressure fill=%0d",fill);
        w0=fifo_writes;release_rate();q0=requests;cc(51,127);applied_rate(0,q0+1);
        if(usb.fifo_ready || fifo_writes!=w0)$fatal(1,"rate press used full FIFO");tests++;
        // Generic/25K attachment cannot impersonate a physical Push Session.
        put(0,7);@(negedge clk);sel=1;wr=1;addr=4;wd={1'b0,7'd127,1'b0,7'd51,16'hb00b};#1;
        if(usb_ready)$fatal(1,"25K accepted raw Push rate control");@(negedge clk);sel=0;wr=0;tests++;
        $display("PASS push_rate_control tests=%0d USB_pulses=%0d source_rejects=%0d service_rejects=%0d real_core_requests=%0d applies=%0d actual_FIFO_fill=%0d",tests,usb_pulses,usb_rejects,service_rejects,requests,applies,fill);
        $finish;
    end
    initial begin #20000000;$fatal(1,"test timeout");end
endmodule
