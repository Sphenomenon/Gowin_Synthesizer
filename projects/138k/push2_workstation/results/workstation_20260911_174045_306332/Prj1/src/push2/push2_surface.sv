module push2_surface(input wire clk,rst,audio_clk,audio_reset_n,pc_rx,
    input wire [447:0] performance_words,
    output wire htclk,htreq,htvld,input wire htrdy,
    input wire hrclk,hrreq,hrvld,output wire hrack,inout wire [15:0] hd,
    output wire audio_valid,input wire audio_ready,output wire [17:0] audio_event,
    output wire [223:0] telemetry);
    wire enable;
    push2_host_gate gate(.clk(clk),.rst(rst),.serial_in(pc_rx),.enabled(enable));
    wire configured,hs;wire [15:0] vid,pid;wire [6:0] address;
    wire [7:0] dep,mep,host_state,enum_error,hspi_errors;wire [10:0] dm,mm;
    wire req,req_ready,td1,tvalid,tready,tlast,tdone;wire [2:0] tresp;
    wire [6:0] taddr;wire [3:0] tep;wire [9:0] tlength;wire [7:0] tdata;
    wire raw_valid,raw_ready;wire [31:0] raw;
    wire [31:0] replies,link_errors,in_errors,packets;
    push2_hspi_link link(.clk(clk),.rst(rst),.host_enable(enable),
        .htclk(htclk),.htreq(htreq),.htvld(htvld),.htrdy(htrdy),.hrclk(hrclk),.hrreq(hrreq),.hrvld(hrvld),.hrack(hrack),.hd(hd),
        .req_valid(req),.req_ready(req_ready),.req_address(taddr),.req_endpoint(tep),.req_data1(td1),.req_length(tlength),
        .tx_valid(tvalid),.tx_ready(tready),.tx_data(tdata),.tx_last(tlast),.out_done(tdone),.out_response(tresp),
        .midi_valid(raw_valid),.midi_ready(raw_ready),.midi_event(raw),.configured(configured),.high_speed(hs),
        .vid(vid),.pid(pid),.address(address),.display_ep(dep),.midi_ep(mep),.display_mps(dm),.midi_mps(mm),
        .replies(replies),.link_errors(link_errors),.usb_in_errors(in_errors),.usb_packets(packets),
        .host_state(host_state),.enum_error(enum_error),.hspi_errors(hspi_errors));
    wire valid,ready;wire [3:0] kind,cable,channel;wire [6:0] a,b;
    // Independent input decoder: a stopped display scheduler cannot stop MIDI.
    push2_midi_rx midi(.clk(clk),.rst(rst || !configured),.usb_valid(raw_valid),.usb_ready(raw_ready),.usb_event(raw),
        .event_valid(valid),.event_ready(ready),.event_kind(kind),.event_channel(channel),.event_cable(cable),
        .event_data1(a),.event_data2(b),.event_pitch(),.events_received(),.packets_ignored());
    // Reuse the original telemetry's completed 50 MHz snapshot. No duplicate
    // CDC or extra load on the audio domain; this bus is already coherent.
    wire [447:0] snapshot=performance_words;
    wire [31:0] control=snapshot[63:32], options=snapshot[255:224];
    wire [63:0] actual_held=snapshot[195:132];
    wire mapped_valid,mapped_ready;wire [17:0] mapped_event;wire [63:0] held;wire[6:0]note,velocity;
    wire [31:0] mapped,ignored;
    push2_controls controls(.clk(clk),.rst(rst),.connected(configured),
        .valid(valid),.ready(ready),.kind(kind),.cable(cable),.channel(channel),.a(a),.b(b),
        .actual_control(control),.actual_options(options),.event_valid(mapped_valid),.event_ready(mapped_ready),
        .event_data(mapped_event),.held(held),.last_note(note),.last_velocity(velocity),.mapped(mapped),.ignored(ignored));
    // Source reset asserts with either domain reset and releases on clk.
    // The generated FIFO separately synchronizes its read-side reset.
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] event_release;
    wire event_qualified=!rst && audio_reset_n;
    always @(posedge clk or negedge event_qualified)
        if(!event_qualified) event_release<=0;else event_release<={event_release[1:0],1'b1};
    gw138k_usb_event_fifo events(.usb_clk(clk),.audio_clk(audio_clk),.usb_rst(!event_release[2]),
        .w_data(mapped_event),.w_en(mapped_valid && mapped_ready),.w_rdy(mapped_ready),
        .r_data(audio_event),.r_en(audio_valid && audio_ready),.r_rdy(audio_valid));
    wire session,fault;wire [3:0] fault_code;wire [31:0] frames,commands;
    wire cv,cr;wire [1:0] ck;wire [6:0] ci;wire [7:0] cval;
    wire fs,fr,pv,pr;wire [15:0]pixel;wire [9:0]x;wire [7:0]y;
    push2_lights lights(.clk(clk),.rst(rst || !session),.held(actual_held),.control(control),
        .valid(cv),.ready(cr),.kind(ck),.index(ci),.value(cval));
    push2_surface_pixels pixels(.clk(clk),.rst(rst || !session),.frame_ready(fr),.frame_start(fs),
        .x(x),.y(y),.pixel_valid(pv),.pixel(pixel),.control(control),.options(options),
        .held(actual_held),.note(note),.velocity(velocity));
    push2_driver_core #(.RETRY_DELAY_CYCLES(6250),.WATCHDOG_CYCLES(5000000)) driver(
        .clk(clk),.rst(rst),.usb_configured(configured),.usb_high_speed(hs),.usb_vid(vid),.usb_pid(pid),
        .usb_address(address),.usb_display_out(dep),.usb_display_mps(dm),.usb_midi_out(mep),.usb_midi_mps(mm),.session_ready(session),
        .cmd_valid(cv),.cmd_ready(cr),.cmd_kind(ck),.cmd_index(ci),.cmd_value(cval),.cmd_cable(4'd0),
        .frame_start(fs),.frame_ready(fr),.frame_done(),.pixel_valid(pv),.pixel_ready(pr),.pixel_bgr565(pixel),.pixel_x(x),.pixel_y(y),
        .usb_rx_valid(1'b0),.usb_rx_ready(),.usb_rx_event(32'd0),.event_valid(),.event_ready(1'b1),
        .event_kind(),.event_channel(),.event_cable(),.event_data1(),.event_data2(),.event_pitch(),
        .out_req_valid(req),.out_req_ready(req_ready),.out_device_address(taddr),.out_endpoint(tep),.out_data1(td1),.out_length(tlength),
        .out_valid(tvalid),.out_ready(tready),.out_data(tdata),.out_last(tlast),.out_done(tdone),.out_response(tresp),
        .busy(),.fault(fault),.fault_code(fault_code),.packets_acked(),.nak_count(),.retry_count(),
        .frames_acked(frames),.pixels_accepted(),.commands_acked(commands),.commands_rejected(),.events_received(),.packets_ignored());
    assign telemetry={link_errors,in_errors,frames,commands,mapped,replies,
                      hspi_errors,enum_error,host_state,fault_code,hs,fault,configured,enable};
endmodule
