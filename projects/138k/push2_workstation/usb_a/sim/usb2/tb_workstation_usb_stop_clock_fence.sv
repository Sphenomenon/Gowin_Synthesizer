`timescale 1ns/1ps
// Real MMIO adapter/input owner/generated queue/session; only held-note and
// volume application are modeled. No USB bus, DSP or serial-audio model.
module usb_stop_clock_fence_case #(parameter integer FENCE=0)(
    input wire clk_usb,reset_n,
    output reg done=0
);
    reg compute_clk=0,compute_run=1,consume=1;
    always #6.510417 if(compute_run)compute_clk=!compute_clk;
    wire runtime_reset_n=reset_n;
    wire adapter_audio_reset_n=runtime_reset_n;
    reg selected=0,writing=0;
    reg [7:0] address=0;
    reg [31:0] write_data=0;
    wire service_ready,service_error,owner_select,owner_write,owner_ready;
    wire [7:0] owner_address;
    wire [31:0] owner_write_data,owner_read_data,read_data;
    wire [223:0] telemetry;
    wire audio_valid,lifecycle,cancel,audio_ready,session_ready,internal_event,session_lifecycle;
    wire [17:0] audio_event,committed_event;
    wire committed_valid,initializing;
    wire [3:0] initialization_step;
    reg [127:0] held=0;
    reg [15:0] volume=0;
    reg [9:0] panic_epoch=0;
    integer attaches=0,detaches=0,panics=0,barriers=0,default_events=0,normal_events=0,note_events=0,stores=0;
    integer stale_events=0,fresh_events=0,blocked_checks=0,hold_stop_checks=0,drain_stop_checks=0,pointer_checks=0;
    integer expected_fresh_note=70;reg track_boundary=0,first_fresh_write=0;
    wire [31:0] model_control={volume,6'd1,3'd0,2'd0,2'd2,3'd0};
    wire [447:0] performance={32'h43545231,32'd0,32'd0,32'd0,32'd0,
        panic_epoch,22'd1048576,32'd0,held,32'd0,model_control,32'd0};
    workstation_usb2_service_adapter mmio(
        .clk_cpu(clk_usb),.reset_n(reset_n),.session_valid_i(1'b1),.owner_connected_i(telemetry[1]),
        .service_valid_i(selected),.service_write_i(writing),.service_address_i(address),
        .service_write_data_i(write_data),.service_mask_i(4'hf),.service_ready_o(service_ready),
        .service_error_o(service_error),.service_read_data_o(read_data),.owner_select_o(owner_select),
        .owner_write_o(owner_write),.owner_address_o(owner_address),.owner_write_data_o(owner_write_data),
        .owner_ready_i(owner_ready),.owner_read_data_i(owner_read_data),.canceled_requests_o());
    push2_usb_a_control #(.STOP_CLOCK_QUEUE_FENCE(FENCE)) owner(
        .clk(clk_usb),.reset_n(reset_n),.audio_clk(compute_clk),.audio_reset_n(adapter_audio_reset_n),
        .feedback_clk(compute_clk),.feedback_reset_n(adapter_audio_reset_n),.performance_words(performance),
        .display_meta_data(64'd0),.display_meta_valid(1'b0),.service_state_data(34'd0),.service_state_valid(1'b0),
        .score_valid(1'b0),.analysis_done(1'b0),.score_ready(),.score_note(7'd0),.playlist_valid(1'b0),
        .playlist_ready(),.playlist_word(16'd0),.track_launch(),.track_index(),
        .select(owner_select),.write(owner_write),.address(owner_address),.wdata(owner_write_data),
        .ready(owner_ready),.rdata(owner_read_data),.audio_valid(audio_valid),.audio_ready(audio_ready),
        .audio_event(audio_event),.audio_lifecycle(lifecycle),.audio_cancel(cancel),.telemetry(telemetry));
    // Match the runtime lifecycle merge: cancellation bypasses normal-event
    // backpressure. consume models only a paused normal event consumer.
    assign audio_ready=(consume || lifecycle) && session_ready;
    workstation_session session(
        .clk_i(compute_clk),.rst_ni(runtime_reset_n),.cpu_valid_i(audio_valid && (consume || lifecycle)),.cpu_event_i(audio_event),
        .arbiter_ready_i(1'b1),.cpu_ready_o(session_ready),.internal_o(internal_event),.lifecycle_o(session_lifecycle),
        .fifo_valid_i(audio_valid && consume && !internal_event),.fifo_event_i(audio_event),.fifo_ready_o(),
        .cue_valid_i(1'b0),.cue_stop_i(1'b0),.cue_event_i(18'd0),.cue_ready_o(),.event_ready_i(1'b1),
        .event_valid_o(committed_valid),.event_o(committed_event),.mode_pending_i(1'b0),.mode_i(2'd2),
        .initializing_o(initializing),.initialization_step_o(initialization_step));
    always @(posedge compute_clk)begin
        if(!runtime_reset_n)begin held<=0;volume<=0;panic_epoch<=0;end
        else begin
            if(audio_valid && audio_ready && lifecycle)begin
                if(audio_event[17:14]!=15)$fatal(1,"lifecycle format");
                if(audio_event[6:0]<3)begin
                    if(!cancel)$fatal(1,"lifecycle lost cancellation");
                    held<=0;panic_epoch<=panic_epoch+1'b1;
                    case(audio_event[6:0])
                        0:detaches=detaches+1;
                        1:begin if(!audio_event[7])$fatal(1,"Push/GW25K attach lost defaults flag");attaches=attaches+1;end
                        2:panics=panics+1;
                        default:$fatal(1,"unreachable lifecycle");
                    endcase
                end else if(audio_event[6:0]==3)begin
                    if(cancel || initializing)$fatal(1,"barrier bypassed real session initialization");
                    barriers=barriers+1;
                end else $fatal(1,"unexpected internal event");
            end else if(committed_valid)begin
                if(initializing)default_events=default_events+1;else normal_events=normal_events+1;
                if(committed_event[17:14]==2 && committed_event[13:7]==7)
                    volume<=committed_event[6:0]==127 ? 16'd32768 : {1'b0,committed_event[6:0],8'd0};
                if(committed_event[17:14]==1 || committed_event[17:14]==0)begin
                    held[committed_event[13:7]]<=committed_event[17:14]==1 && committed_event[6:0]!=0;
                    note_events=note_events+1;
                    if(track_boundary && !initializing && committed_event[17:14]==1)begin
                        if(integer'(committed_event[13:7])<expected_fresh_note)stale_events=stale_events+1;
                        else fresh_events=fresh_events+1;
                    end
                end
            end
        end
    end
    task usb_cycles(input integer count);begin repeat(count)@(negedge clk_usb);end endtask
    task access(input bit wr,input [7:0] target,input [31:0] data,output reg [31:0] value);
        integer cycles;
        begin
            @(negedge clk_usb);selected=1;writing=wr;address=target;write_data=data;cycles=0;
            do begin @(posedge clk_usb);cycles=cycles+1;if(cycles>30000)$fatal(1,"MMIO timeout target=%h old=%b",target,FENCE);end while(!service_ready);
            if(service_error)$fatal(1,"MMIO adapter rejected legal request");value=read_data;
            @(negedge clk_usb);selected=0;writing=0;if(wr)stores=stores+1;
        end
    endtask
    reg [31:0] value;
    task store(input [7:0] target,input [31:0] data);begin access(1,target,data,value);end endtask
    task generic_event(input [3:0] kind,input [6:0] a,b);begin store(8'h54,{14'd0,kind,a,b});end endtask
    task user_state;
        begin generic_event(2,7,53);generic_event(1,60,100);wait(volume==16'd13568 && held[60]);usb_cycles(20);end
    endtask
    // The source write may resume only after actual vendor pointer and
    // buffered-consume feedback are empty, not merely after a local timer.
    always @(posedge clk_usb)if(reset_n && FENCE!=0 && first_fresh_write && owner.events.w_en)begin
        if(owner.events.fifo.unbuffered.produce_w_bin!==0 ||
           owner.events.fifo.unbuffered.consume_w_bin!==0 ||
           owner.events.fifo.unbuffered.consume_w_gry!==0 ||
           owner.events.fifo.unbuffered.produce_r_gry!==0 ||
           owner.events.fifo.unbuffered.consume_r_bin!==0 ||
           owner.events.fifo.w_consume_buffered!==0 ||
           owner.events.fifo.unbuffered.r_rst!==0 || owner.events.r_rdy!==0)
            $fatal(1,"write unfenced before real FIFO reset/pointer/buffer round trip");
        first_fresh_write=0;pointer_checks=pointer_checks+1;
    end
    task resume_with_stops;
        begin
            usb_cycles(10);
            if(service_ready || owner.queue_write_ready)$fatal(1,"stopped destination acknowledged new data");
            blocked_checks=blocked_checks+1;compute_run=1;
            repeat(2)@(negedge compute_clk);compute_run=0;usb_cycles(12);
            if(FENCE!=0)begin
                if(!owner.queue_fifo_reset || owner.queue_read_ready || owner.queue_write_ready || service_ready)
                    $fatal(1,"hold-phase destination stop acknowledged reset early");
                hold_stop_checks=hold_stop_checks+1;
            end
            compute_run=1;
            if(FENCE!=0)begin
                wait(!owner.queue_fifo_reset);repeat(2)@(negedge compute_clk);
                compute_run=0;usb_cycles(12);
                if(!owner.queue_flushing || owner.queue_read_ready || owner.queue_write_ready || service_ready)
                    $fatal(1,"drain-phase destination stop acknowledged reset early");
                drain_stop_checks=drain_stop_checks+1;compute_run=1;
            end
        end
    endtask
    task fresh_after_boundary(input integer note_number);
        begin
            first_fresh_write=1;expected_fresh_note=note_number;track_boundary=1;
            fork
                begin generic_event(1,7'(note_number),100);end
                begin resume_with_stops();end
            join
            wait(held[note_number] && !initializing && barriers==attaches+panics);usb_cycles(180);
            if(FENCE!=0 && (stale_events!=0 || held!=(128'd1<<note_number)))
                $fatal(1,"stale pre-boundary event escaped after stopped-clock reset");
        end
    endtask
    initial begin
        wait(reset_n);usb_cycles(20);store(8'h00,7);
        wait(attaches==1 && barriers==1 && !initializing);user_state();
        consume=0;generic_event(1,61,90);generic_event(1,62,80);wait(owner.queued_valid);
        @(negedge compute_clk);compute_run=0;
        store(8'h00,0);usb_cycles(8);store(8'h00,7);usb_cycles(8);consume=1;
        fresh_after_boundary(70);
        if(attaches!=2 || detaches!=1 || default_events!=26)$fatal(1,"stopped hotplug lifecycle/defaults");
        if(FENCE!=0 && volume!=32768)$fatal(1,"stale pre-detach volume replay");
        generic_event(2,7,53);wait(volume==13568);
        consume=0;generic_event(1,71,80);wait(owner.queued_valid);
        @(negedge compute_clk);compute_run=0;
        generic_event(2,120,0);usb_cycles(8);consume=1;
        fresh_after_boundary(72);
        if(attaches!=2 || detaches!=1 || panics!=1 || default_events!=26)$fatal(1,"stopped PANIC invented attach/defaults");
        if(FENCE!=0 && volume!=13568)$fatal(1,"PANIC changed modeled committed volume");
        // Repeated source boundaries while the destination is absent coalesce
        // to the existing detached/latest-attachment lifecycle state. They
        // restart the queue fence and must not leak any earlier generation.
        consume=0;generic_event(1,73,80);wait(owner.queued_valid);
        @(negedge compute_clk);compute_run=0;
        repeat(2)begin store(8'h00,0);usb_cycles(4);store(8'h00,7);usb_cycles(4);end
        consume=1;fresh_after_boundary(74);
        if(attaches!=3 || detaches!=2 || panics!=1 || default_events!=39 || barriers!=4)
            $fatal(1,"repeated stopped boundaries changed existing lifecycle coalescing");
        if(FENCE!=0)begin
            if(pointer_checks!=3 || hold_stop_checks!=3 || drain_stop_checks!=3 || fresh_events!=3 || stale_events!=0)
                $fatal(1,"incomplete opt-in fencing coverage");
        end else if(stale_events==0)$fatal(1,"legacy negative control did not reproduce old RAM replay");
        $display("USB_STOP_CLOCK_FENCE enabled=%0d attaches=%0d barriers=%0d detaches=%0d panics=%0d defaults=%0d stale=%0d fresh=%0d blocked=%0d hold_stops=%0d drain_stops=%0d pointer_checks=%0d stores=%0d",FENCE,attaches,barriers,detaches,panics,default_events,stale_events,fresh_events,blocked_checks,hold_stop_checks,drain_stop_checks,pointer_checks,stores);
        done=1;
    end
endmodule
module tb_workstation_usb_stop_clock_fence;
    reg clk_usb=0,reset_n=0;always #10.416667 clk_usb=!clk_usb;
    wire legacy_done,fenced_done;
    usb_stop_clock_fence_case #(.FENCE(0)) legacy(clk_usb,reset_n,legacy_done);
    usb_stop_clock_fence_case #(.FENCE(1)) fenced(clk_usb,reset_n,fenced_done);
    initial begin repeat(10)@(negedge clk_usb);reset_n=1;end
    initial begin wait(legacy_done && fenced_done);
        $display("PASS usb_stop_clock_fence: stopped_hotplug=1 stopped_panic=1 repeated_boundaries=1 hold_stops=3 drain_stops=3 pointer_roundtrips=3 optin_stale=0 legacy_replay=1");$finish;end
    initial begin #3000000;$fatal(1,"USB stop-clock fence watchdog");end
endmodule
