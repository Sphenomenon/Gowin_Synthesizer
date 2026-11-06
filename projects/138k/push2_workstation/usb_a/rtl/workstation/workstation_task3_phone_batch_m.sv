`timescale 1ns/1ps
// Explicit v3 control executor. Only this transport transaction is buffered;
// every mutation is replayed through the original PCM1 command owner/CDC.
// A reply describes one frozen owner capture, never a scan of live registers.
module workstation_task3_phone_batch_m #(
    parameter integer TIMEOUT_CYCLES=50000,
    parameter integer CAPTURE_COMPARE_GROUP_BITS=32
)(
    input wire clk_i,reset_ni,live_i,cancel_i,
    input wire [31:0] token_i,
    input wire packet_valid_i,
    output wire packet_ready_o,
    input wire [255:0] packet_payload_i,
    input wire [5:0] packet_length_i,
    output wire reply_valid_o,
    input wire reply_ready_i,
    output reg [255:0] reply_payload_o,
    output wire [5:0] reply_length_o,
    output wire command_valid_o,command_write_o,
    output reg [11:0] command_address_o,
    output reg [31:0] command_data_o,
    output wire [3:0] command_strobes_o,
    input wire command_ready_i,
    input wire [31:0] command_response_data_i,
    input wire command_response_error_i,
    output wire busy_o,
    output reg fault_o
);
    localparam [2:0] IDLE=0,SETUP=1,WAIT_COMMAND=2,RELEASE=3,PACK=4,REPLY=5;
    localparam [4:0] PROBE_ID=0,PROBE_VERSION=1,PROBE_CAPS=2,BEFORE_ID=3,
        KEY_CONTROLLER=4,KEY_GENERATION=5,KEY_STREAM=6,KEY_RATE=7,KEY_PHYSICAL=8,
        DESCRIPTOR_SLOT=9,DESCRIPTOR_FRAMES=10,DESCRIPTOR_SEQUENCE=11,
        CONTROL=12,AFTER_ID=13,CAPTURE=14,FIRST_CAPTURE_ID=15,
        SNAPSHOT_WORD=16,LAST_CAPTURE_ID=17;
    localparam integer AGE_BITS=$clog2(TIMEOUT_CYCLES+1);
    reg [2:0] state;
    reg [4:0] operation,word_index;
    reg [AGE_BITS-1:0] age;
    reg lease_valid;
    reg [31:0] lease_token,next_sequence,last_capture_id;
    reg [31:0] request_token,request_sequence,controller,generation,stream,physical,block_sequence;
    reg [2:0] opcode;
    reg rate44100;
    reg [1:0] slot;
    reg [7:0] frames;
    reg [31:0] before_id,probed_caps,capture_id;
    reg [31:0] snapshot[0:19];
    wire [2:0] incoming_opcode=packet_payload_i[226:224];
    wire [7:0] incoming_frames=packet_payload_i[237:230];
    wire shape_good=packet_length_i==6'd30 && packet_payload_i[255:238]==0 &&
        incoming_opcode<=5 && (incoming_opcode==2 ?
            (incoming_frames>=1 && incoming_frames<=128):
            (incoming_frames==0 && packet_payload_i[229:228]==0 && packet_payload_i[223:192]==0));
    wire context_live=reset_ni && live_i && !cancel_i && lease_valid &&
        token_i!=0 && token_i==lease_token;
    assign packet_ready_o=context_live && !fault_o && state==IDLE;
    assign command_valid_o=context_live && !fault_o && state==WAIT_COMMAND;
    assign command_write_o=operation>=KEY_CONTROLLER && operation<=CONTROL;
    assign command_strobes_o=4'hf;
    assign reply_valid_o=context_live && state==REPLY;
    assign reply_length_o=6'd32;
    assign busy_o=state!=IDLE;
    wire [31:0] requested_rate=rate44100 ? 32'd44100:32'd48000;
    wire live_match=snapshot[0]==controller && snapshot[1]==generation;
    wire active_match=snapshot[2]==controller && snapshot[3]==generation &&
        snapshot[4]==stream && snapshot[5]==requested_rate && snapshot[6]==physical;
    wire [31:0] packed_flags={snapshot[16][3],snapshot[8]==32'd44100,1'b1,1'b0,
        active_match,live_match,snapshot[12][3:0],snapshot[11][9:0],snapshot[10][3:0],snapshot[9][7:0]};
    wire snapshot_shape_good=snapshot[8]==32'd44100 || snapshot[8]==32'd48000;
    // TASK3 capture ordering comparison begin.
    // Preserve unsigned <=, including zero, equality and the original wrap
    // rejection. Only the combinational implementation is selectable.
    (* syn_keep=1 *) wire capture_not_newer;
    generate if(CAPTURE_COMPARE_GROUP_BITS==32)begin:g_capture_direct
        assign capture_not_newer=command_response_data_i<=last_capture_id;
    end else begin:g_capture_grouped
        (* syn_keep=1 *) wire [3:0] byte_less,byte_equal;
        for(genvar capture_byte=0;capture_byte<4;capture_byte=capture_byte+1)begin:g_byte
            assign byte_less[capture_byte]=command_response_data_i[capture_byte*8+:8]<last_capture_id[capture_byte*8+:8];
            assign byte_equal[capture_byte]=command_response_data_i[capture_byte*8+:8]==last_capture_id[capture_byte*8+:8];
        end
        assign capture_not_newer=byte_less[3] || (byte_equal[3] &&
            (byte_less[2] || (byte_equal[2] && (byte_less[1] ||
            (byte_equal[1] && (byte_less[0] || byte_equal[0]))))));
    end endgenerate
    initial if(CAPTURE_COMPARE_GROUP_BITS!=32 && CAPTURE_COMPARE_GROUP_BITS!=8)
        $fatal(1,"capture ordering requires the reviewed32-bit direct or8-bit grouped policy");
    // TASK3 capture ordering comparison end.
    wire snapshot_fields_good=snapshot_shape_good && snapshot[9][31:8]==0 &&
        snapshot[10][31:4]==0 && snapshot[11]<=512 && snapshot[12][31:4]==0 &&
        snapshot[16]==probed_caps && snapshot[17]==capture_id && snapshot[18]==0 && snapshot[19]==0 &&
        (opcode==0 || snapshot[14]==before_id+1'b1);
    initial if(TIMEOUT_CYCLES<2)$fatal(1,"invalid PCM batch timeout");
    always @*begin
        command_address_o=0;command_data_o=0;
        case(operation)
            PROBE_ID:command_address_o=12'h000;
            PROBE_VERSION:command_address_o=12'h004;
            PROBE_CAPS:command_address_o=12'h008;
            BEFORE_ID,AFTER_ID:command_address_o=12'h044;
            KEY_CONTROLLER:begin command_address_o=12'h020;command_data_o=controller;end
            KEY_GENERATION:begin command_address_o=12'h024;command_data_o=generation;end
            KEY_STREAM:begin command_address_o=12'h028;command_data_o=stream;end
            KEY_RATE:begin command_address_o=12'h02c;command_data_o=requested_rate;end
            KEY_PHYSICAL:begin command_address_o=12'h030;command_data_o=physical;end
            DESCRIPTOR_SLOT:begin command_address_o=12'h034;command_data_o={30'd0,slot};end
            DESCRIPTOR_FRAMES:begin command_address_o=12'h038;command_data_o={24'd0,frames};end
            DESCRIPTOR_SEQUENCE:begin command_address_o=12'h03c;command_data_o=block_sequence;end
            CONTROL:begin command_address_o=12'h040;command_data_o={29'd0,opcode};end
            CAPTURE:command_address_o=12'h090;
            FIRST_CAPTURE_ID,LAST_CAPTURE_ID:command_address_o=12'h144;
            SNAPSHOT_WORD:command_address_o=12'h100+{5'd0,word_index,2'b00};
            default:begin end
        endcase
    end
    task automatic fail(input [31:0] failed_token,failed_sequence);
        begin
            fault_o<=1;age<=0;
            reply_payload_o<={32'h10000000,160'd0,failed_sequence,failed_token};
            state<=REPLY;
        end
    endtask
    integer w;
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;operation<=PROBE_ID;word_index<=0;age<=0;
            lease_valid<=0;lease_token<=0;next_sequence<=0;last_capture_id<=0;fault_o<=0;
            request_token<=0;request_sequence<=0;controller<=0;generation<=0;stream<=0;physical<=0;
            block_sequence<=0;opcode<=0;rate44100<=0;slot<=0;frames<=0;
            before_id<=0;probed_caps<=0;capture_id<=0;reply_payload_o<=0;
            for(w=0;w<20;w=w+1)snapshot[w]<=0;
        end else if(!live_i)begin
            state<=IDLE;age<=0;lease_valid<=0;lease_token<=0;next_sequence<=0;
            last_capture_id<=0;fault_o<=0;reply_payload_o<=0;
        end else if(cancel_i || token_i==0 || (lease_valid && token_i!=lease_token))begin
            // Cancellation never waits behind owner or reply backpressure.
            // A command already applied remains uncertain and is not replayed.
            fault_o<=1;
            if(state!=IDLE)fail(request_token,request_sequence);
        end else if(!lease_valid)begin
            lease_token<=token_i;lease_valid<=1;
        end else if(state!=IDLE && state!=REPLY && age==AGE_BITS'(TIMEOUT_CYCLES-1))begin
            fail(request_token,request_sequence);
        end else begin
            if(state!=IDLE && state!=REPLY)age<=age+1'b1;
            case(state)
                IDLE:if(packet_valid_i && packet_ready_o)begin
                    request_token<=token_i;request_sequence<=packet_payload_i[63:32];
                    controller<=packet_payload_i[95:64];generation<=packet_payload_i[127:96];
                    stream<=packet_payload_i[159:128];physical<=packet_payload_i[191:160];
                    block_sequence<=packet_payload_i[223:192];opcode<=incoming_opcode;
                    rate44100<=packet_payload_i[227];slot<=packet_payload_i[229:228];frames<=incoming_frames;
                    age<=0;word_index<=0;
                    if(!shape_good || packet_payload_i[31:0]!=token_i ||
                       packet_payload_i[63:32]!=next_sequence || &next_sequence)
                        fail(token_i,packet_payload_i[63:32]);
                    else begin
                        next_sequence<=next_sequence+1'b1;operation<=PROBE_ID;state<=SETUP;
                    end
                end
                // A complete stable-address edge precedes valid, and the
                // previous APB completion must release before another issue.
                SETUP:if(!command_ready_i)state<=WAIT_COMMAND;
                WAIT_COMMAND:if(command_ready_i)begin
                    state<=RELEASE;
                    if(command_response_error_i)fail(request_token,request_sequence);
                    else case(operation)
                        PROBE_ID:if(command_response_data_i!=32'h50434d31)fail(request_token,request_sequence);
                            else operation<=PROBE_VERSION;
                        PROBE_VERSION:if(command_response_data_i!=32'h00010000)fail(request_token,request_sequence);
                            else operation<=PROBE_CAPS;
                        PROBE_CAPS:begin
                            if((command_response_data_i&32'h63)!=32'h63 ||
                               (command_response_data_i&~32'h7f)!=0 || command_response_data_i[4] ||
                               (command_response_data_i[3] && !command_response_data_i[2]))fail(request_token,request_sequence);
                            else begin probed_caps<=command_response_data_i;operation<=opcode==0 ? CAPTURE:BEFORE_ID;end
                        end
                        BEFORE_ID:if(&command_response_data_i)fail(request_token,request_sequence);
                            else begin before_id<=command_response_data_i;operation<=KEY_CONTROLLER;end
                        KEY_CONTROLLER,KEY_GENERATION,KEY_STREAM,KEY_RATE:operation<=operation+1'b1;
                        KEY_PHYSICAL:operation<=opcode==2 ? DESCRIPTOR_SLOT:CONTROL;
                        DESCRIPTOR_SLOT,DESCRIPTOR_FRAMES:operation<=operation+1'b1;
                        DESCRIPTOR_SEQUENCE:operation<=CONTROL;
                        CONTROL:if(command_response_data_i!=before_id+1'b1)fail(request_token,request_sequence);
                            else operation<=AFTER_ID;
                        AFTER_ID:if(command_response_data_i!=before_id+1'b1)fail(request_token,request_sequence);
                            else operation<=CAPTURE;
                        CAPTURE:if(command_response_data_i!=32'h50434d53)fail(request_token,request_sequence);
                            else operation<=FIRST_CAPTURE_ID;
                        FIRST_CAPTURE_ID:if(command_response_data_i==0 || capture_not_newer)
                                fail(request_token,request_sequence);
                            else begin capture_id<=command_response_data_i;word_index<=0;operation<=SNAPSHOT_WORD;end
                        SNAPSHOT_WORD:begin
                            snapshot[word_index]<=command_response_data_i;
                            if(word_index==19)operation<=LAST_CAPTURE_ID;
                            else word_index<=word_index+1'b1;
                        end
                        LAST_CAPTURE_ID:if(command_response_data_i!=capture_id || !snapshot_fields_good)
                                fail(request_token,request_sequence);
                            else begin last_capture_id<=capture_id;state<=PACK;end
                        default:fail(request_token,request_sequence);
                    endcase
                end
                RELEASE:if(!command_ready_i)state<=SETUP;
                PACK:begin
                    reply_payload_o<={packed_flags,snapshot[7],snapshot[17],snapshot[13],
                                      snapshot[15],snapshot[14],request_sequence,request_token};
                    state<=REPLY;
                end
                REPLY:if(reply_valid_o && reply_ready_i)begin state<=IDLE;age<=0;end
                default:fail(request_token,request_sequence);
            endcase
        end
    end
endmodule
