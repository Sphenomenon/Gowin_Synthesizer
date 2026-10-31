// The native physical HCI owner. One H5/UART, one credit ledger and one
// irreversible private TX slot serve initializer, bootstrap, BLE and AE350.
module workstation_hci_native_transport #(
    parameter bit SESSION_ONLY_PAIRING=0,
    parameter integer CLK_HZ=50000000,
    parameter integer BOOTSTRAP_TIMEOUT_CYCLES=CLK_HZ,
    parameter integer COMMAND_TIMEOUT_CYCLES=CLK_HZ*2
) (
    input wire clk_i,reset_ni,enable_i,observer_reset_ni,
    input wire link_up_i,physical_fault_i,
    input wire [63:0] boot_id_i,
    input wire initializer_handoff_i,initialized_i,
    output wire host_flow_ready_o,
    output wire [31:0] controller_epoch_o,classic_generation_o,
    output wire classic_active_o,
    output reg classic_ready_o,
    output wire fault_o,classic_fenced_o,
    output wire [15:0] ble_acl_limit_o,
    input wire init_tx_start_i,
    input wire [3:0] init_tx_type_i,
    input wire [8:0] init_tx_length_i,
    output wire [8:0] init_tx_address_o,
    input wire [7:0] init_tx_data_i,
    output wire init_tx_ready_o,init_tx_done_o,init_tx_error_o,
    output wire init_rx_valid_o,
    output wire [3:0] init_rx_type_o,
    output wire [8:0] init_rx_length_o,
    input wire [8:0] init_rx_address_i,
    output wire [7:0] init_rx_data_o,
    input wire init_rx_consume_i,
    input wire ble_tx_start_i,
    input wire [3:0] ble_tx_type_i,
    input wire [8:0] ble_tx_length_i,
    output wire [8:0] ble_tx_address_o,
    input wire [7:0] ble_tx_data_i,
    output wire ble_tx_ready_o,ble_tx_done_o,ble_tx_error_o,
    output wire ble_rx_valid_o,
    output wire [3:0] ble_rx_type_o,
    output wire [8:0] ble_rx_length_o,
    input wire [8:0] ble_rx_address_i,
    output wire [7:0] ble_rx_data_o,
    input wire ble_rx_consume_i,
    output wire h5_tx_start_o,
    output wire [3:0] h5_tx_type_o,
    output wire [8:0] h5_tx_length_o,
    input wire [8:0] h5_tx_address_i,
    output reg [7:0] h5_tx_data_o,
    input wire h5_tx_ready_i,h5_tx_done_i,h5_tx_error_i,
    input wire h5_rx_valid_i,
    input wire [3:0] h5_rx_type_i,
    input wire [8:0] h5_rx_length_i,
    output wire [8:0] h5_rx_address_o,
    input wire [7:0] h5_rx_data_i,
    output reg h5_rx_consume_o,
    input wire command_valid_i,command_write_i,
    input wire [11:0] command_address_i,
    input wire [31:0] command_data_i,
    input wire [3:0] command_strobes_i,
    output wire command_ready_o,response_error_o,
    output wire [31:0] response_data_o
);
    reg [3:0] tx_state;
    reg [2:0] tx_origin,pending_origin,event_origin;
    reg [3:0] tx_type;
    reg [8:0] tx_length,tx_index;
    reg tx_read_wait,turn_cpu;
    reg [1:0] grant_age;
    // Six bytes cover the complete reviewed Write Class of Device command.
    // Longer accepted commands still use the existing full transmit buffer.
    reg [7:0] tx_header [0:5];
    reg [31:0] tx_generation,tx_token,pending_token;
    reg [11:0] disconnect_handle;
        reg disconnect_issued;
    reg [31:0] command_age,disconnect_age;
    reg local_fault,classic_fenced,link_seen,boot_started;
    wire flow_fault,decoder_fault,host_fault,bootstrap_fault,handle_rejected;
    wire observer_lost,cpu_queue_fault,cpu_fence;
    reg br_accept_pending;
    reg [31:0] published_epoch,published_generation;
    reg ble_cancelled;
    wire cpu_schedulable;
    wire br_admission;
    wire [31:0] epoch;
    wire [1:0] known_active,known_le;
    wire [23:0] known_handles;
    wire [63:0] known_generations;
    wire [31:0] known_outstanding;
    wire configured,le_shared,config_ready;
    wire [15:0] br_limit,le_limit,br_available,le_available;
    wire [7:0] command_credits;
    wire command_pending,flow_command_ready,flow_command_invalid;
    wire flow_acl_ready,flow_acl_invalid;
    wire [2:0] flow_acl_error;
    wire [3:0] flow_reason,decoder_reason,host_reason,bootstrap_reason;
    wire flow_response_valid,flow_response_complete;
    wire [1:0] flow_response_owner;
    wire [15:0] flow_response_opcode;
    wire [7:0] flow_response_status;
    wire command_timeout;
    reg [31:0] time_ms,time_div;
    integer br_slot,tx_handle_slot,close_slot;
    reg [31:0] current_br_generation,close_generation;
    reg [11:0] current_br_handle;
    wire [11:0] tx_handle;
    wire [1:0] selected_owner;
    wire [15:0] selected_opcode;
    wire [31:0] selected_generation;
    wire tx_offer;
    wire command_offer;
    wire acl_offer;
    wire return_still_valid;
    wire cpu_still_valid;
    wire tx_accept;
    reg [7:0] producer_data;
    wire tx_schema;
    wire cpu_context;
    wire cpu_tx_valid,cpu_tx_response;
    wire [31:0] cpu_tx_epoch,cpu_tx_generation,cpu_tx_token;
    wire [3:0] cpu_tx_type;
    wire [8:0] cpu_tx_length;
    wire [7:0] cpu_tx_data;
    reg cpu_tx_reject;
    reg [7:0] cpu_tx_reject_reason;
    wire cpu_tx_accept;
    wire cpu_tx_done;
    wire [8:0] cpu_rx_address;
    wire cpu_rx_ready,cpu_rx_copy_done;
    wire cpu_rx_offer;
    reg cpu_rx_drop;
    reg [31:0] event_generation,event_command_token;
    reg [11:0] event_handle;
    reg [1:0] event_owner;
    reg event_response,event_to_ble,event_to_cpu;
    wire [3:0] cpu_rx_type;
    wire [31:0] cpu_rx_generation;
    wire [11:0] cpu_rx_handle;
    wire boot_command_valid,boot_command_accept,boot_transport_done,boot_pool_valid,host_activate;
    wire [1:0] boot_command_owner;
    wire [15:0] boot_command_opcode,boot_br_length,boot_br_count,boot_le_length,boot_le_count;
    wire [8:0] boot_command_length;
    wire [7:0] boot_command_data;
    wire [15:0] host_data_limit,host_packet_count;
    wire boot_start;
    wire decoder_open,decoder_close,decoder_is_le,decoder_admitted,decoder_open_ready;
    wire [11:0] decoder_handle;
    wire [31:0] decoder_generation,decoder_open_generation;
    wire decoder_completion_start,decoder_completion_pair,decoder_completion_commit;
    wire [11:0] decoder_completion_handle;
    wire [15:0] decoder_completion_count;
    wire decoder_command_response,decoder_complete,decoder_buffer_valid,decoder_buffer_le;
    wire [7:0] decoder_credits,decoder_status,decoder_event;
    wire [15:0] decoder_opcode,decoder_buffer_length,decoder_buffer_count;
    wire completion_active,completion_pair_ready;
    wire [31:0] unknown_completions;
    reg [4:0] rx_state;
    reg [3:0] rx_type;
    reg [8:0] rx_length,rx_index;
    reg rx_read_wait;
    reg [7:0] rx_header [0:3];
    reg [1:0] physical_slot;
    reg [31:0] physical_lease,packet_generation;
    reg [11:0] packet_handle;
    reg packet_le;
    reg [7:0] stage_read_data,slot_read_data;
    wire [8:0] decoder_address,ble_copy_address;
    wire decoder_done,decoder_consume;
    wire ble_queue_ready,ble_copy_done,ble_queue_offer;
    wire route_from_slot;
    wire route_ble;
    wire [8:0] route_address;
    wire [8:0] stage_address;
    wire [7:0] route_read_data;
    wire event_packet_valid;
    wire host_active,host_rx_ready,host_can_hold,host_lease_granted,host_rx_dropped,host_rx_le;
    wire [1:0] host_drop_reason;
    wire host_lease_exhausted,host_release_ready,host_release_rejected;
    wire [3:0] host_rx_slot;
    wire [31:0] host_rx_lease,host_rx_generation;
    wire [15:0] host_budget;
    wire [3:0] host_leases,host_retired;
    wire [127:0] host_tokens;
    wire [31:0] host_outstanding,host_pending_returns,host_dropped,host_bad_releases;
    wire host_return_valid,host_return_can_send,host_return_inflight;
    wire [1:0] host_return_owner;
    wire [15:0] host_return_opcode;
    wire [8:0] host_return_length;
    wire [7:0] host_return_data;
    wire [31:0] host_return_generation;
    wire [15:0] rx_wire_handle;
    wire host_rx_valid;
    integer index;
    reg rx_fault,close_was_le;

    assign cpu_schedulable=cpu_tx_valid && !completion_active &&
        (cpu_tx_type==1 ? !command_pending && command_credits!=0 : br_available!=0);

    localparam [2:0] O_INIT=0,O_BOOT=1,O_BLE=2,O_CPU=3,O_RETURN=4,O_DISCONNECT=5;
    localparam [3:0] T_IDLE=0,T_GRANT=1,T_COPY=2,T_CHECK=3,T_OFFER=4,T_WAIT=5;
    localparam [4:0] R_IDLE=0,R_COPY=1,R_KIND=2,R_EVENT=3,R_EVENT_ROUTE=4,
        R_EVENT_COPY=5,R_EVENT_RELEASE=6,R_EVENT_RETIRE=7,R_INIT=8,
        R_ACL_ADMIT=9,R_ACL_RESULT=10,R_SLOT_COPY=11,R_ACL_ROUTE=12,
        R_ACL_COPY=13,R_ACL_RELEASE=14;

    assign br_admission=initialized_i && host_flow_ready_o && enable_i && link_up_i && h5_tx_ready_i &&
        !fault_o && !classic_fenced_o && br_slot==-1 && known_active!=2'b11 &&
        !br_accept_pending && !command_pending;
    assign epoch=boot_id_i[31:0]!=0 ? boot_id_i[31:0] : boot_id_i[63:32];

    assign command_timeout=command_pending && command_age>=COMMAND_TIMEOUT_CYCLES-1;
    assign fault_o=local_fault || rx_fault || flow_fault || decoder_fault || host_fault || bootstrap_fault;
    assign classic_fenced_o=classic_fenced || cpu_queue_fault;
    assign ble_acl_limit_o=le_limit;
    assign controller_epoch_o=epoch,classic_generation_o=current_br_generation;
    assign classic_active_o=br_slot!=-1 && !classic_fenced_o && !fault_o;

    always @(posedge clk_i)begin
        if(!reset_ni)begin time_ms<=0;time_div<=0;end
        else if(time_div==CLK_HZ/1000-1)begin time_div<=0;time_ms<=time_ms+1'b1;end
        else time_div<=time_div+1'b1;
    end

    assign tx_handle={tx_header[1][3:0],tx_header[0]};
    // Preserve the existing last-match priority while mapping handle tests
    // as bitwise reductions before the selected generation fans out.
    always @* begin
        br_slot=-1;tx_handle_slot=-1;close_slot=-1;
        current_br_generation=0;current_br_handle=0;close_generation=0;
        for(integer at=0;at<2;at=at+1)begin
            if(known_active[at] && !known_le[at])begin
                br_slot=at;current_br_generation=known_generations[32*at+:32];current_br_handle=known_handles[12*at+:12];
            end
            if(known_active[at] && !(|(known_handles[12*at+:12]^tx_handle)))tx_handle_slot=at;
            if(known_active[at] && !(|(known_handles[12*at+:12]^decoder_handle)))begin
                close_slot=at;close_generation=known_generations[32*at+:32];
            end
        end
    end
    assign selected_owner=tx_origin==O_BLE ? 2'd1 :
        tx_origin==O_CPU || tx_origin==O_DISCONNECT ? 2'd2 : tx_origin==O_RETURN ? 2'd3 : 2'd0;
    assign selected_opcode={tx_header[1],tx_header[0]};
    assign selected_generation=tx_origin==O_BLE && tx_handle_slot!=-1 ?
        known_generations[32*tx_handle_slot+:32] : tx_generation;
    assign tx_offer=tx_state==T_OFFER && enable_i && !fault_o;
    assign command_offer=tx_offer && tx_type==1;
    assign acl_offer=tx_offer && tx_type==2;
    assign return_still_valid=tx_origin!=O_RETURN ||
        (host_return_can_send && host_return_generation==tx_generation);
    assign cpu_still_valid=tx_origin!=O_CPU ||
        (!classic_fenced_o && !cpu_fence && !cpu_rx_drop && !observer_lost && observer_reset_ni && cpu_tx_valid && cpu_tx_token==tx_token);
    assign tx_accept=tx_offer && h5_tx_ready_i && return_still_valid && cpu_still_valid &&
        (tx_origin!=O_DISCONNECT || tx_generation==current_br_generation) &&
        (tx_type==1 ? flow_command_ready : flow_acl_ready) &&
        !(tx_origin==O_CPU && tx_type==1 && selected_opcode==16'h0409 && !br_admission);
    assign h5_tx_start_o=tx_accept;
    assign h5_tx_type_o=tx_type,h5_tx_length_o=tx_length;
    assign init_tx_address_o=tx_index,ble_tx_address_o=tx_index;
    // Existing producers raise start one clock after observing ready. Grant
    // reserves the slot through that registered request; no competing producer
    // can steal an advertised ready on the intervening edge.
    assign init_tx_ready_o=tx_state==T_GRANT && tx_origin==O_INIT && !fault_o;
    assign ble_tx_ready_o=tx_state==T_GRANT && tx_origin==O_BLE && grant_age<2 && !fault_o && !completion_active &&
        (ble_tx_type_i==1 ? !command_pending && command_credits!=0 :
         ble_tx_type_i==2 && (le_shared ? br_available!=0 : le_available!=0));
    assign init_tx_done_o=tx_state==T_WAIT && tx_origin==O_INIT && h5_tx_done_i;
    assign ble_tx_done_o=(tx_state==T_WAIT && tx_origin==O_BLE && h5_tx_done_i) || ble_cancelled;
    assign init_tx_error_o=fault_o && tx_origin==O_INIT;
    assign ble_tx_error_o=fault_o && tx_origin==O_BLE;

    always @* begin
        producer_data=0;
        case(tx_origin)
            O_INIT:producer_data=init_tx_data_i;
            O_BOOT:producer_data=boot_command_data;
            O_BLE:producer_data=ble_tx_data_i;
            O_CPU:producer_data=cpu_tx_data;
            O_RETURN:producer_data=host_return_data;
            O_DISCONNECT:case(tx_index)
                0:producer_data=8'h06;1:producer_data=8'h04;2:producer_data=3;
                3:producer_data=disconnect_handle[7:0];
                4:producer_data={4'd0,disconnect_handle[11:8]};5:producer_data=8'h13;
                default:begin end
            endcase
            default:begin end
        endcase
    end
    function automatic cpu_opcode_allowed(input [15:0] opcode);
        case(opcode)
            16'h1003,16'h1004,16'h0c56,16'h0c1a,16'h0406,16'h0409,16'h040a,
            16'h040b,16'h040c,16'h040e,16'h0411,16'h0413,16'h041b,16'h041c,
            16'h042b,16'h042c,16'h042d,16'h042f,16'h0433,16'h0434,16'h1408:
                cpu_opcode_allowed=1;
            16'h0c24:cpu_opcode_allowed=SESSION_ONLY_PAIRING;
            default:cpu_opcode_allowed=0;
        endcase
    endfunction
    function automatic cpu_command_shape(input [15:0] opcode,input [8:0] length,input [7:0] byte3,byte4,byte5);
        case(opcode)
            16'h1003:cpu_command_shape=length==3;
            16'h1004,16'h0c56:cpu_command_shape=length==4 && byte3==1;
            16'h0c1a:cpu_command_shape=length==4 && (byte3==2 || (SESSION_ONLY_PAIRING && byte3==3));
            16'h0c24:cpu_command_shape=SESSION_ONLY_PAIRING && length==6 && byte3==8'h14 && byte4==8'h04 && byte5==8'h24;
            16'h0406,16'h0413,16'h041c:cpu_command_shape=length==6;
            16'h0411,16'h041b,16'h1408:cpu_command_shape=length==5;
            16'h0409,16'h040a,16'h0434:cpu_command_shape=length==10;
            16'h040b:cpu_command_shape=length==25;
            16'h042b:cpu_command_shape=length==12;
            16'h040c,16'h040e,16'h042c,16'h042d,16'h042f,16'h0433:cpu_command_shape=length==9;
            default:cpu_command_shape=0;
        endcase
    endfunction
    function automatic cpu_handle_command(input [15:0] opcode);
        case(opcode)
            16'h0406,16'h0411,16'h0413,16'h041b,16'h041c,16'h1408:cpu_handle_command=1;
            default:cpu_handle_command=0;
        endcase
    endfunction
    assign tx_schema=tx_length!=0 && tx_length<=280 &&
        (tx_type==1 ? tx_length>=3 && tx_length=={1'b0,tx_header[2]}+9'd3 :
        tx_type==2 && tx_length>=5 && {tx_header[3],tx_header[2]}=={7'd0,tx_length}-16'd4 &&
        tx_header[1][7:6]==0 && tx_header[1][5:4]!=3 && tx_handle_slot!=-1);
    assign cpu_context=epoch!=0 && initialized_i && host_flow_ready_o &&
        cpu_tx_epoch==epoch && tx_generation==current_br_generation &&
        (tx_type==1 ? tx_length<=25 && cpu_opcode_allowed(selected_opcode) && cpu_command_shape(selected_opcode,tx_length,tx_header[3],tx_header[4],tx_header[5]) &&
            (!cpu_handle_command(selected_opcode) || (br_slot!=-1 && {tx_header[4],tx_header[3]}=={4'd0,current_br_handle})) :
            tx_handle_slot!=-1 && !known_le[tx_handle_slot] && tx_generation!=0);
    (* ram_style="block" *) reg [7:0] private_tx_ram [0:279];
    always @(posedge clk_i)begin
        if(reset_ni && tx_state==T_COPY && !tx_read_wait)private_tx_ram[tx_index]<=producer_data;
        h5_tx_data_o<=private_tx_ram[h5_tx_address_i];
    end

    assign cpu_tx_accept=tx_accept && tx_origin==O_CPU;
    assign cpu_tx_done=tx_state==T_WAIT && tx_origin==O_CPU && h5_tx_done_i;
    assign cpu_tx_response=flow_response_valid && pending_origin==O_CPU && flow_response_owner==2;

    assign cpu_rx_type=rx_type;
    assign cpu_rx_generation=rx_type==4 ? event_generation : packet_generation;
    assign cpu_rx_handle=rx_type==4 ? event_handle : packet_handle;
    workstation_hci_cpu_mailbox cpu (
        .clk_i(clk_i),.reset_ni(reset_ni),.observer_reset_ni(observer_reset_ni),
        .ready_i(initialized_i && host_flow_ready_o && enable_i),.controller_fault_i(fault_o),
        .classic_fenced_i(classic_fenced_o),.admission_i(br_admission),.epoch_i(epoch),.time_ms_i(time_ms),
        .br_limit_i(br_limit),.le_limit_i(le_limit),.br_available_i(br_available),.le_available_i(le_available),
        .observer_lost_o(observer_lost),.queue_fault_o(cpu_queue_fault),.fence_o(cpu_fence),
        .command_valid_i(command_valid_i),.command_write_i(command_write_i),.command_address_i(command_address_i),
        .command_data_i(command_data_i),.command_strobes_i(command_strobes_i),.command_ready_o(command_ready_o),
        .response_error_o(response_error_o),.response_data_o(response_data_o),
        .tx_valid_o(cpu_tx_valid),.tx_epoch_o(cpu_tx_epoch),.tx_generation_o(cpu_tx_generation),.tx_token_o(cpu_tx_token),
        .tx_type_o(cpu_tx_type),.tx_length_o(cpu_tx_length),.tx_address_i(tx_index),.tx_data_o(cpu_tx_data),
        .tx_accept_i(cpu_tx_accept),.tx_reject_i(cpu_tx_reject),.tx_reject_reason_i(cpu_tx_reject_reason),
        .tx_transport_done_i(cpu_tx_done),.tx_response_i(cpu_tx_response),.tx_uncertain_i(fault_o),
        .rx_offer_i(cpu_rx_offer),.rx_ready_o(cpu_rx_ready),.rx_type_i(cpu_rx_type),.rx_length_i(rx_length),
        .rx_generation_i(cpu_rx_generation),.rx_command_token_i(rx_type==4 && event_response ? event_command_token : 32'd0),
        .rx_handle_i(cpu_rx_handle),.rx_owner_i(rx_type==4 && event_response ? event_owner : 2'd2),
        .rx_response_i(rx_type==4 && event_response),.rx_address_o(cpu_rx_address),.rx_data_i(route_read_data),
        .rx_copy_done_o(cpu_rx_copy_done),.rx_drop_i(cpu_rx_drop),
        .disconnect_i(decoder_close),.disconnect_generation_i(close_generation)
    );

    assign boot_start=initializer_handoff_i && !boot_started && !fault_o;
    assign boot_command_accept=tx_accept && tx_origin==O_BOOT;
    assign boot_transport_done=tx_state==T_WAIT && tx_origin==O_BOOT && h5_tx_done_i;
    workstation_hci_host_bootstrap #(.STEP_TIMEOUT_CYCLES(BOOTSTRAP_TIMEOUT_CYCLES)) bootstrap (
        .clk_i(clk_i),.reset_ni(reset_ni),.start_i(boot_start),.initializer_handoff_i(initializer_handoff_i),
        .links_idle_i(known_active==0),.controller_fault_i(local_fault || flow_fault || decoder_fault || host_fault),
        .host_data_length_i(host_data_limit),.host_packet_count_i(host_packet_count),.fault_o(bootstrap_fault),
        .fault_reason_o(bootstrap_reason),.ready_o(host_flow_ready_o),.activate_host_rx_o(host_activate),
        .command_valid_o(boot_command_valid),.command_owner_o(boot_command_owner),.command_opcode_o(boot_command_opcode),
        .command_length_o(boot_command_length),.command_address_i(tx_index[3:0]),.command_data_o(boot_command_data),
        .command_accept_i(boot_command_accept),.command_transport_done_i(boot_transport_done),
        .response_valid_i(flow_response_valid && pending_origin==O_BOOT),.response_is_complete_i(flow_response_complete),
        .response_owner_i(flow_response_owner),.response_opcode_i(flow_response_opcode),.response_status_i(flow_response_status),
        .response_acl_length_i(decoder_buffer_length),.response_acl_count_i(decoder_buffer_count),
        .pool_config_valid_o(boot_pool_valid),.pool_config_ready_i(config_ready),
        .br_acl_length_o(boot_br_length),.br_acl_count_o(boot_br_count),.le_acl_length_o(boot_le_length),.le_acl_count_o(boot_le_count)
    );

    workstation_hci_flow_owner flow (
        .clk_i(clk_i),.reset_ni(reset_ni),.transport_fault_i(local_fault || decoder_fault || host_fault || bootstrap_fault),
        .config_valid_i(boot_pool_valid),.br_acl_length_i(boot_br_length),.br_acl_count_i(boot_br_count),
        .le_acl_length_i(boot_le_length),.le_acl_count_i(boot_le_count),.config_ready_o(config_ready),
        .configured_o(configured),.fault_o(flow_fault),.fault_reason_o(flow_reason),.le_shared_o(le_shared),
        .br_acl_limit_o(br_limit),.le_acl_limit_o(le_limit),.br_available_o(br_available),.le_available_o(le_available),
        .handle_open_i(decoder_open),.handle_close_i(decoder_close),.handle_is_le_i(decoder_is_le),.handle_i(decoder_handle),
        .handle_open_ready_o(decoder_open_ready),.handle_open_generation_o(decoder_open_generation),.handle_rejected_o(handle_rejected),
        .handle_active_o(known_active),.handle_is_le_o(known_le),.handle_numbers_o(known_handles),
        .handle_generations_o(known_generations),.handle_outstanding_o(known_outstanding),
        .acl_valid_i(acl_offer),.acl_send_i(tx_accept && tx_type==2),.acl_handle_i(tx_handle),
        .acl_generation_i(selected_generation),.acl_data_length_i({7'd0,tx_length}-16'd4),
        .acl_ready_o(flow_acl_ready),.acl_invalid_o(flow_acl_invalid),.acl_error_o(flow_acl_error),
        .completion_start_i(decoder_completion_start),.completion_pair_valid_i(decoder_completion_pair),
        .completion_handle_i(decoder_completion_handle),.completion_count_i(decoder_completion_count),
        .completion_commit_i(decoder_completion_commit),.completion_abort_i(1'b0),.completion_active_o(completion_active),
        .completion_pair_ready_o(completion_pair_ready),.unknown_completion_packets_o(unknown_completions),
        .command_valid_i(command_offer),.command_send_i(tx_accept && tx_type==1),
        .command_owner_i(selected_owner),.command_opcode_i(selected_opcode),
        .command_ready_o(flow_command_ready),.command_invalid_o(flow_command_invalid),
        .command_credits_o(command_credits),.command_pending_o(command_pending),
        .command_response_i(decoder_command_response),.command_timeout_i(command_timeout),
        .response_is_complete_i(decoder_complete),.response_credits_i(decoder_credits),
        .response_status_i(decoder_status),.response_opcode_i(decoder_opcode),
        .response_valid_o(flow_response_valid),.response_is_complete_o(flow_response_complete),
        .response_owner_o(flow_response_owner),.response_opcode_o(flow_response_opcode),.response_status_o(flow_response_status)
    );

    (* ram_style="block" *) reg [7:0] receive_staging [0:279];
    (* ram_style="block" *) reg [7:0] host_slots [0:2047];

    assign route_from_slot=rx_state==R_ACL_ROUTE || rx_state==R_ACL_COPY || rx_state==R_ACL_RELEASE;
    assign route_ble=rx_type==4 ? event_to_ble : packet_le;
    assign route_address=route_ble ? ble_copy_address : cpu_rx_address;
    assign stage_address=rx_state==R_SLOT_COPY ? rx_index : rx_state==R_INIT ? init_rx_address_i :
        rx_state==R_EVENT_COPY || rx_state==R_EVENT_ROUTE ? route_address : decoder_address;
    assign route_read_data=route_from_slot ? slot_read_data : stage_read_data;
    assign h5_rx_address_o=rx_index;
    always @(posedge clk_i)begin
        if(reset_ni && rx_state==R_COPY && !rx_read_wait)receive_staging[rx_index]<=h5_rx_data_i;
        stage_read_data<=receive_staging[stage_address];
        if(reset_ni && rx_state==R_SLOT_COPY && !rx_read_wait)host_slots[{physical_slot,rx_index}]<=stage_read_data;
        slot_read_data<=host_slots[{physical_slot,route_address}];
    end
    assign init_rx_valid_o=rx_state==R_INIT;
    assign init_rx_type_o=rx_type,init_rx_length_o=rx_length,init_rx_data_o=stage_read_data;
    assign event_packet_valid=!decoder_consume && (rx_state==R_EVENT || rx_state==R_EVENT_ROUTE || rx_state==R_EVENT_COPY ||
        rx_state==R_EVENT_RELEASE || rx_state==R_EVENT_RETIRE || rx_state==R_INIT);
    workstation_hci_event_decoder decoder (
        .clk_i(clk_i),.reset_ni(reset_ni),.packet_valid_i(event_packet_valid),.packet_length_i(rx_length),
        .packet_read_address_o(decoder_address),.packet_read_data_i(stage_read_data),
        .packet_release_i(rx_state==R_EVENT_RELEASE),.packet_consume_o(decoder_consume),.packet_done_o(decoder_done),
        .packet_event_o(decoder_event),.fault_o(decoder_fault),.fault_reason_o(decoder_reason),
        .handle_open_o(decoder_open),.handle_close_o(decoder_close),.handle_is_le_o(decoder_is_le),.handle_o(decoder_handle),
        .handle_open_ready_i(decoder_open_ready),.handle_open_generation_i(decoder_open_generation),
        .handle_admitted_o(decoder_admitted),.handle_generation_o(decoder_generation),
        .completion_start_o(decoder_completion_start),.completion_pair_valid_o(decoder_completion_pair),
        .completion_handle_o(decoder_completion_handle),.completion_count_o(decoder_completion_count),
        .completion_commit_o(decoder_completion_commit),.command_response_o(decoder_command_response),
        .response_is_complete_o(decoder_complete),.response_credits_o(decoder_credits),.response_status_o(decoder_status),
        .response_opcode_o(decoder_opcode),.buffer_info_valid_o(decoder_buffer_valid),.buffer_info_is_le_o(decoder_buffer_le),
        .buffer_info_length_o(decoder_buffer_length),.buffer_info_count_o(decoder_buffer_count)
    );
    assign ble_queue_offer=((rx_state==R_EVENT_ROUTE && event_to_ble) ||
        (rx_state==R_ACL_ROUTE && packet_le)) && ble_queue_ready && !fault_o;
    assign cpu_rx_offer=((rx_state==R_EVENT_ROUTE && event_to_cpu) ||
        (rx_state==R_ACL_ROUTE && !packet_le)) && cpu_rx_ready && !fault_o;
    workstation_hci_ble_queue ble_queue (
        .clk_i(clk_i),.reset_ni(reset_ni),.offer_i(ble_queue_offer),.ready_o(ble_queue_ready),
        .type_i(rx_type),.length_i(rx_length),.source_address_o(ble_copy_address),.source_data_i(route_read_data),
        .copy_done_o(ble_copy_done),.valid_o(ble_rx_valid_o),.type_o(ble_rx_type_o),.length_o(ble_rx_length_o),
        .address_i(ble_rx_address_i),.data_o(ble_rx_data_o),.consume_i(ble_rx_consume_i)
    );

    assign rx_wire_handle={4'd0,rx_header[1][3:0],rx_header[0]};
    assign host_rx_valid=rx_state==R_ACL_ADMIT;
    workstation_hci_host_rx_owner host_rx (
        .clk_i(clk_i),.reset_ni(reset_ni),.transport_fault_i(local_fault || flow_fault || decoder_fault || bootstrap_fault),
        .activate_i(host_activate),.active_o(host_active),.fault_o(host_fault),.fault_reason_o(host_reason),
        .host_data_limit_o(host_data_limit),.host_packet_count_o(host_packet_count),.controller_budget_o(host_budget),
        .known_active_i(known_active),.known_is_le_i(known_le),.known_handles_i(known_handles),.known_generations_i(known_generations),
        .rx_valid_i(host_rx_valid),.rx_take_i(host_rx_valid && host_rx_ready),
        .rx_want_lease_i(packet_le ? ble_queue_ready : cpu_rx_ready && !classic_fenced_o),
        .rx_handle_i(rx_wire_handle),.rx_data_length_i({rx_header[3],rx_header[2]}),
        .rx_ready_o(host_rx_ready),.rx_can_hold_o(host_can_hold),.lease_granted_o(host_lease_granted),
        .rx_dropped_o(host_rx_dropped),.rx_is_le_o(host_rx_le),.rx_drop_reason_o(host_drop_reason),
        .lease_exhausted_o(host_lease_exhausted),.rx_slot_o(host_rx_slot),.rx_lease_o(host_rx_lease),.rx_generation_o(host_rx_generation),
        .release_valid_i(rx_state==R_ACL_RELEASE),.release_lease_i(physical_lease),
        .release_ready_o(host_release_ready),.release_rejected_o(host_release_rejected),
        .disconnect_valid_i(decoder_close),.disconnect_handle_i(decoder_handle),.disconnect_generation_i(close_generation),
        .lease_active_o(host_leases),.lease_retired_o(host_retired),.lease_tokens_o(host_tokens),
        .outstanding_o(host_outstanding),.pending_returns_o(host_pending_returns),
        .return_valid_o(host_return_valid),.return_can_send_o(host_return_can_send),.return_owner_o(host_return_owner),
        .return_opcode_o(host_return_opcode),.return_length_o(host_return_length),.return_address_i(tx_index[3:0]),
        .return_data_o(host_return_data),.return_send_i(tx_accept && tx_origin==O_RETURN),
        .return_transport_done_i(tx_state==T_WAIT && tx_origin==O_RETURN && h5_tx_done_i),
        .return_inflight_o(host_return_inflight),.return_generation_o(host_return_generation),
        .dropped_packets_o(host_dropped),.rejected_releases_o(host_bad_releases)
    );

    initial begin
        if(CLK_HZ<1000 || CLK_HZ%1000!=0 || BOOTSTRAP_TIMEOUT_CYCLES<2 || COMMAND_TIMEOUT_CYCLES<2)
            $fatal(1,"unsupported native HCI clock/deadline");
    end
    // A coherent live identity source for the independently owned audio CDC.
    // Every tuple change has a full low-ready clock before publication; close,
    // fence, reset and controller faults withdraw ready on their actual edge.
    always @(posedge clk_i)begin
        if(!reset_ni)begin classic_ready_o<=0;published_epoch<=0;published_generation<=0;end
        else begin
            published_epoch<=epoch;published_generation<=current_br_generation;
            if(!classic_active_o || !observer_reset_ni || cpu_fence || observer_lost || cpu_queue_fault ||
                cpu_rx_drop || (decoder_close && close_slot!=-1 && !known_le[close_slot]) ||
                epoch!=published_epoch || current_br_generation!=published_generation)
                classic_ready_o<=0;
            else classic_ready_o<=1;
        end
    end
    task automatic start_copy(input [2:0] origin,input [3:0] kind,input [8:0] length);
        begin tx_origin<=origin;tx_type<=kind;tx_length<=length;tx_index<=0;tx_read_wait<=1;tx_state<=T_COPY;end
    endtask

    always @(posedge clk_i)begin
        cpu_tx_reject<=0;ble_cancelled<=0;
        if(!reset_ni)begin
            tx_state<=T_IDLE;tx_origin<=O_INIT;pending_origin<=O_INIT;event_origin<=O_INIT;
            tx_type<=0;tx_length<=0;tx_index<=0;tx_read_wait<=1;turn_cpu<=0;grant_age<=0;
            tx_generation<=0;tx_token<=0;pending_token<=0;disconnect_handle<=0;
            disconnect_issued<=0;command_age<=0;disconnect_age<=0;local_fault<=0;
            classic_fenced<=0;link_seen<=0;boot_started<=0;cpu_tx_reject_reason<=0;
            event_command_token<=0;event_owner<=0;br_accept_pending<=0;
            for(index=0;index<6;index=index+1)tx_header[index]<=0;
        end else begin
            if(link_up_i)link_seen<=1;
            if(boot_start)boot_started<=1;
            if(!command_pending || decoder_command_response)command_age<=0;
            else command_age<=command_age+1'b1;
            if(physical_fault_i || h5_tx_error_i || (link_seen && !link_up_i) || handle_rejected ||
                host_release_rejected || (disconnect_issued && disconnect_age>=COMMAND_TIMEOUT_CYCLES-1))local_fault<=1;
            if(observer_lost || cpu_queue_fault || cpu_rx_drop || cpu_fence)classic_fenced<=1;
            if(br_slot==-1)begin disconnect_issued<=0;disconnect_age<=0;end
            else if(disconnect_issued)disconnect_age<=disconnect_age+1'b1;
            if(rx_state==R_EVENT && decoder_done && decoder_event==3)br_accept_pending<=0;
            if(decoder_command_response)begin
                event_origin<=pending_origin;
                event_command_token<=pending_origin==O_CPU ? pending_token : 0;
                event_owner<=pending_origin==O_BLE ? 1 : pending_origin==O_CPU ? 2 : 0;
            end
            if(!fault_o && enable_i)case(tx_state)
                T_IDLE:begin
                    tx_index<=0;grant_age<=0;
                    if(host_return_can_send)begin
                        start_copy(O_RETURN,1,host_return_length);tx_generation<=host_return_generation;
                    end else if(boot_command_valid)start_copy(O_BOOT,1,boot_command_length);
                    else if(!initialized_i)begin
                        if(!initializer_handoff_i || host_flow_ready_o)begin tx_origin<=O_INIT;tx_state<=T_GRANT;end
                    end else if(classic_fenced_o && br_slot!=-1 && !disconnect_issued)begin
                        disconnect_handle<=current_br_handle;
                        tx_generation<=current_br_generation;start_copy(O_DISCONNECT,1,6);
                    end else if(cpu_schedulable && turn_cpu)begin
                        start_copy(O_CPU,cpu_tx_type,cpu_tx_length);tx_generation<=cpu_tx_generation;tx_token<=cpu_tx_token;
                        turn_cpu<=0;
                    end else begin tx_origin<=O_BLE;tx_state<=T_GRANT;end
                end
                T_GRANT:begin
                    if(tx_origin==O_INIT && init_tx_start_i)start_copy(O_INIT,init_tx_type_i,init_tx_length_i);
                    else if(tx_origin==O_BLE && ble_tx_start_i)begin
                        start_copy(O_BLE,ble_tx_type_i,ble_tx_length_i);turn_cpu<=1;
                    end else if(tx_origin==O_BLE && grant_age==3)begin
                        if(cpu_schedulable)begin
                            start_copy(O_CPU,cpu_tx_type,cpu_tx_length);tx_generation<=cpu_tx_generation;tx_token<=cpu_tx_token;
                            turn_cpu<=0;
                        end else tx_state<=T_IDLE;
                    end else grant_age<=grant_age+1'b1;
                    if(tx_origin==O_INIT && (initialized_i || (initializer_handoff_i && !host_flow_ready_o)))tx_state<=T_IDLE;
                end
                T_COPY:if(tx_read_wait)tx_read_wait<=0;else begin
                    tx_read_wait<=1;
                    if(tx_index<6)tx_header[tx_index[2:0]]<=producer_data;
                    if(tx_index+1'b1==tx_length)tx_state<=T_CHECK;
                    else if(tx_index==279)local_fault<=1;
                    else tx_index<=tx_index+1'b1;
                end
                T_CHECK:begin
                    if(!tx_schema || (tx_origin==O_CPU && !cpu_context))begin
                        if(tx_origin==O_CPU)begin cpu_tx_reject<=1;cpu_tx_reject_reason<=8'd4;tx_state<=T_IDLE;end
                        else if(tx_origin==O_BLE && tx_type==2 && tx_handle_slot==-1)begin ble_cancelled<=1;tx_state<=T_IDLE;end
                        else local_fault<=1;
                    end else tx_state<=T_OFFER;
                end
                T_OFFER:begin
                    if(!return_still_valid || (tx_origin==O_DISCONNECT && tx_generation!=current_br_generation))tx_state<=T_IDLE;
                    else if(!cpu_still_valid)begin cpu_tx_reject<=1;cpu_tx_reject_reason<=8'd2;tx_state<=T_IDLE;end
                    else if(tx_origin==O_CPU && command_offer && selected_opcode==16'h0409 && !br_admission)begin
                        cpu_tx_reject<=1;cpu_tx_reject_reason<=8'd5;tx_state<=T_IDLE;
                    end
                    else if((command_offer && flow_command_invalid) || (acl_offer && flow_acl_invalid))begin
                        if(tx_origin==O_CPU)begin cpu_tx_reject<=1;cpu_tx_reject_reason<=8'd3;tx_state<=T_IDLE;end
                        else if(tx_origin==O_BLE && tx_handle_slot==-1)begin ble_cancelled<=1;tx_state<=T_IDLE;end
                        else local_fault<=1;
                    end else if(tx_accept)begin
                        tx_state<=T_WAIT;
                        if(tx_type==1 && tx_origin!=O_RETURN)begin pending_origin<=tx_origin;pending_token<=tx_token;end
                        if(tx_origin==O_CPU && tx_type==1 && selected_opcode==16'h0409)br_accept_pending<=1;
                        if(tx_origin==O_DISCONNECT)begin disconnect_issued<=1;disconnect_age<=0;end
                    end
                end
                T_WAIT:if(h5_tx_done_i)tx_state<=T_IDLE;
                default:local_fault<=1;
            endcase
        end
    end

    // Every full physical packet is first copied from the actual H5 registered
    // RAM, then validated/routed without waiting on CPU service or CPU MMIO.
    always @(posedge clk_i)begin
        h5_rx_consume_o<=0;cpu_rx_drop<=0;
        if(!reset_ni)begin
            rx_state<=R_IDLE;rx_type<=0;rx_length<=0;rx_index<=0;rx_read_wait<=1;
            physical_slot<=0;physical_lease<=0;packet_generation<=0;packet_handle<=0;packet_le<=0;
            event_generation<=0;event_handle<=0;event_response<=0;rx_fault<=0;event_to_ble<=0;event_to_cpu<=0;
            // command-origin fields are set in the TX owner on dispatch.
            for(integer at=0;at<4;at=at+1)rx_header[at]<=0;
        end else if(!fault_o && enable_i)begin
            if(decoder_open)begin
                event_handle<=decoder_handle;
                event_generation<=decoder_open_ready ? decoder_open_generation : 0;
            end
            if(decoder_close)begin event_handle<=decoder_handle;event_generation<=close_generation;end
            case(rx_state)
                R_IDLE:if(h5_rx_valid_i)begin
                    if((h5_rx_type_i!=2 && h5_rx_type_i!=4) || h5_rx_length_i==0 ||
                        h5_rx_length_i>280 || (h5_rx_type_i==4 && h5_rx_length_i>257))begin
                        rx_fault<=1;
                    end else begin
                        rx_type<=h5_rx_type_i;rx_length<=h5_rx_length_i;rx_index<=0;rx_read_wait<=1;
                        event_generation<=current_br_generation;event_handle<=current_br_handle;
                        event_response<=0;event_to_ble<=0;event_to_cpu<=0;rx_state<=R_COPY;
                    end
                end
                R_COPY:if(rx_read_wait)rx_read_wait<=0;else begin
                    rx_read_wait<=1;
                    if(rx_index<4)rx_header[rx_index[1:0]]<=h5_rx_data_i;
                    if(rx_index+1'b1==rx_length)begin h5_rx_consume_o<=1;rx_state<=R_KIND;end
                    else rx_index<=rx_index+1'b1;
                end
                R_KIND:begin
                    if(rx_type==4)rx_state<=R_EVENT;
                    else if(rx_length<5 || {rx_header[3],rx_header[2]}!={7'd0,rx_length}-16'd4 ||
                        rx_header[1][7:6]!=0 || rx_header[1][5:4]==3)rx_fault<=1;
                    else begin
                        packet_handle<=rx_wire_handle[11:0];packet_le<=0;
                        for(integer at=0;at<2;at=at+1)
                            if(known_active[at] && !(|(known_handles[12*at+:12]^rx_wire_handle[11:0])))packet_le<=known_le[at];
                        rx_state<=R_ACL_ADMIT;
                    end
                end
                R_EVENT:if(decoder_done)begin
                    event_response<=(decoder_event==8'h0e || decoder_event==8'h0f) && decoder_opcode!=0;
                    event_to_ble<=initialized_i && (decoder_event==8'h3e || decoder_event==8'h13 ||
                        (decoder_event==5 && close_was_le) ||
                        ((decoder_event==8'h0e || decoder_event==8'h0f) && decoder_opcode!=0 && event_origin==O_BLE));
                    event_to_cpu<=initialized_i && !classic_fenced_o && decoder_event!=8'h3e && decoder_event!=8'h13 &&
                        !(decoder_event==5 && close_was_le) &&
                        ((decoder_event!=8'h0e && decoder_event!=8'h0f) || (decoder_opcode!=0 && event_origin==O_CPU));
                    rx_state<=R_EVENT_ROUTE;
                end
                R_EVENT_ROUTE:begin
                    if(event_origin==O_INIT && event_response && !initialized_i)rx_state<=R_INIT;
                    else if(event_to_ble)begin
                        if(ble_queue_ready)rx_state<=R_EVENT_COPY;else rx_fault<=1;
                    end else if(event_to_cpu)begin
                        if(cpu_rx_ready)rx_state<=R_EVENT_COPY;
                        else begin cpu_rx_drop<=1;rx_state<=R_EVENT_RELEASE;end
                    end else rx_state<=R_EVENT_RELEASE;
                end
                R_EVENT_COPY:if(route_ble ? ble_copy_done : cpu_rx_copy_done)rx_state<=R_EVENT_RELEASE;
                R_INIT:if(init_rx_consume_i)rx_state<=R_EVENT_RELEASE;
                R_EVENT_RELEASE:rx_state<=R_EVENT_RETIRE;
                R_EVENT_RETIRE:if(decoder_consume)rx_state<=R_IDLE;
                R_ACL_ADMIT:if(host_rx_ready)rx_state<=R_ACL_RESULT;
                R_ACL_RESULT:begin
                    if(host_lease_granted)begin
                        physical_slot<=host_rx_slot[1:0];physical_lease<=host_rx_lease;packet_generation<=host_rx_generation;
                        packet_le<=host_rx_le;rx_index<=0;rx_read_wait<=1;rx_state<=R_SLOT_COPY;
                    end else if(host_rx_dropped)begin
                        if(packet_le)rx_fault<=1;
                        else if(!classic_fenced_o)cpu_rx_drop<=1;
                        rx_state<=R_IDLE;
                    end
                end
                R_SLOT_COPY:if(rx_read_wait)rx_read_wait<=0;else begin
                    rx_read_wait<=1;
                    if(rx_index+1'b1==rx_length)rx_state<=R_ACL_ROUTE;
                    else rx_index<=rx_index+1'b1;
                end
                R_ACL_ROUTE:begin
                    if(packet_le)begin if(ble_queue_ready)rx_state<=R_ACL_COPY;else rx_fault<=1;end
                    else if(cpu_rx_ready)rx_state<=R_ACL_COPY;
                    else begin if(!classic_fenced_o)cpu_rx_drop<=1;rx_state<=R_ACL_RELEASE;end
                end
                R_ACL_COPY:if(route_ble ? ble_copy_done : cpu_rx_copy_done)rx_state<=R_ACL_RELEASE;
                R_ACL_RELEASE:if(host_release_ready)rx_state<=R_IDLE;
                default:rx_fault<=1;
            endcase
        end
    end

    always @(posedge clk_i)begin
        if(!reset_ni)begin close_was_le<=0;end
        else begin
            if(decoder_close)close_was_le<=close_slot!=-1 && known_le[close_slot];
        end
    end

endmodule
