`timescale 1ns/1ps
module tb_runtime_counter_cdc;
    reg reset_n=0,source_clk=0,destination_clk=0,source_run=1,destination_run=1;
    reg [31:0] source_count=0;
    wire [31:0] old_count,new_count;
    real source_half=3.7,destination_half=5.1,source_phase=0.2,destination_phase=1.3;
    integer checks=0,final_deliveries=0,stopped_resets=0;
    legacy_counter_cdc reference(.reset_n(reset_n),.source_clk(source_clk),.destination_clk(destination_clk),.source_count(source_count),.destination_count(old_count));
    gw138k_counter_cdc candidate(.reset_n(reset_n),.source_clk(source_clk),.destination_clk(destination_clk),.source_count(source_count),.destination_count(new_count));
    initial begin
        if($value$plusargs("SOURCE_HALF=%f",source_half))begin end
        if($value$plusargs("SOURCE_PHASE=%f",source_phase))begin end
        #source_phase;forever begin #source_half;if(source_run)source_clk=!source_clk;end
    end
    initial begin
        if($value$plusargs("DESTINATION_HALF=%f",destination_half))begin end
        if($value$plusargs("DESTINATION_PHASE=%f",destination_phase))begin end
        #destination_phase;forever begin #destination_half;if(destination_run)destination_clk=!destination_clk;end
    end
    task compare;
        begin
            if(new_count!==old_count || candidate.gray!==reference.gray || candidate.meta!==reference.meta ||
               candidate.sync_value!==reference.sync_value || candidate.source_release!==reference.source_release ||
               candidate.destination_release!==reference.destination_release)$fatal(1,"counter state/output/latency mismatch");
            checks=checks+1;
        end
    endtask
    always @(posedge source_clk or posedge destination_clk or negedge reset_n)begin #0.01;compare();end
    task drain(input [31:0] expected);
        begin repeat(8)@(negedge destination_clk);#0.01;compare();
            if(new_count!==expected)$fatal(1,"final published count lost without more source edges: %h %h",new_count,expected);
            final_deliveries=final_deliveries+1;
        end
    endtask
    integer i;
    reg [31:0] gray_fixture;
    initial begin
        #1;reset_n=1;
        repeat(8)@(negedge source_clk);
        repeat(96)begin @(negedge source_clk);source_count=source_count+1;end
        // The source registers its last Gray word, then stops permanently for
        // this case. Destination delivery requires no later source edge.
        @(posedge source_clk);#0.02;source_run=0;drain(source_count);
        source_run=1;
        @(negedge destination_clk);destination_run=0;
        repeat(73)begin @(negedge source_clk);source_count=source_count+1;end
        @(posedge source_clk);#0.02;source_run=0;destination_run=1;drain(source_count);
        // Root assertion clears both domains even while both clocks stop;
        // root release itself does not release either local three-edge fence.
        destination_run=0;reset_n=0;#0.1;compare();
        if(new_count!==0 || candidate.gray!==0 || candidate.meta!==0 || candidate.sync_value!==0)$fatal(1,"stopped-clock async reset failed");
        reset_n=1;#20;compare();
        if(candidate.source_release!==0 || candidate.destination_release!==0)$fatal(1,"root release bypassed local clock fences");
        stopped_resets=stopped_resets+1;source_count=0;source_run=1;destination_run=1;
        repeat(8)@(negedge source_clk);drain(0);
        // Near-wrap start is a test state; subsequent source updates are each
        // exactly one increment and traverse the full counter wrap.
        @(negedge source_clk);source_count=32'hfffffff0;
        repeat(32)begin @(negedge source_clk);source_count=source_count+1;end
        @(posedge source_clk);#0.02;source_run=0;drain(32'h10);
        // Four-state propagation of each Gray bit must also agree. These
        // local comb tests do not model physical metastability resolution.
        destination_run=0;
        for(i=0;i<32;i=i+1)begin
            gray_fixture=32'b1<<i;
            force candidate.sync_value=gray_fixture;force reference.sync_value=gray_fixture;#0.02;
            if(new_count!==old_count)$fatal(1,"basis decode mismatch");checks=checks+1;
            release candidate.sync_value;release reference.sync_value;
            gray_fixture=(32'b1<<i)^32'h963ac50f;
            force candidate.sync_value=gray_fixture;force reference.sync_value=gray_fixture;#0.02;
            if(new_count!==old_count)$fatal(1,"affine fixture mismatch");checks=checks+1;
            force candidate.sync_value=32'hffffffff;force reference.sync_value=32'hffffffff;#0.02;
            release candidate.sync_value;release reference.sync_value;
            gray_fixture=32'h963ac50f;gray_fixture[i]=1'bx;
            force candidate.sync_value=gray_fixture;force reference.sync_value=gray_fixture;#0.02;
            if(new_count!==old_count)$fatal(1,"unknown Gray propagation mismatch");checks=checks+1;
            release candidate.sync_value;release reference.sync_value;
            gray_fixture[i]=1'bz;
            force candidate.sync_value=gray_fixture;force reference.sync_value=gray_fixture;#0.02;
            if(new_count!==old_count)$fatal(1,"high impedance Gray propagation mismatch");checks=checks+1;
            release candidate.sync_value;release reference.sync_value;
        end
        $display("PASS runtime_counter_cdc checks=%0d final_deliveries=%0d stopped_resets=%0d wraps=1 latency_equal=1",checks,final_deliveries,stopped_resets);
        $finish;
    end
    initial begin #200000;$fatal(1,"counter watchdog");end
endmodule
