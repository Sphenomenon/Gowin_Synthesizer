`default_nettype none
// Direct full-speed host for NEO Dock J18. 15k pulldowns and protected 5V
// are on the dock. Pins must be constrained as 3.3V GPIO, never LVDS.
module gw138k_usb_midi_host (
    input wire usb_clk, audio_clk, reset_n,
    inout wire usb_dp, usb_dn,
    output wire event_valid,
    output wire [17:0] event_data,
    input wire event_ready,
    output wire ready, failed,
    output wire [31:0] packets, duplicates, crc_errors, malformed_packets, naks,
    output wire [31:0] accepted, filtered, unsupported, malformed,
    output reg [31:0] restarts,
    output wire [26:0] sie_status,
    output wire [24:0] endpoint_status,
    output wire [4:0] phy_diagnostics
);
    wire [7:0] tx_data,rx_data;
    wire tx_valid,tx_ready,rx_valid,rx_active,rx_error;
    wire [1:0] line_state,op_mode,xcvr_select;
    wire term_select;
    reg rx_seen,tx_seen;
    always @(posedge usb_clk or negedge reset_n)
        if(!reset_n) begin rx_seen<=0;tx_seen<=0;end
        else begin
            if(rx_valid)rx_seen<=1;
            if(tx_valid && tx_ready)tx_seen<=1;
        end
    // Global-reset sticky activity includes enumeration (MIDI packet counters
    // start later). Kept in the five previously reserved U138 flag bits.
    assign phy_diagnostics={tx_seen,rx_seen,sie_status[23],line_state};
    wire tx_dp,tx_dn,tx_oe_n;
    assign usb_dp=(!tx_oe_n && reset_n) ? tx_dp : 1'bz;
    assign usb_dn=(!tx_oe_n && reset_n) ? tx_dn : 1'bz;
    usb_fs_phy u_phy(
        .clk_i(usb_clk),.rstn_i(reset_n),.utmi_data_out_i(tx_data),.utmi_txvalid_i(tx_valid),
        .utmi_op_mode_i(op_mode),.utmi_xcvrselect_i(xcvr_select),.utmi_termselect_i(term_select),
        .utmi_dppulldown_i(1'b1),.utmi_dmpulldown_i(1'b1),
        .usb_rx_rcv_i(usb_dp && !usb_dn),.usb_rx_dp_i(usb_dp),.usb_rx_dn_i(usb_dn),
        .usb_reset_assert_i(1'b0),.utmi_data_in_o(rx_data),.utmi_txready_o(tx_ready),
        .utmi_rxvalid_o(rx_valid),.utmi_rxactive_o(rx_active),.utmi_rxerror_o(rx_error),
        .utmi_linestate_o(line_state),.usb_tx_dp_o(tx_dp),.usb_tx_dn_o(tx_dn),.usb_tx_oen_o(tx_oe_n),
        .usb_reset_detect_o(),.usb_en_o());
    // SE0 for >=3 us outside host bus reset is a detach. A normal FS EOP
    // has only two bit times (167 ns); no combinational asynchronous detect.
    reg [7:0] detach_count;
    always @(posedge usb_clk or negedge reset_n)
        if(!reset_n) detach_count<=0;
        else if(line_state!=0 || sie_status[23]) detach_count<=0;
        else if(detach_count!=144) detach_count<=detach_count+1'b1;
    wire stream_valid,stream_ready,restarting;
    wire [9:0] stream_payload;
    gw138k_usb_host_core u_core(
        .usb_clk(usb_clk),.usb_rst(!reset_n),.tx_data(tx_data),.tx_valid(tx_valid),.tx_ready(tx_ready),
        .rx_data(rx_data),.rx_valid(rx_valid),.rx_active(rx_active),.rx_error(rx_error),
        .line_state(line_state),.host_disconnect(detach_count==144),.op_mode(op_mode),
        .xcvr_select(xcvr_select),.term_select(term_select),
        .o_midi__valid(stream_valid),.o_midi__ready(stream_ready),.o_midi__payload(stream_payload),
        .ready(ready),.failed(failed),.packets(packets),.duplicates(duplicates),.crc_errors(crc_errors),
        .malformed_packets(malformed_packets),.naks(naks),.restarting(restarting),
        .ctrl__status(sie_status),.o(endpoint_status));
    reg was_ready;
    always @(posedge usb_clk or negedge reset_n)
        if(!reset_n) begin was_ready<=0;restarts<=0;end
        else begin
            if(ready) was_ready<=1;
            if(restarting) begin was_ready<=0;restarts<=restarts+1'b1;end
        end
    wire decoded_valid,decoded_ready;
    wire [17:0] decoded_data;
    usb_midi_event_decoder u_decoder(
        .clk(usb_clk),.reset_n(reset_n),.session_lost(restarting && was_ready),
        .in_valid(stream_valid),.in_ready(stream_ready),
        .in_data(stream_payload[9:2]),.in_first(stream_payload[0]),.in_last(stream_payload[1]),
        .event_valid(decoded_valid),.event_ready(decoded_ready),.event_data(decoded_data),
        .accepted(accepted),.filtered(filtered),.unsupported(unsupported),.malformed(malformed));
    gw138k_usb_event_fifo u_fifo(
        .usb_clk(usb_clk),.usb_rst(!reset_n),.audio_clk(audio_clk),
        .w_data(decoded_data),.w_en(decoded_valid && decoded_ready),.w_rdy(decoded_ready),
        .r_data(event_data),.r_en(event_valid && event_ready),.r_rdy(event_valid));
endmodule
`default_nettype wire
