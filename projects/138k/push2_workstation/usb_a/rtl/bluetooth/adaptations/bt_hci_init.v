// GW138K resource adaptation of frozen vendor/rtl8723ds_ble/rtl/bt_hci_init.v.
// Original HCI sequence and patch data; command preparation is serialized into
// a single-write parameter RAM, reducing FF/LUT pressure in the full workstation.
// Applied only with --compact-hci; original package and default behavior retained.
// HCI bootstrap and verified ROM-v2 patch download. All decisions execute in PL.
// Patch bytes are a vendor RAM image; no ARM code runs this state machine.
module bt_hci_init #(
    parameter CLK_HZ = 50000000,
    parameter PATCH_BYTES = 30147,
    parameter PATCH_FILE = "rtl8723ds_patch.mem",
    parameter COMMAND_TIMEOUT_MS = 2000
) (
    input wire clk, resetn, enable, link_up,
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
    output reg [47:0] bd_addr
);
    localparam WAIT_LINK=0, BUILD=1, PATCH_ADDR=2, PATCH_WAIT=3,
        PATCH_COPY=4, SEND=5, WAIT_RESPONSE=6, COPY_RX=7,
        PARSE_RX=8, ADVANCE=9, PATCH_SETTLE=10, FINISHED=11, ERROR=12, LOAD_PARAMS=13, PATCH_INDEX=14;
    localparam TIMEOUT_TICKS = (CLK_HZ/1000)*COMMAND_TIMEOUT_MS;
    // One async-read / one synchronous-write parameter RAM; HCI header is held
    // in last_opcode/tx_length. Serializing preparation avoids 32 parallel writes.
    (* syn_ramstyle = "distributed_ram" *) reg [7:0] parameter_mem [0:255];
    reg [4:0] parameter_index;
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
                             tx_payload_addr < 259 ? parameter_mem[parameter_address] : 8'd0;
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
                3: case(at) 0:command_parameter=8'h14; 1:command_parameter=8'hc0;
                       2:command_parameter=8'h52; 3:command_parameter=8'h02; endcase
                6: if(at==0) command_parameter=1; // LE Host Supported
                8: command_parameter= at==7 ? 8'h3f : 8'hff;
                9: if(at==0) command_parameter=8'h1f;
                10: if(at==0 || at==2) command_parameter=8'ha0;
                    else if(at==13) command_parameter=7;
                11: case(at)
                    0:command_parameter=20; 1:command_parameter=2; 2:command_parameter=1;
                    3:command_parameter=6; 4:command_parameter=3; 5:command_parameter=3;
                    6:command_parameter=8'hf0; 7:command_parameter=8'hff;
                    8:command_parameter=12; 9:command_parameter=9;
                    10:command_parameter="R"; 11:command_parameter="T"; 12:command_parameter="L";
                    13:command_parameter="8"; 14:command_parameter="7"; 15:command_parameter="2";
                    16:command_parameter="3"; 17:command_parameter="-"; 18:command_parameter="B";
                    19:command_parameter="L"; 20:command_parameter="E";
                    default:command_parameter=0;
                endcase
                12: if(at==0) command_parameter=1;
            endcase
        end
    endfunction
    wire parameter_write = state==LOAD_PARAMS || state==PATCH_INDEX || state==PATCH_COPY;
    wire [7:0] parameter_write_address = state==LOAD_PARAMS ? {3'd0,parameter_index} :
                                         state==PATCH_INDEX ? 8'd0 : fill_index[7:0]+8'd1;
    wire [7:0] parameter_write_data = state==LOAD_PARAMS ? command_parameter(step,parameter_index) :
                                      state==PATCH_INDEX ? (fragment_index | (fragment_size<252 ? 8'h80 : 8'h00)) : rom_data;
    always @(posedge clk)
        if(resetn && enable && parameter_write)
            parameter_mem[parameter_write_address] <= parameter_write_data;
    always @(posedge clk) begin
        tx_start <= 0;
        rx_consume <= 0;
        if (!resetn || !enable) begin
            state <= WAIT_LINK; debug_state <= WAIT_LINK; error_code <= 0;
            initialized <= 0; failed <= 0; step <= 0; fragment_index <= 0;
            patch_position <= 0; fragment_size <= 0; fill_index <= 0;
            command_count <= 0; patch_fragments <= 0; hci_valid_mask <= 0;
            last_opcode <= 0; last_status <= 0; rom_version <= 8'hff; bd_addr <= 0;
            tx_length <= 0; rx_payload_addr <= 0; event_size <= 0;
            timeout_count <= 0; settle_count <= 0; transport_done <= 0;
            response_done <= 0; rom_addr <= 0; parameter_index <= 0;
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
                        12: begin last_opcode<=16'h200a; tx_length<=4; end
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
                                event_size<=rx_length; rx_payload_addr<=0; state<=COPY_RX;
                            end else rx_consume<=1;
                        end
                    end
                end
                COPY_RX: begin
                    event_mem[rx_payload_addr] <= rx_payload_data;
                    if(rx_payload_addr+1 >= event_size) begin rx_consume<=1; state<=PARSE_RX; end
                    else rx_payload_addr<=rx_payload_addr+1;
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
                        end else begin
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
                    end else if(step==12) begin initialized<=1; state<=FINISHED; end
                    else begin step<=step+1; state<=BUILD; end
                end
                PATCH_SETTLE: if(settle_count >= CLK_HZ/20) state<=BUILD;
                    else settle_count<=settle_count+1;
                FINISHED: initialized<=1;
                ERROR: failed<=1;
                default: state<=WAIT_LINK;
            endcase
        end
    end
endmodule
