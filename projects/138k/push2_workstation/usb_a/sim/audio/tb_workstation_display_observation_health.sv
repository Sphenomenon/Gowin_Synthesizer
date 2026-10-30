`timescale 1ns/1ps
module tb_workstation_display_observation_health;
    reg physical_clk=0,compute_clk=0,clk50=0,physical_run=1,compute_run=1,rst_n=0;
    always #7 if(physical_run)physical_clk=!physical_clk;
    always #6.5 if(compute_run)compute_clk=!compute_clk;
    always #10 clk50=!clk50;
    reg frame_valid=0,physical_ready=0,display_valid=0;
    reg [31:0] sequence_number=0;
    wire [31:0] physical_source_drop,physical_drop,display_drop;
    wire observed_valid,display_received,fault;
    workstation_pcm_observation_bridge #(.FIFO_ADDRESS_BITS(2)) physical(
        .reset_ni(rst_n),.source_clk_i(physical_clk),.destination_clk_i(compute_clk),
        .frame_valid_i(frame_valid),.frame_44k1_i(1'b0),.frame_error_i(1'b0),
        .frame_epoch_i(32'd1),.frame_sequence_i(sequence_number),.frame_pcm_i(32'h12345678),
        .source_drop_count_o(physical_source_drop),.destination_drop_count_o(physical_drop),
        .destination_drop_event_o(),.destination_loss_seen_o(),.frame_valid_o(observed_valid),.frame_ready_i(physical_ready),
        .frame_44k1_o(),.frame_error_o(),.frame_epoch_o(),.frame_sequence_o(),.frame_pcm_o(),
        .left_q31_o(),.right_q31_o(),.stream_change_o(),.sequence_gap_o());
    gw138k_stream_cdc #(.WIDTH(203)) display(
        .reset_n(rst_n),.source_clk(compute_clk),.destination_clk(clk50),.source_valid(display_valid),
        .source_data(203'h123456789abcdef),.drop_count(display_drop),.destination_valid(display_received),.destination_data());
    workstation_display_observation_health health(
        .reset_ni(rst_n),.compute_clk_i(compute_clk),.clk_50m_i(clk50),
        .physical_observation_drop_i(physical_drop),.display_mailbox_drop_i(display_drop),.fault_50_o(fault));
    integer physical_cases=0,display_cases=0,resets=0;
    task clocks50(input integer n);begin repeat(n)@(negedge clk50);end endtask
    task reset_all;
        begin
            rst_n=0;frame_valid=0;display_valid=0;clocks50(4);
            if(fault || health.source_sticky!=0 || physical_drop!=0 || display_drop!=0)$fatal(1,"common reset did not clear stopped-source health");
            physical_run=1;compute_run=1;rst_n=1;clocks50(10);
            if(fault)$fatal(1,"empty released path faulted");resets=resets+1;
        end
    endtask
    initial begin
        reset_all();
        // Fill the real four-slot physical FIFO, drop exactly one final frame,
        // then stop selected MCLK before its next edge. The bridge's next_drop
        // Gray register must still carry that last loss into compute and 50MHz.
        repeat(4)begin @(negedge physical_clk);frame_valid=1;@(posedge physical_clk);#0.1;@(negedge physical_clk);frame_valid=0;sequence_number=sequence_number+1;end
        @(negedge physical_clk);frame_valid=1;@(posedge physical_clk);#0.1;
        if(physical_source_drop!=1)$fatal(1,"physical fixture did not create final drop");
        frame_valid=0;physical_run=0;clocks50(12);
        if(physical_drop!=1 || !fault)$fatal(1,"last physical drop hidden without later MCLK/frame");
        physical_cases=physical_cases+1;clocks50(20);if(!fault)$fatal(1,"fault self-rearmed");
        reset_all();
        // A real display mailbox accepts one tuple. Its next source edge drops
        // the final tuple. Stop compute on that exact edge, before the health
        // source_sticky can see the newly incremented registered counter.
        @(negedge compute_clk);display_valid=1;@(posedge compute_clk);#0.1;
        @(posedge compute_clk);#0.1;
        if(display_drop!=1 || health.source_sticky[1])$fatal(1,"display tail-drop fixture missed critical edge");
        display_valid=0;compute_run=0;clocks50(12);
        if(!fault || health.source_sticky[1])$fatal(1,"last compute-edge drop required another source clock");
        display_cases=display_cases+1;clocks50(20);if(!fault)$fatal(1,"stopped-source fault self-cleared");
        reset_all();
        // Source sticky remains high across a real counter wrap. Seed only the
        // mailbox's existing counter near wrap after an actual first drop;
        // the next source transaction performs its normal increment to zero.
        @(negedge compute_clk);display_valid=1;wait(display_drop!=0);@(negedge compute_clk);display_valid=0;
        repeat(2)@(negedge compute_clk);
        if(!health.source_sticky[1])$fatal(1,"source did not retain first drop");
        force display.drop_count=32'hffff_ffff;@(negedge compute_clk);release display.drop_count;
        // Keep the mailbox occupied, then cause its standard source increment.
        display_valid=1;wait(display_drop==0);@(negedge compute_clk);display_valid=0;clocks50(8);
        if(!fault || !health.loss_level[1])$fatal(1,"wrapping display counter rearmed trust");
        reset_all();
        clocks50(20);if(fault)$fatal(1,"common reset failed to rearm clean path");
        $display("PASS display_observation_health: physical_final_drop=%0d display_final_drop=%0d source_stops=2 resets=%0d wrap_checks=1 no_following_frames=1",physical_cases,display_cases,resets);
        $finish;
    end
    initial begin #100000;$fatal(1,"display observation health watchdog");end
endmodule
