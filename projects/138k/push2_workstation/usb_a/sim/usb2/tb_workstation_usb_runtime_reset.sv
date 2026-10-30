`timescale 1ns/1ps
// Real MMIO adapter/input owner/generated queue/session; only held-note and
// volume application are modeled. No USB bus, DSP or serial-audio model.
module usb_runtime_reset_case #(parameter bit OLD_PLL_RESET=0)(
    input wire clk_usb,reset_n,
    output reg done=0
);
    reg compute_clk=0,compute_run=1,pll_qualified=1,consume=1;
    always #6.510417 if(compute_run)compute_clk=!compute_clk;
    wire runtime_reset_n=reset_n;
    wire adapter_audio_reset_n=OLD_PLL_RESET ? reset_n && pll_qualified : runtime_reset_n;
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
    integer recovery_checks=0,resumed_queue_events=0,detach_flush_checks=0;
    reg check_resumed_queue=0;
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
    push2_usb_a_control owner(
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
                    if(check_resumed_queue && committed_event[17:14]==1)begin
                        if(committed_event[13:7]!=7'(61+resumed_queue_events))$fatal(1,"retained queue event order");
                        resumed_queue_events=resumed_queue_events+1;
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
            do begin @(posedge clk_usb);cycles=cycles+1;if(cycles>30000)$fatal(1,"MMIO timeout target=%h old=%b",target,OLD_PLL_RESET);end while(!service_ready);
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
    initial begin
        wait(reset_n);usb_cycles(20);
        store(8'h00,32'd7);wait(attaches==1 && barriers==1 && !initializing);usb_cycles(20);
        if(default_events!=13 || volume!=32768)$fatal(1,"initial real session defaults incomplete");
        user_state();
        // A qualification pulse shorter than one compute period must not be
        // a USB lifecycle reset. The old connection resets asynchronously.
        @(negedge compute_clk);#1;pll_qualified=0;#3;pll_qualified=1;usb_cycles(150);
        if(OLD_PLL_RESET)begin
            if(attaches!=2 || barriers!=2 || default_events!=26 || volume!=32768 || held!=0)
                $fatal(1,"negative control did not reproduce first phantom attach/defaults");
        end else if(attaches!=1 || barriers!=1 || default_events!=13 || volume!=13568 || !held[60])
            $fatal(1,"short compute PLL qualification loss invented a USB attach");
        recovery_checks=recovery_checks+1;
        user_state();consume=0;usb_cycles(4);
        generic_event(1,61,90);generic_event(1,62,80);wait(owner.queued_valid);
        @(negedge compute_clk);compute_run=0;pll_qualified=0;usb_cycles(100);
        access(0,8'h00,0,value);if(value!=7 || !telemetry[1])$fatal(1,"compute stop changed MMIO attachment");
        if(volume!=13568 || !held[60])$fatal(1,"modeled owner changed without compute edges");
        pll_qualified=1;usb_cycles(20);check_resumed_queue=!OLD_PLL_RESET;consume=1;compute_run=1;usb_cycles(150);
        if(OLD_PLL_RESET)begin
            if(attaches!=3 || barriers!=3 || default_events!=39)
                $fatal(1,"negative control stopped-clock counts attach=%0d barrier=%0d defaults=%0d volume=%0d held=%h",attaches,barriers,default_events,volume,held);
        end else if(attaches!=1 || barriers!=1 || default_events!=13 || volume!=13568 ||
            !held[60] || !held[61] || !held[62] || resumed_queue_events!=2)
            $fatal(1,"compute recovery reset lifecycle/defaults or lost queued events");
        check_resumed_queue=0;recovery_checks=recovery_checks+1;
        // Real MMIO detach/reattach after compute recovery still creates both
        // boundaries, even with normal consumer backpressure. The lifecycle
        // priority path cancels and queued pre-detach notes must be flushed.
        consume=0;generic_event(1,63,70);wait(owner.queued_valid);
        store(8'h00,0);wait(detaches==1);usb_cycles(20);
        store(8'h00,1);usb_cycles(8);consume=1;
        wait(detaches==1 && attaches==(OLD_PLL_RESET ? 4:2) && barriers==attaches && !initializing);usb_cycles(100);
        if(held!=0 || volume!=32768 || default_events!=13*attaches)$fatal(1,"real detach/reattach old=%b attach=%0d defaults=%0d volume=%0d held=%h",OLD_PLL_RESET,attaches,default_events,volume,held);
        detach_flush_checks=detach_flush_checks+1;
        wait(owner.push_warmup==0);
        store(8'h04,32'h02249009);wait(held[36]);
        store(8'h04,32'h7f4fb00b);wait(volume==32256);
        store(8'h04,32'h7f1bb00b);wait(panics==1 && held==0);usb_cycles(100);
        store(8'h04,32'h7f1bb00b);usb_cycles(100);
        if(panics!=1 || volume!=32256 || default_events!=13*attaches || barriers!=attaches+panics || detaches!=1)
            $fatal(1,"PANIC old=%b attach=%0d barrier=%0d detach=%0d panic=%0d defaults=%0d volume=%0d held=%h",OLD_PLL_RESET,attaches,barriers,detaches,panics,default_events,volume,held);
        $display("USB_RUNTIME_RESET old=%0d attaches=%0d barriers=%0d detaches=%0d panics=%0d default_events=%0d recovery_checks=%0d resumed_queue_events=%0d detach_flush_checks=%0d stores=%0d notes=%0d",OLD_PLL_RESET,attaches,barriers,detaches,panics,default_events,recovery_checks,resumed_queue_events,detach_flush_checks,stores,note_events);
        done=1;
    end
endmodule

module tb_workstation_usb_runtime_reset;
    reg clk_usb=0,reset_n=0;
    always #10.416667 clk_usb=!clk_usb;
    wire old_done,current_done;
    usb_runtime_reset_case #(.OLD_PLL_RESET(1)) old_connection(clk_usb,reset_n,old_done);
    usb_runtime_reset_case #(.OLD_PLL_RESET(0)) current_connection(clk_usb,reset_n,current_done);
    initial begin repeat(10)@(negedge clk_usb);reset_n=1;end
    initial begin wait(old_done && current_done);
        $display("PASS usb_runtime_reset: recoveries=2 current_phantom_attach=0 old_phantom_attach=2 real_detach_reattach=1 panic=1 retained_queue_events=2 real_session_defaults=13");$finish;end
    initial begin #3000000;$fatal(1,"USB runtime reset watchdog");end
endmodule
