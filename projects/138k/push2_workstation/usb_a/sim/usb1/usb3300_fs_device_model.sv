`timescale 1ns/1ps
module usb3300_fs_device_model #(parameter integer TRACE=0)(
    input wire clk_ulpi, clk_fs, reset_n, attached,
    inout wire [7:0] ulpi_data,
    output reg ulpi_dir, ulpi_nxt,
    input wire ulpi_stp,
    inout wire usb_dp, usb_dm,
    output reg [7:0] function_control,
    output reg [31:0] chirp_commands, normal_packets,
    output wire tx_driving, dp_pullup
);
    localparam IDLE=0, REG_COMMAND=1, REG_WRITE=2, REG_STOP=3,
               REG_TURN=4, REG_READ=5, RELEASE=6, TRANSMIT=7,
               RX_TURN=8, RECEIVE=9, STATUS_TURN=10, STATUS=11;
    integer state=IDLE;
    reg [7:0] registers [0:24];
    reg [5:0] address;
    reg write_register, raw_chirp;
    reg [7:0] write_data, phy_data;
    reg [1:0] reported_line;
    reg [8:0] tx_fifo [0:4095];
    reg [9:0] rx_fifo [0:4095];
    integer tx_write=0, tx_read=0, rx_write=0, rx_read=0;
    integer register_index, next_rx_write;
    reg previous_rx_active=0, rx_active_reported=0;
    integer traced_bytes=0;
    wire [7:0] fs_rxdata;
    wire fs_rxvalid, fs_rxactive, fs_rxerror, fs_txready;
    wire [1:0] fs_line;
    wire fs_tx_dp, fs_tx_dm, fs_tx_disable;
    wire normal_fs=function_control[4:3]==0 && function_control[1:0]==1 && function_control[2];
    wire tx_present=tx_read!=tx_write && !tx_fifo[tx_read%4096][8];
    wire [1:0] current_line=!attached ? 2'b00 : raw_chirp ? 2'b10 : fs_line;
    wire tx_command=ulpi_data[7:6]==2'b01 && !ulpi_stp;
    assign ulpi_data=ulpi_dir && state!=REG_TURN && state!=RX_TURN && state!=STATUS_TURN ? phy_data : 8'bz;
    assign dp_pullup=function_control[2] && function_control[1:0]<=1;
    assign tx_driving=attached && normal_fs && !fs_tx_disable;
    assign usb_dp=tx_driving ? fs_tx_dp : 1'bz;
    assign usb_dm=tx_driving ? fs_tx_dm : 1'bz;

    usb_fs_phy serializer (
        .clk_i(clk_fs),.rstn_i(reset_n),
        .utmi_data_out_i(tx_fifo[tx_read%4096][7:0]),.utmi_txvalid_i(tx_present && normal_fs),
        .utmi_op_mode_i(2'b00),.utmi_xcvrselect_i(2'b01),.utmi_termselect_i(1'b1),
        .utmi_dppulldown_i(1'b0),.utmi_dmpulldown_i(1'b0),
        .usb_rx_rcv_i(attached && usb_dp && !usb_dm),
        .usb_rx_dp_i(attached && usb_dp),.usb_rx_dn_i(attached && usb_dm),.usb_reset_assert_i(1'b0),
        .utmi_data_in_o(fs_rxdata),.utmi_txready_o(fs_txready),
        .utmi_rxvalid_o(fs_rxvalid),.utmi_rxactive_o(fs_rxactive),.utmi_rxerror_o(fs_rxerror),
        .utmi_linestate_o(fs_line),.usb_tx_dp_o(fs_tx_dp),.usb_tx_dn_o(fs_tx_dm),
        .usb_tx_oen_o(fs_tx_disable),.usb_reset_detect_o(),.usb_en_o()
    );

    always @(posedge clk_fs or negedge reset_n) begin
        if(!reset_n)begin
            tx_read<=0;rx_write<=0;previous_rx_active<=0;
        end else begin
            if(tx_read!=tx_write && (tx_fifo[tx_read%4096][8] || (normal_fs && fs_txready)))
                tx_read<=tx_read+1;
            previous_rx_active<=fs_rxactive && normal_fs;
            next_rx_write=rx_write;
            if(normal_fs && fs_rxactive && !previous_rx_active)begin
                rx_fifo[next_rx_write%4096]<=10'h100;next_rx_write=next_rx_write+1;
            end
            if(normal_fs && fs_rxvalid)begin
                if(TRACE && traced_bytes<80)begin
                    $display("USB3300 FS RX %02x at %0t",fs_rxdata,$time);traced_bytes=traced_bytes+1;
                end
                rx_fifo[next_rx_write%4096]<={2'b10,fs_rxdata};next_rx_write=next_rx_write+1;
            end
            if(previous_rx_active && (!fs_rxactive || !normal_fs))begin
                rx_fifo[next_rx_write%4096]<={2'b11,7'd0,fs_rxerror};next_rx_write=next_rx_write+1;
            end
            rx_write<=next_rx_write;
            if(next_rx_write-rx_read>=4096)$fatal(1,"USB3300 model RX overflow");
        end
    end

    always @* begin
        ulpi_dir=0;ulpi_nxt=0;phy_data=0;
        case(state)
            IDLE:ulpi_nxt=tx_command && tx_write-tx_read<32;
            REG_COMMAND,REG_WRITE:ulpi_nxt=1;
            REG_TURN,RX_TURN,STATUS_TURN:ulpi_dir=1;
            REG_READ:begin ulpi_dir=1;phy_data=registers[address];end
            TRANSMIT:ulpi_nxt=raw_chirp || tx_write-tx_read<32;
            RECEIVE:begin
                ulpi_dir=1;
                phy_data={2'b01,rx_active_reported ? 2'b01 : 2'b00,attached ? 2'b11 : 2'b00,current_line};
                if(rx_read!=rx_write)case(rx_fifo[rx_read%4096][9:8])
                    1:phy_data={2'b01,2'b01,2'b11,current_line};
                    2:begin ulpi_nxt=1;phy_data=rx_fifo[rx_read%4096][7:0];end
                    3:phy_data={2'b01,rx_fifo[rx_read%4096][0] ? 2'b11 : 2'b00,2'b11,current_line};
                    default:$fatal(1,"USB3300 model invalid RX event");
                endcase
            end
            STATUS:begin ulpi_dir=1;phy_data={2'b01,2'b00,attached ? 2'b11 : 2'b00,current_line};end
            default:begin end
        endcase
    end

    always @(posedge clk_ulpi or negedge reset_n) begin
        if(!reset_n)begin
            state<=IDLE;address<=0;write_register<=0;write_data<=0;raw_chirp<=0;
            function_control<=8'h41;reported_line<=0;tx_write<=0;rx_read<=0;
            rx_active_reported<=0;chirp_commands<=0;normal_packets<=0;
            for(register_index=0;register_index<25;register_index=register_index+1)registers[register_index]<=0;
            registers[0]<=8'h24;registers[1]<=8'h04;registers[2]<=8'h04;
            registers[4]<=8'h41;
        end else begin
            if(tx_write-tx_read>=4096)$fatal(1,"USB3300 model TX overflow");
            case(state)
                IDLE:begin
                    if(tx_command && ulpi_nxt)begin
                        if(TRACE && normal_packets<20)$display("USB3300 TX CMD %02x function=%02x at %0t",ulpi_data,function_control,$time);
                        raw_chirp<=function_control[4:3]==2'b10;
                        if(function_control[4:3]==2'b10)begin
                            if(ulpi_data!=8'h40)$fatal(1,"USB3300 chirp must use NOPID");
                            chirp_commands<=chirp_commands+1;
                        end else begin
                            if(!normal_fs)$fatal(1,"USB3300 packet before FS mode %02x",function_control);
                            tx_fifo[tx_write%4096]<={1'b0,~ulpi_data[3:0],ulpi_data[3:0]};
                            tx_write<=tx_write+1;normal_packets<=normal_packets+1;
                        end
                        state<=TRANSMIT;
                    end else if(ulpi_data[7] && !ulpi_stp)begin
                        if(ulpi_data[5:0]>24)$fatal(1,"USB3300 reserved register");
                        address<=ulpi_data[5:0];write_register<=!ulpi_data[6];state<=REG_COMMAND;
                    end else if(rx_read!=rx_write)state<=RX_TURN;
                    else if(current_line!=reported_line && !fs_rxactive)state<=STATUS_TURN;
                end
                REG_COMMAND:state<=write_register ? REG_WRITE : REG_TURN;
                REG_WRITE:begin write_data<=ulpi_data;state<=REG_STOP;end
                REG_STOP:begin
                    if(!ulpi_stp)$fatal(1,"USB3300 register write missing STP");
                    registers[address]<=address==4 ? write_data & 8'hdf : write_data;
                    if(address==4)function_control<=write_data & 8'hdf;
                    if(TRACE)$display("USB3300 register %02x=%02x at %0t",address,write_data,$time);
                    state<=IDLE;
                end
                REG_TURN:state<=REG_READ;
                REG_READ:state<=RELEASE;
                RELEASE:state<=IDLE;
                TRANSMIT:begin
                    if(ulpi_stp)begin
                        if(!raw_chirp)begin tx_fifo[tx_write%4096]<=9'h100;tx_write<=tx_write+1;end
                        raw_chirp<=0;state<=IDLE;
                    end else if(ulpi_nxt && !raw_chirp)begin
                        tx_fifo[tx_write%4096]<={1'b0,ulpi_data};tx_write<=tx_write+1;
                    end
                end
                RX_TURN:state<=RECEIVE;
                RECEIVE:begin
                    if(rx_read!=rx_write)begin
                        rx_read<=rx_read+1;
                        if(rx_fifo[rx_read%4096][9:8]==1)rx_active_reported<=1;
                        if(rx_fifo[rx_read%4096][9:8]==3)begin
                            rx_active_reported<=0;reported_line<=current_line;state<=RELEASE;
                        end
                    end
                end
                STATUS_TURN:state<=STATUS;
                STATUS:begin reported_line<=current_line;state<=RELEASE;end
                default:$fatal(1,"USB3300 model invalid state");
            endcase
        end
    end
endmodule
