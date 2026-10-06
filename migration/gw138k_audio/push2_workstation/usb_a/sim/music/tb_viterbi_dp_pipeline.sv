`timescale 1ns/1ps
`include "basic_pitch_fixed_pkg.svh"
`include "basic_pitch_ddr_map.svh"
// Independent recurrence oracle across a production-length window. Both
// internal and stalled external history must preserve every score/backpointer.
module tb_viterbi_dp_pipeline;
    localparam integer FRAMES = 172, BINS = 88, STATES = 89;
    reg clk=0, rstn=0, start=0, nv=0, ov=0, fv=0, last=0;
    reg [6:0] idx=0;
    reg signed [15:0] nq=0, oq=0;
    always #10 clk=~clk;
    wire ready_a,ready_b,sv_a,sv_b,complete_a,complete_b;
    wire [6:0] sn_a,sn_b;
    wire req,wr;
    wire [31:0] addr;
    wire [15:0] wd;
    reg rsp=0;
    reg [15:0] rd=0;
    integer cycles=0,timer=0;
    wire mem_ready = timer==0 && !rsp && cycles%7!=0;
    wire score_ready = cycles%11<8;
    reg [15:0] mem[0:65535];
    wire [15:0] mi={addr[21:20],addr[14:1]};
    basic_pitch_viterbi #(.FRAMES(FRAMES),.USE_EXTERNAL_STATE(0)) dut_a(
        .clk_i(clk),.rst_ni(rstn),.start_i(start),.active_i(1'b1),
        .note_valid_i(nv),.note_idx_i(idx),.note_q_i(nq),
        .onset_valid_i(ov),.onset_idx_i(idx),.onset_q_i(oq),
        .frame_valid_i(fv),.frame_last_i(last),.frame_ready_o(ready_a),
        .result_valid_o(),.result_note_o(),.result_conf_o(),.result_frame_o(),
        .score_valid_o(sv_a),.score_ready_i(score_ready),.score_note_o(sn_a),
        .score_complete_o(complete_a),.done_o(),.busy_o(),
        .mem_req_o(),.mem_write_o(),.mem_byte_addr_o(),.mem_wdata_o(),
        .mem_ready_i(1'b0),.mem_rsp_valid_i(1'b0),.mem_rdata_i(16'd0));
    basic_pitch_viterbi #(.FRAMES(FRAMES),.USE_EXTERNAL_STATE(1)) dut_b(
        .clk_i(clk),.rst_ni(rstn),.start_i(start),.active_i(1'b1),
        .note_valid_i(nv),.note_idx_i(idx),.note_q_i(nq),
        .onset_valid_i(ov),.onset_idx_i(idx),.onset_q_i(oq),
        .frame_valid_i(fv),.frame_last_i(last),.frame_ready_o(ready_b),
        .result_valid_o(),.result_note_o(),.result_conf_o(),.result_frame_o(),
        .score_valid_o(sv_b),.score_ready_i(score_ready),.score_note_o(sn_b),
        .score_complete_o(complete_b),.done_o(),.busy_o(),
        .mem_req_o(req),.mem_write_o(wr),.mem_byte_addr_o(addr),.mem_wdata_o(wd),
        .mem_ready_i(mem_ready),.mem_rsp_valid_i(rsp),.mem_rdata_i(rd));
    always @(posedge clk) if(rstn) begin
        cycles<=cycles+1;
        rsp<=0;
        if(req && mem_ready) begin
            if(addr[31:22]!=(`BP_DDR_BPTR_BYTE_BASE>>22) || addr[0])
                $fatal(1,"invalid history address %h",addr);
            if(wr) mem[mi]<=wd;
            else begin rd<=mem[mi]; timer<=1+cycles%5; end
        end else if(timer>0) begin
            timer<=timer-1;
            if(timer==1) rsp<=1;
        end
    end
    function automatic integer note_q(input integer f,b);
        integer main_note;
        begin
            main_note=20+(f/6)%40;
            if(f%31>=27) note_q=0;
            else if(b==main_note || (f%17==0 && b==main_note+1)) note_q=28000;
            else note_q=1024+(b*67+f*103)%4096;
        end
    endfunction
    function automatic integer onset_q(input integer f,b);
        onset_q=(b==20+(f/6)%40 && f%6==0) ? 30000 : 512;
    endfunction
    // Mathematical DP recurrence; no RTL FSM or staging is copied here.
    integer gold[0:STATES-1], prev[0:STATES-1], emit[0:STATES-1];
    integer gold_bp[0:FRAMES*STATES-1];
    integer peak,f,d,p,delta,tr,cand,best,best_p;
    task reference_frame(input integer frame_no);
        begin
            peak=0;
            for(d=0;d<BINS;d=d+1) begin
                if(note_q(frame_no,d)>peak) peak=note_q(frame_no,d);
                emit[d]=(note_q(frame_no,d)*`BP_EMIT_NOTE_W>>>15)+
                        (onset_q(frame_no,d)*`BP_EMIT_ONSET_W>>>15);
            end
            emit[BINS]=peak>=`BP_SILENCE_THRESHOLD ? `BP_EMIT_SIL_ACTIVE : `BP_EMIT_SIL_IDLE;
            for(d=0;d<STATES;d=d+1) prev[d]=gold[d];
            for(d=0;d<STATES;d=d+1) begin
                if(frame_no==0) gold[d]=emit[d];
                else begin
                    best=-2147483647-1; best_p=0;
                    for(p=0;p<STATES;p=p+1) begin
                        if(d==BINS) tr=p==BINS ? `BP_TRANS_SIL_STAY : `BP_TRANS_NOTE_TO_SIL;
                        else if(p==BINS) tr=`BP_TRANS_SIL_TO_NOTE;
                        else begin
                            delta=d>p ? d-p : p-d;
                            tr=delta==0 ? `BP_TRANS_STAY : -`BP_TRANS_STEP_SLOPE*delta;
                            if(delta>`BP_TRANS_JUMP_KNEE)
                                tr=tr-`BP_TRANS_JUMP_SLOPE*(delta-`BP_TRANS_JUMP_KNEE);
                        end
                        cand=prev[p]+tr;
                        if(cand>best) begin best=cand; best_p=p; end
                    end
                    gold[d]=emit[d]+best;
                    gold_bp[frame_no*STATES+d]=best_p;
                end
            end
        end
    endtask
    integer checked_a=0,checked_b=0,j;
    always @(negedge clk) if(rstn) begin
        if(dut_a.state==5 || (dut_a.state==6 && dut_a.d_cnt==0)) begin
            for(j=0;j<STATES;j=j+1) begin
                if(dut_a.score[j]!==gold[j]) $fatal(1,"internal score frame=%0d state=%0d got=%0d expected=%0d",f,j,dut_a.score[j],gold[j]);
                if(f>0 && dut_a.bptr_mem[f*STATES+j]!==7'(gold_bp[f*STATES+j]))
                    $fatal(1,"internal backpointer frame=%0d state=%0d",f,j);
            end
            checked_a=checked_a+1;
        end
        if(dut_b.state==5 || (dut_b.state==6 && dut_b.d_cnt==0)) begin
            for(j=0;j<STATES;j=j+1) begin
                if(dut_b.score[j]!==gold[j]) $fatal(1,"external score frame=%0d state=%0d got=%0d expected=%0d",f,j,dut_b.score[j],gold[j]);
                if(f>0 && mem[f*STATES+j]!==16'(gold_bp[f*STATES+j]))
                    $fatal(1,"external backpointer frame=%0d state=%0d",f,j);
            end
            checked_b=checked_b+1;
        end
    end
    reg [6:0] seq_a[0:FRAMES-1],seq_b[0:FRAMES-1];
    integer na=0,nb=0;
    reg finished_a=0,finished_b=0;
    always @(posedge clk) if(rstn) begin
        if(sv_a && score_ready) begin seq_a[na]<=sn_a; na=na+1; end
        if(sv_b && score_ready) begin seq_b[nb]<=sn_b; nb=nb+1; end
        if(complete_a) finished_a<=1;
        if(complete_b) finished_b<=1;
    end
    initial begin
        for(j=0;j<65536;j=j+1) mem[j]=0;
        for(j=0;j<STATES;j=j+1) gold[j]=0;
        repeat(4) @(negedge clk); rstn=1;
        @(negedge clk); start=1;
        @(negedge clk); start=0;
        for(f=0;f<FRAMES;f=f+1) begin
            wait(ready_a && ready_b);
            reference_frame(f);
            for(integer b=0;b<BINS;b=b+1) begin
                wait(ready_a && ready_b);
                @(negedge clk); idx=b; nq=note_q(f,b); oq=onset_q(f,b); nv=1; ov=1;
                @(negedge clk); nv=0; ov=0;
            end
            wait(ready_a && ready_b);
            @(negedge clk); fv=1; last=f==FRAMES-1;
            @(negedge clk); fv=0;
            // Wait for both complete score rows before advancing the oracle.
            wait(checked_a>f && checked_b>f);
        end
        wait(finished_a && finished_b);
        @(negedge clk);
        if(checked_a!=FRAMES || checked_b!=FRAMES || na==0 || na!=nb)
            $fatal(1,"coverage frames=%0d/%0d notes=%0d/%0d",checked_a,checked_b,na,nb);
        for(j=0;j<na;j=j+1) if(seq_a[j]!==seq_b[j]) $fatal(1,"score sequence mismatch index=%0d",j);
        $display("PASS Viterbi DP oracle: %0d frames x %0d states; all scores/backpointers, ties, silence, DDR stalls, %0d notes",FRAMES,STATES,na);
        $finish;
    end
    initial begin
        repeat(10000000) @(posedge clk);
        $fatal(1,"Viterbi DP timeout");
    end
endmodule
