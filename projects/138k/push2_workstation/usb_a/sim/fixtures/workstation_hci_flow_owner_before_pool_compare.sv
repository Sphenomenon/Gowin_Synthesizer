// One controller command/ACL accounting authority. Not selected by a profile.
// Wire parsing and H5 packet queues surround this module; all inputs below are
// complete, validated HCI transactions in this clock domain.
module workstation_hci_flow_owner #(
    parameter integer HANDLE_SLOTS = 2,
    parameter integer H5_ACL_DATA_LIMIT = 276
) (
    input wire clk_i, reset_ni, transport_fault_i,
    input wire config_valid_i,
    input wire [15:0] br_acl_length_i, br_acl_count_i,
    input wire [15:0] le_acl_length_i, le_acl_count_i,
    output wire config_ready_o,
    output reg configured_o, fault_o,
    output reg [3:0] fault_reason_o,
    output wire le_shared_o,
    output wire [15:0] br_acl_limit_o, le_acl_limit_o,
    output reg [15:0] br_available_o, le_available_o,

    input wire handle_open_i, handle_close_i, handle_is_le_i,
    input wire [11:0] handle_i,
    output wire handle_open_ready_o,
    output wire [31:0] handle_open_generation_o,
    output reg handle_rejected_o,
    output wire [HANDLE_SLOTS-1:0] handle_active_o,
    output wire [HANDLE_SLOTS-1:0] handle_is_le_o,
    output wire [HANDLE_SLOTS*12-1:0] handle_numbers_o,
    output wire [HANDLE_SLOTS*32-1:0] handle_generations_o,
    output wire [HANDLE_SLOTS*16-1:0] handle_outstanding_o,

    input wire acl_valid_i, acl_send_i,
    input wire [11:0] acl_handle_i,
    input wire [31:0] acl_generation_i,
    input wire [15:0] acl_data_length_i,
    output wire acl_ready_o,
    output wire acl_invalid_o,
    output reg [2:0] acl_error_o,

    // Number Of Completed Packets is one atomic batch. No ACL transmission or
    // handle lifecycle change is accepted between start and commit/abort.
    input wire completion_start_i, completion_pair_valid_i,
    input wire [11:0] completion_handle_i,
    input wire [15:0] completion_count_i,
    input wire completion_commit_i, completion_abort_i,
    output reg completion_active_o,
    output wire completion_pair_ready_o,
    output reg [31:0] unknown_completion_packets_o,

    // owner 0=initializer, 1=BLE, 2=CPU classic, 3=host receive-credit return.
    input wire command_valid_i, command_send_i,
    input wire [1:0] command_owner_i,
    input wire [15:0] command_opcode_i,
    output wire command_ready_o, command_invalid_o,
    output reg [7:0] command_credits_o,
    output reg command_pending_o,
    input wire command_response_i, command_timeout_i,
    input wire response_is_complete_i,
    input wire [7:0] response_credits_i, response_status_i,
    input wire [15:0] response_opcode_i,
    output reg response_valid_o,
    output reg response_is_complete_o,
    output reg [1:0] response_owner_o,
    output reg [15:0] response_opcode_o,
    output reg [7:0] response_status_o
);
    localparam [3:0] F_TRANSPORT=1, F_CONFIG=2, F_PROTOCOL=3,
        F_ACL_SEND=4, F_COMPLETION=5, F_COMMAND_SEND=6,
        F_COMMAND_RESPONSE=7, F_COMMAND_TIMEOUT=8, F_HOST_COMPLETION=9;
    localparam [15:0] WIRE_ACL_LIMIT = H5_ACL_DATA_LIMIT[15:0];
    reg [15:0] br_capacity, le_capacity, br_length, le_length;
    reg shared_pool;
    reg [HANDLE_SLOTS-1:0] active, is_le;
    reg [11:0] numbers [0:HANDLE_SLOTS-1];
    reg [31:0] generations [0:HANDLE_SLOTS-1];
    reg [15:0] outstanding [0:HANDLE_SLOTS-1];
    reg [31:0] returns [0:HANDLE_SLOTS-1];
    reg [31:0] last_generation;
    reg [31:0] batch_unknown;
    reg [5:0] batch_pairs;
    reg [15:0] pending_opcode;
    reg [1:0] pending_owner;
    integer lifecycle_slot, free_slot, acl_slot, completion_slot, index;
    reg [32:0] br_return, le_return;
    reg completion_bad;
    wire lifecycle_action = handle_open_i || handle_close_i;
    wire completion_action = completion_start_i || completion_pair_valid_i ||
                             completion_commit_i || completion_abort_i;
    wire control_action = config_valid_i || lifecycle_action || completion_action;
    wire special_command = command_owner_i == 3 && command_opcode_i == 16'h0c35;
    wire ordinary_command = command_owner_i != 3 && command_opcode_i != 16'h0c35 &&
                            command_opcode_i != 16'h0000;
    wire command_schema = special_command || ordinary_command;
    wire config_good = (br_acl_count_i != 0 && br_acl_length_i != 0) &&
        (le_acl_count_i == 0 || le_acl_length_i != 0);
    wire protocol_bad = (config_valid_i && (lifecycle_action || completion_action)) ||
        (lifecycle_action && completion_action) || (handle_open_i && handle_close_i) ||
        (completion_start_i && (completion_active_o || completion_pair_valid_i ||
            completion_commit_i || completion_abort_i)) ||
        (completion_commit_i && completion_abort_i) ||
        ((completion_commit_i || completion_abort_i) && completion_pair_valid_i) ||
        (completion_active_o && lifecycle_action) ||
        ((completion_pair_valid_i || completion_commit_i || completion_abort_i) && !completion_active_o);
    wire response_bad = command_response_i &&
        (response_opcode_i == 16'h0c35 ||
         (response_opcode_i != 0 && (!command_pending_o || response_opcode_i != pending_opcode)));
    wire transaction_bad =
        (config_valid_i && (!config_ready_o || !config_good)) ||
        (handle_close_i && (!configured_o || completion_active_o)) ||
        (completion_start_i && !configured_o) ||
        (completion_pair_valid_i && (!completion_pair_ready_o || batch_pairs == 63)) ||
        (completion_commit_i && completion_bad);
    assign le_shared_o = shared_pool;
    assign br_acl_limit_o = br_length;
    assign le_acl_limit_o = shared_pool ? br_length : le_length;
    assign config_ready_o = !configured_o && !fault_o && !completion_active_o;
    assign handle_open_ready_o = configured_o && !fault_o && !completion_active_o &&
        !config_valid_i && !completion_action && !handle_close_i &&
        !transport_fault_i && !command_timeout_i && !response_bad && !protocol_bad &&
        lifecycle_slot == -1 && free_slot != -1 && handle_i <= 12'heff &&
        last_generation != 32'hffffffff;
    assign handle_open_generation_o = handle_open_ready_o ? last_generation + 1'b1 : 32'd0;
    assign handle_active_o = active;
    assign handle_is_le_o = is_le;
    for (genvar slot = 0; slot < HANDLE_SLOTS; slot = slot + 1) begin: expose
        assign handle_numbers_o[12*slot+:12] = numbers[slot];
        assign handle_generations_o[32*slot+:32] = generations[slot];
        assign handle_outstanding_o[16*slot+:16] = outstanding[slot];
    end

    always @* begin
        lifecycle_slot=-1; free_slot=-1; acl_slot=-1; completion_slot=-1;
        br_return=0; le_return=0; completion_bad=0;
        for (integer at = 0; at < HANDLE_SLOTS; at = at + 1) begin
            if (!active[at] && free_slot == -1) free_slot=at;
            if (active[at] && numbers[at] == handle_i) lifecycle_slot=at;
            if (active[at] && numbers[at] == acl_handle_i) acl_slot=at;
            if (active[at] && numbers[at] == completion_handle_i) completion_slot=at;
            if (returns[at] > {16'd0,outstanding[at]}) completion_bad=1;
            if (is_le[at] && !shared_pool) le_return=le_return+{1'b0,returns[at]};
            else br_return=br_return+{1'b0,returns[at]};
        end
        if ({17'd0,br_available_o}+br_return > {17'd0,br_capacity} ||
            {17'd0,le_available_o}+le_return > {17'd0,le_capacity}) completion_bad=1;
        acl_error_o=0;
        if (!configured_o || fault_o) acl_error_o=1;
        else if (acl_slot == -1) acl_error_o=2;
        else if (acl_generation_i != generations[acl_slot]) acl_error_o=3;
        else if (acl_data_length_i == 0 ||
            acl_data_length_i > (is_le[acl_slot] && !shared_pool ? le_length : br_length)) acl_error_o=4;
    end
    wire acl_credit = acl_slot != -1 &&
        (is_le[acl_slot] && !shared_pool ? le_available_o != 0 : br_available_o != 0);
    assign acl_ready_o = acl_error_o == 0 && acl_credit && !completion_active_o && !control_action &&
        !transport_fault_i && !command_timeout_i && !response_bad;
    assign acl_invalid_o = acl_valid_i && acl_error_o != 0;
    assign completion_pair_ready_o = configured_o && !fault_o && completion_active_o &&
        !config_valid_i && !lifecycle_action && !completion_start_i &&
        !completion_commit_i && !completion_abort_i && batch_pairs != 63 &&
        !transport_fault_i && !command_timeout_i && !response_bad && !protocol_bad;
    // Only one ordinary command is in flight even if the controller advertises
    // a larger command queue. The special host-credit command never consumes
    // command credit and never becomes the pending ordinary opcode.
    assign command_ready_o = !fault_o && !transport_fault_i && !command_response_i &&
        !command_timeout_i && command_schema &&
        !transaction_bad && !protocol_bad &&
        (special_command || (!command_pending_o && command_credits_o != 0));
    assign command_invalid_o = command_valid_i && !command_schema;

    task automatic fail;
        input [3:0] reason;
        begin fault_o<=1;fault_reason_o<=reason;end
    endtask
    initial begin
        if (HANDLE_SLOTS < 1 || HANDLE_SLOTS > 16 || H5_ACL_DATA_LIMIT < 1 || H5_ACL_DATA_LIMIT > 276)
            $fatal(1, "unsupported HCI flow owner parameter");
    end
    always @(posedge clk_i) begin
        response_valid_o<=0;handle_rejected_o<=0;
        if (!reset_ni) begin
            configured_o<=0;fault_o<=0;fault_reason_o<=0;
            br_capacity<=0;le_capacity<=0;br_length<=0;le_length<=0;shared_pool<=0;
            br_available_o<=0;le_available_o<=0;active<=0;is_le<=0;last_generation<=0;
            completion_active_o<=0;batch_unknown<=0;batch_pairs<=0;unknown_completion_packets_o<=0;
            command_credits_o<=1;command_pending_o<=0;pending_opcode<=0;pending_owner<=0;
            response_owner_o<=0;response_opcode_o<=0;response_status_o<=0;response_is_complete_o<=0;
            for (index=0;index<HANDLE_SLOTS;index=index+1) begin
                numbers[index]<=0;generations[index]<=0;outstanding[index]<=0;returns[index]<=0;
            end
        end else if (!fault_o) begin
            if (transport_fault_i) fail(F_TRANSPORT);
            else if (command_timeout_i) begin
                if (command_pending_o) fail(F_COMMAND_TIMEOUT);
                else fail(F_PROTOCOL);
            end
            else if (response_bad) begin
                if (response_opcode_i == 16'h0c35) fail(F_HOST_COMPLETION);
                else fail(F_COMMAND_RESPONSE);
            end
            else if (protocol_bad) fail(F_PROTOCOL);
            else if (config_valid_i && (!config_ready_o || !config_good)) fail(F_CONFIG);
            else if ((handle_close_i && !configured_o) ||
                     (completion_start_i && !configured_o) ||
                     (completion_pair_valid_i && (!completion_pair_ready_o || batch_pairs == 63))) fail(F_PROTOCOL);
            else if (completion_commit_i && completion_bad) fail(F_COMPLETION);
            else if (acl_send_i && (!acl_valid_i || !acl_ready_o || command_send_i)) fail(F_ACL_SEND);
            else if (command_send_i && (!command_valid_i || !command_ready_o)) fail(F_COMMAND_SEND);
            else begin
                if (config_valid_i) begin
                    configured_o<=1;shared_pool<=le_acl_count_i==0;
                    br_capacity<=br_acl_count_i;le_capacity<=le_acl_count_i;
                    br_available_o<=br_acl_count_i;le_available_o<=le_acl_count_i;
                    br_length<=br_acl_length_i>WIRE_ACL_LIMIT ? WIRE_ACL_LIMIT : br_acl_length_i;
                    le_length<=le_acl_length_i>WIRE_ACL_LIMIT ? WIRE_ACL_LIMIT : le_acl_length_i;
                end
                if (handle_open_i) begin
                    if (!handle_open_ready_o) handle_rejected_o<=1;
                    else begin
                        active[free_slot]<=1;is_le[free_slot]<=handle_is_le_i;numbers[free_slot]<=handle_i;
                        generations[free_slot]<=last_generation+1'b1;last_generation<=last_generation+1'b1;
                        outstanding[free_slot]<=0;returns[free_slot]<=0;
                    end
                end
                if (handle_close_i) begin
                    if (lifecycle_slot == -1) handle_rejected_o<=1;
                    else begin
                        // HCI section 4.3: Disconnection Complete frees all
                        // controller buffers still outstanding for this handle.
                        if (is_le[lifecycle_slot] && !shared_pool)
                            le_available_o<=le_available_o+outstanding[lifecycle_slot];
                        else br_available_o<=br_available_o+outstanding[lifecycle_slot];
                        active[lifecycle_slot]<=0;outstanding[lifecycle_slot]<=0;returns[lifecycle_slot]<=0;
                    end
                end
                if (acl_send_i) begin
                    outstanding[acl_slot]<=outstanding[acl_slot]+1'b1;
                    if (is_le[acl_slot] && !shared_pool) le_available_o<=le_available_o-1'b1;
                    else br_available_o<=br_available_o-1'b1;
                end
                if (completion_start_i) begin
                    completion_active_o<=1;batch_unknown<=0;batch_pairs<=0;
                    for (index=0;index<HANDLE_SLOTS;index=index+1) returns[index]<=0;
                end
                if (completion_pair_valid_i) begin
                    batch_pairs<=batch_pairs+1'b1;
                    if (completion_slot == -1) batch_unknown<=batch_unknown+{16'd0,completion_count_i};
                    else returns[completion_slot]<=returns[completion_slot]+{16'd0,completion_count_i};
                end
                if (completion_abort_i) begin
                    completion_active_o<=0;
                    for (index=0;index<HANDLE_SLOTS;index=index+1) returns[index]<=0;
                end
                if (completion_commit_i) begin
                    completion_active_o<=0;
                    br_available_o<=br_available_o+br_return[15:0];
                    le_available_o<=le_available_o+le_return[15:0];
                    if ({1'b0,unknown_completion_packets_o}+{1'b0,batch_unknown}>33'h0ffffffff)
                        unknown_completion_packets_o<=32'hffffffff;
                    else unknown_completion_packets_o<=unknown_completion_packets_o+batch_unknown;
                    for (index=0;index<HANDLE_SLOTS;index=index+1) begin
                        outstanding[index]<=outstanding[index]-returns[index][15:0];returns[index]<=0;
                    end
                end
                if (command_send_i && !special_command) begin
                    command_pending_o<=1;pending_opcode<=command_opcode_i;pending_owner<=command_owner_i;
                    command_credits_o<=command_credits_o-1'b1;
                end
                if (command_response_i) begin
                    command_credits_o<=response_credits_i;
                    if (response_opcode_i == 16'h0000) begin end
                    else begin
                        command_pending_o<=0;response_valid_o<=1;response_owner_o<=pending_owner;
                        response_is_complete_o<=response_is_complete_i;
                        response_opcode_o<=response_opcode_i;response_status_o<=response_status_i;
                    end
                end
            end
        end
    end
endmodule
