// Gowin USER/ER1 mailbox. IR 0x42 is the instruction used by vendor GAO.
// 128-bit LSB-first requests: magic, tag/op, address/argument, data/command.
// Request/reply bundles are held stable across synchronized toggle handshakes.
module wifi_jtag_mailbox(
    input wire clk,
    input wire tck_pad_i,tms_pad_i,tdi_pad_i,
    output wire tdo_pad_o,
    output reg request=0,
    output reg [95:0] request_data=0,
    input wire reply,
    input wire [95:0] reply_data
);
    wire tck=tck_pad_i,tdi=tdi_pad_i;
    // Track the standard TAP on its physical clock. This also avoids relying
    // on device-specific gating of the GW_JTAG internal DR clock.
    reg [3:0] tap_state=0;
    reg [7:0] instruction=0,instruction_shift=0;
    wire reset_jtag=tap_state==0;
    wire shift_capture=tap_state==3 || tap_state==4;
    wire update=tap_state==8;
    wire enabled=instruction==8'h42;
    always @(posedge tck) begin
        if(tap_state==0) instruction<=0;
        if(tap_state==10) instruction_shift<=1;
        if(tap_state==11) instruction_shift<={tdi,instruction_shift[7:1]};
        if(tap_state==15) instruction<=instruction_shift;
        case(tap_state)
            0:tap_state<=tms_pad_i?0:1; 1:tap_state<=tms_pad_i?2:1;
            2:tap_state<=tms_pad_i?9:3; 3:tap_state<=tms_pad_i?5:4;
            4:tap_state<=tms_pad_i?5:4; 5:tap_state<=tms_pad_i?8:6;
            6:tap_state<=tms_pad_i?7:6; 7:tap_state<=tms_pad_i?8:4;
            8:tap_state<=tms_pad_i?2:1; 9:tap_state<=tms_pad_i?0:10;
            10:tap_state<=tms_pad_i?12:11; 11:tap_state<=tms_pad_i?12:11;
            12:tap_state<=tms_pad_i?15:13; 13:tap_state<=tms_pad_i?14:13;
            14:tap_state<=tms_pad_i?15:11; 15:tap_state<=tms_pad_i?2:1;
        endcase
    end
    reg [127:0] shift_register=0, visible_reply=128'h31505357;
    GW_JTAG tap(.tms_pad_i(tms_pad_i),.tck_pad_i(tck_pad_i),.tdi_pad_i(tdi_pad_i),
        .tdo_pad_o(tdo_pad_o),.tck_o(),.tdi_o(),.test_logic_reset_o(),
        .shift_dr_capture_dr_o(),.update_dr_o(),.enable_er1_o(),
        .enable_er2_o(),.run_test_idle_er1_o(),.run_test_idle_er2_o(),.pause_dr_o(),
        .tdo_er1_i(shift_register[0]),.tdo_er2_i(1'b0));
    reg [95:0] held_request=0, held_reply=0;
    reg request_toggle=0, reply_toggle=0;
    reg was_shift=0,was_update=0;
    reg [7:0] shifted=0;
    (* ASYNC_REG="TRUE" *) reg ack1=0,ack2=0;
    reg seen_ack=0;
    always @(posedge tck) begin
        ack1<=reply_toggle; ack2<=ack1;
        if(ack2!=seen_ack) begin
            visible_reply<={held_reply,32'h31505357}; seen_ack<=ack2;
        end
        was_shift<=enabled && shift_capture;
        was_update<=enabled && update;
        if(reset_jtag || !enabled) begin shifted<=0; was_shift<=0; was_update<=0; end
        else if(shift_capture) begin
            if(!was_shift) begin shift_register<=visible_reply; shifted<=0; end
            else begin
                shift_register<={tdi,shift_register[127:1]};
                if(shifted<129) shifted<=shifted+1'b1;
            end
        end
        if(enabled && update && !was_update && shifted==128 && shift_register[31:0]==32'h47544a57) begin
            held_request<=shift_register[127:32]; request_toggle<=!request_toggle;
        end
    end
    (* ASYNC_REG="TRUE" *) reg req1=0,req2=0;
    reg seen_request=0;
    always @(posedge clk) begin
        req1<=request_toggle; req2<=req1; request<=0;
        if(req2!=seen_request) begin
            request_data<=held_request; request<=1; seen_request<=req2;
        end
        if(reply) begin held_reply<=reply_data; reply_toggle<=!reply_toggle; end
    end
endmodule
