`timescale 1ns/1ps
module tb_task3_m_sync_storage;
    reg clk=0; always #5 clk=~clk;
    reg reset_n=0,link=1,panic=0;
    reg arm=0,cancel=0,frame=0,rate=0,error=0,tx_ready=0;
    reg [31:0] generation=1,epoch=7,first=0,seq=0,pcm=0;
    wire [1:0] arm_ready,arm_tx,armed,fault,tx_valid,cancel_tx;
    wire [1:0] tx_rate,tx_error;
    wire [31:0] tx_seq[0:1],tx_pcm[0:1],tx_epoch[0:1];
    wire [8:0] queued[0:1];
    wire [31:0] captured[0:1],exported[0:1];
    wire [3:0] failure[0:1];
    reg [31:0] expected_seq;
    integer checks=0,tap_frames=0;
    function automatic [31:0] sample(input [31:0] index);
        sample=index^32'ha51c03f7;
    endfunction
    genvar g;
    generate for(g=0;g<2;g=g+1)begin:tap
        workstation_task3_final_tap_export #(.SYNC_READ_STORAGE(g==1)) dut(
            .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.panic_i(panic),
            .arm_valid_i(arm),.arm_ready_o(arm_ready[g]),.arm_boot_i(32'd1),.arm_session_i(32'd2),
            .arm_generation_i(generation),.arm_physical_epoch_i(epoch),.arm_first_sequence_i(first),
            .arm_accepted_o(),.arm_rejected_o(),.arm_tx_valid_o(arm_tx[g]),.arm_tx_ready_i(1'b1),
            .arm_result_accepted_i(1'b1),.arm_result_rejected_i(1'b0),
            .boot_o(),.session_o(),.generation_o(),.physical_epoch_o(),.first_sequence_o(),
            .cancel_valid_i(cancel),.cancel_session_i(32'd2),.cancel_generation_i(generation),
            .frame_valid_i(frame),.frame_44k1_i(rate),.frame_error_i(error),
            .frame_epoch_i(epoch),.frame_sequence_i(seq),.frame_pcm_i(pcm),
            .frame_tx_valid_o(tx_valid[g]),.frame_tx_ready_i(tx_ready),
            .frame_tx_epoch_o(tx_epoch[g]),.frame_tx_sequence_o(tx_seq[g]),.frame_tx_pcm_o(tx_pcm[g]),
            .frame_tx_44k1_o(tx_rate[g]),.frame_tx_error_o(tx_error[g]),
            .cancel_tx_valid_o(cancel_tx[g]),.cancel_tx_ready_i(1'b1),.armed_o(armed[g]),.fault_o(fault[g]),
            .failure_code_o(failure[g]),.queued_frames_o(queued[g]),
            .captured_frames_o(captured[g]),.exported_frames_o(exported[g]));
    end endgenerate
    always @(posedge clk)if(reset_n)begin
        checks=checks+1;
        if({arm_ready[0],arm_tx[0],armed[0],fault[0],tx_valid[0],cancel_tx[0],queued[0],captured[0],exported[0],failure[0]} !==
           {arm_ready[1],arm_tx[1],armed[1],fault[1],tx_valid[1],cancel_tx[1],queued[1],captured[1],exported[1],failure[1]})
            $fatal(1,"tap cycle contract differs");
        if(tx_valid[1])begin
            if({tx_epoch[0],tx_seq[0],tx_pcm[0],tx_rate[0],tx_error[0]} !==
               {tx_epoch[1],tx_seq[1],tx_pcm[1],tx_rate[1],tx_error[1]})$fatal(1,"tap payload differs");
            if(tx_seq[1]!==expected_seq || tx_pcm[1]!==sample(expected_seq))$fatal(1,"tap order/data");
            if(tx_ready)begin expected_seq=expected_seq+1;tap_frames=tap_frames+1;end
        end
    end
    task automatic tick;begin @(posedge clk);#1;@(negedge clk);end endtask
    task automatic start_tap(input [31:0] start_seq);
        begin
            frame=0;tx_ready=0;cancel=0;panic=0;link=1;rate=0;error=0;
            repeat(3)tick();generation=generation+1;first=start_seq;seq=start_seq;
            expected_seq=start_seq;arm=1;tick();arm=0;repeat(4)tick();
            if(!(&armed))$fatal(1,"tap arm");
        end
    endtask
    task automatic put;begin frame=1;pcm=sample(seq);tick();seq=seq+1;end endtask
    task automatic stop_tap;begin frame=0;cancel=1;tick();cancel=0;repeat(3)tick();end endtask

    reg score_arm=0,score_valid=0,terminal_valid=0,score_cancel=0,score_ready=0,append=0,last=1;
    reg [127:0] identity=128'h1000000020000000300000004;
    reg [31:0] clip_index=0,terminal_count=0;
    reg [3:0] terminal_error=0;
    reg [6:0] note=0,base_note=0;
    wire [1:0] note_valid,done,failed;
    wire [6:0] output_note[0:1];
    wire [31:0] note_count[0:1];
    integer seen[0:1];
    generate for(g=0;g<2;g=g+1)begin:score
        workstation_task3_score_commit_m #(.SYNC_READ_STORAGE(g==1)) dut(
            .clk_i(clk),.reset_ni(reset_n),.link_ready_i(link),.cancel_i(score_cancel),.panic_i(panic),
            .arm_valid_i(score_arm),.arm_ready_o(),.arm_identity_i(identity),.arm_append_i(append),.chunk_file_last_i(last),
            .score_valid_i(score_valid),.score_ready_o(),.score_i({identity,clip_index,note}),
            .terminal_valid_i(terminal_valid),.terminal_ready_o(),.terminal_i({identity,terminal_count,terminal_error}),
            .completion_valid_o(),.completion_o(),.push_score_valid_o(note_valid[g]),.push_score_ready_i(score_ready),
            .push_score_note_o(output_note[g]),.analysis_done_o(done[g]),.failed_o(failed[g]),
            .failure_code_o(),.note_count_o(note_count[g]));
        always @(posedge clk)if(reset_n && note_valid[g] && score_ready)begin
            if(output_note[g]!==7'(seen[g]+integer'(base_note)))$fatal(1,"score order/data");
            seen[g]=seen[g]+1;
        end
    end endgenerate
    task automatic score_start(input bit add,input bit final_clip);
        begin
            score_arm=1;append=add;last=final_clip;clip_index=0;identity=identity+1;
            tick();score_arm=0;
        end
    endtask
    task automatic seal(input [31:0] count);
        begin terminal_count=count;terminal_valid=1;tick();terminal_valid=0;score_valid=0;end
    endtask
    task automatic drain_notes(input integer count);
        integer k;
        begin
            for(k=0;k<count*3+16;k=k+1)begin score_ready=(k%5)!=0;tick();end
            score_ready=0;
            if(seen[0]!=count || seen[1]!=count || !(&done))$fatal(1,"score publication did not finish");
        end
    endtask
    integer i;
    reg [31:0] random_state=32'hf50ba193;
    initial begin
        seen[0]=0;seen[1]=0;
        repeat(3)tick();reset_n=1;tick();
        start_tap(32'hfffffff0);
        // Empty forwarding followed by steady last-pop/new-push forwarding.
        tx_ready=1;repeat(80)put();frame=0;repeat(8)tick();
        // Burst, stalls, pointer wrap and arbitrary concurrent push/pop.
        for(i=0;i<3000;i=i+1)begin
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            tx_ready=random_state[0] || random_state[1];
            frame=random_state[2] && queued[0]<240;pcm=sample(seq);tick();if(frame)seq=seq+1;
        end
        frame=0;tx_ready=1;repeat(270)tick();stop_tap();
        // Exactly the original 256 slots; overflow revokes only this branch.
        start_tap(0);repeat(256)put();
        if(queued[1]!=256)$fatal(1,"tap capacity shrunk");
        put();frame=0;if(!(&fault) || failure[1]!=1)$fatal(1,"tap overflow");
        start_tap(9000);repeat(5)put();frame=0;panic=1;#1;if(tx_valid!=0)$fatal(1,"PANIC visibility");
        tick();panic=0;repeat(3)tick();start_tap(10000);repeat(4)put();frame=0;
        link=0;#1;if(tx_valid!=0)$fatal(1,"link visibility");tick();link=1;repeat(3)tick();
        start_tap(20000);tx_ready=1;repeat(4)put();frame=0;repeat(5)tick();stop_tap();
        // Full score capacity; final note and terminal arrive on the same edge.
        score_start(0,1);
        for(i=0;i<2047;i=i+1)begin score_valid=1;clip_index=32'(i);note=7'(i);tick();end
        clip_index=2047;note=127;seal(2048);
        if(note_count[1]!=2048)$fatal(1,"score capacity shrunk");
        drain_notes(2048);
        // Cancel a stalled prefetched head, then publish a distinct new song.
        score_start(0,1);score_valid=1;clip_index=0;note=7'd55;tick();score_valid=0;seal(1);
        repeat(3)tick();score_cancel=1;#1;if(note_valid!=0)$fatal(1,"score cancel visibility");tick();score_cancel=0;
        seen[0]=0;seen[1]=0;base_note=17;
        score_start(0,0);
        for(i=0;i<7;i=i+1)begin score_valid=1;clip_index=32'(i);note=7'(i+17);tick();end
        score_valid=0;seal(7);repeat(3)tick();if(note_valid!=0)$fatal(1,"partial clip published");
        score_start(1,1);
        for(i=0;i<12;i=i+1)begin score_valid=1;clip_index=32'(i);note=7'(i+24);tick();end
        score_valid=0;seal(12);drain_notes(19);
        // Failed seal must not expose the old RAM contents.
        score_start(0,1);terminal_error=3;seal(0);repeat(4)tick();
        if(note_valid!=0 || failed!=3)$fatal(1,"failed terminal published");
        $display("PASS M sync storage checks=%0d tap_frames=%0d full_tap=256 full_score=2048 append_score=19",checks,tap_frames);
        $finish;
    end
    initial begin #2000000;$fatal(1,"watchdog");end
endmodule
