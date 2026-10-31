`timescale 1ns/1ps
`default_nettype none
// Two disjoint recording stores share owner8 without sharing object state.
// Each client retains its native_commit bridge. A local slot acceptance is
// not a native write commit, and a read owns the channel through its return.
module workstation_recording_ddr_owner_mux #(
    parameter [28:0] FIRST0=0,LAST0=7,FIRST1=8,LAST1=15,
    parameter integer BUDGET_CYCLES=10000
)(
    input wire clk_i,rst_ni,channel_ready_i,
    input wire [1:0] valid_i,write_i,
    input wire [28:0] address0_i,address1_i,
    input wire [255:0] data0_i,data1_i,
    input wire [31:0] mask0_i,mask1_i,
    output wire [1:0] ready_o,native_accept_o,response_o,
    output wire valid_o,write_o,
    output wire [28:0] address_o,
    output wire [255:0] data_o,
    output wire [31:0] mask_o,
    input wire ready_i,native_accept_i,response_i,transport_fault_i,
    output wire transport_fault_o,
    output reg fault_o,
    output wire busy_o
);
    localparam [1:0] IDLE=0,NATIVE=1,RESPONSE=2;
    reg [1:0] state;
    reg owner,prefer,active_write;
    reg [31:0] waited;
    wire chosen=state!=IDLE ? owner : valid_i[prefer] ? prefer : !prefer;
    wire available=valid_i[chosen];
    assign address_o=chosen ? address1_i:address0_i;
    assign data_o=chosen ? data1_i:data0_i;
    assign mask_o=chosen ? mask1_i:mask0_i;
    assign write_o=write_i[chosen];
    wire address_good=address_o[2:0]==0 &&
        (chosen ? address_o>=FIRST1 && address_o<=LAST1-7 :
                  address_o>=FIRST0 && address_o<=LAST0-7);
    wire native_event=state==NATIVE && native_accept_i;
    wire read_return=(state==RESPONSE || (native_event && !active_write)) && response_i;
    wire invalid_native=native_accept_i && state!=NATIVE;
    wire invalid_response=response_i && !(state==RESPONSE || (native_event && !active_write));
    wire timed_out=state!=IDLE && waited>=BUDGET_CYCLES-1 &&
        !(state==NATIVE ? native_accept_i:response_i);
    wire fault_now=transport_fault_i || invalid_native || invalid_response || timed_out ||
        (state!=IDLE && !channel_ready_i) ||
        (state==IDLE && available && !address_good);
    assign transport_fault_o=fault_o || fault_now;
    // Only the DDR authority may rearm after proving old untagged returns can
    // no longer arrive. A local mux/client reset alone cannot establish that.
    wire open=rst_ni && channel_ready_i && !transport_fault_o;
    assign valid_o=open && state==IDLE && available;
    assign ready_o=valid_o && ready_i ? (chosen ? 2'b10:2'b01):2'b00;
    // An owned transfer excludes IDLE address admission and its timeout.
    // Keep immediate transport and write/response protocol vetoes. The false
    // arms retain the original four-state behavior before state initialization;
    // their binary transfer predicates are zero.
    wire owned_open=rst_ni && channel_ready_i && !fault_o && !transport_fault_i;
    wire owned_native_allowed=native_event ?
        (owned_open && !(response_i && active_write)) : (open && native_event);
    wire owned_response_allowed=read_return ?
        (owned_open && !invalid_native) : (open && read_return);
    assign native_accept_o=owned_native_allowed ? (owner ? 2'b10:2'b01):2'b00;
    assign response_o=owned_response_allowed ? (owner ? 2'b10:2'b01):2'b00;
    assign busy_o=state!=IDLE;
    initial begin
        if(BUDGET_CYCLES<2 || FIRST0>LAST0 || FIRST1>LAST1 ||
            LAST0-FIRST0<7 || LAST1-FIRST1<7 || FIRST0[2:0]!=0 || FIRST1[2:0]!=0 ||
            LAST0[2:0]!=7 || LAST1[2:0]!=7 || !(LAST0<FIRST1 || LAST1<FIRST0))
            $fatal(1,"invalid recording subclient geometry/budget");
    end
    always @(posedge clk_i or negedge rst_ni)begin
        if(!rst_ni)begin state<=IDLE;owner<=0;prefer<=0;active_write<=0;waited<=0;fault_o<=0;end
        else begin
            if(fault_now)fault_o<=1;
            if(open)case(state)
                IDLE:begin
                    waited<=0;
                    if(valid_o && ready_i)begin
                        owner<=chosen;active_write<=write_o;state<=NATIVE;
                    end
                end
                NATIVE:begin
                    if(native_accept_i)begin
                        waited<=0;
                        if(active_write || response_i)begin state<=IDLE;prefer<=!owner;end
                        else state<=RESPONSE;
                    end else waited<=waited+1'b1;
                end
                RESPONSE:begin
                    if(response_i)begin state<=IDLE;prefer<=!owner;waited<=0;end
                    else waited<=waited+1'b1;
                end
                default:begin end
            endcase
        end
    end
endmodule
`default_nettype wire
