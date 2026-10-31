`timescale 1ns/1ps
module tb_workstation_hci_flow_owner;
    reg clk_i=0;always #5 clk_i=~clk_i;
    reg reset_ni=0,transport_fault_i=0,config_valid_i=0;
    reg [15:0] br_acl_length_i=0,br_acl_count_i=0,le_acl_length_i=0,le_acl_count_i=0;
    wire config_ready_o,configured_o,fault_o,le_shared_o;
    wire [3:0] fault_reason_o;
    wire [15:0] br_acl_limit_o,le_acl_limit_o,br_available_o,le_available_o;
    reg handle_open_i=0,handle_close_i=0,handle_is_le_i=0;
    reg [11:0] handle_i=0;
    wire handle_open_ready_o,handle_rejected_o;
    wire [31:0] handle_open_generation_o;
    wire [1:0] handle_active_o;
    wire [1:0] handle_is_le_o;
    wire [23:0] handle_numbers_o;
    wire [63:0] handle_generations_o;
    wire [31:0] handle_outstanding_o;
    reg acl_valid_i=0,acl_send_i=0;
    reg [11:0] acl_handle_i=0;
    reg [31:0] acl_generation_i=0;
    reg [15:0] acl_data_length_i=0;
    wire acl_ready_o,acl_invalid_o;
    wire [2:0] acl_error_o;
    reg completion_start_i=0,completion_pair_valid_i=0;
    reg [11:0] completion_handle_i=0;
    reg [15:0] completion_count_i=0;
    reg completion_commit_i=0,completion_abort_i=0;
    wire completion_active_o,completion_pair_ready_o;
    wire [31:0] unknown_completion_packets_o;
    reg command_valid_i=0,command_send_i=0;
    reg [1:0] command_owner_i=0;
    reg [15:0] command_opcode_i=0;
    wire command_ready_o,command_invalid_o;
    wire [7:0] command_credits_o;
    wire command_pending_o;
    reg command_response_i=0,command_timeout_i=0;
    reg response_is_complete_i=1;
    wire response_is_complete_o;
    reg [7:0] response_credits_i=0,response_status_i=0;
    reg [15:0] response_opcode_i=0;
    wire response_valid_o;
    wire [1:0] response_owner_o;
    wire [15:0] response_opcode_o;
    wire [7:0] response_status_o;
    workstation_hci_flow_owner dut(.*);
    integer checks=0, scenarios=0;
    reg [31:0] le_gen,br_gen,old_gen;
    integer le_out,br_out,expect_br,expect_le;
    reg [31:0] random_state=32'h13579bdf;
    task check;input condition;input [639:0] text;
        begin checks=checks+1;if(condition!==1'b1)begin $display("FAIL %0s t=%0t",text,$time);$fatal(1);end end
    endtask
    task tick;begin @(posedge clk_i);#1;end endtask
    task reset_owner;
        begin
            reset_ni=0;transport_fault_i=0;config_valid_i=0;handle_open_i=0;handle_close_i=0;
            acl_valid_i=0;acl_send_i=0;completion_start_i=0;completion_pair_valid_i=0;
            completion_commit_i=0;completion_abort_i=0;command_valid_i=0;command_send_i=0;
            command_response_i=0;command_timeout_i=0;tick();tick();reset_ni=1;tick();
            check(!configured_o&&!fault_o&&!command_pending_o,"reset fences ledger");
            check(command_credits_o==1&&handle_active_o==0,"one startup command, no stale handles");
            scenarios=scenarios+1;
        end
    endtask
    task configure;input shared;
        begin
            br_acl_length_i=1021;br_acl_count_i=3;
            le_acl_length_i=shared?0:27;le_acl_count_i=shared?0:2;
            config_valid_i=1;#1;check(config_ready_o,"initial config ready");tick();config_valid_i=0;#1;
            check(configured_o&&!fault_o&&br_available_o==3,"configure controller capacity");
            check(br_acl_limit_o==276&&le_acl_limit_o==(shared?276:27),"wire limit includes four-byte HCI header");
            check(le_shared_o==shared&&le_available_o==(shared?0:2),"zero LE count selects BR shared pool");
        end
    endtask
    task open_handle;input [11:0] number;input le;output [31:0] generation;
        begin
            handle_i=number;handle_is_le_i=le;handle_open_i=1;#1;
            check(handle_open_ready_o,"open unique handle");generation=handle_open_generation_o;
            check(generation!=0,"nonzero handle generation");tick();handle_open_i=0;#1;
            check(!fault_o&&!handle_rejected_o,"handle established");
        end
    endtask
    task close_handle;input [11:0] number;
        begin handle_i=number;handle_close_i=1;tick();handle_close_i=0;#1;check(!fault_o,"close reclaims only its outstanding packets");end
    endtask
    task send_acl;input [11:0] number;input [31:0] generation;input [15:0] bytes;
        begin
            acl_handle_i=number;acl_generation_i=generation;acl_data_length_i=bytes;acl_valid_i=1;#1;
            check(acl_ready_o&&!acl_invalid_o,"ACL physical packet authorized");acl_send_i=1;tick();
            acl_send_i=0;acl_valid_i=0;#1;check(!fault_o,"ACL debit accepted once");
        end
    endtask
    task start_returns;begin completion_start_i=1;tick();completion_start_i=0;#1;check(completion_active_o&&!fault_o,"atomic completion starts");end endtask
    task return_pair;input [11:0] number;input [15:0] count;
        begin completion_handle_i=number;completion_count_i=count;completion_pair_valid_i=1;#1;
            check(completion_pair_ready_o,"completion pair ready");tick();completion_pair_valid_i=0;end
    endtask
    task commit_returns;begin completion_commit_i=1;tick();completion_commit_i=0;#1;end endtask
    task command_send;input [1:0] owner;input [15:0] opcode;
        begin command_owner_i=owner;command_opcode_i=opcode;command_valid_i=1;#1;
            check(command_ready_o&&!command_invalid_o,"single command owner grants packet");
            command_send_i=1;tick();command_send_i=0;command_valid_i=0;#1;check(!fault_o,"command grant accepted");end
    endtask
    task command_reply;input [15:0] opcode;input [7:0] credits;input [7:0] status;
        begin response_opcode_i=opcode;response_credits_i=credits;response_status_i=status;command_response_i=1;
            tick();command_response_i=0;#1;end
    endtask
    task snapshot;input integer br_free,le_free,br_pending,le_pending;
        integer observed_br,observed_le;
        begin
            observed_br=0;observed_le=0;
            for(integer at=0;at<2;at=at+1)begin
                if(handle_active_o[at])begin
                    if(handle_numbers_o[12*at+:12]==12'h042)observed_br=observed_br+handle_outstanding_o[16*at+:16];
                    else if(handle_numbers_o[12*at+:12]==12'h031)observed_le=observed_le+handle_outstanding_o[16*at+:16];
                    else check(0,"unexpected handle in random model");
                end
            end
            check(!fault_o&&br_available_o==br_free&&le_available_o==le_free,"pool credits match independent reference");
            check(observed_br==br_pending&&observed_le==le_pending,"per-handle outstanding matches reference");
        end
    endtask
    initial begin
        reset_owner();configure(1);open_handle(12'h031,1,le_gen);open_handle(12'h042,0,br_gen);
        send_acl(12'h031,le_gen,27);send_acl(12'h042,br_gen,276);send_acl(12'h042,br_gen,1);
        snapshot(0,0,2,1);acl_handle_i=12'h031;acl_generation_i=le_gen;acl_data_length_i=27;acl_valid_i=1;#1;
        check(!acl_ready_o&&!acl_invalid_o,"shared BR traffic exhausts LE physical credit");acl_valid_i=0;
        start_returns();return_pair(12'h042,1);snapshot(0,0,2,1);return_pair(12'h031,1);snapshot(0,0,2,1);
        commit_returns();snapshot(2,0,1,0);
        start_returns();return_pair(12'h042,1);completion_abort_i=1;tick();completion_abort_i=0;#1;
        snapshot(2,0,1,0);check(!completion_active_o,"aborted malformed event refunds nothing");
        start_returns();return_pair(12'h042,2);commit_returns();
        check(fault_o&&fault_reason_o==5&&br_available_o==2,"over-completion faults without partial credit");

        reset_owner();configure(0);open_handle(12'h031,1,le_gen);open_handle(12'h042,0,br_gen);
        send_acl(12'h031,le_gen,27);send_acl(12'h031,le_gen,27);send_acl(12'h042,br_gen,276);
        snapshot(2,0,1,2);start_returns();return_pair(12'h999,50000);return_pair(12'h042,1);commit_returns();
        snapshot(3,0,0,2);check(unknown_completion_packets_o==50000,"unknown completions cannot inflate either pool");
        start_returns();return_pair(12'h031,1);return_pair(12'h031,1);commit_returns();snapshot(3,2,0,0);
        send_acl(12'h031,le_gen,27);send_acl(12'h042,br_gen,276);close_handle(12'h031);snapshot(2,2,1,0);
        close_handle(12'h031);check(handle_rejected_o,"duplicate disconnect does not free buffers twice");snapshot(2,2,1,0);
        old_gen=le_gen;open_handle(12'h031,1,le_gen);check(le_gen>old_gen,"same controller handle receives new generation");
        acl_handle_i=12'h031;acl_generation_i=old_gen;acl_data_length_i=1;acl_valid_i=1;#1;
        check(acl_invalid_o&&acl_error_o==3&&!acl_ready_o,"old CPU ACL descriptor cannot use reused handle");
        acl_generation_i=le_gen;acl_data_length_i=28;#1;check(acl_invalid_o&&acl_error_o==4,"LE packet respects its own controller length");
        acl_data_length_i=0;#1;check(acl_invalid_o,"zero payload descriptor rejected");acl_valid_i=0;
        handle_i=12'h055;handle_open_i=1;#1;check(!handle_open_ready_o,"handle table is bounded");tick();handle_open_i=0;#1;
        check(handle_rejected_o&&!fault_o,"overflow handle is rejected for surrounding owner to disconnect");snapshot(2,2,1,0);
        close_handle(12'h031);handle_i=12'hf00;handle_open_i=1;#1;check(!handle_open_ready_o,"reserved handle range rejected");tick();handle_open_i=0;
        dut.last_generation=32'hfffffffe;open_handle(12'h031,1,le_gen);check(le_gen==32'hffffffff,"last nonwrapped handle generation admitted");
        close_handle(12'h031);handle_i=12'h031;handle_open_i=1;#1;check(!handle_open_ready_o,"generation exhaustion never wraps");tick();handle_open_i=0;
        check(handle_rejected_o&&!fault_o,"generation exhaustion preserves other active handle");snapshot(2,2,1,0);

        reset_owner();configure(1);open_handle(12'h031,1,le_gen);open_handle(12'h042,0,br_gen);
        send_acl(12'h031,le_gen,27);send_acl(12'h042,br_gen,276);close_handle(12'h042);
        snapshot(2,0,0,1);check(handle_active_o==1,"classic disconnect returns shared credits while preserving live LE");

        reset_owner();command_send(0,16'h1001);check(command_pending_o&&command_credits_o==0,"initial command consumes sole credit");
        command_owner_i=1;command_opcode_i=16'h200a;command_valid_i=1;#1;check(!command_ready_o,"BLE waits behind initializer command");command_valid_i=0;
        command_send(3,16'h0c35);check(command_pending_o&&command_credits_o==0,"host receive-credit command bypasses zero normal credit");
        command_owner_i=2;command_opcode_i=16'h0c35;command_valid_i=1;#1;check(command_invalid_o&&!command_ready_o,"CPU cannot impersonate host credit-return owner");command_valid_i=0;
        command_reply(0,0,0);check(!response_valid_o&&command_pending_o,"opcode zero credit update is not a false completion");
        command_reply(16'h1001,2,8'h01);check(!fault_o&&response_valid_o&&response_owner_o==0&&response_status_o==1,"failed command result reaches exact owner");
        check(!command_pending_o&&command_credits_o==2,"response refreshes controller command quota");
        command_send(1,16'h200a);command_reply(16'h200a,0,0);check(response_valid_o&&response_owner_o==1&&!command_pending_o,"command status/complete retires exact BLE owner");
        command_owner_i=2;command_opcode_i=16'h0409;#1;check(!command_ready_o,"zero command quota stops classic commands");
        command_reply(0,1,0);command_send(2,16'h0409);command_timeout_i=1;tick();command_timeout_i=0;
        check(fault_o&&fault_reason_o==8&&command_pending_o,"uncertain command timeout fences without refund or replay");
        reset_owner();command_send(0,16'h1001);command_reply(16'h1002,1,0);
        check(fault_o&&fault_reason_o==7&&!response_valid_o,"mismatched opcode cannot complete another owner");
        reset_owner();command_send(0,16'h1001);command_reply(16'h0c35,1,8'h12);
        check(fault_o&&fault_reason_o==9&&command_pending_o&&!response_valid_o,"invalid special command event does not retire ordinary command");
        reset_owner();command_send(2,16'h0409);
        command_timeout_i=1;command_response_i=1;response_opcode_i=16'h0409;response_credits_i=1;response_status_i=0;
        tick();command_timeout_i=0;command_response_i=0;
        check(fault_o&&fault_reason_o==8&&command_pending_o&&!response_valid_o&&command_credits_o==0,"simultaneous timeout dominates success without a false accepted result");
        reset_owner();command_send(0,16'h1001);config_valid_i=1;br_acl_count_i=0;
        command_response_i=1;response_opcode_i=16'h1001;tick();config_valid_i=0;command_response_i=0;
        check(fault_o&&fault_reason_o==2&&command_pending_o&&!response_valid_o,"invalid config dominates simultaneous command response");
        reset_owner();configure(1);open_handle(12'h031,1,le_gen);
        acl_handle_i=12'h031;acl_generation_i=le_gen;acl_data_length_i=27;acl_valid_i=1;transport_fault_i=1;#1;
        command_owner_i=3;command_opcode_i=16'h0c35;command_valid_i=1;#1;
        check(!acl_ready_o&&!command_ready_o,"transport fault cancels grants immediately");tick();transport_fault_i=0;acl_valid_i=0;command_valid_i=0;
        check(fault_o&&fault_reason_o==1&&br_available_o==3,"transport failure never guesses a credit refund");
        reset_owner();config_valid_i=1;br_acl_count_i=0;tick();config_valid_i=0;
        check(fault_o&&fault_reason_o==2&&!configured_o,"missing BR pool cannot silently enable classic transport");
        reset_owner();completion_commit_i=1;tick();completion_commit_i=0;
        check(fault_o&&fault_reason_o==3,"unframed completion commit rejected");
        reset_owner();configure(1);start_returns();
        for(integer n=0;n<63;n=n+1)return_pair(12'h999,65535);
        completion_pair_valid_i=1;#1;check(!completion_pair_ready_o,"64th completion pair is never advertised ready");
        tick();completion_pair_valid_i=0;check(fault_o&&fault_reason_o==3,"more than 63 pairs cannot overflow atomic batch sums");

        for(integer shared=0;shared<2;shared=shared+1)begin
            reset_owner();configure(shared);open_handle(12'h031,1,le_gen);open_handle(12'h042,0,br_gen);
            le_out=0;br_out=0;
            for(integer step=0;step<5000;step=step+1)begin
                random_state=random_state*32'd1664525+32'd1013904223;
                expect_br=3-br_out-(shared?le_out:0);expect_le=shared?0:2-le_out;
                if(random_state[2:0]<4)begin
                    if(random_state[3]&&(shared?expect_br:expect_le)>0)begin send_acl(12'h031,le_gen,27);le_out=le_out+1;end
                    else if(!random_state[3]&&expect_br>0)begin send_acl(12'h042,br_gen,276);br_out=br_out+1;end
                    else begin tick();end
                end else if(random_state[2:0]<7)begin
                    start_returns();
                    if(le_out!=0)begin return_pair(12'h031,1);le_out=le_out-1;end
                    if(br_out!=0)begin return_pair(12'h042,1);br_out=br_out-1;end
                    commit_returns();
                end else if(random_state[3])begin close_handle(12'h031);le_out=0;old_gen=le_gen;open_handle(12'h031,1,le_gen);check(le_gen>old_gen,"random LE reconnect advances generation");end
                else begin close_handle(12'h042);br_out=0;old_gen=br_gen;open_handle(12'h042,0,br_gen);check(br_gen>old_gen,"random classic reconnect advances generation");end
                snapshot(3-br_out-(shared?le_out:0),shared?0:2-le_out,br_out,le_out);
            end
        end
        reset_owner();configure(1);
        for(integer event_index=0;event_index<1100;event_index=event_index+1)begin
            start_returns();for(integer pair_index=0;pair_index<63;pair_index=pair_index+1)return_pair(12'h999,65535);
            commit_returns();check(!fault_o&&br_available_o==3,"unknown saturated diagnostics never affect credit");
        end
        check(unknown_completion_packets_o==32'hffffffff,"unknown completion counter saturates");
        $display("PASS checks=%0d scenarios=%0d random_steps=10000",checks,scenarios);$finish;
    end
    initial begin #100000000;$fatal(1,"watchdog");end
endmodule
