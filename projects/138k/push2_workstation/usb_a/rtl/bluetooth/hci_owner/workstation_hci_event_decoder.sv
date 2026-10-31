// Validates an immutable, complete HCI Event held by an external packet RAM.
// The read port has one registered clock of latency, matching bt_h5_transport.
// No complete event RAM or CPU queue is duplicated here. Not profile-selected.
module workstation_hci_event_decoder (
    input wire clk_i, reset_ni,
    input wire packet_valid_i,
    input wire [8:0] packet_length_i,
    output reg [8:0] packet_read_address_o,
    input wire [7:0] packet_read_data_i,
    input wire packet_release_i,
    output reg packet_consume_o, packet_done_o,
    output reg [7:0] packet_event_o,
    output reg fault_o,
    output reg [3:0] fault_reason_o,

    output reg handle_open_o, handle_close_o, handle_is_le_o,
    output reg [11:0] handle_o,
    input wire handle_open_ready_i,
    input wire [31:0] handle_open_generation_i,
    output reg handle_admitted_o,
    output reg [31:0] handle_generation_o,

    output reg completion_start_o, completion_pair_valid_o,
    output reg [11:0] completion_handle_o,
    output reg [15:0] completion_count_o,
    output reg completion_commit_o,

    output reg command_response_o,
    output reg response_is_complete_o,
    output reg [7:0] response_credits_o, response_status_o,
    output reg [15:0] response_opcode_o,
    output reg buffer_info_valid_o, buffer_info_is_le_o,
    output reg [15:0] buffer_info_length_o, buffer_info_count_o
);
    localparam [3:0] IDLE=0, READ_WAIT=1, READ_BYTE=2, VALIDATE=3,
        DISPATCH=4, RETIRE=5, HOLD=6, FAILED=7;
    localparam [3:0] F_LENGTH=1, F_SCHEMA=2, F_HANDLE=3, F_LIFETIME=4,
        F_HARDWARE=5;
    reg [3:0] state;
    reg [8:0] length;
    reg [7:0] prefix [0:15];
    reg [7:0] pair_handle_low, pair_count_low;
    reg [3:0] pair_handle_high;
    integer index;
    wire [15:0] complete_opcode = {prefix[4],prefix[3]};
    wire [15:0] status_opcode = {prefix[5],prefix[4]};
    wire [15:0] lifecycle_handle = {prefix[4],prefix[3]};
    wire [15:0] le_handle = {prefix[5],prefix[4]};

    task automatic fail;
        input [3:0] reason;
        begin
            fault_o<=1;fault_reason_o<=reason;state<=FAILED;
            packet_done_o<=0;packet_consume_o<=1;
            completion_start_o<=0;completion_pair_valid_o<=0;completion_commit_o<=0;
            command_response_o<=0;handle_open_o<=0;handle_close_o<=0;
            buffer_info_valid_o<=0;
        end
    endtask
    always @(posedge clk_i) begin
        packet_consume_o<=0;handle_open_o<=0;handle_close_o<=0;
        completion_start_o<=0;completion_pair_valid_o<=0;completion_commit_o<=0;
        command_response_o<=0;buffer_info_valid_o<=0;
        if (!reset_ni) begin
            state<=IDLE;packet_read_address_o<=0;length<=0;packet_done_o<=0;
            packet_event_o<=0;fault_o<=0;fault_reason_o<=0;
            handle_is_le_o<=0;handle_o<=0;handle_admitted_o<=0;handle_generation_o<=0;
            completion_handle_o<=0;completion_count_o<=0;
            response_credits_o<=0;response_status_o<=0;response_opcode_o<=0;response_is_complete_o<=0;
            buffer_info_is_le_o<=0;buffer_info_length_o<=0;buffer_info_count_o<=0;
            pair_handle_low<=0;pair_handle_high<=0;pair_count_low<=0;
            for(index=0;index<16;index=index+1)prefix[index]<=0;
        end else if (state != IDLE && state != FAILED &&
            (!packet_valid_i || packet_length_i != length)) fail(F_LIFETIME);
        else case(state)
            IDLE: if(packet_valid_i)begin
                packet_done_o<=0;handle_admitted_o<=0;handle_generation_o<=0;
                packet_read_address_o<=0;length<=packet_length_i;
                if(packet_length_i<2 || packet_length_i>257)fail(F_LENGTH);
                else state<=READ_WAIT;
            end
            READ_WAIT: state<=READ_BYTE;
            READ_BYTE: begin
                if(packet_read_address_o==0 && packet_read_data_i==0)fail(F_SCHEMA);
                else if(packet_read_address_o==1 && length!={1'b0,packet_read_data_i}+9'd2)fail(F_LENGTH);
                else if(packet_event_o==8'h13 && packet_read_address_o==2 &&
                    (packet_read_data_i>63 || length!=9'd3+{1'b0,packet_read_data_i[5:0],2'b00}))fail(F_SCHEMA);
                else if(packet_event_o==8'h13 && packet_read_address_o>=3 &&
                    ((packet_read_address_o-9'd3)&9'd3)==1 &&
                    {packet_read_data_i,pair_handle_low}>16'h0eff)fail(F_HANDLE);
                else begin
                    if(packet_read_address_o<16)prefix[packet_read_address_o[3:0]]<=packet_read_data_i;
                    if(packet_read_address_o==0)packet_event_o<=packet_read_data_i;
                    if(packet_event_o==8'h13 && packet_read_address_o==2)begin
                        // Eight-bit event parameter length permits at most63
                        // pairs. Num_Handles zero commits a legal empty batch.
                        completion_start_o<=1;
                    end else if(packet_event_o==8'h13 && packet_read_address_o>=3)begin
                        case((packet_read_address_o-9'd3)&9'd3)
                            0: pair_handle_low<=packet_read_data_i;
                            1: pair_handle_high<=packet_read_data_i[3:0];
                            2: pair_count_low<=packet_read_data_i;
                            3: begin
                                completion_pair_valid_o<=1;
                                completion_handle_o<={pair_handle_high[3:0],pair_handle_low};
                                completion_count_o<={packet_read_data_i,pair_count_low};
                            end
                        endcase
                    end
                    if(packet_read_address_o+1'b1==length)state<=VALIDATE;
                    else begin packet_read_address_o<=packet_read_address_o+1'b1;state<=READ_WAIT;end
                end
            end
            VALIDATE: begin
                state<=DISPATCH;
                case(packet_event_o)
                    8'h03: begin
                        if(length!=13)fail(F_SCHEMA);
                        else if(prefix[2]==0 && (lifecycle_handle>16'h0eff || prefix[11]>1))fail(F_HANDLE);
                    end
                    8'h05: begin
                        if(length!=6)fail(F_SCHEMA);
                        else if(prefix[2]==0 && lifecycle_handle>16'h0eff)fail(F_HANDLE);
                    end
                    8'h0e: begin
                        if(length<5 || (complete_opcode!=0 && length<6))fail(F_SCHEMA);
                        else if(complete_opcode==16'h1005 && prefix[5]==0 && length!=13)fail(F_SCHEMA);
                        else if(complete_opcode==16'h2002 && prefix[5]==0 && length!=9)fail(F_SCHEMA);
                    end
                    8'h0f: if(length!=6)fail(F_SCHEMA);
                    8'h10,8'h1a: fail(F_HARDWARE);
                    8'h13: if(length<3)fail(F_SCHEMA);
                    8'h3e: begin
                        if(length<3)fail(F_SCHEMA);
                        else if(prefix[2]==1 || prefix[2]==10)begin
                            if((prefix[2]==1 && length!=21) || (prefix[2]==10 && length!=33))fail(F_SCHEMA);
                            else if(prefix[3]==0 && le_handle>16'h0eff)fail(F_HANDLE);
                        end
                    end
                    default: begin end // Other complete events go to the external bounded router.
                endcase
            end
            DISPATCH: begin
                state<=RETIRE;
                case(packet_event_o)
                    8'h03: if(prefix[2]==0 && prefix[11]==1)begin
                        handle_open_o<=1;handle_is_le_o<=0;handle_o<=lifecycle_handle[11:0];
                    end
                    8'h05: if(prefix[2]==0)begin handle_close_o<=1;handle_o<=lifecycle_handle[11:0];end
                    8'h0e: begin
                        response_is_complete_o<=1;
                        command_response_o<=1;response_credits_o<=prefix[2];response_opcode_o<=complete_opcode;
                        response_status_o<=complete_opcode == 0 ? 0 : prefix[5];
                        if(prefix[5]==0 && (complete_opcode==16'h1005 || complete_opcode==16'h2002))begin
                            buffer_info_valid_o<=1;buffer_info_is_le_o<=complete_opcode==16'h2002;
                            buffer_info_length_o<={prefix[7],prefix[6]};
                            buffer_info_count_o<=complete_opcode == 16'h2002 ? {8'd0,prefix[8]} : {prefix[10],prefix[9]};
                        end
                    end
                    8'h0f: begin
                        response_is_complete_o<=0;
                        command_response_o<=1;response_status_o<=prefix[2];response_credits_o<=prefix[3];
                        response_opcode_o<=status_opcode;
                    end
                    8'h13: completion_commit_o<=1;
                    8'h3e: if((prefix[2]==1 || prefix[2]==10) && prefix[3]==0)begin
                        handle_open_o<=1;handle_is_le_o<=1;handle_o<=le_handle[11:0];
                    end
                    default: begin end
                endcase
            end
            RETIRE: begin
                // The flow owner accepts the preceding cycle's pulse here.
                if(handle_open_o)begin
                    handle_admitted_o<=handle_open_ready_i;
                    handle_generation_o<=handle_open_ready_i?handle_open_generation_i:0;
                end
                packet_done_o<=1;state<=HOLD;
            end
            HOLD: if(packet_release_i)begin
                packet_done_o<=0;packet_consume_o<=1;state<=IDLE;
            end
            FAILED: begin end
            default: fail(F_SCHEMA);
        endcase
    end
endmodule
