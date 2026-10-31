// USB Host CPU MMIO -> existing Push mapper -> audio event FIFO.
// USB runs at 48 MHz; sample processing remains in the 76.8 MHz audio domain.
module push2_usb_a_control #(
    parameter integer STOP_CLOCK_QUEUE_FENCE=0,
    parameter bit CNN_FOLLOW_ENABLE=1'b1
)(
    input wire clk,reset_n,audio_clk,audio_reset_n,
    output wire audio_lifecycle,audio_cancel,
    input wire feedback_clk,feedback_reset_n,
    input wire [447:0] performance_words,
    input wire [63:0] display_meta_data,
    input wire display_meta_valid,
    input wire [33:0] service_state_data,
    input wire service_state_valid,
    input wire score_valid,
    input wire analysis_done,
    output wire score_ready,
    input wire [6:0] score_note,
    input wire playlist_valid,
    output wire playlist_ready,
    input wire [15:0] playlist_word,
    output wire track_launch,
    output wire [3:0] track_index,
    input wire select,write,input wire [7:0] address,
    input wire [31:0] wdata,output wire ready,output reg [31:0] rdata,
    output wire audio_valid,input wire audio_ready,output wire [17:0] audio_event,
    output wire [223:0] telemetry
);
    reg [11:0] feedback_divider;
    always @(posedge feedback_clk or negedge feedback_reset_n)
        if(!feedback_reset_n) feedback_divider<=0;else feedback_divider<=feedback_divider+1'b1;
    wire [447:0] snapshot;
    wire snapshot_valid;
    gw138k_stream_cdc #(.WIDTH(448)) feedback(
        .reset_n(reset_n && feedback_reset_n),.source_clk(feedback_clk),.destination_clk(clk),
        .source_valid(&feedback_divider),.source_data(performance_words),.drop_count(),
        .destination_valid(snapshot_valid),.destination_data(snapshot));
    wire [31:0] control=snapshot[63:32],options=snapshot[255:224];
    wire [9:0] panic_epoch=snapshot[287:278];
    wire [63:0] actual_held=snapshot[195:132];
    reg [63:0] display_meta_q;
    reg display_meta_seen;
    reg [33:0] service_state_q;
    always @(posedge clk or negedge reset_n)
        if(!reset_n)begin display_meta_q<=0;display_meta_seen<=0;service_state_q<=0;end
        else begin
            if(display_meta_valid)begin display_meta_q<=display_meta_data;display_meta_seen<=1;end
            if(service_state_valid)service_state_q<=service_state_data;
        end
    // Bit 2 qualifies the existing generic route as this GW25K panel. Bits
    // 0/1 and all existing event/register layouts retain their meanings.
    reg connected,generic_midi,gw25k;
    wire rst,push_connected,lifecycle_pending;
    reg audio_online,panic_seen,settle_wait;
    reg [1:0] panic_buttons;
    reg panic_toggle,panic_flush;
    reg [1:0] push_warmup;
    (* ASYNC_REG="TRUE" *) reg [1:0] settled_sync;
    wire queue_flushing;
    wire input_settled=audio_online && !settle_wait && !lifecycle_pending && !queue_flushing;
    // Two fresh feedback commits after the audio fence keep a delayed PANIC
    // epoch from clearing a newly mapped Push press. Relative knobs also see
    // the initialized absolute parameters before accepting the first turn.
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin settled_sync<=0;push_warmup<=2;end
        else begin
            settled_sync<={settled_sync[0],input_settled};
            if(!push_connected || panic_flush || !settled_sync[1]) push_warmup<=2;
            else if(snapshot_valid && push_warmup!=0) push_warmup<=push_warmup-1'b1;
        end
    end
    wire input_reset=rst || !connected || panic_flush;
    // The generated FIFO has a read-side output buffer without a reset pin.
    // Drain that buffer through its real read port while the asynchronous
    // pointer reset crosses. Hold new writes until this flush is acknowledged.
    (* ASYNC_REG="TRUE" *) reg [5:0] queue_release;
    (* ASYNC_REG="TRUE" *) reg [1:0] queue_write_release;
    wire queue_fifo_reset,queue_read_ready;
    always @(posedge audio_clk or posedge input_reset)
        if(input_reset) queue_release<=0;else queue_release<={queue_release[4:0],1'b1};
    generate if(STOP_CLOCK_QUEUE_FENCE!=0)begin: stopped_clock_queue_fence
        // The generated FIFO's producer pointer takes three destination edges
        // to reach read-side use, longer than its two-edge reset release.
        // Hold its original reset through six REAL destination edges; a
        // stopped destination cannot acknowledge this boundary early.
        assign queue_fifo_reset=input_reset || !queue_release[5];
        (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [5:0] drain_release;
        always @(posedge audio_clk or posedge queue_fifo_reset)
            if(queue_fifo_reset)drain_release<=0;
            else drain_release<={drain_release[4:0],1'b1};
        // A further six edges empty the read buffer and settle pointer/consume
        // feedback before the existing two-USB-edge write release. Normal
        // events stay fenced; lifecycle cancellation remains independent.
        // The USB request may assert asynchronous reset pins, but it must
        // not bypass a local release flop into audio FIFO read/data control.
        // queue_release asserts without an audio edge and releases only on
        // real audio edges, including when PANIC arrives with audio stopped.
        assign queue_flushing=!queue_release[5] || !drain_release[5];
        assign queue_read_ready=drain_release[5] && !queue_fifo_reset;
    end else begin: legacy_queue_release
        assign queue_fifo_reset=input_reset;
        assign queue_flushing=!queue_release[5];
        assign queue_read_ready=!queue_flushing;
    end endgenerate
    always @(posedge clk or posedge input_reset)
        if(input_reset) queue_write_release<=0;
        else queue_write_release<={queue_write_release[0],queue_read_ready};
    wire queue_write_ready=queue_write_release[1];
    assign push_connected=connected && !generic_midi;
    reg [31:0] received,frames,out_errors,in_diagnostics;
    wire raw_ready,valid,map_ready;wire [3:0] kind,cable,channel;wire [6:0] a,b;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] event_release;
    wire event_qualified=reset_n && audio_reset_n;
    always @(posedge clk or negedge event_qualified)
        if(!event_qualified) event_release<=0;else event_release<={event_release[1:0],1'b1};
    assign rst=!event_release[2];
    // A CPU store is acknowledged only when the decoder accepts the word.
    // Full event FIFO stalls the USB CPU, never the audio sample clock.
    wire raw_store=select && write && address==8'h04;
    wire generic_store=select && write && address==8'h54;
    // Reserved generic-MIDI controls: CC110 is absolute guide enable,
    // CC111 (0/127) browses, and CC112 (rising >=64) selects/returns.
    // Consume these locally; normal CC/program data retain their audio path.
    wire generic_guide_command=wdata[17:14]==4'd2 &&
        (wdata[13:7]==7'd110 || wdata[13:7]==7'd111 || wdata[13:7]==7'd112);
    wire generic_panic=generic_store && wdata[17:14]==4'd2 && wdata[13:7]==7'd120;
    wire raw_panic=raw_store && wdata[15:0]==16'hb00b &&
        (wdata[23:16]==8'd27 || wdata[23:16]==8'd29);
    wire raw_panic_down=wdata[30:24]!=0;
    wire raw_panic_fire=raw_panic && raw_panic_down &&
        !panic_buttons[wdata[23:16]==8'd29];
    wire pixel_read=select && !write && address==8'h2c;
    reg pixel_loaded,pixel_wait;
    reg [15:0] pixel_q;
    wire fifo_ready;
    wire mapped_valid,mapped_ready;wire [17:0] mapped_event;
    // Both routes share the existing audio FIFO. Push/disconnect PANIC has
    // priority over a generic store; the USB CPU waits if the FIFO is full.
    assign ready=select && (raw_store ? ((raw_panic || (raw_ready && push_warmup==0 && queue_write_ready)) && !input_reset && push_connected) :
        generic_store ? ((generic_panic || generic_guide_command || (queue_write_ready && fifo_ready && !mapped_valid)) &&
                         !input_reset && connected && generic_midi) :
        pixel_read ? pixel_loaded : 1'b1);
    wire accepted=select && ready;
    push2_midi_rx midi(.clk(clk),.rst(input_reset),
        .usb_valid(raw_store && !raw_panic && !input_reset && queue_write_ready && push_warmup==0 && push_connected),.usb_ready(raw_ready),.usb_event(wdata),
        .event_valid(valid),.event_ready(map_ready),.event_kind(kind),.event_cable(cable),
        .event_channel(channel),.event_data1(a),.event_data2(b),.event_pitch(),
        .events_received(),.packets_ignored());
    wire [63:0] held;wire [6:0] note,velocity;wire [31:0] mapped,ignored;
    wire guide_toggle,guide_mode,guide_target_valid;
    wire guide_prev,guide_next,guide_select;
    wire push_guide_toggle,push_guide_prev,push_guide_next,push_guide_select;
    reg generic_select_down;
    wire generic_accepted=generic_store && accepted;
    wire generic_played=generic_accepted && !gw25k && wdata[17:14]==4'd1 && wdata[6:0]!=7'd0;
    wire generic_guide_accepted=generic_accepted && generic_guide_command && !gw25k;
    assign guide_toggle=push_guide_toggle || (generic_guide_accepted &&
        wdata[13:7]==7'd110 && wdata[6]!=guide_mode);
    assign guide_prev=push_guide_prev || (generic_guide_accepted &&
        wdata[13:7]==7'd111 && wdata[6:0]==7'd0);
    assign guide_next=push_guide_next || (generic_guide_accepted &&
        wdata[13:7]==7'd111 && wdata[6:0]==7'd127);
    assign guide_select=push_guide_select || (generic_guide_accepted &&
        wdata[13:7]==7'd112 && wdata[6] && !generic_select_down);
    wire guide_chosen;
    wire [3:0] guide_browse;
    reg [4:0] guide_track_count;
    assign playlist_ready=1'b1;
    wire playlist_invalid=playlist_valid && playlist_ready &&
        playlist_word==16'hff00;
    // A recovered TF transport stall rescans and briefly invalidates the
    // playlist; the hold keeps the menu on the practice screen for that
    // window, and only a list that stays invalid clears the selection.
    push2_playlist_hold #(.HOLD_CYCLES(29'd480_000_000)) u_playlist_hold(
        .clk(clk),.reset_n(reset_n),
        .word_valid(playlist_valid && playlist_ready),.word(playlist_word),
        .track_count(guide_track_count));
    wire [6:0] guide_target_note;
    wire [63:0] guide_mask;
    wire [15:0] guide_score_count,guide_cursor;
    wire [15:0] guide_wrong_count;
    reg analysis_done_meta,analysis_done_sync;
    generate if(CNN_FOLLOW_ENABLE)begin: cnn_analysis_status
        always @(posedge clk or negedge reset_n)
            if(!reset_n)begin analysis_done_meta<=0;analysis_done_sync<=0;end
            else begin analysis_done_meta<=analysis_done;analysis_done_sync<=analysis_done_meta;end
    end else begin: no_cnn_analysis_status
        assign analysis_done_sync=1'b0;
    end endgenerate
    push2_controls #(.INITIAL_VOLUME(127)) controls(.clk(clk),.rst(input_reset),.connected(connected),
        .valid(valid && !generic_midi),.ready(map_ready),.kind(kind),.cable(cable),.channel(channel),.a(a),.b(b),
        .actual_control(control),.actual_options(options),.actual_panic_epoch(panic_epoch),
        .guide_enabled_i(CNN_FOLLOW_ENABLE),.guide_mode_i(guide_mode),
        .guide_toggle_o(push_guide_toggle),.guide_prev_o(push_guide_prev),
        .guide_next_o(push_guide_next),.guide_select_o(push_guide_select),
        .event_valid(mapped_valid),.event_ready(mapped_ready),.event_data(mapped_event),
        .held(held),.last_note(note),.last_velocity(velocity),.mapped(mapped),.ignored(ignored));
    reg [18:0] score_flush_count;
    wire score_flushing=score_flush_count!=0;
    generate if(CNN_FOLLOW_ENABLE)begin: cnn_follow
    push2_song_menu u_song_menu(.clk(clk),.rst(!reset_n),
        .toggle(guide_toggle),.mode(guide_mode),
        .prev(guide_prev),.next(guide_next),.select_key(guide_select),
        .track_count(guide_track_count),.chosen(guide_chosen),
        .browse_index(guide_browse),.track_index(track_index),.launch(track_launch));
    wire guide_score_ready;
    assign score_ready=score_flushing || guide_score_ready;
    always @(posedge clk or negedge reset_n)
        if(!reset_n) score_flush_count<=0;
        else if(track_launch || playlist_invalid) score_flush_count<=19'd480_000;
        else if(score_flushing) score_flush_count<=score_flush_count-1'b1;
    push2_score_guide u_guide(.clk(clk),.rst(!reset_n),
        .score_valid(score_valid && !score_flushing && !track_launch),
        .score_ready(guide_score_ready),.score_note(score_note),
        .toggle(guide_toggle),.selected_i(guide_chosen),.clear_i(track_launch || playlist_invalid),
        .played_valid((mapped_valid && mapped_ready &&
                       mapped_event[17:14]==4'd1 && mapped_event[6:0]!=7'd0) ||
                      generic_played),
        .played_note(generic_played ? wdata[13:7] : mapped_event[13:7]),.mode(guide_mode),
        .target_valid(guide_target_valid),.target_note(guide_target_note),
        .score_count(guide_score_count),.cursor(guide_cursor),
        .wrong_count(guide_wrong_count),.guide_mask(guide_mask));
    end else begin: no_cnn_follow
        assign score_flush_count=19'd0;
        assign guide_mode=1'b0;
        assign guide_chosen=1'b0;
        assign guide_browse=4'd0;
        assign track_index=4'd0;
        assign track_launch=1'b0;
        assign guide_target_valid=1'b0;
        assign guide_target_note=7'd0;
        assign guide_mask=64'd0;
        assign guide_score_count=16'd0;
        assign guide_cursor=16'd0;
        assign guide_wrong_count=16'd0;
        // The absent CNN producer must never backpressure unrelated owners.
        assign score_ready=1'b1;
    end endgenerate
    assign mapped_ready=fifo_ready && !input_reset && queue_write_ready;
    reg [31:0] generic_received;
    reg [6:0] generic_note,generic_velocity;
    // Resetting Push-local latches on a device boundary must not reset the
    // existing lifetime diagnostic count exposed at MMIO 0x3c/P138.
    reg [31:0] mapped_previous,mapped_lifetime;
    wire mapped_boundary=accepted && (raw_panic_fire ||
        (write && address==8'h00 && connected && !wdata[0]));
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin mapped_previous<=0;mapped_lifetime<=0;end
        else if(rst) begin mapped_previous<=0;mapped_lifetime<=0;end
        else begin
            mapped_previous<=input_reset ? 32'd0 : mapped;
            if(!input_reset)
                mapped_lifetime<=mapped_lifetime+mapped-mapped_previous+{31'd0,mapped_boundary};
        end
    end
    wire [31:0] total_mapped=mapped_lifetime+generic_received;
    wire [17:0] queued_event;
    wire queued_valid;
    // Reset the existing queue on detach/PANIC, including buffered DATA. No
    // second event store or DDR client is needed for initialization.
    gw138k_usb_event_fifo events(.usb_clk(clk),.audio_clk(audio_clk),.usb_rst(queue_fifo_reset),
        .w_data(mapped_valid ? mapped_event : wdata[17:0]),
        .w_en(!input_reset && queue_write_ready && ((mapped_valid && mapped_ready) ||
              (generic_accepted && !generic_guide_command && !generic_panic))),.w_rdy(fifo_ready),
        .r_data(queued_event),.r_en(queue_flushing || (audio_valid && audio_ready && !lifecycle_pending && !settle_wait)),.r_rdy(queued_valid));

    // Internal kind 15 is never a USB/PL command. It preempts buffered input
    // at the audio boundary to cancel stale events and apply attach defaults.
    // b=0 detach, b=1 attach (a[0] enables Push/GW25K defaults), b=2 PANIC.
    // Async assertion preserves even a short detach; release is synchronized.
    (* ASYNC_REG="TRUE" *) reg [1:0] online_sync,panic_sync,defaults_sync;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] audio_release;
    always @(posedge audio_clk or negedge event_qualified)
        if(!event_qualified) audio_release<=0;else audio_release<={audio_release[0],1'b1};
    wire audio_local_reset_n=audio_release[1];
    wire online_reset_n=audio_local_reset_n && connected;
    always @(posedge audio_clk or negedge online_reset_n)
        if(!online_reset_n) online_sync<=0;else online_sync<={online_sync[0],1'b1};
    always @(posedge audio_clk or negedge audio_local_reset_n)
        if(!audio_local_reset_n) begin panic_sync<=0;defaults_sync<=0;end
        else begin
            panic_sync<={panic_sync[0],panic_toggle};
            defaults_sync<={defaults_sync[0],(!generic_midi || gw25k)};
        end
    wire connection_changed=audio_online!=online_sync[1];
    assign lifecycle_pending=connection_changed || (audio_online && panic_seen!=panic_sync[1]);
    assign audio_lifecycle=lifecycle_pending || settle_wait;
    assign audio_cancel=lifecycle_pending;
    assign audio_valid=lifecycle_pending || settle_wait || (audio_online && online_sync[1] && !queue_flushing && queued_valid);
    assign audio_event=lifecycle_pending ?
        {4'd15,6'd0,(connection_changed && online_sync[1] && defaults_sync[1]),
         5'd0,(!connection_changed), (connection_changed && online_sync[1])} : settle_wait ? {4'd15,7'd0,7'd3} : queued_event;
    always @(posedge audio_clk or negedge audio_local_reset_n)
        if(!audio_local_reset_n) begin audio_online<=0;panic_seen<=0;settle_wait<=0;end
        else if(audio_valid && audio_ready && lifecycle_pending) begin
            audio_online<=online_sync[1];panic_seen<=panic_sync[1];settle_wait<=online_sync[1];
        end else if(audio_valid && audio_ready && settle_wait) settle_wait<=0;

    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin panic_toggle<=0;panic_flush<=0;panic_buttons<=0;end
        else begin
            panic_flush<=0;
            if(!connected) panic_buttons<=0;
            if(accepted && raw_panic) panic_buttons[wdata[23:16]==8'd29]<=raw_panic_down;
            if(accepted && (generic_panic || raw_panic_fire)) begin
                panic_toggle<=~panic_toggle;panic_flush<=1;
            end
        end
    end

    // Reuse the workstation's existing state-driven LED and display renderers.
    wire cv,cr;wire [1:0] ck;wire [6:0] ci;wire [7:0] cval;
    wire packet_valid;wire [9:0] packet_length;wire [7:0] packet_data;
    wire [31:0] commands;reg [8:0] packet_index;
    wire packet_ack=accepted && write && address==8'h44 && wdata==1;
    push2_lights lights(.clk(clk),.rst(!reset_n || !push_connected),.held(actual_held),.control(control),
        .score_mask(service_state_q[31:0]),.score_running(service_state_q[32]),.record_enabled(service_state_q[33]),
        .guide_mode(guide_mode),.guide_mask(guide_mask),
        .valid(cv),.ready(cr),.kind(ck),.index(ci),.value(cval));
    push2_led_tx led(.clk(clk),.rst(!reset_n || !push_connected),
        .cmd_valid(cv),.cmd_ready(cr),.cmd_kind(ck),.cmd_index(ci),.cmd_value(cval),.cmd_cable(4'd0),
        .packet_valid(packet_valid),.packet_length(packet_length),.packet_index(packet_index),
        .packet_data(packet_data),.packet_acked(packet_ack),.commands_acked(commands),.commands_rejected());
    reg [17:0] pixel_index;
    wire frame_capture=accepted && write && address==8'h08;
    wire [15:0] pixel;
    push2_surface_pixels #(.PIPELINED(1)) pixels(.clk(clk),.rst(!reset_n || !push_connected),
        .frame_ready(frame_capture),.frame_start(),.x(pixel_index[9:0]),.y(pixel_index[17:10]),
        .pixel_valid(),.pixel(pixel),.control(control),.options(options),.held(actual_held),
        .note(note),.velocity(velocity),.display_meta(display_meta_q),
        .score_mask(service_state_q[31:0]),.score_running(service_state_q[32]),.record_enabled(service_state_q[33]),
        .guide_mode(guide_mode),.guide_chosen(guide_chosen),
        .guide_browse(guide_browse),.guide_track(track_index),
        .guide_track_count(guide_track_count),.guide_score_count(guide_score_count),
        .guide_cursor(guide_cursor),.guide_analysis_done(analysis_done_sync),
        .name_write_valid(playlist_valid && playlist_ready && playlist_word[15:8]!=8'hff),
        .name_write_addr(playlist_word[15:8]),.name_write_data(playlist_word[7:0]),
        // Keep the rendered bytes identical when a packet is regenerated
        // after NAK, just as the other UI fields are held for the whole frame.
        .display_meta_valid(display_meta_seen && frame_capture));
    // Read response is captured by the SoC in the accepting bus cycle.
    always @* begin
        rdata=0;
        case(address)
            8'h00:rdata={29'd0,gw25k,generic_midi,connected};
            8'h10:rdata=control;
            8'h14:rdata=options;
            8'h18:rdata=snapshot[287:256];
            8'h1c:rdata=actual_held[31:0];
            8'h20:rdata=actual_held[63:32];
            8'h24:rdata=generic_midi ? {18'd0,generic_velocity,generic_note} :
                                     {18'd0,velocity,note};
            8'h2c:rdata=pixel_index[9:0]<960?{16'd0,pixel_q}:32'd0;
            8'h30:rdata=frames;
            8'h34:rdata=out_errors;
            8'h38:rdata=received;
            8'h3c:rdata=total_mapped;
            8'h40:rdata={packet_valid,21'd0,packet_length};
            8'h4c:rdata={24'd0,packet_data};
            8'h58:rdata=in_diagnostics;
            8'h5c:rdata={guide_mode,guide_target_valid,guide_score_count[7:0],
                         guide_cursor[7:0],guide_chosen,guide_target_note,6'd0};
            // Unpacked feedback for a non-Push host. The service score mask
            // uses MIDI notes 36..67; guide_target_note is a raw MIDI pitch.
            8'h60:rdata={6'd0,track_index,guide_track_count,guide_browse,
                         service_state_q[33:32],analysis_done_sync,guide_chosen,
                         guide_mode,guide_target_valid,guide_target_note};
            8'h64:rdata=service_state_q[31:0];
            8'h68:rdata={guide_score_count,guide_cursor};
            8'h6c:rdata={16'd0,guide_wrong_count};
            default:rdata=0;
        endcase
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n)begin
            connected<=0;generic_midi<=0;gw25k<=0;generic_received<=0;
            generic_note<=0;generic_velocity<=0;generic_select_down<=0;
            received<=0;frames<=0;out_errors<=0;in_diagnostics<=0;pixel_index<=0;packet_index<=0;
            pixel_loaded<=0;pixel_wait<=0;pixel_q<=0;
        end else if(accepted)begin
            if(write)case(address)
                8'h00:begin
                    connected<=wdata[0];generic_midi<=wdata[0] && wdata[1];
                    gw25k<=wdata[0] && wdata[1] && wdata[2];
                    if(!wdata[0] || !wdata[1])begin
                        generic_note<=0;generic_velocity<=0;generic_select_down<=0;
                    end
                end
                8'h04:received<=received+1'b1;
                8'h54:begin
                    received<=received+1'b1;generic_received<=generic_received+1'b1;
                    if(generic_guide_command && wdata[13:7]==7'd112)
                        generic_select_down<=wdata[6];
                    else if((wdata[17:14]==4'd1 && wdata[6:0]!=0) || wdata[17:14]==4'd5)begin
                        generic_note<=wdata[13:7];generic_velocity<=wdata[6:0];
                    end else if((wdata[17:14]==4'd0 ||
                                 (wdata[17:14]==4'd1 && wdata[6:0]==0)) &&
                                wdata[13:7]==generic_note)generic_velocity<=0;
                    else if(wdata[17:14]==4'd2 &&
                            (wdata[13:7]==7'd120 || wdata[13:7]==7'd123))begin
                        generic_note<=0;generic_velocity<=0;
                    end
                end
                8'h08:begin pixel_index<=0;pixel_loaded<=0;pixel_wait<=0;end
                8'h28:begin pixel_index<=wdata[17:0];pixel_loaded<=0;pixel_wait<=0;end // Rewind an unacknowledged screen packet.
                8'h30:frames<=wdata;
                8'h34:out_errors<=wdata;
                8'h58:in_diagnostics<=wdata;
                8'h48:packet_index<=wdata[8:0];
                default:begin end
            endcase
            else if(address==8'h2c)begin pixel_index<=pixel_index+1'b1;pixel_loaded<=0;pixel_wait<=0;end
            else if(address==8'h4c)packet_index<=packet_index+1'b1;
        end else if(!pixel_loaded) begin
            // Renderer registers character/background before the font. The
            // index and frame snapshot must cross that stage before capture.
            if(!pixel_wait)pixel_wait<=1;
            else begin pixel_q<=pixel;pixel_loaded<=1;end
        end
    end
    // P138 word 6 carries four saturating USB IN counters: disconnects, normal
    // NAKs, duplicate DATA, and transfer/protocol errors. Bit 8 identifies
    // this USB-A route; the other established counters retain their positions.
    assign telemetry={out_errors,in_diagnostics,frames,commands,total_mapped,received,
                      23'd0,1'b1,6'd0,connected,1'b1};
endmodule
