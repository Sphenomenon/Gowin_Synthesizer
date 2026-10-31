// Explicit initializer handoff, before any link. Unselected source component.
// The sole HCI owner supplies command quota/routed results and actual H5 slots.
module workstation_hci_host_bootstrap #(
    parameter integer STEP_TIMEOUT_CYCLES=50000000
) (
    input wire clk_i,reset_ni,start_i,initializer_handoff_i,links_idle_i,
    input wire controller_fault_i,
    input wire [15:0] host_data_length_i,host_packet_count_i,
    output reg fault_o,
    output reg [3:0] fault_reason_o,
    output wire ready_o,
    output reg activate_host_rx_o,
    output wire command_valid_o,
    output wire [1:0] command_owner_o,
    output wire [15:0] command_opcode_o,
    output wire [8:0] command_length_o,
    input wire [3:0] command_address_i,
    output reg [7:0] command_data_o,
    input wire command_accept_i,command_transport_done_i,
    input wire response_valid_i,
    input wire response_is_complete_i,
    input wire [1:0] response_owner_i,
    input wire [15:0] response_opcode_i,
    input wire [7:0] response_status_i,
    input wire [15:0] response_acl_length_i,response_acl_count_i,
    output wire pool_config_valid_o,
    input wire pool_config_ready_i,
    output reg [15:0] br_acl_length_o,br_acl_count_o,le_acl_length_o,le_acl_count_o
);
    localparam [2:0] IDLE=0,OFFER=1,WAIT=2,POOL=3,DONE=4,FAILED=5;
    localparam [3:0] F_CONTROLLER=1,F_START=2,F_CONFIG=3,F_RESPONSE=4,
        F_STATUS=5,F_TRANSPORT=6,F_TIMEOUT=7,F_BUFFERS=8,F_LINK=9;
    reg [2:0] state;
    reg [1:0] step;
    // Gowin V1.9.12 folds both constant-bound capabilities into a false drift
    // condition unless these captures survive optimization. Keep the dynamic
    // capability/drift contract, including the start-edge capture and reset.
    (* syn_preserve=1 *) reg [15:0] host_length,host_count;
    reg response_seen,transport_owned;
    reg [31:0] elapsed;
    wire started=state!=IDLE;
    wire busy=state==OFFER||state==WAIT||state==POOL;
    wire deadline=busy&&elapsed>=32'(STEP_TIMEOUT_CYCLES-1);
    wire config_drift=started&&(host_length!=host_data_length_i||host_count!=host_packet_count_i);
    wire owner_response=response_valid_i&&response_owner_i==0;
    wire expected_response=state==WAIT&&!response_seen&&response_is_complete_i&&response_opcode_i==command_opcode_o;
    wire response_good=owner_response&&expected_response&&response_status_i==0;
    wire buffers_good=step==0 ? response_acl_length_i!=0&&response_acl_count_i!=0 :
        step==1 ? response_acl_count_i[15:8]==0&&(response_acl_count_i==0||response_acl_length_i!=0) : 1'b1;
    assign command_owner_o=0;
    assign command_opcode_o=step==0 ? 16'h1005 : step==1 ? 16'h2002 :
        step==2 ? 16'h0c33 : 16'h0c31;
    assign command_length_o=step<2 ? 3 : step==2 ? 10 : 4;
    assign command_valid_o=state==OFFER&&!fault_o&&!controller_fault_i&&!config_drift&&links_idle_i&&!deadline;
    assign pool_config_valid_o=state==POOL&&!fault_o&&!controller_fault_i&&!config_drift&&links_idle_i&&!deadline;
    assign ready_o=state==DONE&&!fault_o&&!controller_fault_i&&!config_drift;
    always @* begin
        command_data_o=0;
        case(command_address_i)
            0:command_data_o=command_opcode_o[7:0];
            1:command_data_o=command_opcode_o[15:8];
            2:command_data_o=step<2 ? 0 : step==2 ? 7 : 1;
            3:command_data_o=step==2 ? host_length[7:0] : step==3 ? 8'd1 : 8'd0;
            4:command_data_o=step==2 ? host_length[15:8] : 0;
            5:command_data_o=0; // No synchronous HCI data supported.
            6:command_data_o=step==2 ? host_count[7:0] : 0;
            7:command_data_o=step==2 ? host_count[15:8] : 0;
            8,9:command_data_o=0;
            default:begin end
        endcase
    end
    task automatic fail;input [3:0] reason;
        begin fault_o<=1;fault_reason_o<=reason;activate_host_rx_o<=0;state<=FAILED;end
    endtask
    initial begin
        if(STEP_TIMEOUT_CYCLES<2||STEP_TIMEOUT_CYCLES>1000000000)
            $fatal(1,"unsupported HCI bootstrap timeout");
    end
    always @(posedge clk_i)begin
        activate_host_rx_o<=0;
        if(!reset_ni)begin
            state<=IDLE;step<=0;host_length<=0;host_count<=0;elapsed<=0;
            fault_o<=0;fault_reason_o<=0;response_seen<=0;transport_owned<=0;
            br_acl_length_o<=0;br_acl_count_o<=0;le_acl_length_o<=0;le_acl_count_o<=0;
        end else if(!fault_o)begin
            if(controller_fault_i)fail(F_CONTROLLER);
            else if(config_drift)fail(F_CONFIG);
            else if(busy&&!links_idle_i)fail(F_LINK);
            else if(deadline)fail(F_TIMEOUT);
            else if(start_i&&(state!=IDLE||!initializer_handoff_i||!links_idle_i))fail(F_START);
            else if(start_i&&(host_data_length_i<4||host_data_length_i>276||
                host_packet_count_i<2||host_packet_count_i>16))fail(F_CONFIG);
            else if(command_accept_i&&!command_valid_o)fail(F_TRANSPORT);
            else if(command_transport_done_i&&(state!=WAIT||!transport_owned))fail(F_TRANSPORT);
            else if(owner_response&&started&&!expected_response)fail(F_RESPONSE);
            else if(owner_response&&started&&response_status_i!=0)fail(F_STATUS);
            else if(response_good&&!buffers_good)fail(F_BUFFERS);
            else begin
                if(busy)elapsed<=elapsed+1'b1;
                case(state)
                    IDLE: if(start_i)begin
                        host_length<=host_data_length_i;host_count<=host_packet_count_i;
                        state<=OFFER;step<=0;elapsed<=0;
                    end
                    OFFER: if(command_accept_i)begin
                        state<=WAIT;response_seen<=0;transport_owned<=1;elapsed<=0;
                    end
                    WAIT: begin
                        if(command_transport_done_i)transport_owned<=0;
                        if(response_good)begin
                            response_seen<=1;
                            if(step==0)begin br_acl_length_o<=response_acl_length_i;br_acl_count_o<=response_acl_count_i;end
                            if(step==1)begin le_acl_length_o<=response_acl_length_i;le_acl_count_o<=response_acl_count_i;end
                        end
                        if((response_seen||response_good)&&(!transport_owned||command_transport_done_i))begin
                            elapsed<=0;
                            if(step==1)state<=POOL;
                            else if(step==3)begin state<=DONE;activate_host_rx_o<=1;end
                            else begin step<=step+1'b1;state<=OFFER;end
                        end
                    end
                    POOL: if(pool_config_ready_i)begin step<=2;state<=OFFER;elapsed<=0;end
                    DONE:begin end
                    default:fail(F_START);
                endcase
            end
        end
    end
endmodule
