`timescale 1ns/1ps
module tb_tf_control_snapshot;
  parameter integer SOURCE_HALF=5,COMPUTE_HALF=7,COMPUTE_PHASE=2;
  reg source_clk=0,compute_clk=0,source_run=1,compute_run=1,rst_n=1;
  reg [35:0] desired=0;
  reg [31:0] expected_generation=0;
  reg expected_valid=0;
  wire pending,active;
  always #(SOURCE_HALF)if(source_run)source_clk=~source_clk;
  initial begin #(COMPUTE_PHASE);forever begin #(COMPUTE_HALF);if(compute_run)compute_clk=~compute_clk;end end
  tf_control_snapshot_exact u_dut(.clk_50m_i(source_clk),.compute_clk_i(compute_clk),.rst_ni(rst_n),
      .desired_control(desired),.expected_generation_o(expected_generation),.expected_valid(expected_valid),
      .control_pending_o(pending),.active_o(active));
  integer source_checks=0,destination_checks=0,updates=0,captures=0,held_checks=0,cancel_checks=0,stop_cases=0,reset_cases=0;
  reg [35:0] before_held,before_compute,before_compute_held,expected_held;
  reg before_request,before_ack,before_capture,before_sync,expect_update;
  always @(posedge source_clk)if(rst_n)begin
    before_held=u_dut.held_control;before_request=u_dut.control_request;
    expect_update=u_dut.ack_sync[1]==before_request && before_held!=desired;
    expected_held=expect_update?desired:before_held;
    if(u_dut.ack_sync[1]!=before_request)held_checks=held_checks+1;
    #1;
    if(rst_n && (u_dut.held_control!==expected_held || u_dut.control_request!==(before_request^expect_update)))
      $fatal(1,"source overwrote unACKed payload or request toggle");
    source_checks=source_checks+1;if(expect_update)updates=updates+1;
  end
  always @(posedge compute_clk)if(rst_n)begin
    before_compute=u_dut.compute_control;before_ack=u_dut.control_ack;
    before_capture=u_dut.control_capture;before_sync=u_dut.request_sync[1];
    before_compute_held=u_dut.held_control;
    #1;
    if(rst_n)begin
      if(u_dut.compute_control!==(before_capture?before_compute_held:before_compute) ||
         u_dut.control_ack!==(before_capture?before_sync:before_ack) ||
         u_dut.control_capture!==(!before_capture && (before_sync!=before_ack)))
        $fatal(1,"capture/ACK delay or snapshot changed");
      if(active && (!expected_valid || u_dut.compute_control[35:4]!=expected_generation))
        $fatal(1,"stale generation control became active");
      destination_checks=destination_checks+1;if(before_capture)captures=captures+1;
    end
  end
  task automatic settle;
    integer guard;
    begin
      guard=0;
      while(pending || u_dut.compute_control!=desired)begin
        @(negedge compute_clk);guard=guard+1;if(guard>200)$fatal(1,"snapshot failed to converge");
      end
      repeat(3)@(negedge compute_clk);
    end
  endtask
  task automatic common_reset;
    begin
      desired=0;expected_valid=0;rst_n=0;#3;
      if(u_dut.held_control!==0 || u_dut.compute_control!==0 || u_dut.control_request!==0 ||
         u_dut.control_ack!==0 || u_dut.control_capture!==0 || u_dut.request_sync!==0 || u_dut.ack_sync!==0)
        $fatal(1,"common async reset required a running clock");
      rst_n=1;reset_cases=reset_cases+1;
    end
  endtask
  reg [31:0] random_value=32'h6281b93a;
  reg [35:0] frozen;
  integer i,level;
  initial begin
    #1;common_reset();repeat(5)@(negedge source_clk);
    // The source can coalesce desired state; every issued snapshot must hold
    // until matching ACK. Assert the exact source/destination next-Q each edge.
    for(i=0;i<600;i=i+1)begin
      @(negedge source_clk);random_value=(random_value>>1)^(random_value[0]?32'h80200003:0);
      desired={random_value,random_value[7:4]};
    end
    settle();
    for(level=0;level<2;level=level+1)begin
      // Stop destination high and low. Source may queue one snapshot but
      // cannot overwrite it or invent an ACK while the destination is stopped.
      if(level)@(posedge compute_clk);else @(negedge compute_clk);
      #2;compute_run=0;
      @(negedge source_clk);desired={32'h12340000+32'(level),4'b1111};
      repeat(3)@(negedge source_clk);frozen=u_dut.held_control;
      for(i=0;i<20;i=i+1)begin @(negedge source_clk);desired=desired+36'd17;end
      if(u_dut.held_control!==frozen || !pending)$fatal(1,"stopped compute did not hold transaction");
      compute_run=1;stop_cases=stop_cases+1;settle();
      // Source may stop after publishing. Destination may finish/ACK, but
      // source cannot publish a newer desired snapshot until it resumes.
      if(level)@(posedge source_clk);else @(negedge source_clk);
      #2;source_run=0;frozen=u_dut.held_control;desired=desired+36'd257;
      repeat(20)@(negedge compute_clk);
      if(u_dut.held_control!==frozen || u_dut.compute_control!==frozen || !pending)
        $fatal(1,"stopped source changed held or invented latest desired");
      source_run=1;stop_cases=stop_cases+1;settle();
      // Cancel occurs after the last source edge: the old active snapshot may
      // remain held. The independently received generation fence must revoke it.
      @(negedge source_clk);desired={32'h42+32'(level),4'b0110};expected_generation=32'h42+32'(level);expected_valid=1;
      settle();if(!active)$fatal(1,"active control setup");
      @(posedge source_clk);#2;source_run=0;desired={32'h90+32'(level),4'b0000};
      repeat(3)@(negedge compute_clk);expected_generation=32'h90+32'(level);
      repeat(20)begin @(negedge compute_clk);if(active)$fatal(1,"cancel fence did not revoke held active control");cancel_checks=cancel_checks+1;end
      source_run=1;settle();if(active)$fatal(1,"late old control resurrected after resume");
      // A common assertion resets both domains even when either one is stopped.
      if(level)begin @(posedge source_clk);#2;source_run=0;end
      else begin @(negedge compute_clk);#2;compute_run=0;end
      common_reset();source_run=1;compute_run=1;repeat(8)@(negedge source_clk);settle();
    end
    if(source_checks<600 || destination_checks<100 || held_checks<100 || updates<10 || captures<10 || cancel_checks!=40 || stop_cases!=4 || reset_cases!=3)
      $fatal(1,"protocol coverage incomplete");
    $display("PASS exact TF control snapshot source_checks=%0d destination_checks=%0d updates=%0d captures=%0d held=%0d cancels=%0d stops=%0d resets=%0d",source_checks,destination_checks,updates,captures,held_checks,cancel_checks,stop_cases,reset_cases);
    $finish;
  end
  initial begin #1000000;$fatal(1,"TF control protocol watchdog");end
endmodule
