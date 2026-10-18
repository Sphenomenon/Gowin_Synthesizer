`timescale 1ns/1ps
// Register access + USB3300 Table 6-7 three-pin serial behavior. This model
// obtains all transmit symbols from the actual shared DATA[2:0] pins.
// Independent model hypothesis: simulations can validate both mappings but
// cannot establish which DATA1 polarity the physical part actually uses.
module usb3300_serial_phy_model #(
    parameter [0:0] PHY_D1_INVERT = 1'b0
) (
    input wire clk,
    input wire reset_n,
    inout wire [7:0] data,
    output reg dir = 0,
    output reg nxt = 0,
    input wire stp,
    input wire attach_request,
    inout wire dp,
    inout wire dm,
    output reg serial_mode = 0,
    output reg [15:0] writes = 0,
    output reg [15:0] reads = 0,
    output reg [31:0] tx_cycles = 0,
    output reg [31:0] rx_cycles = 0
);
    localparam P_IDLE=0, P_CMD_STALL=1, P_CMD_ACK=2, P_R_TURN=3,
               P_R_DATA=4, P_R_RELEASE=5, P_W_WAIT=6, P_W_DATA=7,
               P_W_STOP=8, P_W_RELEASE=9, P_MODE=10, P_SERIAL=11;
    integer state = P_IDLE, stall = 0, mode_count = 0;
    integer clock_count = 0, attach_clock = 0;
    reg [7:0] regs [0:63];
    reg [7:0] command_byte = 0, write_byte = 0;
    reg [5:0] addr = 0;
    reg write_op = 0, phy_oe = 0;
    reg [7:0] phy_data = 0;
    wire serial_tx = serial_mode && data[0] === 1'b1;
    wire serial_rx = serial_mode && !serial_tx;
    assign data = !serial_mode && phy_oe ? phy_data : 8'hzz;
    // D0 is always a PHY input. D1=data and D2=SE0 are PHY outputs only
    // while TX_ENABLE=0. D3 is the PHY's interrupt output.
    wire serial_d1_tx = data[1] ^ PHY_D1_INVERT;
    assign data[1] = serial_rx ? (dp ^ PHY_D1_INVERT) : 1'bz;
    assign data[2] = serial_rx ? !(dp || dm) : 1'bz;
    assign data[3] = serial_mode ? 1'b0 : 1'bz;
    assign dp = serial_tx ? (!data[2] && serial_d1_tx) : 1'bz;
    assign dm = serial_tx ? (!data[2] && !serial_d1_tx) : 1'bz;
    // Function TermSelect controls the PHY's physical FS D+ pull-up.
    assign (pull1, highz0) dp = regs[4][2] ? 1'b1 : 1'bz;
    // Weak host termination avoids equal-strength conflicts with the D+ pullup.
    assign (highz1, weak0) dp = 1'b0;
    assign (highz1, weak0) dm = 1'b0;
    integer i;
    always @(posedge clk) begin
        if (!reset_n) begin
            state <= P_IDLE; stall <= 0; mode_count <= 0;
            addr <= 0; command_byte <= 0; write_byte <= 0; write_op <= 0;
            dir <= 0; nxt <= 0; phy_oe <= 0; phy_data <= 0;
            serial_mode <= 0; writes <= 0; reads <= 0;
            tx_cycles <= 0; rx_cycles <= 0;
            clock_count <= 0; attach_clock <= 0;
            for(i=0;i<64;i=i+1) regs[i] <= 0;
            regs[0] <= 8'h24; regs[1] <= 8'h04; regs[2] <= 8'h04;
            regs[3] <= 0; regs[4] <= 8'h41; regs[7] <= 0; regs[10] <= 6;
            regs[19] <= 8'h06; // InterruptStatus13h: VbusValid + SessValid
            regs[21] <= 8'h01; // Debug 15h UTMI LineState: FS idle J
        end else begin
            clock_count <= clock_count + 1;
            case(state)
                P_IDLE: begin
                    dir <= 0; nxt <= 0; phy_oe <= 0;
                    if (!stp && (data[7:6] == 2'b10 || data[7:6] == 2'b11)) begin
                        command_byte <= data; addr <= data[5:0];
                        write_op <= !data[6]; stall <= 2; state <= P_CMD_STALL;
                    end
                end
                P_CMD_STALL: begin
                    if (data !== command_byte || stp) $fatal(1,"ULPI command changed while stalled");
                    if (stall==0) begin nxt<=1; state<=P_CMD_ACK; end
                    else stall<=stall-1;
                end
                P_CMD_ACK: begin
                    if (data !== command_byte || stp) $fatal(1,"ULPI command invalid at ACK");
                    nxt<=0;
                    if(write_op) begin stall<=3; state<=P_W_WAIT; end
                    else begin
                        if(addr==6'h15 && clock_count-attach_clock<6000)
                            $fatal(1,"Debug read before 100us attach settling");
                        dir<=1; phy_oe<=0; reads<=reads+1; state<=P_R_TURN;
                    end
                end
                P_R_TURN: begin phy_oe<=1; phy_data<=regs[addr]; state<=P_R_DATA; end
                P_R_DATA: begin dir<=0; phy_oe<=0; state<=P_R_RELEASE; end
                P_R_RELEASE: begin
                    if (data !== 8'hzz) $fatal(1,"ULPI read return turnaround driven");
                    state<=P_IDLE;
                end
                P_W_WAIT: begin
                    if(stp) $fatal(1,"ULPI write terminated before data ACK");
                    if(stall==0) begin nxt<=1; state<=P_W_DATA; end
                    else stall<=stall-1;
                end
                P_W_DATA: begin
                    if(stp) $fatal(1,"ULPI data and stop overlap");
                    write_byte<=data; state<=P_W_STOP;
                end
                P_W_STOP: begin
                    if(!stp || data!==8'h00) $fatal(1,"ULPI stop not STP1/Idle00");
                    case(writes)
                        0: if(addr!=6'h16 || write_byte!=8'h55) $fatal(1,"scratch55");
                        1: if(addr!=6'h16 || write_byte!=8'haa) $fatal(1,"scratchAA");
                        2: if(addr!=6'h04 || write_byte!=8'h41) $fatal(1,"detach FC41");
                        3: if(addr!=6'h0a || write_byte!=8'h00) $fatal(1,"unsafe OTG");
                        4: if(addr!=6'h07 || write_byte!=8'h08) $fatal(1,"IF08");
                        5: begin
                            if(addr!=6'h04 || write_byte!=8'h45) $fatal(1,"attach FC45");
                            if(!attach_request) $fatal(1,"attached before CDC request");
                            attach_clock <= clock_count;
                        end
                        6: if(addr!=6'h07 || write_byte!=8'h0a) $fatal(1,"serial IF0A");
                        default: $fatal(1,"unexpected init write");
                    endcase
                    regs[addr]<=write_byte; writes<=writes+1; nxt<=0;
                    if(addr==6'h07 && write_byte==8'h0a) begin
                        dir<=1; phy_oe<=0; mode_count<=0; state<=P_MODE;
                    end else state<=P_W_RELEASE;
                end
                P_W_RELEASE: begin
                    if(stp || data!==8'h00) $fatal(1,"ULPI release invalid");
                    state<=P_IDLE;
                end
                P_MODE: begin
                    if(stp) $fatal(1,"STP reasserted during serial entry");
                    if(data!==8'hzz) $fatal(1,"FPGA drove during serial mode guard");
                    if(mode_count>=4) begin serial_mode<=1; state<=P_SERIAL; end
                    else mode_count<=mode_count+1;
                end
                P_SERIAL: begin
                    if(stp) $fatal(1,"STP asserted after serial entry");
                    if(serial_tx) begin
                        tx_cycles<=tx_cycles+1;
                        if(data[2:1] === 2'bxx || (^data[2:1]) === 1'bx)
                            $fatal(1,"unknown/contention on serial TX DATA1/2");
                    end else rx_cycles<=rx_cycles+1;
                end
                default: $fatal(1,"PHY model invalid state");
            endcase
        end
    end
endmodule
