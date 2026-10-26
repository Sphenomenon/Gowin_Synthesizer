// 25K v1 command-test extension of the 138K compact initializer.
// GW138K resource adaptation of frozen vendor/rtl8723ds_ble/rtl/bt_hci_init.v.
// Original HCI sequence and patch data; command preparation is serialized into
// a single-write parameter RAM, reducing FF/LUT pressure in the full workstation.
// Applied only with --compact-hci; original package and default behavior retained.
// HCI bootstrap and verified ROM-v2 patch download. All decisions execute in PL.
// Patch bytes are a vendor RAM image; no ARM code runs this state machine.
module bt_hci_init #(
    parameter [87:0] DEVICE_NAME="GW25K-PROTO",
    parameter CLK_HZ = 50000000,
    parameter BAUD = 115200,
    parameter FAST_BAUD = 921600,
    parameter PATCH_BYTES = 30147,
    parameter PATCH_FILE = "rtl8723ds_patch.mem",
    parameter COMMAND_TIMEOUT_MS = 2000
) (
    input wire clk, resetn, enable, link_up,
    input wire baud_idle, output reg fast_mode,
    output reg tx_start,
    output wire [3:0] tx_type,
    output reg [8:0] tx_length,
    input wire tx_ready, tx_done, tx_error,
    input wire [8:0] tx_payload_addr,
    output wire [7:0] tx_payload_data,
    input wire rx_valid,
    input wire [3:0] rx_type,
    input wire [8:0] rx_length,
    output reg [8:0] rx_payload_addr,
    input wire [7:0] rx_payload_data,
    output reg rx_consume,
    output reg initialized, failed,
    output reg [7:0] debug_state, error_code,
    output reg [15:0] last_opcode,
    output reg [7:0] last_status, rom_version,
    output reg [31:0] command_count, patch_fragments,
    output reg [2:0] hci_valid_mask,
    output reg [47:0] bd_addr,
    output reg [63:0] boot_id,
    output reg [7:0] acl_packet_count
);
    localparam WAIT_LINK=0, BUILD=1, PATCH_ADDR=2, PATCH_WAIT=3,
        PATCH_COPY=4, SEND=5, WAIT_RESPONSE=6, COPY_RX=7,
        PARSE_RX=8, ADVANCE=9, PATCH_SETTLE=10, FINISHED=11, ERROR=12, LOAD_PARAMS=13, PATCH_INDEX=14, BAUD_DRAIN=15, BAUD_SETTLE=16;
    localparam TIMEOUT_TICKS = (CLK_HZ/1000)*COMMAND_TIMEOUT_MS;
    // One async-read / one synchronous-write parameter RAM; HCI header is held
    // in last_opcode/tx_length. Serializing preparation avoids 32 parallel writes.
    (* ram_style="block" *) reg [7:0] parameter_mem [0:255];
    reg [4:0] parameter_index;
    reg [7:0] parameter_data;
    reg receive_wait;
    wire [8:0] parameter_length = tx_length-9'd3;
    wire [7:0] parameter_address = tx_payload_addr[7:0]-8'd3;
    reg [7:0] event_mem [0:259];
    (* rom_style = "block", syn_romstyle = "block_rom" *) reg [7:0] patch_mem [0:32767];
    reg [14:0] rom_addr;
    reg [7:0] rom_data;
    initial $readmemh(PATCH_FILE, patch_mem);
    always @(posedge clk) rom_data <= patch_mem[rom_addr];
    assign tx_type = 4'd1;
    assign tx_payload_data = tx_payload_addr == 0 ? last_opcode[7:0] :
                             tx_payload_addr == 1 ? last_opcode[15:8] :
                             tx_payload_addr == 2 ? parameter_length[7:0] :
                             tx_payload_addr < 259 ? parameter_data : 8'd0;
    reg [7:0] step;
    reg [7:0] fragment_index;
    reg [15:0] patch_position;
    reg [8:0] fragment_size, fill_index, event_size;
    reg [31:0] timeout_count, settle_count;
    reg transport_done, response_done;
    reg [7:0] state;
    integer i;
    function [7:0] command_parameter;
        input [7:0] command_step;
        input integer at;
        begin
            command_parameter = 0;
            case (command_step)
                16: case(at)
                    0:command_parameter=8'h04; 1:command_parameter=8'h50;
                    2:command_parameter=8'hf7; 3:command_parameter=8'h05;
                endcase // Realtek 0x05f75004 = 921600 baud
                3: case(at) 0:command_parameter=8'h14; 1:command_parameter=8'hc0;
                       2:command_parameter=8'h52; 3:command_parameter=8'h02; endcase
                6: if(at==0) command_parameter=1; // LE Host Supported
                8: command_parameter= at==7 ? 8'h3f : 8'hff;
                9: if(at==0) command_parameter=8'h1f;
                10: if(at==0 || at==2) command_parameter=8'ha0;
                    else if(at==13) command_parameter=7;
                    else if(at==5) command_parameter=1; // static random address
                11: case(at)
                    0:command_parameter=8'h15;
                    1:command_parameter=8'h02;
                    2:command_parameter=8'h01;
                    3:command_parameter=8'h06;
                    4:command_parameter=8'h11;
                    5:command_parameter=8'h07;
                    6:command_parameter=8'h01;
                    7:command_parameter=8'h00;
                    8:command_parameter=8'h00;
                    9:command_parameter=8'h00;
                    10:command_parameter=8'h80;
                    11:command_parameter=8'h13;
                    12:command_parameter=8'h31;
                    13:command_parameter=8'h9a;
                    14:command_parameter=8'h87;
                    15:command_parameter=8'h4f;
                    16:command_parameter=8'h2a;
                    17:command_parameter=8'h4c;
                    18:command_parameter=8'h00;
                    19:command_parameter=8'h00;
                    20:command_parameter=8'h6d;
                    21:command_parameter=8'h9b;
                endcase
                12: case(at)
                    0:command_parameter=8'h0d;
                    1:command_parameter=8'h0c;
                    2:command_parameter=8'h09;
                    3:command_parameter=DEVICE_NAME[87:80];
                    4:command_parameter=DEVICE_NAME[79:72];
                    5:command_parameter=DEVICE_NAME[71:64];
                    6:command_parameter=DEVICE_NAME[63:56];
                    7:command_parameter=DEVICE_NAME[55:48];
                    8:command_parameter=DEVICE_NAME[47:40];
                    9:command_parameter=DEVICE_NAME[39:32];
                    10:command_parameter=DEVICE_NAME[31:24];
                    11:command_parameter=DEVICE_NAME[23:16];
                    12:command_parameter=DEVICE_NAME[15:8];
                    13:command_parameter=DEVICE_NAME[7:0];
                endcase
                // GATT database revision salt avoids retaining old properties.
                14: case(at)
                    0:command_parameter=((boot_id[7:0]^8'h5c)&8'hfe)|8'h02;
                    1:command_parameter=boot_id[15:8]^8'h21;
                    2:command_parameter=boot_id[23:16];
                    3:command_parameter=boot_id[31:24];
                    4:command_parameter=boot_id[39:32];
                    5:command_parameter=boot_id[47:40]|8'hc0;
                endcase
                15: if(at==0) command_parameter=1;
            endcase
        end
    endfunction
    wire parameter_write = state==LOAD_PARAMS || state==PATCH_INDEX || state==PATCH_COPY;
    wire [7:0] parameter_write_address = state==LOAD_PARAMS ? {3'd0,parameter_index} :
                                         state==PATCH_INDEX ? 8'd0 : fill_index[7:0]+8'd1;
    wire [7:0] parameter_write_data = state==LOAD_PARAMS ? command_parameter(step,parameter_index) :
                                      state==PATCH_INDEX ? (fragment_index | (fragment_size<252 ? 8'h80 : 8'h00)) : rom_data;
    always @(posedge clk) parameter_data<=parameter_mem[parameter_address];
    always @(posedge clk)
        if(resetn && enable && parameter_write)
            parameter_mem[parameter_write_address] <= parameter_write_data;
    always @(posedge clk) begin
        tx_start <= 0;
        rx_consume <= 0;
        if (!resetn || !enable) begin
            fast_mode<=0;
            state <= WAIT_LINK; debug_state <= WAIT_LINK; error_code <= 0;
            initialized <= 0; failed <= 0; step <= 0; fragment_index <= 0;
            patch_position <= 0; fragment_size <= 0; fill_index <= 0;
            command_count <= 0; patch_fragments <= 0; hci_valid_mask <= 0;
            last_opcode <= 0; last_status <= 0; rom_version <= 8'hff; bd_addr <= 0; boot_id <= 0;acl_packet_count<=1;
            tx_length <= 0; rx_payload_addr <= 0; event_size <= 0;
            timeout_count <= 0; settle_count <= 0; transport_done <= 0;
            response_done <= 0; rom_addr <= 0; parameter_index <= 0; receive_wait<=1;
        end else begin
            debug_state <= state;
            if (tx_done) transport_done <= 1;
            if (tx_error && !initialized) begin
                failed <= 1; error_code <= 1; state <= ERROR;
            end else case (state)
                WAIT_LINK: if (link_up) state <= BUILD;
                BUILD: begin
                    parameter_index <= 0;
                    transport_done <= 0; response_done <= 0; timeout_count <= 0;
                    case (step)
                        0: begin last_opcode<=16'h1001; tx_length<=3; end
                        1: begin last_opcode<=16'hfc6d; tx_length<=3; end
                        2: begin last_opcode<=16'h1009; tx_length<=3; end
                        3: begin last_opcode<=16'hfc17; tx_length<=7; end
                        4: begin
                            last_opcode<=16'hfc20; if (PATCH_BYTES-patch_position >= 252) begin
                                fragment_size<=252; tx_length<=256;
                            end else begin
                                fragment_size<=PATCH_BYTES-patch_position;
                                tx_length<=PATCH_BYTES-patch_position+4;
                            end
                            fill_index<=0;
                        end
                        5: begin last_opcode<=16'h0c03; tx_length<=3; end
                        6: begin last_opcode<=16'h0c6d; tx_length<=5; end
                        7: begin last_opcode<=16'h2002; tx_length<=3; end
                        8: begin last_opcode<=16'h0c01; tx_length<=11; end
                        9: begin last_opcode<=16'h2001; tx_length<=11; end
                        10: begin last_opcode<=16'h2006; tx_length<=18; end
                        11: begin last_opcode<=16'h2008; tx_length<=35; end
                        12: begin last_opcode<=16'h2009; tx_length<=35; end
                        13: begin last_opcode<=16'h2018; tx_length<=3; end
                        14: begin last_opcode<=16'h2005; tx_length<=9; end
                        15: begin last_opcode<=16'h200a; tx_length<=4; end
                        16: begin last_opcode<=16'hfc17; tx_length<=7; end
                    endcase
                    state <= step == 4 ? PATCH_INDEX : LOAD_PARAMS;
                end
                LOAD_PARAMS: begin
                    if(parameter_index==31) state<=SEND;
                    else parameter_index<=parameter_index+1'b1;
                end
                PATCH_INDEX: state<=PATCH_ADDR;
                PATCH_ADDR: begin rom_addr <= patch_position+fill_index; state<=PATCH_WAIT; end
                PATCH_WAIT: state<=PATCH_COPY;
                PATCH_COPY: begin
                    if(fill_index+1 >= fragment_size) state<=SEND;
                    else begin fill_index<=fill_index+1; state<=PATCH_ADDR; end
                end
                SEND: if (tx_ready) begin
                    tx_start<=1; state<=WAIT_RESPONSE; command_count<=command_count+1;
                end
                WAIT_RESPONSE: begin
                    if (transport_done && response_done) state<=ADVANCE;
                    else if(timeout_count >= TIMEOUT_TICKS) begin failed<=1; error_code<=2; state<=ERROR; end
                    else begin
                        timeout_count<=timeout_count+1;
                        if(rx_valid && !rx_consume) begin
                            if(rx_type==4 && rx_length>=2 && rx_length<=257) begin
                                event_size<=rx_length; rx_payload_addr<=0; receive_wait<=1; state<=COPY_RX;
                            end else rx_consume<=1;
                        end
                    end
                end
                COPY_RX: begin
                    if(receive_wait) receive_wait<=0;
                    else begin
                        receive_wait<=1;
                        event_mem[rx_payload_addr] <= rx_payload_data;
                        if(rx_payload_addr+1 >= event_size) begin rx_consume<=1; state<=PARSE_RX; end
                        else rx_payload_addr<=rx_payload_addr+1;
                    end
                end
                PARSE_RX: begin
                    state<=WAIT_RESPONSE;
                    if(event_mem[0]==8'h0e && event_size>=6 && event_mem[1]+2==event_size &&
                       {event_mem[4],event_mem[3]}==last_opcode) begin
                        last_status<=event_mem[5];
                        if(event_mem[5]!=0) begin failed<=1; error_code<=3; state<=ERROR; end
                        else if(step==0 && (event_size!=14 || event_mem[6]!=8 ||
                            {event_mem[8],event_mem[7]}!=16'h000d ||
                            {event_mem[11],event_mem[10]}!=16'h005d ||
                            {event_mem[13],event_mem[12]}!=16'h8723)) begin
                            failed<=1; error_code<=4; state<=ERROR;
                        end else if(step==1 && (event_size!=7 || event_mem[6]!=2)) begin
                            rom_version<=event_mem[6]; failed<=1; error_code<=5; state<=ERROR;
                        end else if(step==2 && event_size!=12) begin
                            failed<=1; error_code<=6; state<=ERROR;
                        end else if(step==4 && (event_size!=7 || event_mem[6]!=(fragment_index | (fragment_size<252 ? 8'h80 : 8'h00)))) begin
                            failed<=1; error_code<=7; state<=ERROR;
                        end else if(step==7 && (event_size!=9 || {event_mem[7],event_mem[6]}<27 || event_mem[8]==0)) begin
                            failed<=1;error_code<=11;state<=ERROR;
                        end else if(step==13 && (event_size!=14 ||
                            {event_mem[13],event_mem[12],event_mem[11],event_mem[10],event_mem[9],event_mem[8],event_mem[7],event_mem[6]}==0)) begin
                            failed<=1; error_code<=10; state<=ERROR;
                        end else begin
                            if(step==13) boot_id<={event_mem[13],event_mem[12],event_mem[11],event_mem[10],event_mem[9],event_mem[8],event_mem[7],event_mem[6]};
                            if(step==7 && event_size==9 && {event_mem[7],event_mem[6]}>=27 && event_mem[8]!=0)
                                acl_packet_count<=event_mem[8]>8 ? 8 : event_mem[8];
                            response_done<=1;
                            if(step==0) hci_valid_mask[1]<=1;
                            if(step==1) rom_version<=event_mem[6];
                            if(step==2) begin
                                hci_valid_mask[2]<=1;
                                bd_addr<={event_mem[11],event_mem[10],event_mem[9],event_mem[8],event_mem[7],event_mem[6]};
                            end
                            if(step==5) hci_valid_mask[0]<=1;
                        end
                    end
                end
                ADVANCE: begin
                    if(step==4) begin
                        patch_fragments<=patch_fragments+1;
                        if(fragment_size<252) begin step<=5; settle_count<=0; state<=PATCH_SETTLE; end
                        else begin
                            patch_position<=patch_position+fragment_size;
                            fragment_index<=fragment_index+1; state<=BUILD;
                        end
                    end else if(step==5 && FAST_BAUD!=BAUD) begin step<=16; state<=BUILD; end
                    else if(step==16) begin settle_count<=0; state<=BAUD_DRAIN; end
                    else if(step==15) begin initialized<=1; state<=FINISHED; end
                    else begin step<=step+1; state<=BUILD; end
                end
                // Preserve the patch's validated 115200 config. Change speed
                // after patch + Reset, only on a successful FC17 completion.
                // Drain the old-rate H5 ACK and require 20ms idle before switch.
                BAUD_DRAIN: begin
                    if(!baud_idle) settle_count<=0;
                    else if(settle_count >= CLK_HZ/50) begin
                        fast_mode<=1; settle_count<=0; state<=BAUD_SETTLE;
                    end else settle_count<=settle_count+1;
                end
                BAUD_SETTLE: if(settle_count >= CLK_HZ/20) begin step<=6; state<=BUILD; end
                    else settle_count<=settle_count+1;
                PATCH_SETTLE: if(settle_count >= CLK_HZ/20) state<=BUILD;
                    else settle_count<=settle_count+1;
                FINISHED: initialized<=1;
                ERROR: failed<=1;
                default: state<=WAIT_LINK;
            endcase
        end
    end
endmodule
