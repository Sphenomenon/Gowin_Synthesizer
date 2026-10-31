`timescale 1ns/1ps
module tb_runtime_context_decode;
    reg compute_clk_i=0,compute_reset_n=0,context_toggle=0;
    reg [32:0] context_payload=0;
    reg service_fault=0,pcm_hard_fault=0,router_quiet=0,service_quiet=0,bridge_busy=0;
    reg config_ready=0,config_applied=0,service_rate=0;
    current_context dut(.*);
    reference_context reference(.*);
    integer state_value,control_value,checks=0;
    task compare;
        begin
            if(dut.config_accept_pending !== (dut.config_state==3) ||
               {dut.config_valid,dut.config_state,dut.context_sync,dut.context_ack,
                dut.pending_rate,dut.pending_epoch,dut.compute_rate,dut.compute_epoch,
                dut.compute_context_valid,dut.integration_fault} !==
               {reference.config_valid,reference.config_state,reference.context_sync,reference.context_ack,
                reference.pending_rate,reference.pending_epoch,reference.compute_rate,reference.compute_epoch,
                reference.compute_context_valid,reference.integration_fault})
                $fatal(1,"context decode differs state=%0d control=%h checks=%0d",state_value,control_value,checks);
            checks=checks+1;
        end
    endtask
    initial begin
        // Establish the actual asynchronous-reset base case first.
        #1;compute_clk_i=1;#1;compare();compute_clk_i=0;compute_reset_n=1;
        // Every encoded state (including invalid5..7) and all sixteen
        // independent scalar controls/state operands. Re-establish only the
        // inductive predicate relation before each free transition.
        for(state_value=0;state_value<8;state_value=state_value+1)
            for(control_value=0;control_value<65536;control_value=control_value+1)begin
                #1;
                {dut.config_state,reference.config_state}={2{3'(state_value)}};
                dut.config_accept_pending=(state_value==3);
                dut.context_sync={control_value[9],control_value[14]};
                reference.context_sync=dut.context_sync;
                dut.context_ack=control_value[10];reference.context_ack=dut.context_ack;
                dut.pending_rate=control_value[11];reference.pending_rate=dut.pending_rate;
                dut.integration_fault=control_value[12];reference.integration_fault=dut.integration_fault;
                dut.compute_context_valid=control_value[13];reference.compute_context_valid=dut.compute_context_valid;
                dut.compute_rate=control_value[15];reference.compute_rate=dut.compute_rate;
                dut.pending_epoch=32'(control_value*32'h9e3779b9);reference.pending_epoch=dut.pending_epoch;
                dut.compute_epoch=~dut.pending_epoch;reference.compute_epoch=dut.compute_epoch;
                {service_rate,config_applied,config_ready,bridge_busy,service_quiet,router_quiet}=control_value[5:0];
                service_fault=control_value[6];pcm_hard_fault=control_value[7];context_toggle=control_value[8];
                context_payload={control_value[0],32'(control_value*32'h1234567)};
                #1;compare();compute_clk_i=1;#1;compare();compute_clk_i=0;
            end
        compute_reset_n=0;#1;compare();
        $display("PASS actual context decode states=8 controls=65536 transitions=524288 comparisons=%0d",checks);
        $finish;
    end
endmodule
