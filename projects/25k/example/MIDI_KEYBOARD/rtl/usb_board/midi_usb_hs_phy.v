//-----------------------------------------------------------------
//                       USB CDC Device
//                            V0.1
//                     Ultra-Embedded.com
//                     Copyright 2014-2019
//
//                 Email: admin@ultra-embedded.com
//
//                         License: LGPL
//-----------------------------------------------------------------
//
// This source file may be used and distributed without         
// restriction provided that this copyright statement is not    
// removed from the file and that any derivative work contains  
// the original copyright notice and the associated disclaimer. 
//
// This source file is free software; you can redistribute it   
// and/or modify it under the terms of the GNU Lesser General   
// Public License as published by the Free Software Foundation; 
// either version 2.1 of the License, or (at your option) any   
// later version.
//
// This source is distributed in the hope that it will be       
// useful, but WITHOUT ANY WARRANTY; without even the implied   
// warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR      
// PURPOSE.  See the GNU Lesser General Public License for more 
// details.
//
// You should have received a copy of the GNU Lesser General    
// Public License along with this source; if not, write to the 
// Free Software Foundation, Inc., 59 Temple Place, Suite 330, 
// Boston, MA  02111-1307  USA
//-----------------------------------------------------------------

//-----------------------------------------------------------------
//                          Generated File
//-----------------------------------------------------------------


// Derived from USB3300_HS/hs/usb_cdc_core.v transceiver control.
// Copyright 2014-2019 Ultra-Embedded.com; LGPL-2.1-or-later.
// Original license/disclaimer retained in vendor/LICENSE-LGPL-2.1.
module midi_usb_hs_phy(input wire clk,reset,enable,se0_reset,bus_active,
 input wire[1:0]line_state,output wire[1:0]opmode,xcvr,
 output wire termsel,dppd,dmpd,chirp,high_speed,bus_reset,suspended,output wire[2:0]state);
localparam STATE_W                       = 3;
localparam STATE_IDLE                    = 3'd0;
localparam STATE_WAIT_RST                = 3'd1;
localparam STATE_SEND_CHIRP_K            = 3'd2;
localparam STATE_WAIT_CHIRP_JK           = 3'd3;
localparam STATE_FULLSPEED               = 3'd4;
localparam STATE_HIGHSPEED               = 3'd5;
localparam STATE_HS_SUSPEND              = 3'd6;
localparam STATE_HS_RESUME               = 3'd7;
reg [STATE_W-1:0] state_q;
reg [STATE_W-1:0] next_state_r;

// 60MHz clock rate
`define USB_RST_W  20
reg [`USB_RST_W-1:0] usb_rst_time_q;
reg [7:0]            chirp_count_q;
reg [1:0]            last_linestate_q;

localparam DETACH_TIME    = 20'd60000;  // 1ms -> T0
localparam ATTACH_FS_TIME = 20'd180000; // T0 + 3ms = T1
localparam CHIRPK_TIME    = 20'd246000; // T1 + ~1ms
localparam HS_RESET_TIME  = 20'd600000; // T0 + 10ms = T9
localparam HS_CHIRP_COUNT = 8'd6;
localparam SUSPEND_TIME   = 18'd180000; // 3ms without bus activity
localparam FS_SETTLE_TIME = 13'd7500;   // 125us after restoring FS termination
reg [7:0] chirp_stable_q;
reg       chirp_qualified_q;
reg [17:0] idle_time_q;
reg [12:0] fs_settle_q;
reg fs_suspended_q;
reg fs_reset_armed_q;

reg [  1:0]  utmi_op_mode_r;
reg [  1:0]  utmi_xcvrselect_r;
reg          utmi_termselect_r;
reg          utmi_dppulldown_r;
reg          utmi_dmpulldown_r;

