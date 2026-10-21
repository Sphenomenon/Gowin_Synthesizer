module usb3300_packet_model #(
    parameter integer HIGH_SPEED = 1
)(
    input wire clk,
    input wire reset_n,
    input wire [7:0] link_data_i,
    input wire link_oe_i,
    input wire link_stp_i,
    input wire byte_ready_i,
    input wire stall_i,
    input wire [7:0] peer_data_i,
    input wire peer_valid_i,
    input wire peer_active_i,
    input wire peer_error_i,
    input wire peer_disconnect_i,
    input wire [1:0] peer_line_i,
    output wire peer_ready_o,
    output wire [7:0] usb_txdata_o,
    output wire usb_txvalid_o,
    output wire usb_txactive_o,
    output reg [7:0] phy_data_o,
    output wire phy_data_oe_o,
    output reg phy_dir_o,
    output reg phy_nxt_o
);
    localparam IDLE = 0, TRANSMIT = 1, RX_TURN = 2, RX_STATUS = 3,
               RX_DATA = 4, RX_END = 5, RX_RELEASE = 6, LINE_TURN = 7, LINE_DATA = 8;
    integer state_q = IDLE;
    reg [7:0] fifo [0:7];
    reg [2:0] write_q, read_q;
    reg [3:0] count_q;
    reg error_q;
    reg disconnected_q;
    reg [1:0] reported_line_q;
    integer cycle = 0, last_stp = -1000, last_receive_end = -1000, last_j = -1000;
    wire command_present = link_oe_i && !link_stp_i && link_data_i[7:6] == 2'b01;
    wire consume = state_q == RX_DATA && count_q != 0;
    assign peer_ready_o = reset_n && count_q < 7 && byte_ready_i;
    assign usb_txdata_o = state_q == IDLE ? {~link_data_i[3:0], link_data_i[3:0]} : link_data_i;
    assign usb_txvalid_o = reset_n && link_oe_i && !link_stp_i &&
                          ((state_q == IDLE && command_present && !stall_i) ||
                           (state_q == TRANSMIT && phy_nxt_o));
    assign usb_txactive_o = reset_n && (state_q == TRANSMIT ||
                           (state_q == IDLE && command_present && !stall_i));
    assign phy_data_oe_o = phy_dir_o && state_q != RX_TURN && state_q != LINE_TURN;
    always @* begin
        phy_data_o = 0; phy_dir_o = 0; phy_nxt_o = 0;
        case (state_q)
            IDLE: phy_nxt_o = command_present && !stall_i;
            TRANSMIT: phy_nxt_o = byte_ready_i && !stall_i;
            RX_TURN, LINE_TURN: phy_dir_o = 1;
            RX_STATUS: begin phy_dir_o = 1; phy_data_o = {2'b01, error_q ? 2'b11 : 2'b01, 2'b11, peer_line_i}; end
            RX_DATA: begin
                phy_dir_o = 1;
                if (count_q != 0) begin phy_nxt_o = 1; phy_data_o = fifo[read_q]; end
                else phy_data_o = {2'b01, error_q ? 2'b11 : 2'b01, 2'b11, peer_line_i};
            end
            RX_END: begin phy_dir_o = 1; phy_data_o = {6'b010011, peer_line_i}; end
            LINE_DATA: begin
                phy_dir_o = 1;
                phy_data_o = {2'b01, peer_disconnect_i ? 2'b10 : 2'b00, 2'b11, peer_line_i};
            end
            default: begin end
        endcase
    end
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            state_q <= IDLE; write_q <= 0; read_q <= 0; count_q <= 0; error_q <= 0;
            reported_line_q <= 1; disconnected_q <= 0;
            cycle = 0; last_stp = -1000; last_receive_end = -1000; last_j = -1000;
        end else begin
            cycle = cycle + 1;
            if (peer_valid_i) begin fifo[write_q] <= peer_data_i; write_q <= write_q + 3'd1; end
            if (consume) read_q <= read_q + 3'd1;
            case ({peer_valid_i, consume})
                2'b10: count_q <= count_q + 4'd1;
                2'b01: count_q <= count_q - 4'd1;
                default: begin end
            endcase
            if (peer_valid_i && count_q == 8 && !consume) $fatal(1, "packet model RX pipeline overflow");
            if (peer_error_i) error_q <= 1;
            if (!peer_disconnect_i) disconnected_q <= 0;
            if (phy_dir_o && link_oe_i) $fatal(1, "physical ULPI DATA contention");
            if (phy_dir_o && state_q != RX_TURN && state_q != LINE_TURN && !phy_nxt_o) begin
                if (reported_line_q == 0 && phy_data_o[1:0] == 1) last_j = cycle;
                reported_line_q <= phy_data_o[1:0];
            end
            case (state_q)
                IDLE: begin
                    if (command_present && !stall_i) begin
                        if (link_data_i[3:0] == 4'h3 || link_data_i[3:0] == 4'hb) begin
                            if (HIGH_SPEED != 0 && (cycle - last_stp < 15 || cycle - last_stp > 24))
                                $fatal(1, "physical HS token/data TX CMD delay %0d", cycle - last_stp);
                            if (HIGH_SPEED == 0 && (cycle - last_j < 7 || cycle - last_j > 18))
                                $fatal(1, "physical FS token/data TX CMD delay %0d", cycle - last_j);
                        end
                        if (link_data_i[3:0] == 4'h2) begin
                            if (HIGH_SPEED != 0 && (cycle - last_receive_end < 1 || cycle - last_receive_end > 14))
                                $fatal(1, "physical HS RX/ACK TX CMD delay %0d", cycle - last_receive_end);
                            if (HIGH_SPEED == 0 && (cycle - last_j < 7 || cycle - last_j > 18))
                                $fatal(1, "physical FS RX/ACK TX CMD delay %0d", cycle - last_j);
                        end
                        state_q <= TRANSMIT;
                    end else if (peer_active_i) begin state_q <= RX_TURN; error_q <= peer_error_i; end
                    else if ((peer_disconnect_i && !disconnected_q) || peer_line_i != reported_line_q)
                        state_q <= LINE_TURN;
                end
                TRANSMIT: if (link_stp_i) begin
                    if (!link_oe_i || link_data_i != 0) $fatal(1, "normal packet STP/idle DATA violation");
                    last_stp = cycle; state_q <= IDLE;
                end
                RX_TURN: state_q <= RX_STATUS;
                RX_STATUS: state_q <= RX_DATA;
                RX_DATA: if (count_q == 0 && !peer_active_i && !peer_valid_i) state_q <= RX_END;
                RX_END: begin last_receive_end = cycle; state_q <= RX_RELEASE; end
                RX_RELEASE: state_q <= IDLE;
                LINE_TURN: state_q <= LINE_DATA;
                LINE_DATA: begin disconnected_q <= peer_disconnect_i; state_q <= RX_RELEASE; end
                default: $fatal(1, "invalid packet model state");
            endcase
        end
    end
endmodule
