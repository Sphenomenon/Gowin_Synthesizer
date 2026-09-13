// Two immutable packet sources -> one USB Host OUT transaction stream.
// Response values match GUH: 1 ACK, 2 NAK, 3 STALL, 4 TIMEOUT, 5 CRC error.
// The backend supplies USB token/PID/CRC/SOF/physical signalling and enumeration.
module push2_out_scheduler #(
    parameter integer RETRY_DELAY_CYCLES=7500,
    parameter integer WATCHDOG_CYCLES=6000000,
    parameter integer MAX_ERRORS=3
) (
    input wire clk, input wire rst, input wire [6:0] device_address,
    input wire midi_valid, input wire [9:0] midi_length,
    input wire [7:0] midi_data, output reg midi_acked,
    input wire display_valid, input wire [9:0] display_length,
    input wire [7:0] display_data, output reg display_acked,
    output wire [8:0] packet_index,
    output wire out_req_valid, input wire out_req_ready,
    output wire [6:0] out_device_address, output wire [3:0] out_endpoint,
    output wire out_data1, output wire [9:0] out_length,
    output wire out_valid, input wire out_ready,
    output wire [7:0] out_data, output wire out_last,
    input wire out_done, input wire [2:0] out_response,
    output wire busy, output reg fault, output reg [3:0] fault_code,
    output reg [31:0] packets_acked, output reg [31:0] nak_count,
    output reg [31:0] retry_count
);
    localparam IDLE=3'd0, ISSUE=3'd1, SEND=3'd2, WAIT_REPLY=3'd3,
               BACKOFF=3'd4, RETURN=3'd5, FAILED=3'd6;
    localparam integer WD_BITS=(WATCHDOG_CYCLES<2)?1:$clog2(WATCHDOG_CYCLES+1);
    localparam integer BO_BITS=(RETRY_DELAY_CYCLES<2)?1:$clog2(RETRY_DELAY_CYCLES+1);
    reg [2:0] state;
    reg owner, last_owner, midi_toggle, display_toggle;
    reg [6:0] address_q;
    reg [9:0] length_q;
    reg [8:0] index_q;
    reg [WD_BITS-1:0] watchdog;
    reg [BO_BITS-1:0] backoff;
    reg [7:0] errors;
    wire choose_display=display_valid && (!midi_valid || !last_owner);
    wire [9:0] chosen_length=choose_display ? display_length : midi_length;
    assign packet_index=index_q;
    assign out_req_valid=state==ISSUE;
    assign out_device_address=address_q;
    assign out_endpoint=owner ? 4'd1 : 4'd2;
    assign out_data1=owner ? display_toggle : midi_toggle;
    assign out_length=length_q;
    assign out_valid=state==SEND;
    assign out_data=owner ? display_data : midi_data;
    assign out_last={1'b0,index_q}==length_q-1'b1;
    assign busy=state!=IDLE;
    wire last_byte=out_valid && out_ready && out_last;
    wire completion=out_done && (state==WAIT_REPLY || last_byte);
    always @(posedge clk) begin
        if (rst) begin
            state<=IDLE; owner<=0; last_owner<=1;
            midi_toggle<=0; display_toggle<=0;
            address_q<=0; length_q<=0; index_q<=0;
            watchdog<=0; backoff<=0; errors<=0;
            midi_acked<=0; display_acked<=0; fault<=0; fault_code<=0;
            packets_acked<=0; nak_count<=0; retry_count<=0;
        end else begin
            midi_acked<=0; display_acked<=0;
            if (state==ISSUE || state==SEND || state==WAIT_REPLY)
                watchdog<=watchdog+1'b1;
            if (completion) begin
                watchdog<=0;
                case (out_response)
                    3'd1:begin
                        if (owner) begin display_acked<=1; display_toggle<=!display_toggle; end
                        else begin midi_acked<=1; midi_toggle<=!midi_toggle; end
                        packets_acked<=packets_acked+1'b1;
                        last_owner<=owner; errors<=0; state<=RETURN;
                    end
                    3'd2:begin
                        // NAK is flow control, not successful delivery or data loss.
                        nak_count<=nak_count+1'b1;
                        index_q<=0; backoff<=0; state<=BACKOFF;
                    end
                    3'd4,3'd5:begin
                        retry_count<=retry_count+1'b1;
                        if (errors>=8'(MAX_ERRORS-1)) begin
                            fault<=1; fault_code<=2; state<=FAILED;
                        end else begin
                            errors<=errors+1'b1; index_q<=0; backoff<=0; state<=BACKOFF;
                        end
                    end
                    default:begin
                        fault<=1; fault_code<=out_response==3 ? 4'd1 : 4'd5;
                        state<=FAILED;
                    end
                endcase
            end else if ((state==ISSUE || state==SEND || state==WAIT_REPLY) &&
                         watchdog>=WD_BITS'(WATCHDOG_CYCLES-1)) begin
                // Backend progress is unknown: fail closed instead of submitting
                // another transaction into a controller that may still be busy.
                fault<=1; fault_code<=3; state<=FAILED;
            end else if (out_done && state==SEND) begin
                fault<=1; fault_code<=5; state<=FAILED;
            end else begin
                case (state)
                    IDLE:if (midi_valid || display_valid) begin
                        owner<=choose_display; address_q<=device_address;
                        length_q<=chosen_length; index_q<=0; watchdog<=0; errors<=0;
                        if (chosen_length==0 || chosen_length>512) begin
                            fault<=1; fault_code<=4; state<=FAILED;
                        end else state<=ISSUE;
                    end
                    ISSUE:if (out_req_ready) state<=SEND;
                    SEND:if (out_ready) begin
                        if (out_last) state<=WAIT_REPLY;
                        else index_q<=index_q+1'b1;
                    end
                    BACKOFF:if (backoff>=BO_BITS'(RETRY_DELAY_CYCLES-1)) begin
                        watchdog<=0; state<=ISSUE;
                    end else backoff<=backoff+1'b1;
                    RETURN:state<=IDLE;
                    default:begin end
                endcase
            end
        end
    end
endmodule
