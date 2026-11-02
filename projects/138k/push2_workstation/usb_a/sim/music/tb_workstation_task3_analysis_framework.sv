`timescale 1ns/1ps
// M source/result lifecycle with an explicit deterministic W responder.
// It does not prove the actual CNN, TF SPI, CDC or LCD transport.
module tb_workstation_task3_analysis_framework;
    reg clk=0,rst=0,link=1,start=0,enable_input=0,hold_result=0,inject_stale=0;
    always #10 clk=~clk;
    reg [31:0] boot=1,session=2,task_id=10,generation=20;
    integer target_frames=23,input_index=0,notes_per_clip=2,cycle=0,checks=0;
    wire start_ready,pcm_ready,dv,fv,zv,cv,av,ar,append,last_chunk;
    wire [199:0] desc;
    wire [191:0] frame,seal;
    wire [127:0] cancel,arm_id;
    wire [31:0] total_frames,completed_clips;
    wire busy,done,source_failed;
    wire [3:0] source_failure;
    wire score_ready,term_ready,completion,psv,analysis_done,score_failed;
    wire [163:0] completion_data;
    wire [6:0] push_note;
    wire [31:0] note_count;
    wire dr=cycle%5!=0;
    wire fr=worker_state==1 && cycle%7>=3;
    wire zr=worker_state==1 && cycle%11>=2;
    wire pr=cycle%9>=4;
    wire pcm_valid=enable_input && input_index<target_frames;
    wire [31:0] pcm_word=32'h4d230000^32'(input_index*1291);
    workstation_task3_tf_analysis_source #(.QUEUE_FRAMES(8),.WAIT_TIMEOUT_CYCLES(2000)) source(
        .clk_i(clk),.reset_ni(rst),.link_ready_i(link),.transport_fault_i(1'b0),.cancel_i(1'b0),.panic_i(1'b0),
        .start_valid_i(start),.start_ready_o(start_ready),.start_boot_i(boot),.start_session_i(session),
        .start_task_id_i(task_id),.start_generation_i(generation),.clip_frames_i(32'd16),
        .pcm_valid_i(pcm_valid),.pcm_ready_o(pcm_ready),.pcm_pair_i(pcm_word),.pcm_last_i(input_index==target_frames-1),
        .desc_valid_o(dv),.desc_ready_i(dr),.desc_o(desc),.frame_valid_o(fv),.frame_ready_i(fr),.frame_o(frame),
        .seal_valid_o(zv),.seal_ready_i(zr),.seal_o(seal),.cancel_valid_o(cv),.cancel_ready_i(1'b1),.cancel_o(cancel),
        .arm_valid_o(av),.arm_ready_i(ar),.arm_identity_o(arm_id),.arm_append_o(append),.chunk_file_last_o(last_chunk),
        .completion_valid_i(completion),.completion_i(completion_data),.busy_o(busy),.done_o(done),.failed_o(source_failed),
        .failure_code_o(source_failure),.total_frames_o(total_frames),.completed_clips_o(completed_clips));
    reg [127:0] worker_id,old_id;
    integer worker_state=0,worker_frames=0,worker_note=0,worker_clip=0,worker_wait=0,clips=0;
    reg [31:0] worker_crc;
    wire worker_sv=worker_state==2 && !hold_result && worker_wait==0 && worker_note<notes_per_clip;
    wire worker_tv=worker_state==3 && !hold_result;
    wire [166:0] response_score=inject_stale?{old_id,32'd0,7'd127}:
        {worker_id,32'(worker_note),7'(60+worker_clip*notes_per_clip+worker_note)};
    wire [163:0] response_term={worker_id,32'(notes_per_clip),4'd0};
    workstation_task3_score_commit_m #(.MAX_NOTES(4)) collector(
        .clk_i(clk),.reset_ni(rst),.link_ready_i(link),.cancel_i(source_failed),.panic_i(1'b0),
        .arm_valid_i(av),.arm_ready_o(ar),.arm_identity_i(arm_id),.arm_append_i(append),.chunk_file_last_i(last_chunk),
        .score_valid_i(inject_stale || worker_sv),.score_ready_o(score_ready),.score_i(response_score),
        .terminal_valid_i(worker_tv),.terminal_ready_o(term_ready),.terminal_i(response_term),
        .completion_valid_o(completion),.completion_o(completion_data),.push_score_valid_o(psv),.push_score_ready_i(pr),
        .push_score_note_o(push_note),.analysis_done_o(analysis_done),.failed_o(score_failed),.failure_code_o(),.note_count_o(note_count));
    function automatic [31:0] cb(input [31:0] old_crc,input [7:0] data);
        reg [31:0] c;integer j;begin c=old_crc^{24'd0,data};for(j=0;j<8;j=j+1)c=c[0]?((c>>1)^32'hedb88320):(c>>1);cb=c;end
    endfunction
    function automatic [31:0] cw(input [31:0] old_crc,input [31:0] data);
        reg [31:0] c;integer j;begin c=old_crc;for(j=0;j<4;j=j+1)c=cb(c,data[j*8+:8]);cw=c;end
    endfunction
    integer pushed=0;
    reg [31:0] held_frame;
    reg prior_frame_stall=0;
    always @(posedge clk)begin
        if(!rst)begin input_index<=0;cycle<=0;worker_state<=0;worker_frames<=0;worker_note<=0;worker_clip<=0;
            worker_wait<=0;worker_id<=0;worker_crc<=32'hffffffff;clips<=0;pushed<=0;prior_frame_stall<=0;held_frame<=0;end
        else begin
            cycle<=cycle+1;
            if(pcm_valid && pcm_ready)input_index<=input_index+1;
            if(prior_frame_stall && link && !source_failed && fv && frame[31:0]!=held_frame)$fatal(1,"unstable stalled frame");
            prior_frame_stall<=fv && !fr;held_frame<=frame[31:0];
            if(dv && dr)begin
                if(worker_state!=0)$fatal(1,"overlapping worker tasks");
                if(desc[71:40]!=16 || desc[39:8]!=0 || desc[7:0]!=1)$fatal(1,"descriptor fields");
                if(clips!=0 && desc[103:72]!=worker_id[31:0]+1)$fatal(1,"generation did not advance");
                worker_id<=desc[199:72];worker_frames<=0;worker_crc<=32'hffffffff;worker_note<=0;worker_state<=1;
            end
            if(fv && fr)begin
                if(frame[191:64]!=worker_id || frame[63:32]!=32'(worker_frames))$fatal(1,"frame identity/index");
                worker_crc<=cw(worker_crc,frame[31:0]);worker_frames<=worker_frames+1;
            end
            if(zv && zr)begin
                if(seal[191:64]!=worker_id || seal[63:32]!=32'(worker_frames) || seal[31:0]!=(~worker_crc))$fatal(1,"seal identity/count/CRC");
                if(clips==0 && worker_frames!=16)$fatal(1,"wrong first boundary");
                if(last_chunk && worker_frames!=target_frames-clips*16)$fatal(1,"wrong actual EOF");
                worker_state<=2;worker_wait<=17;clips<=clips+1;
            end
            if(worker_state==2 && worker_wait!=0)worker_wait<=worker_wait-1;
            if(worker_sv && score_ready)begin worker_note<=worker_note+1;if(worker_note+1==notes_per_clip)worker_state<=3;end
            if(worker_tv && term_ready)begin worker_state<=0;worker_clip<=worker_clip+1;end
            if(cv)worker_state<=0;
            if(!link)worker_state<=0;
            if(psv && pr)begin
                if(!last_chunk || input_index!=target_frames)$fatal(1,"partial song published");
                if(push_note!=7'(60+pushed))$fatal(1,"wrong complete published score");
                pushed<=pushed+1;
            end
        end
    end
    task automatic check(input bit ok,input string text_value);
        begin checks=checks+1;if(!ok)$fatal(1,"check failed %s",text_value);end
    endtask
    task automatic reset_all;
        begin @(negedge clk);rst=0;link=1;start=0;enable_input=0;hold_result=0;inject_stale=0;
            repeat(5)@(negedge clk);rst=1;repeat(4)@(negedge clk);end
    endtask
    task automatic launch;
        begin while(!start_ready)@(negedge clk);start=1;enable_input=1;@(negedge clk);start=0;end
    endtask
    initial begin
        reset_all();launch();while(!done)@(negedge clk);while(!analysis_done)@(negedge clk);
        check(!source_failed && !score_failed && total_frames==23 && completed_clips==2,"two exact clips cover full real EOF");
        check(clips==2 && pushed==4 && note_count==4,"all clips publish only final complete score under stalls");
        reset_all();hold_result=1;launch();while(clips!=1)@(negedge clk);old_id=worker_id;
        check(pushed==0 && !analysis_done,"unpublished first clip while worker stalled");
        link=0;repeat(5)@(negedge clk);check(source_failed && source_failure==1 && note_count==0,"disconnect fences score and source");
        link=1;inject_stale=1;repeat(3)@(negedge clk);inject_stale=0;
        check(note_count==0 && pushed==0,"old identity is discarded after reconnect");
        reset_all();notes_per_clip=3;launch();while(!done)@(negedge clk);
        check(source_failed && score_failed && pushed==0 && !analysis_done,"bounded song overflow rejects partial score");
        reset_all();notes_per_clip=2;hold_result=1;launch();while(!done)@(negedge clk);
        check(source_failed && source_failure==5 && pushed==0,"missing terminal expires without publication");
        repeat(3)@(negedge clk);check(!busy && note_count==0,"timeout cancellation retires and clears result image");
        $display("PASS task3_analysis_logic checks=%0d scenarios=4 deterministic_worker=1",checks);$finish;
    end
    initial begin #3000000;$fatal(1,"test timeout");end
endmodule
