`timescale 1ns/1ps
module tb_workstation_hci_host_rx_owner;
    reg clk_i=0;always #5 clk_i=~clk_i;
    reg reset_ni=0,transport_fault_i=0,activate_i=0;
    wire active_o,fault_o;
    wire [3:0] fault_reason_o;
    wire [15:0] host_data_limit_o,host_packet_count_o,controller_budget_o;
    wire [1:0] known_active_i,known_is_le_i;
    wire [23:0] known_handles_i;
    wire [63:0] known_generations_i;
    reg rx_valid_i=0,rx_take_i=0,rx_want_lease_i=0;
    reg [15:0] rx_handle_i=0,rx_data_length_i=27;
    wire rx_ready_o,rx_can_hold_o,lease_granted_o,rx_dropped_o,rx_is_le_o;
    wire lease_exhausted_o;
    wire [1:0] rx_drop_reason_o;
    wire [3:0] rx_slot_o;
    wire [31:0] rx_lease_o,rx_generation_o;
    reg release_valid_i=0;
    reg [31:0] release_lease_i=0;
    wire release_ready_o,release_rejected_o;
    reg disconnect_valid_i=0;
    reg [11:0] disconnect_handle_i=0;
    reg [31:0] disconnect_generation_i=0;
    wire [3:0] lease_active_o,lease_retired_o;
    wire [127:0] lease_tokens_o;
    wire [31:0] outstanding_o,pending_returns_o;
    wire return_valid_o,return_can_send_o;
    wire [1:0] return_owner_o;
    wire [15:0] return_opcode_o;
    wire [8:0] return_length_o;
    reg [3:0] return_address_i=0;
    wire [7:0] return_data_o;
    reg return_send_i=0,return_transport_done_i=0;
    wire return_inflight_o;
    wire [31:0] return_generation_o,dropped_packets_o,rejected_releases_o;
    workstation_hci_host_rx_owner dut(.*);

    reg configure=0,open_handle=0,close_handle=0,handle_le=0;
    reg [11:0] lifecycle_handle=0;
    wire open_ready,owner_fault,command_ready;
    wire [31:0] open_generation;
    reg ordinary_send=0;
    wire [7:0] command_credits;
    workstation_hci_flow_owner flow(
        .clk_i(clk_i),.reset_ni(reset_ni),.transport_fault_i(transport_fault_i||fault_o),
        .config_valid_i(configure),.br_acl_length_i(16'd1021),.br_acl_count_i(16'd3),
        .le_acl_length_i(16'd27),.le_acl_count_i(16'd2),
        .handle_open_i(open_handle),.handle_close_i(close_handle),.handle_is_le_i(handle_le),
        .handle_i(lifecycle_handle),.handle_open_ready_o(open_ready),.handle_open_generation_o(open_generation),
        .handle_active_o(known_active_i),.handle_is_le_o(known_is_le_i),
        .handle_numbers_o(known_handles_i),.handle_generations_o(known_generations_i),
        .fault_o(owner_fault),.acl_valid_i(1'b0),.acl_send_i(1'b0),.acl_handle_i(12'd0),
        .acl_generation_i(32'd0),.acl_data_length_i(16'd0),
        .completion_start_i(1'b0),.completion_pair_valid_i(1'b0),.completion_handle_i(12'd0),
        .completion_count_i(16'd0),.completion_commit_i(1'b0),.completion_abort_i(1'b0),
        .command_valid_i(ordinary_send||return_can_send_o),.command_send_i(ordinary_send||return_send_i),
        .command_owner_i(ordinary_send ? 2'd0 : return_owner_o),
        .command_opcode_i(ordinary_send ? 16'h1001 : return_opcode_o),
        .command_ready_o(command_ready),.command_credits_o(command_credits),
        .command_response_i(1'b0),.command_timeout_i(1'b0),.response_credits_i(8'd0),
        .response_status_i(8'd0),.response_opcode_i(16'd0)
    );
    integer checks=0,scenarios=0,received=0,returned=0;
    integer model_out[0:1],model_pending[0:1];
    reg [3:0] model_active,model_retired;
    reg [31:0] model_token[0:3],model_generation[0:3],generation[0:1],model_last_token;
    integer model_owner[0:3];
    reg [31:0] random_state=32'hc01dcafe;
    reg [63:0] held_bytes;
    reg [31:0] held_generation,stale_token;
    task check;input condition;input [767:0] text;
        begin checks=checks+1;if(condition!==1'b1)begin $display("FAIL %0s t=%0t scenario=%0d",text,$time,scenarios);$fatal(1);end end
    endtask
    task tick;begin @(posedge clk_i);#1;end endtask
    task snapshot;
        begin
            if(fault_o||owner_fault)$display("health host_fault=%0d reason=%0d flow_fault=%0d out=%h pending=%h budget=%0d",fault_o,fault_reason_o,owner_fault,outstanding_o,pending_returns_o,controller_budget_o);
            check(!fault_o&&!owner_fault,"both physical accounting owners healthy");
            check(controller_budget_o==4-model_out[0]-model_out[1],"controller budget matches independent received-minus-returned model");
            check(outstanding_o=={16'(model_out[1]),16'(model_out[0])},"per-handle host outstanding matches model");
            check(pending_returns_o=={16'(model_pending[1]),16'(model_pending[0])},"physical pending returns match consumer retirement");
            check(lease_active_o==model_active&&lease_retired_o==model_retired,"external RAM leases and quarantine match reference");
            for(integer at=0;at<4;at=at+1)if(model_active[at])
                check(lease_tokens_o[32*at+:32]==model_token[at],"leased memory token remains stable until real release");
        end
    endtask
    task open_link;input integer who;
        begin
            @(negedge clk_i);
            lifecycle_handle=who ? 12'h031 : 12'h042;handle_le=who!=0;open_handle=1;#1;
            check(open_ready,"sole flow owner admits fresh handle");generation[who]=open_generation;
            tick();open_handle=0;#1;
        end
    endtask
    task reset_all;
        begin
            reset_ni=0;transport_fault_i=0;activate_i=0;rx_valid_i=0;rx_take_i=0;
            release_valid_i=0;disconnect_valid_i=0;return_send_i=0;return_transport_done_i=0;
            configure=0;open_handle=0;close_handle=0;ordinary_send=0;
            tick();tick();reset_ni=1;tick();configure=1;tick();configure=0;
            activate_i=1;tick();activate_i=0;
            model_active=0;model_retired=0;model_last_token=0;
            for(integer at=0;at<2;at=at+1)begin model_out[at]=0;model_pending[at]=0;end
            for(integer at=0;at<4;at=at+1)begin model_token[at]=0;model_generation[at]=0;model_owner[at]=0;end
            open_link(0);open_link(1);scenarios=scenarios+1;
            check(active_o&&host_data_limit_o==276&&host_packet_count_o==4,"activate only after external confirmed host-flow bootstrap");
            snapshot();
        end
    endtask
    task receive_packet;input integer who;input want;
        integer free_count,free_index;reg hold;
        begin
            @(negedge clk_i);
            free_count=0;free_index=-1;
            for(integer at=0;at<4;at=at+1)if(!model_active[at])begin free_count=free_count+1;if(free_index==-1)free_index=at;end
            hold=want&&free_index!=-1&&model_last_token!=32'hffffffff&&(who!=0||free_count>1);
            rx_valid_i=1;rx_handle_i=who ? 16'h0031 : 16'h0042;rx_data_length_i=who ? 27 : 276;rx_want_lease_i=want;
            #1;check(rx_ready_o,"complete physical packet can be accounted without waiting for CPU");
            check(rx_can_hold_o==(free_index!=-1&&model_last_token!=32'hffffffff&&(who!=0||free_count>1)),"BLE reserve and token exhaustion affect storage only");
            rx_take_i=1;tick();rx_take_i=0;rx_valid_i=0;received=received+1;
            model_out[who]=model_out[who]+1;
            check(rx_is_le_o==(who!=0)&&rx_generation_o==generation[who],"RX descriptor binds exact sole-owner identity");
            if(hold)begin
                model_active[free_index]=1;model_retired[free_index]=0;model_last_token=model_last_token+1;
                model_token[free_index]=model_last_token;model_generation[free_index]=generation[who];model_owner[free_index]=who;
                if(!(lease_granted_o&&!rx_dropped_o&&rx_slot_o==free_index&&rx_lease_o==model_last_token))
                    $display("allocation actual grant=%0d drop=%0d slot=%0d token=%h expected slot=%0d token=%h",lease_granted_o,rx_dropped_o,rx_slot_o,rx_lease_o,free_index,model_last_token);
                check(lease_granted_o&&!rx_dropped_o&&rx_slot_o==free_index&&rx_lease_o==model_last_token,"one physical slot allocated exactly once");
            end else begin
                model_pending[who]=model_pending[who]+1;
                check(rx_dropped_o&&!lease_granted_o,"slow/full route drops complete packet and schedules physical return");
                check(rx_drop_reason_o==(!want ? 1 : model_last_token==32'hffffffff ? 3 : 2),"policy/full/exhausted drop reason remains explicit");
            end
            snapshot();
        end
    endtask
    task release_token;input [31:0] token;
        integer at_slot,who;
        begin
            @(negedge clk_i);
            at_slot=-1;for(integer at=0;at<4;at=at+1)if(model_active[at]&&model_token[at]==token)at_slot=at;
            release_lease_i=token;release_valid_i=1;#1;check(release_ready_o,"consumer retirement has bounded hardware acceptance");
            tick();release_valid_i=0;
            if(at_slot==-1)check(release_rejected_o,"stale or duplicate release cannot mint credits");
            else begin
                check(!release_rejected_o,"live lease retired once");who=model_owner[at_slot];
                if(!model_retired[at_slot])model_pending[who]=model_pending[who]+1;
                model_active[at_slot]=0;model_retired[at_slot]=0;
            end
            snapshot();
        end
    endtask
    task command_bytes;output [63:0] bytes;
        begin for(integer at=0;at<8;at=at+1)begin return_address_i=at;#1;bytes[8*at+:8]=return_data_o;end end
    endtask
    task wait_offer;
        integer waited;
        begin #1;waited=0;while(!return_valid_o&&waited<10)begin tick();waited=waited+1;end
            #1;
            check(waited<10&&return_can_send_o&&command_ready,"host credit return bypasses ordinary command quota");end
    endtask
    task send_return;input finish;
        reg [63:0] bytes;integer who,count;
        begin
            wait_offer();command_bytes(bytes);
            check(bytes[31:0]==32'h01050c35&&return_length_o==8&&return_owner_o==3,"actual HCI0c35 header and one-handle parameters");
            who=bytes[47:32]==16'h0031 ? 1 : 0;count=bytes[63:48];
            check(bytes[47:32]==(who ? 16'h0031 : 16'h0042)&&return_generation_o==generation[who],"return snapshot preserves handle generation");
            check(count>0&&count<=model_pending[who],"returned physical count never exceeds retired packet count");
            @(negedge clk_i);return_send_i=1;tick();return_send_i=0;
            model_pending[who]=model_pending[who]-count;model_out[who]=model_out[who]-count;returned=returned+count;
            check(return_inflight_o&&!return_valid_o,"irreversible transport acceptance is not replayable");snapshot();
            command_bytes(held_bytes);held_generation=return_generation_o;check(held_bytes==bytes,"payload remains owned by transport after accept");
            if(finish)begin @(negedge clk_i);return_transport_done_i=1;tick();return_transport_done_i=0;check(!return_inflight_o,"transport completion releases builder bytes");end
        end
    endtask
    task disconnect_link;input integer who;
        reg [31:0] old;
        begin
            @(negedge clk_i);
            old=generation[who];disconnect_valid_i=1;disconnect_handle_i=who ? 12'h031 : 12'h042;
            disconnect_generation_i=old;close_handle=1;lifecycle_handle=disconnect_handle_i;
            #1;check(!return_can_send_o&&!rx_ready_o&&!release_ready_o,"disconnect atomically preempts unaccepted mutations");
            tick();disconnect_valid_i=0;close_handle=0;
            model_out[who]=0;model_pending[who]=0;
            for(integer at=0;at<4;at=at+1)if(model_active[at]&&model_owner[at]==who&&model_generation[at]==old)model_retired[at]=1;
            snapshot();open_link(who);snapshot();
        end
    endtask
    initial begin
        reset_all();ordinary_send=1;tick();ordinary_send=0;check(command_credits==0,"ordinary initializer command deliberately holds sole credit");
        receive_packet(0,1);receive_packet(0,1);receive_packet(0,1);
        receive_packet(0,1);check(model_active==7&&model_pending[0]==1,"Classic cannot consume reserved BLE RAM slot");
        send_return(0);receive_packet(1,1);check(model_active==15,"BLE uses reserved slot despite stalled Classic consumers");
        release_token(model_token[3]);tick();tick();
        begin reg [63:0] now;command_bytes(now);check(now==held_bytes&&return_generation_o==held_generation,"later RX does not mutate in-flight return bytes");end
        @(negedge clk_i);return_transport_done_i=1;tick();return_transport_done_i=0;
        send_return(1);receive_packet(1,1);
        stale_token=model_token[0];release_token(stale_token);release_token(stale_token);send_return(1);
        disconnect_link(0);check(model_retired==6,"disconnected Classic readers remain quarantined until release");
        receive_packet(0,1);check(rx_dropped_o,"reused HCI handle cannot overwrite retired DMA RAM or BLE reserve");send_return(1);
        release_token(model_token[1]);release_token(model_token[2]);snapshot();
        receive_packet(0,1);check(rx_lease_o>stale_token,"reused physical slot receives nonrepeating lease token");

        reset_all();receive_packet(0,0);wait_offer();disconnect_link(0);
        check(!return_valid_o&&controller_budget_o==4,"disconnect cancels old unaccepted0c35 snapshot and implicitly frees controller credits");
        receive_packet(0,0);send_return(0);disconnect_link(0);
        begin reg [63:0] now;command_bytes(now);check(now==held_bytes&&return_inflight_o,"already accepted old-generation bytes remain immutable through disconnect");end
        @(negedge clk_i);return_transport_done_i=1;tick();return_transport_done_i=0;snapshot();

        reset_all();receive_packet(0,0);wait_offer();command_bytes(held_bytes);
        receive_packet(0,0);
        begin reg [63:0] now;command_bytes(now);check(now==held_bytes&&model_pending[0]==2,"new completions cannot change an unaccepted return snapshot");end
        send_return(1);check(model_pending[0]==1&&model_out[0]==1,"snapshot accepts only its original physical count");send_return(1);

        reset_all();receive_packet(0,1);dut.last_lease=32'hfffffffe;model_last_token=32'hfffffffe;
        receive_packet(1,1);check(rx_lease_o==32'hffffffff,"last nonwrapped lease admitted");
        receive_packet(0,1);check(rx_dropped_o&&!fault_o&&lease_exhausted_o&&rx_drop_reason_o==3,"lease exhaustion drops and retires with explicit permanent-recovery reason");
        send_return(1);

        reset_all();
        for(integer step=0;step<10000;step=step+1)begin
            random_state=random_state*32'd1664525+32'd1013904223;
            if(random_state[3:0]<8&&model_out[0]+model_out[1]<4)
                receive_packet(random_state[4]?1:0,random_state[5]);
            else if(random_state[3:0]<11)begin
                if(model_active[random_state[5:4]])release_token(model_token[random_state[5:4]]);
                else release_token(0);
            end else if(random_state[3:0]<14&&(model_pending[0]+model_pending[1])!=0)send_return(1);
            else if(random_state[3:0]==14)disconnect_link(random_state[4]?1:0);
            else tick();
            snapshot();
        end

        reset_all();rx_valid_i=1;rx_handle_i=16'h1042;rx_data_length_i=27;tick();rx_valid_i=0;
        check(fault_o&&fault_reason_o==3&&controller_budget_o==4&&lease_active_o==0,"reserved wire handle bits fault before allocation");
        reset_all();rx_valid_i=1;rx_handle_i=16'h0042;rx_data_length_i=277;tick();rx_valid_i=0;
        check(fault_o&&fault_reason_o==3&&controller_budget_o==4,"oversize physical packet cannot consume guessed host buffer");
        reset_all();for(integer n=0;n<4;n=n+1)receive_packet(1,1);
        rx_valid_i=1;rx_handle_i=16'h0031;rx_data_length_i=27;tick();rx_valid_i=0;
        check(fault_o&&fault_reason_o==3&&controller_budget_o==0,"controller overrun at zero advertised budget is fail closed");
        reset_all();receive_packet(0,1);close_handle=1;lifecycle_handle=12'h042;tick();close_handle=0;tick();
        check(fault_o&&fault_reason_o==4&&lease_active_o==1,"lost disconnect fencing cannot silently rebind outstanding generation");
        reset_all();receive_packet(0,0);send_return(0);transport_fault_i=1;tick();transport_fault_i=0;
        check(fault_o&&fault_reason_o==1&&return_inflight_o,"uncertain transport stops without replay or invented packet loss");
        reset_all();return_transport_done_i=1;tick();return_transport_done_i=0;
        check(fault_o&&fault_reason_o==5,"unowned transport completion rejected");
        reset_all();activate_i=1;tick();activate_i=0;
        check(fault_o&&fault_reason_o==2,"host flow cannot silently reactivate and reset credits");
        $display("PASS checks=%0d scenarios=%0d random_steps=10000 received=%0d returned=%0d",checks,scenarios,received,returned);$finish;
    end
    initial begin #100000000;$fatal(1,"watchdog");end
endmodule
