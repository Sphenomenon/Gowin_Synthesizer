`timescale 1ns/1ps
// One native owner5, two bounded producers. Source ready acknowledges actual
// native acceptance, not admission into the media-memory local request slot.
module workstation_cnn_ddr_broker #(
    parameter integer TIMEOUT_CYCLES=50000000
) (
    input wire clk_i,reset_ni,backend_ready_i,transport_fault_i,
    input wire cnn_valid_i,cnn_write_i,
    input wire [28:0] cnn_address_i,
    input wire [255:0] cnn_data_i,
    input wire [31:0] cnn_mask_i,
    output wire cnn_ready_o,cnn_response_o,
    input wire stage_valid_i,stage_write_i,
    input wire [28:0] stage_address_i,
    input wire [255:0] stage_data_i,
    input wire [31:0] stage_mask_i,
    output wire stage_ready_o,stage_response_o,
    output wire slot_valid_o,
    output reg write_o,
    output reg [28:0] address_o,
    output reg [255:0] data_o,
    output reg [31:0] mask_o,
    input wire slot_ready_i,native_accept_i,response_i,
    output wire idle_o,
    output reg fault_o
);
    localparam [1:0] IDLE=0,SUBMIT=1,NATIVE=2,RETURN=3;
    reg [1:0] state;
    reg stage_owner,prefer_stage;
    localparam integer TIMER_BITS=TIMEOUT_CYCLES<2?1:$clog2(TIMEOUT_CYCLES);
    reg [TIMER_BITS-1:0] timer;
    initial if(TIMEOUT_CYCLES<4)$fatal(1,"CNN broker timeout must be at least four cycles");
    wire live=reset_ni && backend_ready_i && !transport_fault_i && !fault_o;
    assign slot_valid_o=live && state==SUBMIT;
    assign cnn_ready_o=live && state==NATIVE && !stage_owner && native_accept_i;
    assign stage_ready_o=live && state==NATIVE && stage_owner && native_accept_i;
    assign cnn_response_o=live && state==RETURN && !stage_owner && response_i;
    assign stage_response_o=live && state==RETURN && stage_owner && response_i;
    assign idle_o=state==IDLE && !fault_o;
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;stage_owner<=0;prefer_stage<=0;timer<=0;fault_o<=0;
            write_o<=0;address_o<=0;data_o<=0;mask_o<=0;
        end else begin
            if(transport_fault_i || (native_accept_i && state!=NATIVE) ||
               (response_i && state!=RETURN))fault_o<=1;
            if(state==IDLE)timer<=0;
            else if(timer==TIMER_BITS'(TIMEOUT_CYCLES-1))fault_o<=1;
            else timer<=timer+1'b1;
            if(live)case(state)
                IDLE:if(cnn_valid_i || stage_valid_i)begin
                    stage_owner<=stage_valid_i && (!cnn_valid_i || prefer_stage);
                    if(stage_valid_i && (!cnn_valid_i || prefer_stage))begin
                        write_o<=stage_write_i;address_o<=stage_address_i;data_o<=stage_data_i;mask_o<=stage_mask_i;
                    end else begin
                        write_o<=cnn_write_i;address_o<=cnn_address_i;data_o<=cnn_data_i;mask_o<=cnn_mask_i;
                    end
                    state<=SUBMIT;
                end
                SUBMIT:if(slot_ready_i)begin state<=NATIVE;timer<=0;end
                NATIVE:if(native_accept_i)begin
                    timer<=0;
                    if(write_o)begin state<=IDLE;prefer_stage<=!stage_owner;end
                    else state<=RETURN;
                end
                RETURN:if(response_i)begin state<=IDLE;prefer_stage<=!stage_owner;timer<=0;end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
