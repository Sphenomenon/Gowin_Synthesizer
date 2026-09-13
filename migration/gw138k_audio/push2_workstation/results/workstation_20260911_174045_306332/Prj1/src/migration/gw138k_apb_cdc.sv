`timescale 1ns/1ps
// One APB transaction in flight. Request and response payloads are held until
// the round trip completes. Both sides share reset assertion and release locally.
// Future physical integration MUST constrain held payload paths, not blanket-cut
// these clock domains. Stalling either side never generates audio backpressure.
module gw138k_apb_cdc (
    input wire reset_n, pclk, audio_clk,
    input wire psel, penable, pwrite,
    input wire [11:0] paddr,
    input wire [31:0] pwdata,
    input wire [3:0] pstrb,
    output wire pready, pslverr,
    output wire [31:0] prdata,
    output wire command_reset_n,
    output wire command_valid,
    input wire command_ready,
    output wire command_write,
    output wire [11:0] command_address,
    output wire [31:0] command_data,
    output wire [3:0] command_strobes,
    input wire [31:0] response_data,
    input wire response_error
);
    logic [2:0] p_release, a_release;
    always_ff @(posedge pclk or negedge reset_n)
        if(!reset_n) p_release<=0; else p_release<={p_release[1:0],1'b1};
    always_ff @(posedge audio_clk or negedge reset_n)
        if(!reset_n) a_release<=0; else a_release<={a_release[1:0],1'b1};
    wire p_reset_n=p_release[2];
    assign command_reset_n=a_release[2];
    logic [48:0] request_held, request_local;
    logic [32:0] response_held, response_local;
    logic request_toggle, acknowledge_toggle;
    (* ASYNC_REG="TRUE" *) logic req_meta, req_sync, ack_meta, ack_sync;
    logic req_settled, ack_settled;
    localparam [1:0] IDLE=0, WAIT_RESPONSE=1, COMPLETE=2;
    logic [1:0] state;
    assign pready=p_reset_n && state==COMPLETE;
    assign pslverr=pready && response_local[32];
    assign prdata=response_local[31:0];
    assign {command_write,command_strobes,command_address,command_data}=request_local;
    assign command_valid=command_reset_n && req_settled!=acknowledge_toggle;
    always_ff @(posedge pclk or negedge p_reset_n) begin
        if(!p_reset_n) begin
            state<=IDLE; request_held<=0; request_toggle<=0; response_local<=0;
            ack_meta<=0; ack_sync<=0; ack_settled<=0;
        end else begin
            ack_meta<=acknowledge_toggle; ack_sync<=ack_meta; ack_settled<=ack_sync;
            case(state)
                IDLE: if(psel && penable) begin
                    request_held<={pwrite,pstrb,paddr,pwdata};
                    request_toggle<=~request_toggle; state<=WAIT_RESPONSE;
                end
                WAIT_RESPONSE: if(ack_settled==request_toggle) begin
                    response_local<=response_held; state<=COMPLETE;
                end
                COMPLETE: if(psel && penable) state<=IDLE;
                default: state<=IDLE;
            endcase
        end
    end
    always_ff @(posedge audio_clk or negedge command_reset_n) begin
        if(!command_reset_n) begin
            req_meta<=0; req_sync<=0; req_settled<=0;
            acknowledge_toggle<=0; response_held<=0; request_local<=0;
        end else begin
            req_meta<=request_toggle; req_sync<=req_meta; req_settled<=req_sync;
            // Capture the held word at the third synchronizer edge. Decode
            // only the local register, keeping CDC routing out of service
            // combinational logic and BRAM address/write-enable paths.
            if(req_sync!=req_settled) request_local<=request_held;
            if(command_valid && command_ready) begin
                response_held<={response_error,response_data};
                acknowledge_toggle<=req_settled;
            end
        end
    end
endmodule
