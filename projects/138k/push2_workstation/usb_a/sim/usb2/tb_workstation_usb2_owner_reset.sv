`timescale 1ns/1ps
// Only the USB CPU/ULPI producer is replaced by a controlled MMIO source.
// Wrapper, service adapter, owner, CDC, generated FIFO and session are real.
module workstation_usb2_soc #(
    parameter ROM_FILE="", parameter integer CPU_FREQUENCY_HZ=48000000,
    parameter integer ATTACH_DEBOUNCE_US=1, BUS_TIMEOUT_CYCLES=100
)(
    input wire clk_cpu,clk_ref,clk_ulpi,reset_n,uart_rx_i,
    output wire uart_tx_o,
    input wire [7:0] ulpi_data_i,
    input wire ulpi_dir_i,ulpi_nxt_i,
    output wire [7:0] ulpi_data_o,
    output wire ulpi_data_oe_o,ulpi_stp_o,
    output reg service_valid_o=0,service_write_o=0,
    output reg [7:0] service_address_o=0,
    output reg [31:0] service_write_data_o=0,
    output wire [3:0] service_mask_o,
    input wire service_ready_i,service_error_i,
    input wire [31:0] service_read_data_i,
    output wire [3:0] cpu_fault_o,
    output wire [31:0] cpu_fault_address_o,
    output wire transaction_reset_n_o,phy_ready_o,failed_o,high_speed_o,traffic_enable_o,
    output wire [31:0] sof_count_o
);
    assign uart_tx_o=1'b1;
    assign ulpi_data_o=0;assign ulpi_data_oe_o=0;assign ulpi_stp_o=0;
    assign service_mask_o=4'hf;assign cpu_fault_o=0;assign cpu_fault_address_o=0;
    assign transaction_reset_n_o=reset_n;assign phy_ready_o=reset_n;
    assign failed_o=0;assign high_speed_o=0;assign traffic_enable_o=reset_n;assign sof_count_o=0;
endmodule

module usb2_owner_reset_case #(parameter integer SYNC=1,parameter real AUDIO_PHASE_NS=0.001)(
    input wire clk_usb,clk_ref,
    output reg done=0
);
    reg clk_audio=0,audio_run=1,reset_n=1,runtime_ready=1,consume=1;
    initial begin #(AUDIO_PHASE_NS);forever #6.510417 if(audio_run)clk_audio=!clk_audio;end
    wire runtime_reset_n=reset_n && runtime_ready;
    wire audio_valid,lifecycle,cancel,session_ready,audio_ready,committed_valid,internal_event;
    wire [17:0] audio_event,committed_event;
    wire [223:0] telemetry;
    wire initializing;
    reg [127:0] held=0;
    reg [15:0] volume=0;
    reg [9:0] epoch=0;
    integer attaches=0,detaches=0,panics=0,barriers=0,defaults=0,notes=0;
    integer release_edges=0,release_checks=0,assert_checks=0,stop_fences=0,retained=0;
    reg check_retained=0;
    wire [31:0] model_control={volume,6'd1,3'd0,2'd0,2'd2,3'd0};
    wire [447:0] performance={32'h43545231,32'd0,32'd0,32'd0,32'd0,
        epoch,22'd1048576,32'd0,held,32'd0,model_control,32'd0};
    workstation_usb2_input #(.FEEDBACK_AUDIO_DOMAIN(1),.STOP_CLOCK_QUEUE_FENCE(1),
        .AUDIO_OWNER_RESET_SYNC(SYNC),.CNN_FOLLOW_ENABLE(0)) dut(
        .clk_cpu(clk_usb),.clk_ref(clk_ref),.clk_ulpi(clk_ref),.clk_audio(clk_audio),
        .reset_n(reset_n),.audio_reset_n(runtime_reset_n),.uart_rx_i(1'b1),.uart_tx_o(),
        .ulpi_data_i(8'd0),.ulpi_dir_i(1'b0),.ulpi_nxt_i(1'b0),.ulpi_data_o(),.ulpi_data_oe_o(),.ulpi_stp_o(),
        .performance_words_i(performance),.display_meta_data_i(64'd0),.display_meta_valid_i(1'b0),
        .service_state_data_i(34'd0),.service_state_valid_i(1'b0),.score_valid_i(1'b0),.analysis_done_i(1'b0),
        .score_ready_o(),.score_note_i(7'd0),.playlist_valid_i(1'b0),.playlist_ready_o(),.playlist_word_i(16'd0),
        .track_launch_o(),.track_index_o(),.audio_valid_o(audio_valid),.audio_lifecycle_o(lifecycle),
        .audio_cancel_o(cancel),.audio_ready_i(audio_ready),.audio_event_o(audio_event),.telemetry_o(telemetry),
        .canceled_requests_o(),.cpu_fault_o(),.cpu_fault_address_o(),.transaction_reset_n_o(),
        .phy_ready_o(),.failed_o(),.high_speed_o(),.traffic_enable_o(),.sof_count_o());
    workstation_session session(
        .clk_i(clk_audio),.rst_ni(runtime_reset_n),.cpu_valid_i(audio_valid && (consume || lifecycle)),
        .cpu_event_i(audio_event),.arbiter_ready_i(1'b1),.cpu_ready_o(session_ready),
        .internal_o(internal_event),.lifecycle_o(),.fifo_valid_i(audio_valid && consume && !internal_event),
        .fifo_event_i(audio_event),.fifo_ready_o(),.cue_valid_i(1'b0),.cue_stop_i(1'b0),.cue_event_i(18'd0),
        .cue_ready_o(),.event_ready_i(1'b1),.event_valid_o(committed_valid),.event_o(committed_event),
        .mode_pending_i(1'b0),.mode_i(2'd2),.initializing_o(initializing),.initialization_step_o());
    assign audio_ready=(consume || lifecycle) && session_ready;

    always @(posedge clk_audio or negedge runtime_reset_n)
        if(!runtime_reset_n)release_edges=0;else release_edges=release_edges+1;
    always @(posedge dut.owner_audio_reset_n)begin
        #0.001;
        if(SYNC!=0 && (release_edges!=3 || !clk_audio))
            $fatal(1,"owner reset release did not wait for three real audio edges: sync=%0d edges=%0d",SYNC,release_edges);
        if($realtime>0.01)release_checks=release_checks+1;
    end
    always @(dut.owner_audio_reset_n or dut.input_owner.audio_reset_n)begin
        #0.001;
        if(SYNC!=0 && dut.owner_audio_reset_n!==dut.input_owner.audio_reset_n)
            $fatal(1,"owner audio reset bypassed the selected local release");
    end
    always @(posedge clk_audio)begin
        #0.001;
        if(SYNC!=0 && !dut.owner_audio_reset_n && dut.input_owner.feedback_divider!==0)
            $fatal(1,"feedback functional state released before local reset");
    end
    always @(posedge clk_audio)begin
        if(!runtime_reset_n)begin held<=0;volume<=0;epoch<=0;end
        else if(audio_valid && audio_ready && lifecycle)begin
            if(audio_event[6:0]<3)begin
                if(!cancel)$fatal(1,"lifecycle lost cancellation");
                held<=0;epoch<=epoch+1'b1;
                case(audio_event[6:0])
                    0:detaches=detaches+1;
                    1:begin if(!audio_event[7])$fatal(1,"attach defaults flag");attaches=attaches+1;end
                    2:panics=panics+1;
                    default:$fatal(1,"unreachable lifecycle");
                endcase
            end else begin
                if(cancel || initializing)$fatal(1,"initialization barrier bypass");
                barriers=barriers+1;
            end
        end else if(committed_valid)begin
            if(initializing)defaults=defaults+1;
            if(committed_event[17:14]==2 && committed_event[13:7]==7)
                volume<=committed_event[6:0]==127 ? 16'd32768 : {1'b0,committed_event[6:0],8'd0};
            if(committed_event[17:14]==1 || committed_event[17:14]==0)begin
                held[committed_event[13:7]]<=committed_event[17:14]==1 && committed_event[6:0]!=0;
                notes=notes+1;
                if(check_retained && committed_event[17:14]==1)begin
                    if(committed_event[13:7]!=7'(61+retained))$fatal(1,"retained queue order");
                    retained=retained+1;
                end
                if(committed_event[13:7]==63 || committed_event[13:7]==64)
                    $fatal(1,"pre-detach/PANIC event escaped queue fence");
            end
        end
    end

    task usb_cycles(input integer count);begin repeat(count)@(negedge clk_usb);end endtask
    task stop_audio(input bit high_level);
        begin
            if(high_level)@(posedge clk_audio);else @(negedge clk_audio);
            #0.1;audio_run=0;
        end
    endtask
    task reset_while_stopped(input bit high_level,input bit board_reset);
        begin
            stop_audio(high_level);#0.3;
            if(board_reset)reset_n=0;else runtime_ready=0;
            #0.1;
            if(dut.owner_audio_reset_n!==0 || dut.input_owner.feedback_divider!==0)
                $fatal(1,"owner reset failed asynchronous assertion while stopped");
            assert_checks=assert_checks+1;
            #2.1;
            if(board_reset)reset_n=1;else runtime_ready=1;
            #0.1;
            if(SYNC==0 && dut.owner_audio_reset_n!==1)$fatal(1,"default direct reset changed");
            usb_cycles(12);
            if(SYNC!=0 && dut.owner_audio_reset_n!==0)$fatal(1,"owner reset released on stopped clock");
            if(dut.input_owner.feedback_divider!==0)$fatal(1,"stopped feedback divider advanced");
            audio_run=1;wait(dut.owner_audio_reset_n);repeat(5)@(negedge clk_audio);
            if(dut.input_owner.feedback_divider==0)$fatal(1,"feedback did not restart");
        end
    endtask
    task store(input [7:0] target,input [31:0] data);
        integer cycles;
        begin
            @(negedge clk_usb);
            dut.host.service_valid_o=1;dut.host.service_write_o=1;
            dut.host.service_address_o=target;dut.host.service_write_data_o=data;cycles=0;
            do begin @(posedge clk_usb);cycles=cycles+1;if(cycles>30000)$fatal(1,"MMIO timeout %h",target);end
            while(!dut.host.service_ready_i);
            if(dut.host.service_error_i)$fatal(1,"legal MMIO rejected");
            @(negedge clk_usb);dut.host.service_valid_o=0;dut.host.service_write_o=0;
        end
    endtask
    task event_store(input [3:0] kind,input [6:0] a,b);
        begin store(8'h54,{14'd0,kind,a,b});end
    endtask

    initial begin
        #1;reset_n=0;runtime_ready=0;usb_cycles(5);reset_n=1;runtime_ready=1;
        wait(dut.owner_audio_reset_n);usb_cycles(20);
        reset_while_stopped(0,0);reset_while_stopped(1,0);reset_while_stopped(1,1);
        // A sub-cycle request must reset immediately, then restart the full
        // release chain. This is a platform reset, before any attached user.
        @(negedge clk_audio);#0.2;runtime_ready=0;#0.1;
        if(dut.owner_audio_reset_n!==0 || dut.input_owner.feedback_divider!==0)$fatal(1,"short request missed");
        assert_checks=assert_checks+1;#0.1;runtime_ready=1;
        wait(dut.owner_audio_reset_n);usb_cycles(20);
        store(8'h00,7);wait(attaches==1 && barriers==1 && !initializing);usb_cycles(20);
        if(defaults!=13 || volume!=32768)$fatal(1,"initial defaults");
        event_store(2,7,53);event_store(1,60,100);wait(volume==13568 && held[60]);

        consume=0;usb_cycles(4);event_store(1,61,90);event_store(1,62,80);
        wait(dut.input_owner.queued_valid);stop_audio(0);usb_cycles(30);
        if(!dut.owner_audio_reset_n || !telemetry[1])$fatal(1,"clock stop reset attachment");
        check_retained=1;consume=1;audio_run=1;wait(retained==2);usb_cycles(20);check_retained=0;
        if(attaches!=1 || defaults!=13 || volume!=13568 || !held[60] || !held[61] || !held[62])
            $fatal(1,"clock recovery changed state or queue");
        stop_fences=stop_fences+1;

        consume=0;event_store(1,63,70);wait(dut.input_owner.queued_valid);stop_audio(1);
        store(8'h00,0);store(8'h00,7);usb_cycles(30);
        if(!dut.input_owner.queue_flushing || dut.input_owner.queue_write_ready)
            $fatal(1,"stopped destination acknowledged detach queue fence");
        consume=1;audio_run=1;wait(detaches==1 && attaches==2 && barriers==2 && !initializing);
        usb_cycles(100);if(defaults!=26 || held!=0)$fatal(1,"reattach defaults/flush");
        stop_fences=stop_fences+1;

        event_store(2,7,53);event_store(1,60,100);wait(volume==13568 && held[60]);
        consume=0;event_store(1,64,70);wait(dut.input_owner.queued_valid);stop_audio(0);
        event_store(2,120,0);usb_cycles(30);
        if(!dut.input_owner.queue_flushing || dut.input_owner.queue_write_ready)
            $fatal(1,"stopped destination acknowledged PANIC queue fence");
        consume=1;audio_run=1;wait(panics==1 && barriers==3);usb_cycles(100);
        if(defaults!=26 || volume!=13568 || held!=0)$fatal(1,"PANIC altered defaults/volume or failed cancel");
        stop_fences=stop_fences+1;
        event_store(1,65,90);wait(held[65]);event_store(0,65,0);wait(!held[65]);usb_cycles(20);
        if(attaches!=2 || detaches!=1 || panics!=1 || retained!=2 || release_checks!=5 || assert_checks!=4)
            $fatal(1,"coverage missing sync=%0d releases=%0d assertions=%0d",SYNC,release_checks,assert_checks);
        $display("USB2_OWNER_RESET sync=%0d releases=%0d assertions=%0d stopped_fences=%0d attaches=%0d detaches=%0d panics=%0d defaults=%0d retained=%0d",SYNC,release_checks,assert_checks,stop_fences,attaches,detaches,panics,defaults,retained);
        done=1;
    end
endmodule

module tb_workstation_usb2_owner_reset #(parameter real AUDIO_PHASE_NS=0.001);
    reg clk_usb=0,clk_ref=0;
    always #10.416667 clk_usb=!clk_usb;
    always #10 clk_ref=!clk_ref;
    wire sync_done,default_done;
    usb2_owner_reset_case #(.SYNC(1),.AUDIO_PHASE_NS(AUDIO_PHASE_NS)) synchronized_owner(clk_usb,clk_ref,sync_done);
    usb2_owner_reset_case #(.SYNC(0),.AUDIO_PHASE_NS(AUDIO_PHASE_NS)) default_owner(clk_usb,clk_ref,default_done);
    initial begin wait(sync_done && default_done);$display("PASS usb2 owner reset: real wrapper/MMIO/owner/CDC/FIFO/session, async assert, three audio edges, stopped high/low, default isolation, retained queue, detach and PANIC fences");$finish;end
    initial begin #3000000;$fatal(1,"USB2 owner reset timeout");end
endmodule
