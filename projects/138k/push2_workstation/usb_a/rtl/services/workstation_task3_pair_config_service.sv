`timescale 1ns/1ps
// F808 paired-only command owner after gw138k_apb_cdc, all on clk_i.
// CPU must write actual nonzero identities; this service supplies no boot nonce.
// Admission is immediate. No command waits for the link, CNN, audio or DDR.
module workstation_task3_pair_config_service #(
    parameter bit ALLOW_BUSINESS=1'b0
)(
    input wire clk_i,reset_ni,owner_reset_ni,
    input wire command_valid_i,command_write_i,
    input wire [11:0] command_address_i,
    input wire [31:0] command_data_i,
    input wire [3:0] command_strobes_i,
    output wire command_ready_o,
    output reg response_error_o,
    output reg [31:0] response_data_o,
    input wire link_ready_i,link_fault_i,peer_panic_i,
    input wire [3:0] link_failure_code_i,
    input wire [31:0] tx_packets_i,rx_packets_i,crc_errors_i,sequence_errors_i,
    input wire [31:0] rejected_packets_i,overflow_count_i,congestion_cycles_i,
    input wire [31:0] last_rtt_cycles_i,max_rtt_cycles_i,probe_results_i,link_timeouts_i,
    output reg [31:0] local_boot_o,peer_boot_o,session_o,generation_o,
    output wire probe_enable_o,budget_validated_o,business_enable_o,
    output wire record_arm_o,record_cancel_o,panic_o
);
    reg probe_q,budget_q,business_q,arm_q,cancel_q,panic_q,seen_live;
    reg [3:0] written;
    reg [31:0] last_generation,last_session,revoke_count,rejected_count;
    reg [3:0] last_revoke_reason,last_rejection;
    wire owner_live=reset_ni && owner_reset_ni;
    wire link_fence=probe_q && (link_fault_i || peer_panic_i || (seen_live && !link_ready_i));
    wire config_good=&written && local_boot_o!=0 && peer_boot_o!=0 && local_boot_o!=peer_boot_o &&
        session_o!=0 && session_o!=last_session && generation_o!=0 && generation_o>last_generation;
    assign command_ready_o=1'b1;
    // No combinational link-ready feedback into probe enable. Revocation is
    // sampled on clk_i; CPU reset still closes every grant immediately.
    assign probe_enable_o=owner_live && probe_q;
    assign budget_validated_o=owner_live && probe_q && ALLOW_BUSINESS && budget_q && !link_fence;
    assign business_enable_o=budget_validated_o && business_q && link_ready_i;
    assign record_arm_o=arm_q && business_enable_o;
    assign record_cancel_o=reset_ni && cancel_q;
    // A one-cycle LOCAL request. The board binding must hold the dedicated
    // physical PANIC level separately; a pulse is not physical peer acceptance.
    assign panic_o=reset_ni && panic_q;

    reg [3:0] rejection;
    always @*begin
        response_data_o=0;rejection=0;
        if(!owner_live || link_fence)rejection=4'd4;
        else if(command_address_i[1:0]!=0)rejection=4'd2;
        else if(command_write_i && command_strobes_i!=4'hf)rejection=4'd3;
        case(command_address_i)
            12'h000:response_data_o=32'h54335001;
            12'h004:response_data_o={19'd0,last_revoke_reason,seen_live,link_fault_i,peer_panic_i,
                link_ready_i,business_enable_o,budget_validated_o,probe_enable_o,owner_live,(&written)};
            12'h008:response_data_o={31'd0,ALLOW_BUSINESS};
            12'h010:response_data_o=local_boot_o;
            12'h014:response_data_o=peer_boot_o;
            12'h018:response_data_o=session_o;
            12'h01c:response_data_o=generation_o;
            12'h020:response_data_o={31'd0,probe_enable_o};
            12'h024:response_data_o={31'd0,budget_validated_o};
            12'h028:response_data_o={31'd0,business_enable_o};
            12'h02c,12'h030,12'h034:response_data_o=0;
            12'h038:response_data_o=last_generation;
            12'h03c:response_data_o=last_session;
            12'h040:response_data_o=revoke_count;
            12'h044:response_data_o=rejected_count;
            12'h048:response_data_o={28'd0,last_revoke_reason};
            12'h04c:response_data_o={28'd0,last_rejection};
            12'h050:response_data_o=tx_packets_i;
            12'h054:response_data_o=rx_packets_i;
            12'h058:response_data_o=crc_errors_i;
            12'h05c:response_data_o=sequence_errors_i;
            12'h060:response_data_o=rejected_packets_i;
            12'h064:response_data_o=overflow_count_i;
            12'h068:response_data_o=congestion_cycles_i;
            12'h06c:response_data_o=last_rtt_cycles_i;
            12'h070:response_data_o=max_rtt_cycles_i;
            12'h074:response_data_o=probe_results_i;
            12'h078:response_data_o=link_timeouts_i;
            12'h07c:response_data_o={28'd0,link_failure_code_i};
            default:if(rejection==0)rejection=4'd1;
        endcase
        if(command_write_i && rejection==0)case(command_address_i)
            12'h010,12'h014,12'h018,12'h01c:begin
                if(probe_q)rejection=4'd4;
                else if(command_data_i==0)rejection=4'd5;
                else if(command_address_i==12'h01c && command_data_i<=last_generation)rejection=4'd7;
                else if(command_address_i==12'h018 && command_data_i==last_session)rejection=4'd6;
            end
            12'h020:begin
                if(command_data_i>1)rejection=4'd5;
                else if(command_data_i==1 && (probe_q || !config_good))rejection=4'd6;
            end
            12'h024:begin
                if(command_data_i>1)rejection=4'd5;
                else if(command_data_i==1 && !ALLOW_BUSINESS)rejection=4'd8;
                else if(command_data_i==1 && (!probe_q || !link_ready_i))rejection=4'd9;
            end
            12'h028:begin
                if(command_data_i>1)rejection=4'd5;
                else if(command_data_i==1 && !ALLOW_BUSINESS)rejection=4'd8;
                else if(command_data_i==1 && (!probe_q || !link_ready_i || !budget_q))rejection=4'd9;
            end
            12'h02c:begin
                if(command_data_i!=1)rejection=4'd5;
                else if(!business_enable_o)rejection=4'd9;
            end
            12'h030,12'h034:if(command_data_i!=1)rejection=4'd5;
            default:rejection=4'd1;
        endcase
        response_error_o=rejection!=0;
    end
    wire accepted_write=command_valid_i && command_write_i && !response_error_o;
    wire configured=probe_q || budget_q || business_q || written!=0;
    task automatic revoke(input [3:0] reason);
        begin
            probe_q<=0;budget_q<=0;business_q<=0;seen_live<=0;written<=0;
            local_boot_o<=0;peer_boot_o<=0;session_o<=0;generation_o<=0;
            arm_q<=0;cancel_q<=1;last_revoke_reason<=reason;
            if(!(&revoke_count))revoke_count<=revoke_count+1'b1;
        end
    endtask
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            local_boot_o<=0;peer_boot_o<=0;session_o<=0;generation_o<=0;
            probe_q<=0;budget_q<=0;business_q<=0;arm_q<=0;cancel_q<=0;panic_q<=0;seen_live<=0;written<=0;
            last_generation<=0;last_session<=0;revoke_count<=0;rejected_count<=0;last_revoke_reason<=0;last_rejection<=0;
        end else begin
            arm_q<=0;cancel_q<=0;panic_q<=0;
            if(command_valid_i && response_error_o)begin
                if(!(&rejected_count))rejected_count<=rejected_count+1'b1;
                last_rejection<=rejection;
            end
            if(!owner_reset_ni)begin
                if(configured)revoke(1);
            end else if(link_fence)begin
                if(peer_panic_i)revoke(5);
                else if(link_fault_i)revoke(4);
                else revoke(3);
            end else begin
                if(probe_q && link_ready_i)seen_live<=1;
                if(accepted_write)case(command_address_i)
                    12'h010:begin local_boot_o<=command_data_i;written[0]<=1;end
                    12'h014:begin peer_boot_o<=command_data_i;written[1]<=1;end
                    12'h018:begin session_o<=command_data_i;written[2]<=1;end
                    12'h01c:begin generation_o<=command_data_i;written[3]<=1;end
                    12'h020:if(command_data_i==1)begin
                        probe_q<=1;seen_live<=0;last_generation<=generation_o;last_session<=session_o;
                    end else if(configured)revoke(2);
                    12'h024:if(command_data_i==1)budget_q<=1;
                        else if(budget_q || business_q)revoke(7);
                    12'h028:if(command_data_i==1)business_q<=1;
                        else if(budget_q || business_q)revoke(8);
                    12'h02c:arm_q<=1;
                    12'h030:cancel_q<=1;
                    12'h034:begin revoke(6);panic_q<=1;end
                    default:begin end
                endcase
            end
        end
    end
endmodule
