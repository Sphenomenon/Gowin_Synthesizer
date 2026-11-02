`timescale 1ns/1ps
// Conservative asynchronous bundled-data probe PHY. All state uses clk_i;
// LCD req/ack pins are DATA, never FPGA clocks. Four-phase return-to-zero
// handshakes avoid toggle-phase ambiguity when either peer starts later.
// Data stays stable from req assertion until acknowledged. Two extra local
// guard cycles follow the synchronized req before sampling synchronized data.
// This is a source contract, not a physical CDC/electrical acceptance.
module workstation_task3_lcd_phy #(
    parameter integer STALL_TIMEOUT_CYCLES=50000
)(
    input wire clk_i,reset_ni,enable_i,panic_i,
    input wire tx_valid_i,
    output wire tx_ready_o,
    input wire [7:0] tx_byte_i,
    output reg rx_valid_o,
    input wire rx_ready_i,
    output reg [7:0] rx_byte_o,
    output reg [3:0] tx_data_o,
    output reg tx_req_o,rx_ack_o,
    input wire [3:0] rx_data_i,
    input wire rx_req_i,tx_ack_i,peer_panic_i,
    output wire peer_panic_o,
    output reg fault_o,
    output reg [31:0] timeout_count_o,
    output reg [31:0] tx_bytes_o,rx_bytes_o
);
    localparam [1:0] TX_IDLE=0,TX_HIGH=1,TX_LOW=2;
    localparam [1:0] RX_IDLE=0,RX_GUARD=1,RX_LOW=2;
    localparam integer AGE_BITS=$clog2(STALL_TIMEOUT_CYCLES+1);
    (* ASYNC_REG="TRUE" *) reg ack_meta,ack_sync,req_meta,req_sync,panic_meta,panic_sync;
    (* ASYNC_REG="TRUE" *) reg [3:0] data_meta,data_sync,data_settled;
    reg [1:0] tx_state,rx_state;
    reg [7:0] tx_held;
    reg [3:0] rx_low;
    reg tx_second,rx_second;
    reg [1:0] guard;
    reg [AGE_BITS-1:0] tx_age,rx_age;
    wire live=enable_i && !panic_i && !panic_sync && !fault_o;
    assign tx_ready_o=reset_ni && live && tx_state==TX_IDLE && !ack_sync;
    assign peer_panic_o=reset_ni && enable_i && panic_sync;
    initial if(STALL_TIMEOUT_CYCLES<16)$fatal(1,"invalid LCD nibble timeout");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            ack_meta<=0;ack_sync<=0;req_meta<=0;req_sync<=0;panic_meta<=0;panic_sync<=0;
            data_meta<=0;data_sync<=0;data_settled<=0;
        end else begin
            ack_meta<=tx_ack_i;ack_sync<=ack_meta;req_meta<=rx_req_i;req_sync<=req_meta;
            panic_meta<=peer_panic_i;panic_sync<=panic_meta;
            data_meta<=rx_data_i;data_sync<=data_meta;data_settled<=data_sync;
        end
    end
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            tx_state<=TX_IDLE;rx_state<=RX_IDLE;tx_held<=0;rx_low<=0;
            tx_second<=0;rx_second<=0;guard<=0;tx_age<=0;rx_age<=0;
            tx_data_o<=0;tx_req_o<=0;rx_ack_o<=0;rx_valid_o<=0;rx_byte_o<=0;
            fault_o<=0;timeout_count_o<=0;tx_bytes_o<=0;rx_bytes_o<=0;
        end else if(!enable_i)begin
            tx_state<=TX_IDLE;rx_state<=RX_IDLE;tx_second<=0;rx_second<=0;
            guard<=0;tx_age<=0;rx_age<=0;tx_req_o<=0;rx_ack_o<=0;rx_valid_o<=0;fault_o<=0;
        end else if(panic_i || panic_sync || fault_o)begin
            tx_state<=TX_IDLE;rx_state<=RX_IDLE;tx_req_o<=0;rx_ack_o<=0;rx_valid_o<=0;
            tx_second<=0;rx_second<=0;tx_age<=0;rx_age<=0;
        end else begin
            if(rx_valid_o && rx_ready_i)rx_valid_o<=0;
            if(tx_state!=TX_IDLE)begin
                if(tx_age==AGE_BITS'(STALL_TIMEOUT_CYCLES))begin
                    fault_o<=1;
                    if(!(&timeout_count_o))timeout_count_o<=timeout_count_o+1'b1;
                end else tx_age<=tx_age+1'b1;
            end
            if(rx_state!=RX_IDLE)begin
                if(rx_age==AGE_BITS'(STALL_TIMEOUT_CYCLES))begin
                    fault_o<=1;
                    if(!(&timeout_count_o))timeout_count_o<=timeout_count_o+1'b1;
                end else rx_age<=rx_age+1'b1;
            end
            case(tx_state)
                TX_IDLE:if(tx_valid_i && tx_ready_o)begin
                    tx_held<=tx_byte_i;tx_data_o<=tx_byte_i[3:0];tx_second<=0;
                    tx_req_o<=1;tx_age<=0;tx_state<=TX_HIGH;
                end
                TX_HIGH:if(ack_sync)begin tx_req_o<=0;tx_age<=0;tx_state<=TX_LOW;end
                TX_LOW:if(!ack_sync)begin
                    tx_age<=0;
                    if(!tx_second)begin tx_data_o<=tx_held[7:4];tx_second<=1;tx_req_o<=1;tx_state<=TX_HIGH;end
                    else begin tx_state<=TX_IDLE;if(!(&tx_bytes_o))tx_bytes_o<=tx_bytes_o+1'b1;end
                end
                default:tx_state<=TX_IDLE;
            endcase
            case(rx_state)
                RX_IDLE:if(req_sync && (!rx_valid_o || rx_ready_i))begin
                    guard<=2;rx_age<=0;rx_state<=RX_GUARD;
                end
                RX_GUARD:begin
                    if(!req_sync)fault_o<=1;
                    else if(guard!=0)guard<=guard-1'b1;
                    else begin
                        if(!rx_second)begin rx_low<=data_settled;rx_second<=1;end
                        else begin
                            rx_byte_o<={data_settled,rx_low};rx_valid_o<=1;rx_second<=0;
                            if(!(&rx_bytes_o))rx_bytes_o<=rx_bytes_o+1'b1;
                        end
                        rx_ack_o<=1;rx_age<=0;rx_state<=RX_LOW;
                    end
                end
                RX_LOW:if(!req_sync)begin rx_ack_o<=0;rx_age<=0;rx_state<=RX_IDLE;end
                default:rx_state<=RX_IDLE;
            endcase
        end
    end
endmodule
