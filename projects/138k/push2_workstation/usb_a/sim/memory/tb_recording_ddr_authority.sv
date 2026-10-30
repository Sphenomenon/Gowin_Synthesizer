`timescale 1ns/1ps
module tb_recording_ddr_authority;
    parameter integer PHASE=0;
    reg control_clk=0,memory_clk=0,memory_run=1;
    always #10 control_clk=~control_clk;
    initial begin #(PHASE);forever begin #5;if(memory_run)memory_clk=~memory_clk;end end
    reg root_reset=1,ledger_reset=1,backend_ready=0;
    wire channel,started,fault,epoch_lost,boot_seen,survived;
    workstation_recording_ddr_authority #(.HEARTBEAT_TIMEOUT_CYCLES(12),.HEARTBEAT_BITS(4)) dut(
      .root_reset_ni(root_reset),.control_clk_i(control_clk),.memory_clk_i(memory_clk),
      .ledger_reset_ni(ledger_reset),.backend_ready_i(backend_ready),.channel_ready_o(channel),
      .started_o(started),.fault_o(fault),.epoch_lost_o(epoch_lost),.boot_seen_o(boot_seen),.epoch_survived_o(survived));
    integer checks=0,phases=0,iteration,age;
    task check(input bit ok,input [511:0] text);
      begin checks=checks+1;if(!ok)$fatal(1,"%0s phase=%0d iter=%0d",text,PHASE,iteration);end
    endtask
    task mtick;begin @(posedge memory_clk);#1;end endtask
    task mlow;begin @(negedge memory_clk);#1;end endtask
    task control_cycles(input integer count);begin repeat(count)@(posedge control_clk);#1;end endtask
    task common_reset;
      begin root_reset=0;ledger_reset=0;backend_ready=0;memory_run=1;
      #0.1;check(!channel && !boot_seen && !survived && !epoch_lost,"common root reset clears authority asynchronously");
      control_cycles(3);root_reset=1;repeat(8)mtick();
      check(!boot_seen && !survived && !epoch_lost && !fault && !channel,"no client ledger release waits without creating an epoch");end
    endtask
    task first_ledger_edge;
      begin mlow();ledger_reset=1;mtick();
      check(boot_seen && survived && !epoch_lost,"first globally usable memory edge records and survives epoch");end
    endtask
    task await_started;
      begin backend_ready=1;age=0;while(!started && age<200)begin mtick();age=age+1;end
      check(started && channel && !fault && survived,"qualified first epoch opens once");end
    endtask
    task permanent_closed;
      begin backend_ready=1;ledger_reset=1;memory_run=1;
      repeat(40)begin mtick();check(boot_seen && !survived && epoch_lost && fault && !channel,"reset cannot rearm lost root epoch");end
      end
    endtask
    task loss_pulse;
      begin ledger_reset=0;#0.1;
      check(!survived && epoch_lost && !channel,"ledger loss closes asynchronously before either clock");
      #0.2;ledger_reset=1;#0.1;
      check(!survived && epoch_lost && !channel,"short reset release cannot restore epoch survival");end
    endtask
    initial begin
      #1;common_reset();control_cycles(20);
      // Reset pulses before the first globally usable memory edge are harmless.
      mlow();ledger_reset=1;#0.1;ledger_reset=0;#0.1;
      check(!boot_seen && !epoch_lost,"no memory edge means no global command could have been accepted");
      first_ledger_edge();backend_ready=0;control_cycles(20);
      check(boot_seen && survived && !channel && !fault,"BIST qualification may wait within the same epoch");
      backend_ready=1;#0.2;backend_ready=0;control_cycles(5);
      check(survived && !epoch_lost && !fault,"pre-grant ready changes do not replace ledger identity");
      await_started();phases=phases+1;
      // Every offset covers a subcycle ledger reset before readiness/grant.
      for(iteration=0;iteration<10;iteration=iteration+1)begin
        common_reset();first_ledger_edge();#(iteration);loss_pulse();
        permanent_closed();check(!started,"pre-grant loss never reports a startup");phases=phases+1;
      end
      // Loss immediately after the very first usable edge must also persist.
      common_reset();mlow();ledger_reset=1;@(posedge memory_clk);#0.1;loss_pulse();
      permanent_closed();phases=phases+1;
      // After a grant, retain startup state and reject recovery/new objects.
      common_reset();first_ledger_edge();await_started();mlow();loss_pulse();
      permanent_closed();check(started,"local reset never clears the root startup identity");phases=phases+1;
      // A stopped memory clock must not prevent reset assertion from isolating.
      for(iteration=0;iteration<2;iteration=iteration+1)begin
        common_reset();first_ledger_edge();await_started();
        if(iteration==0)@(negedge memory_clk);else @(posedge memory_clk);
        #1;memory_run=0;loss_pulse();control_cycles(6);
        check(!channel && epoch_lost && fault,"reset isolates while memory clock is stopped");
        permanent_closed();phases=phases+1;
      end
      // Ready-only loss after grant retains the existing guard's permanent policy.
      common_reset();first_ledger_edge();await_started();backend_ready=0;#0.1;
      check(!channel,"ready-only loss closes immediately");backend_ready=1;control_cycles(20);
      check(fault && started && !channel && survived && !epoch_lost,"guard permanently closes healthy ledger after readiness loss");phases=phases+1;
      // The common root reset also clears the epoch with the memory clock stopped.
      common_reset();first_ledger_edge();await_started();@(negedge memory_clk);#1;memory_run=0;root_reset=0;ledger_reset=0;
      #0.1;check(!channel && !boot_seen && !survived && !epoch_lost,"root assertion needs no local edge");
      control_cycles(3);root_reset=1;control_cycles(4);
      check(!channel && !boot_seen,"stopped clock cannot release root-local epoch state");memory_run=1;repeat(8)mtick();
      first_ledger_edge();await_started();phases=phases+1;
      $display("PASS recording authority: phase=%0d phases=%0d checks=%0d",PHASE,phases,checks);$finish;
    end
    initial begin #200000;$fatal(1,"recording authority deadline");end
endmodule
