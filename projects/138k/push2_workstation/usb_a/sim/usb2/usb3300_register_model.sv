module usb3300_register_model #(
    parameter integer HOST_PORT_MODEL = 0
)(
    input wire clk_ulpi,
    input wire reset_n,
    input wire [3:0] fault_i,
    input wire [7:0] link_data_i,
    input wire link_data_oe_i,
    input wire link_stp_i,
    output reg [7:0] phy_data_o,
    output reg phy_data_oe_o,
    output reg phy_dir_o,
    output reg phy_nxt_o,
    output reg [15:0] completed_o,
    output reg [7:0] scratch_o,
    input wire [1:0] device_line_i,
    output reg [7:0] function_o,
    output wire host_chirp_valid_o,
    output wire [7:0] host_chirp_data_o
);
    localparam [3:0] IDLE = 0;
    localparam [3:0] COMMAND = 1;
    localparam [3:0] WRITE_DATA = 2;
    localparam [3:0] WRITE_STOP = 3;
    localparam [3:0] READ_TURN = 4;
    localparam [3:0] READ_DATA = 5;
    localparam [3:0] READ_RELEASE = 6;
    localparam [3:0] PREEMPT_TURN = 7;
    localparam [3:0] PREEMPT_STATUS = 8;
    localparam [3:0] TRANSMIT_COMMAND = 9;
    localparam [3:0] TRANSMIT_DATA = 10;
    localparam [3:0] STATUS_TURN = 11;
    localparam [3:0] STATUS_DATA = 12;
    reg [3:0] state_q;
    reg [5:0] address_q;
    reg write_q;
    reg [7:0] write_data_q;
    reg preempted_q;
    reg [1:0] reported_line_q;
    reg [7:0] registers [0:24];
    integer register_index;

    assign host_chirp_valid_o = state_q == TRANSMIT_DATA && link_data_oe_i && !link_stp_i;
    assign host_chirp_data_o = link_data_i;

    always @* begin
        phy_dir_o = 1'b0;
        phy_nxt_o = 1'b0;
        phy_data_o = 8'h00;
        phy_data_oe_o = 1'b0;
        case (state_q)
            COMMAND: phy_nxt_o = fault_i != 4'd6;
            WRITE_DATA: phy_nxt_o = 1'b1;
            READ_TURN, PREEMPT_TURN: phy_dir_o = 1'b1;
            READ_DATA: begin
                phy_dir_o = 1'b1;
                phy_data_oe_o = 1'b1;
                phy_data_o = registers[address_q];
                if (HOST_PORT_MODEL != 0 && address_q == 6'h15)
                    phy_data_o = {6'b0, device_line_i};
                case (fault_i)
                    1: if (address_q == 6'h00) phy_data_o = 8'h00;
                    2: if (address_q == 6'h16) phy_data_o = 8'h00;
                    3: if (address_q == 6'h07) phy_data_o = 8'h00;
                    4: if (address_q == 6'h0a) phy_data_o = 8'h00;
                    5: if (address_q == 6'h04) phy_data_o = 8'h00;
                    11: if (address_q == 6'h16 && registers[address_q] == 8'haa) phy_data_o = 8'h55;
                    12: if (address_q == 6'h04 && registers[address_q] == 8'h41) phy_data_o = 8'h49;
                    13: if (address_q == 6'h03) phy_data_o = 8'h01;
                    14: if (address_q == 6'h16 && registers[address_q] == 8'h00) phy_data_o = 8'haa;
                    default: begin end
                endcase
            end
            PREEMPT_STATUS: begin
                phy_dir_o = 1'b1;
                phy_data_oe_o = 1'b1;
                phy_data_o = 8'h0d;
            end
            TRANSMIT_COMMAND, TRANSMIT_DATA: phy_nxt_o = 1'b1;
            STATUS_TURN: phy_dir_o = 1'b1;
            STATUS_DATA: begin
                phy_dir_o = 1'b1;
                phy_data_oe_o = 1'b1;
                phy_data_o = {6'b0, device_line_i};
            end
            default: begin end
        endcase
    end

    always @(posedge clk_ulpi or negedge reset_n) begin
        if (!reset_n) begin
            state_q <= IDLE;
            address_q <= 6'h00;
            write_q <= 1'b0;
            write_data_q <= 8'h00;
            preempted_q <= 1'b0;
            reported_line_q <= 0;
            function_o <= 8'h41;
            completed_o <= 16'd0;
            scratch_o <= 8'h00;
            for (register_index = 0; register_index < 25; register_index = register_index + 1)
                registers[register_index] <= 8'h00;
            registers[0] <= 8'h24;
            registers[1] <= 8'h04;
            registers[2] <= 8'h04;
            registers[4] <= 8'h41;
            registers[10] <= 8'h06;
        end else if (link_stp_i && !link_data_oe_i) begin
            state_q <= IDLE;
        end else begin
            case (state_q)
                IDLE: begin
                    if (link_data_oe_i && link_data_i[7]) begin
                        address_q <= link_data_i[5:0];
                        write_q <= !link_data_i[6];
                        if (link_data_i[5:0] > 6'h18)
                            $fatal(1, "reserved PHY register access");
                        if (fault_i == 4'd8 || (fault_i == 4'd7 && !preempted_q)) begin
                            preempted_q <= 1'b1;
                            state_q <= PREEMPT_TURN;
                        end else
                            state_q <= COMMAND;
                    end else if (HOST_PORT_MODEL != 0 && link_data_oe_i && link_data_i == 8'h40)
                        state_q <= TRANSMIT_COMMAND;
                    else if (HOST_PORT_MODEL != 0 && device_line_i != reported_line_q)
                        state_q <= STATUS_TURN;
                end
                COMMAND: begin
                    if (phy_nxt_o) begin
                        if (!link_data_oe_i || link_data_i != {write_q ? 2'b10 : 2'b11, address_q})
                            $fatal(1, "command changed before NXT");
                        if (write_q && fault_i == 4'd10)
                            state_q <= PREEMPT_TURN;
                        else
                            state_q <= write_q ? WRITE_DATA : READ_TURN;
                    end
                end
                WRITE_DATA: begin
                    if (!link_data_oe_i || link_stp_i)
                        $fatal(1, "invalid write data phase");
                    write_data_q <= link_data_i;
                    state_q <= WRITE_STOP;
                end
                WRITE_STOP: begin
                    if (!link_stp_i || !link_data_oe_i || link_data_i != 8'h00)
                        $fatal(1, "invalid write STP/idle phase");
                    if (address_q == 6'h0a && write_data_q != 8'h06)
                        $fatal(1, "unexpected VBUS/pulldown control");
                    registers[address_q] <= write_data_q;
                    if (address_q == 6'h16)
                        scratch_o <= write_data_q;
                    if (address_q == 6'h04)
                        function_o <= write_data_q;
                    completed_o <= completed_o + 1'b1;
                    state_q <= IDLE;
                end
                READ_TURN: begin
                    if (fault_i != 4'd9)
                        state_q <= READ_DATA;
                end
                READ_DATA: begin
                    state_q <= READ_RELEASE;
                    completed_o <= completed_o + 1'b1;
                end
                READ_RELEASE: state_q <= IDLE;
                PREEMPT_TURN: state_q <= PREEMPT_STATUS;
                PREEMPT_STATUS: state_q <= IDLE;
                TRANSMIT_COMMAND: begin
                    if (!link_data_oe_i || link_data_i != 8'h40 || link_stp_i)
                        $fatal(1, "invalid NOPID command");
                    state_q <= TRANSMIT_DATA;
                end
                TRANSMIT_DATA: begin
                    if (!link_data_oe_i)
                        $fatal(1, "missing NOPID data drive");
                    if (link_stp_i) begin
                        if (link_data_i != 0)
                            $fatal(1, "NOPID must end with STP and idle 00");
                        state_q <= STATUS_TURN;
                    end else if (link_data_i != 8'h00 && link_data_i != 8'hff)
                        $fatal(1, "invalid raw K/J byte");
                end
                STATUS_TURN: state_q <= STATUS_DATA;
                STATUS_DATA: begin
                    reported_line_q <= device_line_i;
                    state_q <= IDLE;
                end
                default: $fatal(1, "invalid model state");
            endcase
        end
    end
endmodule