always @ *
begin
    next_state_r = state_q;

    // Default - disconnect
    utmi_op_mode_r    = 2'd1;
    utmi_xcvrselect_r = 2'd0;
    utmi_termselect_r = 1'b0;
    utmi_dppulldown_r = 1'b0;
    utmi_dmpulldown_r = 1'b0;

    case (state_q)
    STATE_IDLE:
    begin
        // Detached
        if (enable && usb_rst_time_q >= DETACH_TIME)
            next_state_r = STATE_WAIT_RST;
    end
    STATE_WAIT_RST:
    begin
        // Assert FS mode, check for SE0 (T0)
        utmi_op_mode_r    = 2'd0;
        utmi_xcvrselect_r = 2'd1;
        utmi_termselect_r = 1'b1;
        utmi_dppulldown_r = 1'b0;
        utmi_dmpulldown_r = 1'b0;

        // Wait for SE0 (T1), send device chirp K
        if (usb_rst_time_q >= ATTACH_FS_TIME)
            next_state_r = STATE_SEND_CHIRP_K;
    end
    STATE_SEND_CHIRP_K:
    begin
        // Send chirp K
        utmi_op_mode_r    = 2'd2;
        utmi_xcvrselect_r = 2'd0;
        utmi_termselect_r = 1'b1;
        utmi_dppulldown_r = 1'b0;
        utmi_dmpulldown_r = 1'b0;

        // End of device chirp K (T2)
        if (usb_rst_time_q >= CHIRPK_TIME)
            next_state_r = STATE_WAIT_CHIRP_JK;
    end
    STATE_WAIT_CHIRP_JK:
    begin
        // Stop sending chirp K and wait for downstream port chirps
        utmi_op_mode_r    = 2'd2;
        utmi_xcvrselect_r = 2'd0;
        utmi_termselect_r = 1'b1;
        utmi_dppulldown_r = 1'b0;
        utmi_dmpulldown_r = 1'b0;

        // Required number of chirps detected, move to HS mode (T7)
        if (chirp_count_q >= HS_CHIRP_COUNT)
            next_state_r = STATE_HIGHSPEED;
        // Time out waiting for chirps, fallback to FS mode
        else if (usb_rst_time_q >= HS_RESET_TIME)
            next_state_r = STATE_FULLSPEED;
    end
    STATE_FULLSPEED:
    begin
        utmi_op_mode_r    = 2'd0;
        utmi_xcvrselect_r = 2'd1;
        utmi_termselect_r = 1'b1;
        utmi_dppulldown_r = 1'b0;
        utmi_dmpulldown_r = 1'b0;

        // USB reset detected...
        if (fs_reset_armed_q && se0_reset && line_state == 2'b00)
            next_state_r = STATE_WAIT_RST;
    end
    STATE_HIGHSPEED:
    begin
        // Enter HS mode
        utmi_op_mode_r    = 2'd0;
        utmi_xcvrselect_r = 2'd0;
        utmi_termselect_r = 1'b0;
        utmi_dppulldown_r = 1'b0;
        utmi_dmpulldown_r = 1'b0;

        // HS idle is SE0, so inactivity alone is not a bus reset. Restore
        // FS termination after 3ms, then distinguish J(suspend) from SE0.
        if (idle_time_q >= SUSPEND_TIME)
            next_state_r = STATE_HS_SUSPEND;
    end
    STATE_HS_SUSPEND:
    begin
        utmi_op_mode_r    = 2'd0;
        utmi_xcvrselect_r = 2'd1;
        utmi_termselect_r = 1'b1;
        if (fs_settle_q >= FS_SETTLE_TIME && line_state == 2'b00)
            next_state_r = STATE_WAIT_RST;
        else if (line_state == 2'b10)
            next_state_r = STATE_HS_RESUME;
    end
    STATE_HS_RESUME:
    begin
        // Host-driven resume K is received in FS mode. Its terminating
        // SE0 EOP returns the previously negotiated connection to HS.
        utmi_op_mode_r    = 2'd0;
        utmi_xcvrselect_r = 2'd1;
        utmi_termselect_r = 1'b1;
        if (line_state == 2'b00)
            next_state_r = STATE_HIGHSPEED;
    end
    default:
        ;
    endcase
end

// Update state
always @ (posedge clk or posedge reset)
if (reset)
    state_q   <= STATE_IDLE;
else if (!enable)
    state_q <= STATE_IDLE;
else
    state_q   <= next_state_r;

always @(posedge clk or posedge reset)
if (reset)
    fs_reset_armed_q <= 1'b0;
else if (!enable || state_q != STATE_FULLSPEED)
    fs_reset_armed_q <= 1'b0;
else if (line_state == 2'b01)
    fs_reset_armed_q <= 1'b1;

// The ULPI clock remains running during suspend: no PHY low-power command
// is issued. Pending endpoint/FIFO payloads and configuration remain intact.
always @(posedge clk or posedge reset)
if (reset)
begin
    idle_time_q <= 0;
    fs_settle_q <= 0;
    fs_suspended_q <= 0;
end
else
begin
    if (!enable || bus_active ||
        (state_q == STATE_HIGHSPEED && line_state != 2'b00) ||
        (state_q == STATE_FULLSPEED && line_state != 2'b01) ||
        (state_q != STATE_HIGHSPEED && state_q != STATE_FULLSPEED))
        idle_time_q <= 0;
    else if (idle_time_q < SUSPEND_TIME)
        idle_time_q <= idle_time_q + 1'b1;
    if (state_q != STATE_HS_SUSPEND)
        fs_settle_q <= 0;
    else if (fs_settle_q < FS_SETTLE_TIME)
        fs_settle_q <= fs_settle_q + 1'b1;
    if (state_q != STATE_FULLSPEED || bus_active || line_state != 2'b01)
        fs_suspended_q <= 0;
    else if (idle_time_q >= SUSPEND_TIME)
        fs_suspended_q <= 1;
end

// Time since T0 (start of HS reset)
always @ (posedge clk or posedge reset)
if (reset)
    usb_rst_time_q <= `USB_RST_W'b0;
// Entering wait for reset state
else if (next_state_r == STATE_WAIT_RST && state_q != STATE_WAIT_RST)
    usb_rst_time_q <= state_q == STATE_HS_SUSPEND ? ATTACH_FS_TIME : `USB_RST_W'b0;
// Waiting for reset, reset count on line state toggle
else if (state_q == STATE_WAIT_RST && (line_state != 2'b00))
    usb_rst_time_q <=  `USB_RST_W'b0;
else if (usb_rst_time_q != {(`USB_RST_W){1'b1}})
    usb_rst_time_q <= usb_rst_time_q + `USB_RST_W'd1;

always @ (posedge clk or posedge reset)
if (reset)
    last_linestate_q   <= 2'b0;
else
    last_linestate_q   <= line_state;

// Accept the required K-J-K-J-K-J sequence only after each state has
// persisted for 2.5 us (150 cycles at 60 MHz). Ignore SE0/SE1 and glitches.
always @ (posedge clk or posedge reset)
if (reset)
begin
    chirp_count_q     <= 8'b0;
    chirp_stable_q    <= 8'b0;
    chirp_qualified_q <= 1'b0;
end
else if (state_q != STATE_WAIT_CHIRP_JK)
begin
    chirp_count_q     <= 8'b0;
    chirp_stable_q    <= 8'b0;
    chirp_qualified_q <= 1'b0;
end
else if (last_linestate_q != line_state)
begin
    chirp_stable_q    <= 8'd1;
    chirp_qualified_q <= 1'b0;
end
else if (!chirp_qualified_q)
begin
    if (chirp_stable_q < 8'd150)
        chirp_stable_q <= chirp_stable_q + 8'd1;
    if (chirp_stable_q == 8'd149)
    begin
        chirp_qualified_q <= 1'b1;
        if (line_state == (chirp_count_q[0] ? 2'b01 : 2'b10))
            chirp_count_q <= chirp_count_q + 8'd1;
        else if (line_state == 2'b10)
            chirp_count_q <= 8'd1;
        else
            chirp_count_q <= 8'd0;
    end
end

assign state = state_q;
assign opmode    = utmi_op_mode_r;
assign xcvr = utmi_xcvrselect_r;
assign termsel = utmi_termselect_r;
assign dppd = utmi_dppulldown_r;
assign dmpd = utmi_dmpulldown_r;

assign chirp   = (state_q == STATE_SEND_CHIRP_K);
assign high_speed = state_q == STATE_HIGHSPEED ||
                    state_q == STATE_HS_SUSPEND || state_q == STATE_HS_RESUME;
assign suspended = fs_suspended_q || state_q == STATE_HS_SUSPEND || state_q == STATE_HS_RESUME;
// Only a persistent SE0 observed with FS termination is destructive.
// In HS the same SE0 before the FS check is the ordinary idle line state.
assign bus_reset = (state_q == STATE_FULLSPEED && se0_reset && line_state == 2'b00) ||
                   (state_q == STATE_HS_SUSPEND && fs_settle_q >= FS_SETTLE_TIME && line_state == 2'b00) ||
                   state_q == STATE_WAIT_RST || state_q == STATE_SEND_CHIRP_K || state_q == STATE_WAIT_CHIRP_JK;

endmodule
