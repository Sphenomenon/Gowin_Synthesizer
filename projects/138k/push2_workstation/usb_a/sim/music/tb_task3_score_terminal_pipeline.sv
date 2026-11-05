`timescale 1ns/1ps
module tb_task3_score_terminal_pipeline;
    reg clk=0;always #10 clk=~clk;
    reg reset_n=0,link=1,cancel=0,panic=0,arm=0,append=0,last=1;
    reg score_valid=0,terminal_valid=0,push_ready=0;
    reg [127:0] identity=128'h80000001400000022000000310000004;
    reg [127:0] score_identity,terminal_identity;
    reg [31:0] index=0,count=0;
    reg [6:0] note=0;
    reg [3:0] error=0;
    wire [3:0] arm_ready,score_ready,terminal_ready,push_valid,done,failed,completion_valid;
    wire [6:0] output_note[0:3];wire [31:0] note_count[0:3];
    wire [163:0] completion[0:3];wire [3:0] failure_code[0:3];
    integer seen[0:3],completions[0:3];reg [163:0] completed[0:3];
    integer checks=0,expected_notes=0,base_note=0;
    reg monitor=1;
    genvar g;
    generate for(g=0;g<4;g=g+1)begin:mode
        workstation_task3_score_commit_m #(.SYNC_READ_STORAGE(g%2),.PIPELINED_TERMINAL(g>=2)) dut(
            .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.cancel_i(cancel),.panic_i(panic),
            .arm_valid_i(arm),.arm_ready_o(arm_ready[g]),.arm_identity_i(identity),.arm_append_i(append),.chunk_file_last_i(last),
            .score_valid_i(score_valid),.score_ready_o(score_ready[g]),.score_i({score_identity,index,note}),
            .terminal_valid_i(terminal_valid),.terminal_ready_o(terminal_ready[g]),.terminal_i({terminal_identity,count,error}),
            .completion_valid_o(completion_valid[g]),.completion_o(completion[g]),
            .push_score_valid_o(push_valid[g]),.push_score_ready_i(push_ready),.push_score_note_o(output_note[g]),
            .analysis_done_o(done[g]),.failed_o(failed[g]),.failure_code_o(failure_code[g]),.note_count_o(note_count[g]));
        always @(posedge clk)if(reset_n && monitor)begin
            if(push_valid[g] && push_ready)begin
                if(output_note[g]!==7'(base_note+seen[g]))$fatal(1,"note order/data mode=%0d n=%0d",g,seen[g]);
                seen[g]=seen[g]+1;
                if(seen[g]>expected_notes)$fatal(1,"unexpected publication mode=%0d",g);
            end
            if(completion_valid[g])begin completions[g]=completions[g]+1;completed[g]=completion[g];end
        end
    end endgenerate
    task tick;begin @(posedge clk);#1;checks=checks+1;@(negedge clk);end endtask
    task clear_observers;
        integer k;begin for(k=0;k<4;k=k+1)begin seen[k]=0;completions[k]=0;completed[k]=0;end end
    endtask
    task start(input bit add,input bit final_clip);
        begin
            if(arm_ready!=4'b1111)$fatal(1,"ARM not bounded/ready");
            identity=identity+128'd1;score_identity=identity;terminal_identity=identity;
            append=add;last=final_clip;arm=1;tick();arm=0;index=0;error=0;
        end
    endtask
    task put(input integer number);
        begin
            if(score_ready!=15)$fatal(1,"unexpected score backpressure");
            score_valid=1;index=32'(number);note=7'(base_note+number);tick();score_valid=0;
        end
    endtask
    task terminal(input integer total,input integer code);
        begin
            if(terminal_ready!=15)$fatal(1,"unexpected terminal backpressure");
            count=32'(total);error=4'(code);terminal_valid=1;tick();terminal_valid=0;score_valid=0;
            if(terminal_ready[3:2]!=0 || score_ready[3:2]!=0)$fatal(1,"missing bounded seal backpressure");
            // Upstream is free to change its payload immediately after accept.
            count=32'hffffffff;error=15;last=~last;terminal_identity=~identity;
            tick();
            if(terminal_ready[3:2]!=3 || score_ready[3:2]!=3)$fatal(1,"seal stall exceeds one cycle");
            repeat(2)tick();
        end
    endtask
    task expect_completion(input [163:0] payload);
        integer k;begin
            for(k=0;k<4;k=k+1)
                if(completions[k]!=1 || completed[k]!==payload)$fatal(1,"completion mismatch mode=%0d",k);
        end
    endtask
    task drain(input integer total);
        integer k,j;begin
            for(j=0;j<total*2+16;j=j+1)begin push_ready=j%7!=0;tick();end
            push_ready=0;
            for(k=0;k<4;k=k+1)
                if(seen[k]!=total || !done[k])$fatal(1,"publication incomplete mode=%0d",k);
        end
    endtask
    task flush;
        begin cancel=1;tick();cancel=0;repeat(2)tick();clear_observers();end
    endtask
    integer i,k,which;
    initial begin
        clear_observers();repeat(3)tick();reset_n=1;tick();
        // All 2048 notes; terminal and the last note accepted on the same edge.
        expected_notes=2048;start(0,1);
        for(i=0;i<2047;i=i+1)put(i);
        score_valid=1;index=2047;note=127;terminal(2048,0);
        expect_completion({identity,32'd2048,4'd0});
        for(k=0;k<4;k=k+1)if(note_count[k]!=2048)$fatal(1,"capacity lost");
        drain(2048);clear_observers();
        // Append: only successful final clip releases the accumulated song.
        base_note=19;expected_notes=19;start(0,0);
        for(i=0;i<7;i=i+1)put(i);
        terminal(7,0);expect_completion({identity,32'd7,4'd0});
        if(push_valid!=0)$fatal(1,"partial clip published");
        clear_observers();start(1,1);
        for(i=0;i<12;i=i+1)begin note=7'(26+i);index=32'(i);score_valid=1;tick();score_valid=0;end
        terminal(12,0);expect_completion({identity,32'd12,4'd0});drain(19);flush();
        // Empty and terminal error, count high bits and poisoned final note.
        expected_notes=0;start(0,1);terminal(0,0);expect_completion({identity,32'd0,4'd0});
        if(done!=15 || push_valid!=0)$fatal(1,"empty final seal");
        flush();start(0,1);terminal(0,3);expect_completion({identity,32'd0,4'd14});
        if(failed!=15 || push_valid!=0)$fatal(1,"error seal published");
        flush();start(0,1);terminal(32'h00001000,0);expect_completion({identity,32'd0,4'd14});
        if(failed!=15 || push_valid!=0)$fatal(1,"count truncated");
        flush();start(0,1);score_valid=1;index=1;note=44;terminal(0,0);
        expect_completion({identity,32'd0,4'd14});if(failed!=15)$fatal(1,"bad final note unpoisoned");
        flush();base_note=0;start(0,1);
        for(i=0;i<2048;i=i+1)put(i);
        score_valid=1;index=2048;note=0;terminal(2049,0);
        expect_completion({identity,32'd2048,4'd14});if(push_valid!=0)$fatal(1,"overflow published");
        flush();
        // Every identity bit is compared; stale traffic cannot poison a job.
        for(i=0;i<128;i=i+1)begin
            start(0,1);score_identity=identity^(128'd1<<i);terminal_identity=score_identity;
            put(0);count=0;error=0;terminal_valid=1;tick();terminal_valid=0;repeat(2)tick();
            if(completion_valid!=0 || push_valid!=0 || failed!=0)$fatal(1,"stale identity accepted bit=%0d",i);
            for(k=0;k<4;k=k+1)if(completions[k]!=0 || note_count[k]!=0)$fatal(1,"stale count");
            flush();
        end
        // Kill the pending terminal on every supported revocation boundary.
        // The direct baseline already completed; only pipelined modes must
        // suppress that completion, and all modes must suppress publication.
        for(which=0;which<4;which=which+1)begin
            start(0,1);put(0);count=1;error=0;terminal_valid=1;tick();terminal_valid=0;
            case(which)0:cancel=1;1:panic=1;2:link=0;3:reset_n=0;endcase
            #1;if(push_valid!=0)$fatal(1,"revoked publication visible");
            tick();cancel=0;panic=0;link=1;reset_n=1;repeat(3)tick();
            for(k=2;k<4;k=k+1)if(completions[k]!=0 || completion_valid[k])$fatal(1,"pending seal survived revoke");
            clear_observers();
            expected_notes=1;start(0,1);put(0);terminal(1,0);
            expect_completion({identity,32'd1,4'd0});drain(1);flush();expected_notes=0;
        end
        $display("PASS terminal pipeline checks=%0d full_score=2048 stale_bits=128 revocations=4 modes=4",checks);
        $finish;
    end
    initial begin #3000000;$fatal(1,"watchdog");end
endmodule
