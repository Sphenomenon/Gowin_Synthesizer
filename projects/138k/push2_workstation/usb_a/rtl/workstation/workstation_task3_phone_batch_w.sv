`timescale 1ns/1ps
// Explicit v3 virtual PCM1 page. Intent is never an owner snapshot. Legacy
// commands retain the original target and its real completion/error response.
module workstation_task3_phone_batch_w #(
    parameter integer TIMEOUT_CYCLES=50000
)(
    input wire clk_i,reset_ni,live_i,capability_i,
    input wire [31:0] token_i,local_boot_i,peer_boot_i,session_i,generation_i,
    input wire local_valid_i,local_write_i,
    input wire [11:0] local_address_i,
    input wire [31:0] local_data_i,
    input wire [3:0] local_strobes_i,
    output wire local_ready_o,local_response_error_o,
    output wire [31:0] local_response_data_o,
    output wire legacy_valid_o,legacy_write_o,
    output wire [11:0] legacy_address_o,
    output wire [31:0] legacy_data_o,
    output wire [3:0] legacy_strobes_o,
    input wire legacy_ready_i,legacy_response_error_i,
    input wire [31:0] legacy_response_data_i,
    output wire request_valid_o,input wire request_ready_i,
    output wire [255:0] request_payload_o,
    output wire [5:0] request_length_o,
    // One pulse per packet already consumed by the outer validated endpoint.
    input wire response_valid_i,
    input wire [255:0] response_payload_i,
    input wire [5:0] response_length_i,
    input wire window_busy_i,
    output wire window_flush_o,busy_o,
    output reg fault_o
);
    localparam [2:0] IDLE=0,LEGACY=1,FLUSH=2,SEND=3,WAIT_RESPONSE=4,COMPLETE=5,RELEASE=6;
    localparam integer AGE_BITS=$clog2(TIMEOUT_CYCLES+1);
    reg [2:0] state;
    reg [AGE_BITS-1:0] age;
    reg held_write,completion_error;
    reg [11:0] held_address;
    reg [31:0] held_data,completion_data;
    reg [3:0] held_strobes;
    reg context_valid,ever_context,allow_context;
    reg [31:0] token,local_boot,peer_boot,session,generation,next_sequence,last_capture;
    reg [31:0] intent_controller,intent_generation,intent_stream,intent_rate;
    reg [31:0] intent_physical,intent_slot,intent_frames,intent_sequence;
    reg [255:0] request_payload,reply;
    reg reply_valid;
    wire identity_good=token_i!=0 && local_boot_i!=0 && peer_boot_i!=0 && session_i!=0 && generation_i!=0;
    wire same_identity=token_i==token && local_boot_i==local_boot && peer_boot_i==peer_boot &&
        session_i==session && generation_i==generation;
    wire qualified=live_i && capability_i && identity_good;
    wire active=reset_ni && qualified && context_valid && same_identity && !fault_o;
    wire virtual_page=local_address_i>=12'h100 && local_address_i<=12'h15f;
    wire held_changed=local_write_i!=held_write || local_address_i!=held_address ||
        local_data_i!=held_data || local_strobes_i!=held_strobes;
    wire batch_pending=state==FLUSH || state==SEND || state==WAIT_RESPONSE;
    wire overlap=(batch_pending || state==LEGACY) && (!local_valid_i || held_changed);
    wire expired=batch_pending && age>=AGE_BITS'(TIMEOUT_CYCLES-1);
    wire context_fence=context_valid && (!qualified || !same_identity);
    wire response_expected=active && state==WAIT_RESPONSE;
    wire response_shape=response_length_i==6'd32 && response_payload_i[31:0]==token &&
        response_payload_i[63:32]==request_payload[63:32] &&
        response_payload_i[191:160]!=0 && response_payload_i[191:160]>last_capture &&
        response_payload_i[253] && response_payload_i[245:236]<=10'd512;
    wire response_fault=response_valid_i && (!response_expected || !response_shape || response_payload_i[252]);
    assign local_ready_o=reset_ni && state==COMPLETE;
    assign local_response_error_o=completion_error;
    assign local_response_data_o=completion_data;
    assign legacy_valid_o=reset_ni && state==LEGACY && !overlap;
    assign legacy_write_o=held_write;
    assign legacy_address_o=held_address;
    assign legacy_data_o=held_data;
    assign legacy_strobes_o=held_strobes;
    assign request_valid_o=active && state==SEND && !overlap && !response_valid_i && !expired;
    assign request_payload_o=request_payload;
    assign request_length_o=6'd30;
    // busy is the original window applied watermark, not local posted credit.
    assign window_flush_o=active && batch_pending;
    assign busy_o=state!=IDLE;
    initial if(TIMEOUT_CYCLES<2)$fatal(1,"invalid W phone batch timeout");
    task automatic fail;
        begin
            fault_o<=1;context_valid<=0;reply_valid<=0;reply<=0;
            if(state!=IDLE && state!=RELEASE)begin
                state<=COMPLETE;completion_error<=1;completion_data<=0;
            end
        end
    endtask
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;age<=0;held_write<=0;held_address<=0;held_data<=0;held_strobes<=0;
            completion_error<=0;completion_data<=0;context_valid<=0;ever_context<=0;allow_context<=1;
            token<=0;local_boot<=0;peer_boot<=0;session<=0;generation<=0;next_sequence<=0;last_capture<=0;
            intent_controller<=0;intent_generation<=0;intent_stream<=0;intent_rate<=48000;
            intent_physical<=0;intent_slot<=0;intent_frames<=0;intent_sequence<=0;
            request_payload<=0;reply<=0;reply_valid<=0;fault_o<=0;
        end else begin
            if(!live_i)allow_context<=1;
            if(qualified && !context_valid && allow_context && (!ever_context || !same_identity) &&
                (state==IDLE || state==RELEASE) && !response_valid_i)begin
                context_valid<=1;ever_context<=1;allow_context<=0;fault_o<=0;
                token<=token_i;local_boot<=local_boot_i;peer_boot<=peer_boot_i;session<=session_i;generation<=generation_i;
                next_sequence<=0;last_capture<=0;reply_valid<=0;reply<=0;
                intent_controller<=0;intent_generation<=0;intent_stream<=0;intent_rate<=48000;
                intent_physical<=0;intent_slot<=0;intent_frames<=0;intent_sequence<=0;
            end
            if(batch_pending)age<=age+1'b1;
            case(state)
                IDLE:if(local_valid_i)begin
                    held_write<=local_write_i;held_address<=local_address_i;
                    held_data<=local_data_i;held_strobes<=local_strobes_i;
                    completion_error<=0;completion_data<=0;age<=0;
                    if(!virtual_page)state<=LEGACY;
                    else begin
                        state<=COMPLETE;
                        if(!local_write_i && local_address_i==12'h100)completion_data<=32'h50434d42;
                        else if(!local_write_i && local_address_i==12'h104)completion_data<=32'h00010000;
                        else if(!local_write_i && local_address_i==12'h108)completion_data<={31'd0,active};
                        else if(!active || local_address_i[1:0]!=0 || (local_write_i && local_strobes_i!=4'hf))begin
                            completion_error<=1;fault_o<=1;reply_valid<=0;reply<=0;context_valid<=0;
                        end else if(!local_write_i)begin
                            case(local_address_i)
                                12'h140,12'h144,12'h148,12'h14c,12'h150,12'h154,12'h158,12'h15c:
                                    if(reply_valid)completion_data<=reply[(local_address_i-12'h140)*8+:32];
                                    else begin completion_error<=1;fault_o<=1;context_valid<=0;end
                                default:begin completion_error<=1;fault_o<=1;reply_valid<=0;reply<=0;context_valid<=0;end
                            endcase
                        end else begin
                            case(local_address_i)
                                12'h110:intent_controller<=local_data_i;
                                12'h114:intent_generation<=local_data_i;
                                12'h118:intent_stream<=local_data_i;
                                12'h11c:if(local_data_i==48000 || local_data_i==44100)intent_rate<=local_data_i;
                                    else begin completion_error<=1;fault_o<=1;reply_valid<=0;reply<=0;context_valid<=0;end
                                12'h120:intent_physical<=local_data_i;
                                12'h124:if(local_data_i<=3)intent_slot<=local_data_i;
                                    else begin completion_error<=1;fault_o<=1;reply_valid<=0;reply<=0;context_valid<=0;end
                                12'h128:if(local_data_i<=128)intent_frames<=local_data_i;
                                    else begin completion_error<=1;fault_o<=1;reply_valid<=0;reply<=0;context_valid<=0;end
                                12'h12c:intent_sequence<=local_data_i;
                                12'h130:if(local_data_i<=5 && next_sequence!=32'hffffffff &&
                                    (local_data_i!=2 || intent_frames!=0))begin
                                    request_payload<={18'd0,local_data_i==2?intent_frames[7:0]:8'd0,
                                        local_data_i==2?intent_slot[1:0]:2'd0,intent_rate==44100,
                                        local_data_i[2:0],local_data_i==2?intent_sequence:32'd0,intent_physical,intent_stream,
                                        intent_generation,intent_controller,next_sequence,token};
                                    reply_valid<=0;reply<=0;state<=FLUSH;
                                end else begin completion_error<=1;fault_o<=1;reply_valid<=0;reply<=0;context_valid<=0;end
                                default:begin completion_error<=1;fault_o<=1;reply_valid<=0;reply<=0;context_valid<=0;end
                            endcase
                        end
                    end
                end
                LEGACY:if(legacy_ready_i)begin
                    completion_data<=legacy_response_data_i;completion_error<=legacy_response_error_i;state<=COMPLETE;
                end
                FLUSH:if(active && !window_busy_i)state<=SEND;
                SEND:if(request_valid_o && request_ready_i)state<=WAIT_RESPONSE;
                WAIT_RESPONSE:if(response_valid_i && response_expected && response_shape && !response_payload_i[252])begin
                    reply<=response_payload_i;reply_valid<=1;last_capture<=response_payload_i[191:160];
                    next_sequence<=next_sequence+1'b1;completion_data<=0;completion_error<=0;state<=COMPLETE;
                end
                COMPLETE:if(local_valid_i)state<=RELEASE;else state<=IDLE;
                RELEASE:if(!local_valid_i)state<=IDLE;
                default:fail();
            endcase
            // Context loss, unexpected packets and a changed held command win
            // over same-edge completion. No old reply can reopen this context.
            if(context_fence || response_fault || overlap || expired)fail();
        end
    end
endmodule
