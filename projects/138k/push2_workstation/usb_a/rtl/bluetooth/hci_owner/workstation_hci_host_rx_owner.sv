// Controller-to-host physical ACL accounting and external RAM leases.
// No payload RAM, H5 engine, CPU queue or second outbound credit owner.
module workstation_hci_host_rx_owner #(
    parameter integer HANDLE_SLOTS=2, RX_SLOTS=4, BLE_RESERVE=1,
    parameter integer HOST_DATA_LIMIT=276
) (
    input wire clk_i,reset_ni,transport_fault_i,activate_i,
    output reg active_o,fault_o,
    output reg [3:0] fault_reason_o,
    output wire [15:0] host_data_limit_o,host_packet_count_o,
    output reg [15:0] controller_budget_o,
    input wire [HANDLE_SLOTS-1:0] known_active_i,known_is_le_i,
    input wire [HANDLE_SLOTS*12-1:0] known_handles_i,
    input wire [HANDLE_SLOTS*32-1:0] known_generations_i,

    // One already complete/validated HCI ACL packet. The outer router must
    // consume/copy exactly once when take is asserted with ready.
    input wire rx_valid_i,rx_take_i,rx_want_lease_i,
    input wire [15:0] rx_handle_i,rx_data_length_i,
    output wire rx_ready_o,rx_can_hold_o,
    output reg lease_granted_o,rx_dropped_o,rx_is_le_o,
    output reg [1:0] rx_drop_reason_o,
    output wire lease_exhausted_o,
    output reg [3:0] rx_slot_o,
    output reg [31:0] rx_lease_o,rx_generation_o,

    // Release only after all reads/copy/DMA references to this lease ended.
    input wire release_valid_i,
    input wire [31:0] release_lease_i,
    output wire release_ready_o,
    output reg release_rejected_o,
    input wire disconnect_valid_i,
    input wire [11:0] disconnect_handle_i,
    input wire [31:0] disconnect_generation_i,
    output wire [RX_SLOTS-1:0] lease_active_o,lease_retired_o,
    output wire [RX_SLOTS*32-1:0] lease_tokens_o,
    output wire [HANDLE_SLOTS*16-1:0] outstanding_o,pending_returns_o,

    // Complete Host_Number_Of_Completed_Packets, hardware owner3 only.
    // can_send gates irreversible acceptance through the shared flow/H5 owner.
    // Bytes remain unchanged from offer through transport_done, including H5
    // internal retries. Accepted commands never replay after uncertainty.
    output wire return_valid_o,return_can_send_o,
    output wire [1:0] return_owner_o,
    output wire [15:0] return_opcode_o,
    output wire [8:0] return_length_o,
    input wire [3:0] return_address_i,
    output reg [7:0] return_data_o,
    input wire return_send_i,return_transport_done_i,
    output reg return_inflight_o,
    output wire [31:0] return_generation_o,
    output reg [31:0] dropped_packets_o,rejected_releases_o
);
    localparam [15:0] CAPACITY=RX_SLOTS[15:0],DATA_LIMIT=HOST_DATA_LIMIT[15:0];
    localparam [3:0] F_TRANSPORT=1,F_ACTIVATION=2,F_RX=3,F_OWNER=4,
        F_RETURN=5,F_INVARIANT=6;
    reg [RX_SLOTS-1:0] leased,retired;
    reg [31:0] tokens[0:RX_SLOTS-1],lease_generations[0:RX_SLOTS-1];
    reg [11:0] lease_handles[0:RX_SLOTS-1];
    reg [15:0] outstanding[0:HANDLE_SLOTS-1],pending[0:HANDLE_SLOTS-1];
    reg [31:0] generations[0:HANDLE_SLOTS-1];
    reg [11:0] handles[0:HANDLE_SLOTS-1];
    reg [31:0] last_lease;
    reg offered;
    reg [11:0] offer_handle;
    reg [31:0] offer_generation;
    reg [15:0] offer_count;
    integer offer_slot;
    integer rx_owner,free_slot,free_count,release_slot,release_owner,disconnect_slot,return_candidate,index;
    reg owner_drift,action_owner_drift,invariant_bad;
    reg [31:0] total_outstanding;
    assign host_data_limit_o=DATA_LIMIT;
    assign host_packet_count_o=CAPACITY;
    assign lease_active_o=leased;
    assign lease_retired_o=retired;
    assign lease_exhausted_o=last_lease==32'hffffffff;
    assign return_owner_o=3;
    assign return_opcode_o=16'h0c35;
    assign return_length_o=8;
    assign return_generation_o=offer_generation;
    for(genvar at=0;at<RX_SLOTS;at=at+1)begin: expose_lease
        assign lease_tokens_o[32*at+:32]=tokens[at];
    end
    for(genvar at=0;at<HANDLE_SLOTS;at=at+1)begin: expose_account
        assign outstanding_o[16*at+:16]=outstanding[at];
        assign pending_returns_o[16*at+:16]=pending[at];
    end
    // Keep identity tests as bitwise trees, including the late disconnect
    // generation, rather than a serial equality carry chain after selection.
    // Preserve eight-bit boundaries: a full-width XOR reduction is otherwise
    // recognized as another equality carry chain by the device mapper.
    (* syn_keep=1 *) wire [HANDLE_SLOTS*4-1:0] disconnect_generation_changed_groups;
    wire [HANDLE_SLOTS-1:0] disconnect_generation_changed;
    for(genvar identity_handle=0;identity_handle<HANDLE_SLOTS;identity_handle=identity_handle+1)begin:disconnect_identity
        for(genvar identity_group=0;identity_group<4;identity_group=identity_group+1)begin:g_generation
            assign disconnect_generation_changed_groups[identity_handle*4+identity_group]=
                |(generations[identity_handle][identity_group*8+:8]^disconnect_generation_i[identity_group*8+:8]);
        end
        assign disconnect_generation_changed[identity_handle]=
            |disconnect_generation_changed_groups[identity_handle*4+:4];
    end
    // Compare each stored/live generation before the drift predicates.
    // Keep byte boundaries explicit so equality cannot become a serial carry.
    (* syn_keep=1 *) wire [HANDLE_SLOTS*4-1:0] known_generation_changed_groups;
    wire [HANDLE_SLOTS-1:0] known_generation_changed;
    for(genvar known_handle=0;known_handle<HANDLE_SLOTS;known_handle=known_handle+1)begin:known_identity
        for(genvar known_group=0;known_group<4;known_group=known_group+1)begin:g_generation
            assign known_generation_changed_groups[known_handle*4+known_group]=
                |(generations[known_handle][known_group*8+:8]^
                  known_generations_i[known_handle*32+known_group*8+:8]);
        end
        assign known_generation_changed[known_handle]=
            |known_generation_changed_groups[known_handle*4+:4];
    end
    // Action readiness excludes a known disconnect edge. Preserve the full
    // owner drift for real disconnect/fault processing and unknown controls.
    (* syn_keep=1 *) reg action_owner_drift_fence;
    always @* begin
        case(disconnect_valid_i)
            1'b0,1'b1:action_owner_drift_fence=action_owner_drift;
            default:action_owner_drift_fence=owner_drift;
        endcase
    end
    always @* begin
        rx_owner=-1;free_slot=-1;free_count=0;release_slot=-1;release_owner=-1;
        disconnect_slot=-1;return_candidate=-1;owner_drift=0;action_owner_drift=0;invariant_bad=0;total_outstanding=0;
        for(integer at=0;at<RX_SLOTS;at=at+1)begin
            if(!leased[at])begin free_count=free_count+1;if(free_slot==-1)free_slot=at;end
            if(leased[at]&&!(|(tokens[at]^release_lease_i)))release_slot=at;
        end
        for(integer at=0;at<HANDLE_SLOTS;at=at+1)begin
            if(known_active_i[at]&&!(|({4'd0,known_handles_i[12*at+:12]}^rx_handle_i)))rx_owner=at;
            if(disconnect_valid_i&&!(|(handles[at]^disconnect_handle_i))&&
                !disconnect_generation_changed[at])disconnect_slot=at;
            if(release_slot!=-1&&!(|(handles[at]^lease_handles[release_slot]))&&
                !(|(generations[at]^lease_generations[release_slot])))release_owner=at;
            if(pending[at]!=0&&return_candidate==-1)return_candidate=at;
            total_outstanding=total_outstanding+{16'd0,outstanding[at]};
            if(pending[at]>outstanding[at])invariant_bad=1;
            if(outstanding[at]!=0&&(!known_active_i[at]||(|(handles[at]^known_handles_i[12*at+:12]))||
                known_generation_changed[at]))action_owner_drift=1;
            if(outstanding[at]!=0&&(!known_active_i[at]||(|(handles[at]^known_handles_i[12*at+:12]))||
                known_generation_changed[at])&&
                !(disconnect_valid_i&&!(|(handles[at]^disconnect_handle_i))&&
                    !disconnect_generation_changed[at]))owner_drift=1;
        end
        if({16'd0,controller_budget_o}+total_outstanding!={16'd0,CAPACITY})invariant_bad=1;
    end
    wire rx_schema_good=rx_owner!=-1&&rx_handle_i<=16'h0eff&&rx_data_length_i!=0&&
        rx_data_length_i<=DATA_LIMIT&&known_generations_i[32*rx_owner+:32]!=0;
    wire rx_le=rx_owner!=-1&&known_is_le_i[rx_owner];
    assign rx_ready_o=active_o&&!fault_o&&!transport_fault_i&&!disconnect_valid_i&&
        !activate_i&&!(return_transport_done_i&&!return_inflight_o)&&
        controller_budget_o!=0&&rx_schema_good&&!action_owner_drift_fence&&!invariant_bad;
    assign rx_can_hold_o=rx_ready_o&&free_slot!=-1&&last_lease!=32'hffffffff&&
        (rx_le||free_count>BLE_RESERVE);
    assign release_ready_o=active_o&&!fault_o&&!transport_fault_i&&!disconnect_valid_i&&
        !activate_i&&!(return_transport_done_i&&!return_inflight_o)&&
        !rx_valid_i&&!action_owner_drift_fence&&!invariant_bad;
    assign return_valid_o=offered&&!return_inflight_o&&!fault_o;
    assign return_can_send_o=return_valid_o&&active_o&&!transport_fault_i&&
        !activate_i&&!(return_transport_done_i&&!return_inflight_o)&&
        !disconnect_valid_i&&!rx_valid_i&&!release_valid_i&&!action_owner_drift_fence&&!invariant_bad;
    always @* begin
        case(return_address_i)
            0:return_data_o=8'h35;
            1:return_data_o=8'h0c;
            2:return_data_o=5;
            3:return_data_o=1;
            4:return_data_o=offer_handle[7:0];
            5:return_data_o={4'd0,offer_handle[11:8]};
            6:return_data_o=offer_count[7:0];
            7:return_data_o=offer_count[15:8];
            default:return_data_o=0;
        endcase
    end
    task automatic fail;input [3:0] reason;
        begin fault_o<=1;fault_reason_o<=reason;end
    endtask
    initial begin
        if(HANDLE_SLOTS<1||HANDLE_SLOTS>16||RX_SLOTS<2||RX_SLOTS>16||
            BLE_RESERVE<1||BLE_RESERVE>=RX_SLOTS||HOST_DATA_LIMIT<4||HOST_DATA_LIMIT>276)
            $fatal(1,"unsupported host RX owner parameter");
    end
    always @(posedge clk_i)begin
        lease_granted_o<=0;rx_dropped_o<=0;release_rejected_o<=0;
        if(!reset_ni)begin
            active_o<=0;fault_o<=0;fault_reason_o<=0;controller_budget_o<=CAPACITY;
            leased<=0;retired<=0;last_lease<=0;
            rx_is_le_o<=0;rx_slot_o<=0;rx_lease_o<=0;rx_generation_o<=0;rx_drop_reason_o<=0;
            offered<=0;offer_handle<=0;offer_generation<=0;offer_count<=0;offer_slot<=0;
            return_inflight_o<=0;dropped_packets_o<=0;rejected_releases_o<=0;
            for(index=0;index<RX_SLOTS;index=index+1)begin
                tokens[index]<=0;lease_generations[index]<=0;lease_handles[index]<=0;
            end
            for(index=0;index<HANDLE_SLOTS;index=index+1)begin
                outstanding[index]<=0;pending[index]<=0;generations[index]<=0;handles[index]<=0;
            end
        end else if(!fault_o)begin
            if(transport_fault_i)fail(F_TRANSPORT);
            else if(activate_i&&(active_o||(|known_active_i)||rx_valid_i||return_send_i||release_valid_i||disconnect_valid_i))fail(F_ACTIVATION);
            else if(owner_drift)fail(F_OWNER);
            else if(invariant_bad)fail(F_INVARIANT);
            else if(rx_valid_i&&(!active_o||!rx_schema_good||controller_budget_o==0))fail(F_RX);
            else if(rx_take_i&&(!rx_valid_i||!rx_ready_o))fail(F_RX);
            else if(return_send_i&&(!return_can_send_o||offer_slot<0||offer_count==0||
                pending[offer_slot]<offer_count||outstanding[offer_slot]<offer_count))fail(F_RETURN);
            else if(return_transport_done_i&&!return_inflight_o)fail(F_RETURN);
            else if(disconnect_valid_i&&(disconnect_generation_i==0||disconnect_handle_i>12'heff))fail(F_OWNER);
            else if(release_valid_i&&release_ready_o&&release_slot!=-1&&
                !retired[release_slot]&&release_owner==-1)fail(F_OWNER);
            else begin
                if(activate_i)active_o<=1;
                if(return_transport_done_i)return_inflight_o<=0;
                if(disconnect_valid_i)begin
                    if(disconnect_slot!=-1)begin
                        controller_budget_o<=controller_budget_o+outstanding[disconnect_slot];
                        outstanding[disconnect_slot]<=0;pending[disconnect_slot]<=0;
                    end
                    for(index=0;index<RX_SLOTS;index=index+1)begin
                        if(leased[index]&&!(|(lease_handles[index]^disconnect_handle_i))&&
                            !(|(lease_generations[index]^disconnect_generation_i)))retired[index]<=1;
                    end
                    if(offered&&!(|(offer_handle^disconnect_handle_i))&&!(|(offer_generation^disconnect_generation_i)))
                        offered<=0;
                end else if(rx_take_i)begin
                    controller_budget_o<=controller_budget_o-1'b1;
                    outstanding[rx_owner]<=outstanding[rx_owner]+1'b1;
                    generations[rx_owner]<=known_generations_i[32*rx_owner+:32];
                    handles[rx_owner]<=rx_handle_i[11:0];
                    rx_is_le_o<=rx_le;rx_generation_o<=known_generations_i[32*rx_owner+:32];
                    if(rx_want_lease_i&&rx_can_hold_o)begin
                        leased[free_slot]<=1;retired[free_slot]<=0;tokens[free_slot]<=last_lease+1'b1;
                        last_lease<=last_lease+1'b1;
                        lease_generations[free_slot]<=known_generations_i[32*rx_owner+:32];
                        lease_handles[free_slot]<=rx_handle_i[11:0];
                        lease_granted_o<=1;rx_slot_o<=free_slot[3:0];rx_lease_o<=last_lease+1'b1;rx_drop_reason_o<=0;
                    end else begin
                        rx_dropped_o<=1;pending[rx_owner]<=pending[rx_owner]+1'b1;
                        rx_drop_reason_o<=!rx_want_lease_i ? 1 : lease_exhausted_o ? 3 : 2;
                        if(dropped_packets_o!=32'hffffffff)dropped_packets_o<=dropped_packets_o+1'b1;
                    end
                end else if(release_valid_i&&release_ready_o)begin
                    if(release_slot==-1)begin
                        release_rejected_o<=1;
                        if(rejected_releases_o!=32'hffffffff)rejected_releases_o<=rejected_releases_o+1'b1;
                    end else begin
                        if(!retired[release_slot])begin
                            pending[release_owner]<=pending[release_owner]+1'b1;
                        end
                        leased[release_slot]<=0;retired[release_slot]<=0;
                    end
                end else if(return_send_i)begin
                    pending[offer_slot]<=pending[offer_slot]-offer_count;
                    outstanding[offer_slot]<=outstanding[offer_slot]-offer_count;
                    controller_budget_o<=controller_budget_o+offer_count;
                    offered<=0;return_inflight_o<=1;
                end
                if(active_o&&!offered&&!return_inflight_o&&return_candidate!=-1&&
                    !rx_valid_i&&!release_valid_i&&!disconnect_valid_i&&!return_send_i&&!return_transport_done_i)begin
                    offered<=1;offer_slot<=return_candidate;offer_count<=pending[return_candidate];
                    offer_handle<=handles[return_candidate];offer_generation<=generations[return_candidate];
                end
            end
        end
    end
endmodule
