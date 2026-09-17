// USB Host CPU MMIO -> existing Push mapper -> audio event FIFO.
// USB runs at 48 MHz; sample processing remains in the 76.8 MHz audio domain.
module push2_usb_a_control(
    input wire clk,reset_n,audio_clk,audio_reset_n,
    input wire feedback_clk,feedback_reset_n,
    input wire [447:0] performance_words,
    input wire [63:0] display_meta_data,
    input wire display_meta_valid,
    input wire [33:0] service_state_data,
    input wire service_state_valid,
    input wire select,write,input wire [7:0] address,
    input wire [31:0] wdata,output wire ready,output reg [31:0] rdata,
    output wire audio_valid,input wire audio_ready,output wire [17:0] audio_event,
    output wire [223:0] telemetry
);
    reg [11:0] feedback_divider;
    always @(posedge feedback_clk or negedge feedback_reset_n)
        if(!feedback_reset_n) feedback_divider<=0;else feedback_divider<=feedback_divider+1'b1;
    wire [447:0] snapshot;
    gw138k_stream_cdc #(.WIDTH(448)) feedback(
        .reset_n(reset_n && feedback_reset_n),.source_clk(feedback_clk),.destination_clk(clk),
        .source_valid(&feedback_divider),.source_data(performance_words),.drop_count(),
        .destination_valid(),.destination_data(snapshot));
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
    reg connected,generic_midi;
    wire push_connected=connected && !generic_midi;
    reg [31:0] received,frames,out_errors;
    wire raw_ready,valid,map_ready;wire [3:0] kind,cable,channel;wire [6:0] a,b;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] event_release;
    wire event_qualified=reset_n && audio_reset_n;
    always @(posedge clk or negedge event_qualified)
        if(!event_qualified) event_release<=0;else event_release<={event_release[1:0],1'b1};
    wire rst=!event_release[2];
    // A CPU store is acknowledged only when the decoder accepts the word.
    // Full event FIFO stalls the USB CPU, never the audio sample clock.
    wire raw_store=select && write && address==8'h04;
    wire generic_store=select && write && address==8'h54;
    wire fifo_ready;
    wire mapped_valid,mapped_ready;wire [17:0] mapped_event;
    // Both routes share the existing audio FIFO. Push/disconnect PANIC has
    // priority over a generic store; the USB CPU waits if the FIFO is full.
    assign ready=select && (raw_store ? (raw_ready && !rst && push_connected) :
        generic_store ? (fifo_ready && !mapped_valid && !rst && connected && generic_midi) : 1'b1);
    wire accepted=select && ready;
    push2_midi_rx midi(.clk(clk),.rst(rst || !connected),
        .usb_valid(raw_store && !rst && push_connected),.usb_ready(raw_ready),.usb_event(wdata),
        .event_valid(valid),.event_ready(map_ready),.event_kind(kind),.event_cable(cable),
        .event_channel(channel),.event_data1(a),.event_data2(b),.event_pitch(),
        .events_received(),.packets_ignored());
    wire [63:0] held;wire [6:0] note,velocity;wire [31:0] mapped,ignored;
    push2_controls controls(.clk(clk),.rst(rst),.connected(connected),
        .valid(valid && !generic_midi),.ready(map_ready),.kind(kind),.cable(cable),.channel(channel),.a(a),.b(b),
        .actual_control(control),.actual_options(options),.actual_panic_epoch(panic_epoch),
        .event_valid(mapped_valid),.event_ready(mapped_ready),.event_data(mapped_event),
        .held(held),.last_note(note),.last_velocity(velocity),.mapped(mapped),.ignored(ignored));
    assign mapped_ready=fifo_ready;
    reg [31:0] generic_received;
    wire [31:0] total_mapped=mapped+generic_received;
    gw138k_usb_event_fifo events(.usb_clk(clk),.audio_clk(audio_clk),.usb_rst(rst),
        .w_data(mapped_valid ? mapped_event : wdata[17:0]),
        .w_en((mapped_valid && mapped_ready) || (generic_store && accepted)),.w_rdy(fifo_ready),
        .r_data(audio_event),.r_en(audio_valid && audio_ready),.r_rdy(audio_valid));

    // Reuse the workstation's existing state-driven LED and display renderers.
    wire cv,cr;wire [1:0] ck;wire [6:0] ci;wire [7:0] cval;
    wire packet_valid;wire [9:0] packet_length;wire [7:0] packet_data;
    wire [31:0] commands;reg [8:0] packet_index;
    wire packet_ack=accepted && write && address==8'h44 && wdata==1;
    push2_lights lights(.clk(clk),.rst(!reset_n || !push_connected),.held(actual_held),.control(control),
        .score_mask(service_state_q[31:0]),.score_running(service_state_q[32]),.record_enabled(service_state_q[33]),
        .valid(cv),.ready(cr),.kind(ck),.index(ci),.value(cval));
    push2_led_tx led(.clk(clk),.rst(!reset_n || !push_connected),
        .cmd_valid(cv),.cmd_ready(cr),.cmd_kind(ck),.cmd_index(ci),.cmd_value(cval),.cmd_cable(4'd0),
        .packet_valid(packet_valid),.packet_length(packet_length),.packet_index(packet_index),
        .packet_data(packet_data),.packet_acked(packet_ack),.commands_acked(commands),.commands_rejected());
    reg [17:0] pixel_index;
    wire frame_capture=accepted && write && address==8'h08;
    wire [15:0] pixel;
    push2_surface_pixels pixels(.clk(clk),.rst(!reset_n || !push_connected),
        .frame_ready(frame_capture),.frame_start(),.x(pixel_index[9:0]),.y(pixel_index[17:10]),
        .pixel_valid(),.pixel(pixel),.control(control),.options(options),.held(actual_held),
        .note(note),.velocity(velocity),.display_meta(display_meta_q),
        .score_mask(service_state_q[31:0]),.score_running(service_state_q[32]),.record_enabled(service_state_q[33]),
        // Keep the rendered bytes identical when a packet is regenerated
        // after NAK, just as the other UI fields are held for the whole frame.
        .display_meta_valid(display_meta_seen && frame_capture));
    // Read response is captured by the SoC in the accepting bus cycle.
    always @* begin
        rdata=0;
        case(address)
            8'h00:rdata={30'd0,generic_midi,connected};
            8'h10:rdata=control;
            8'h14:rdata=options;
            8'h18:rdata=snapshot[287:256];
            8'h1c:rdata=actual_held[31:0];
            8'h20:rdata=actual_held[63:32];
            8'h24:rdata={18'd0,velocity,note};
            8'h2c:rdata=pixel_index[9:0]<960?{16'd0,pixel}:32'd0;
            8'h30:rdata=frames;
            8'h34:rdata=out_errors;
            8'h38:rdata=received;
            8'h3c:rdata=total_mapped;
            8'h40:rdata={packet_valid,21'd0,packet_length};
            8'h4c:rdata={24'd0,packet_data};
            default:rdata=0;
        endcase
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n)begin
            connected<=0;generic_midi<=0;generic_received<=0;
            received<=0;frames<=0;out_errors<=0;pixel_index<=0;packet_index<=0;
        end else if(accepted)begin
            if(write)case(address)
                8'h00:begin connected<=wdata[0];generic_midi<=wdata[0] && wdata[1];end
                8'h04:received<=received+1'b1;
                8'h54:begin received<=received+1'b1;generic_received<=generic_received+1'b1;end
                8'h08:pixel_index<=0;
                8'h28:pixel_index<=wdata[17:0]; // Rewind an unacknowledged screen packet.
                8'h30:frames<=wdata;
                8'h34:out_errors<=wdata;
                8'h48:packet_index<=wdata[8:0];
                default:begin end
            endcase
            else if(address==8'h2c)pixel_index<=pixel_index+1'b1;
            else if(address==8'h4c)packet_index<=packet_index+1'b1;
        end
    end
    // Existing P138 fields: errors, IN errors (unavailable), frames, LEDs,
    // mapped events, received words, flags. Bit 8 identifies this USB-A route.
    assign telemetry={out_errors,32'hffffffff,frames,commands,total_mapped,received,
                      23'd0,1'b1,6'd0,connected,1'b1};
endmodule
