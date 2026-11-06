`timescale 1ns/1ps
module remote_effect_m_boundary(output reg done_o=0,output integer checks_o=0);
    reg clk=0,rst=0,clear=0,admit=1,rate=0,enabled=1,valid=0,qready=1;
    always #5 clk=~clk;
    reg [191:0] key={32'd10,32'd20,32'd30,32'd40,32'd0,32'd50};
    wire ready,ov,clip,qv,qr44,qe,rr,revoked,exhausted;
    wire signed [31:0] ol,oright,ql,qr;
    reg signed [31:0] il=0,ir=0,rl=0,rright=0;
    wire [31:0] qs,overflow,expired,fallback,rejected;
    wire [191:0] qkey;
    reg rv=0,r44=0,error=0,rclip=0,expected_good=0,score=1;
    reg [31:0] rs=0;
    reg [191:0] rkey=0;
    workstation_remote_effect_stream_m #(.DELAY_FRAMES(8),.QUEUE_FRAMES(4)) dut(
        .clk_i(clk),.reset_ni(rst),.clear_i(clear),.admitted_i(admit),.rate_44100_i(rate),
        .enabled_i(enabled),.key_i(key),.valid_i(valid),.left_i(il),.right_i(ir),.ready_o(ready),
        .valid_o(ov),.left_o(ol),.right_o(oright),.clip_o(clip),
        .req_valid_o(qv),.req_ready_i(qready),.req_key_o(qkey),.req_rate_44100_o(qr44),
        .req_enabled_o(qe),.req_sequence_o(qs),.req_left_o(ql),.req_right_o(qr),
        .rsp_valid_i(rv),.rsp_ready_o(rr),.rsp_key_i(rkey),.rsp_rate_44100_i(r44),
        .rsp_error_i(error),.rsp_clip_i(rclip),.rsp_sequence_i(rs),.rsp_left_i(rl),.rsp_right_i(rright),
        .overflow_count_o(overflow),.expired_count_o(expired),.fallback_count_o(fallback),
        .rejected_count_o(rejected),.revoked_o(revoked),.exhausted_o(exhausted));
    typedef struct packed {bit enabled;logic signed[31:0] l,r;} frame_t;
    typedef struct packed {bit clip;logic signed[31:0] l,r;} result_t;
    frame_t frames[integer];
    result_t results[integer],expectation;
    reg [191:0] seenkey=0;
    reg seenrate=0;
    integer index=0,transmitted=0,deadline_checks=0;
    reg should_valid;
    task automatic check(input bit ok,input string why);
        checks_o++;if(!ok)$fatal(1,"M boundary: %s time=%0t",why,$time);
    endtask
    always @(posedge clk)if(rst && !done_o)begin
        if(qv && qready)begin
            transmitted++;
            if(score)begin
                check(frames.exists(int'(qs))!=0,"issued sequence belongs to sample");
                check({qe,ql,qr}==frames[int'(qs)],"issued full32 sample and enable");
            end
        end
        should_valid=valid && !clear;expectation='0;
        if(clear || key!=seenkey || rate!=seenrate)begin
            frames.delete();results.delete();index=0;
            if(!clear)begin seenkey=key;seenrate=rate;end
        end else if(score)begin
            if(rv && expected_good)results[int'(rs)]={rclip,rl,rright};
            if(valid)begin
                if(index>=8)begin
                    expectation={1'b0,frames[index-8].l,frames[index-8].r};
                    if(admit && !revoked && enabled && frames[index-8].enabled && results.exists(index-8)!=0)
                        expectation=results[index-8];
                    deadline_checks++;
                end
                frames[index]={enabled,il,ir};index++;
            end
        end
        #0.001;
        check(ready && rr && ov==should_valid,"fixed output schedule without backpressure");
        if(should_valid && score)check({clip,ol,oright}==expectation,"deadline matches dry or authorised result");
    end
    task automatic frame(input integer n);
        @(negedge clk);valid=1;il=32'(n*33333+7);ir=-32'(n*77777+11);
        @(negedge clk);valid=0;repeat(2)@(negedge clk);
    endtask
    task automatic response(input integer seq,input bit good);
        @(negedge clk);rv=1;rs=32'(seq);rl=32'sh12345679;rright=-32'sh234567b;rclip=1;expected_good=good;
        @(negedge clk);rv=0;expected_good=0;
    endtask
    integer count_before;
    initial begin
        #20;rst=1;repeat(3)@(negedge clk);
        for(integer n=0;n<7;n++)frame(n);
        rkey=key;r44=rate;
        // Every key field must participate; these would all alias PCM slots.
        for(integer field=0;field<6;field++)begin
            rkey=key^(192'd1<<(32*field));count_before=int'(rejected);
            response(0,0);check(rejected==32'(count_before+1),"wrong key field rejected");
        end
        rkey=key;r44=!rate;count_before=int'(rejected);response(0,0);
        check(rejected==32'(count_before+1),"wrong rate rejected");
        r44=rate;error=1;count_before=int'(rejected);response(0,0);
        check(rejected==32'(count_before+1),"failed result rejected");error=0;
        response(2,1);count_before=int'(rejected);response(2,0);
        check(rejected==32'(count_before+1),"duplicate result rejected");
        qready=0;frame(7);count_before=int'(rejected);response(7,0);
        check(rejected==32'(count_before+1),"unissued result rejected");qready=1;
        repeat(3)@(negedge clk);
        // A result exactly on the old frame's deadline must bypass RAM.
        @(negedge clk);valid=1;il=32'd123;ir=-32'sd99;
        rv=1;rs=0;expected_good=1;rl=32'sh12345679;rright=-32'sh234567b;
        @(negedge clk);valid=0;rv=0;expected_good=0;
        count_before=int'(rejected);response(0,0);
        check(rejected==32'(count_before+1),"retired slot rejects late result");
        frame(9);enabled=0;frame(10);enabled=1;frame(11);
        // Invalid context is locally playable dry and cannot transmit.
        key[127:96]=0;repeat(3)@(negedge clk);count_before=transmitted;
        for(integer n=0;n<12;n++)frame(n);
        check(transmitted==count_before && !qv,"zero session blocks remote work");
        key[127:96]=31;repeat(3)@(negedge clk);
        rate=1;repeat(3)@(negedge clk);count_before=transmitted;
        for(integer n=0;n<10;n++)frame(n);
        check(revoked && transmitted==count_before,"rate-only change cannot reuse sequence identity");
        rate=0;repeat(3)@(negedge clk);frame(0);
        check(revoked && transmitted==count_before,"returning to old rate cannot alias an old result");
        key[31:0]++;repeat(3)@(negedge clk);
        // The sequence-wrap case uses a test-only counter deposit. No other
        // checks access implementation state; 2^32 simulation frames avoided.
        score=0;
        dut.sequence_number=32'hfffffffe;dut.cursor=3'd6;
        count_before=transmitted;frame(0);frame(1);frame(2);frame(3);
        check(exhausted && transmitted==count_before+2,"last two sequences once; no wrap transmission");
        check(!qv,"exhaustion preserves dry only");
        check(deadline_checks>=4,"deadline cases executed");
        done_o=1;
    end
endmodule

module remote_effect_w_boundary(output reg done_o=0,output integer checks_o=0);
    reg clk=0,rst=0,clear=0,admit=1,lease=0,rate=0;
    always #7 clk=~clk;
    reg [191:0] key={32'd1,32'd2,32'd3,32'd4,32'd0,32'd5},qkey=0;
    reg qv=0,qrate=0,qe=1,rready=1;
    reg [31:0] qs=0;
    reg signed [31:0] ql=0,qr=0;
    wire qready,rv,rrate,rerror,rclip;
    wire [191:0] rkey;
    wire [31:0] rs,rejected,timeouts;
    wire signed [31:0] rl,rr;
    wire claim,eclear,ecfg,erate,ev,ee;
    wire signed [31:0] el,er;
    reg ecfgdone=0,eoutv=0,eclip=0;
    reg signed [31:0] eol=0,eor=0;
    integer fault=0,engine_count=0,clears=0,configs=0;
    wire ecfgready=fault!=3,eready=fault!=2;
    workstation_remote_effect_stream_w #(.QUEUE_FRAMES(4),.PROCESS_TIMEOUT_CYCLES(32)) dut(
        .clk_i(clk),.reset_ni(rst),.clear_i(clear),.admitted_i(admit),.engine_lease_i(lease),
        .rate_44100_i(rate),.key_i(key),.req_valid_i(qv),.req_ready_o(qready),
        .req_key_i(qkey),.req_rate_44100_i(qrate),.req_enabled_i(qe),.req_sequence_i(qs),
        .req_left_i(ql),.req_right_i(qr),.rsp_valid_o(rv),.rsp_ready_i(rready),
        .rsp_key_o(rkey),.rsp_rate_44100_o(rrate),.rsp_error_o(rerror),.rsp_clip_o(rclip),
        .rsp_sequence_o(rs),.rsp_left_o(rl),.rsp_right_o(rr),.engine_claim_o(claim),
        .engine_clear_o(eclear),.engine_config_valid_o(ecfg),.engine_rate_44100_o(erate),
        .engine_config_ready_i(ecfgready),.engine_config_applied_i(ecfgdone),
        .engine_valid_o(ev),.engine_enabled_o(ee),.engine_left_o(el),.engine_right_o(er),
        .engine_ready_i(eready),.engine_result_valid_i(eoutv),.engine_clip_i(eclip),
        .engine_left_i(eol),.engine_right_i(eor),.rejected_count_o(rejected),.timeout_count_o(timeouts));
    // Deliberately controllable engine for fault boundaries. Real DSP and
    // asynchronous transport are tested separately in the four-clock matrix.
    always @(posedge clk)begin
        ecfgdone<=0;eoutv<=0;
        if(!rst || eclear)begin eoutv<=0;if(rst)clears++;end
        else begin
            if(ecfg && ecfgready)begin configs++;ecfgdone<=fault!=4;end
            if(ev && eready)begin
                engine_count++;
                eoutv<=fault!=1;eol<=el^32'sh01000311;eor<=er^32'sh02000713;eclip<=el[0];
            end
        end
    end
    typedef struct packed {logic[31:0] seq;bit error,clip;logic signed[31:0] l,r;} expected_t;
    expected_t expected[$],head;
    integer received=0,simultaneous=0;
    task automatic check(input bit ok,input string why);
        checks_o++;if(!ok)$fatal(1,"W boundary: %s time=%0t",why,$time);
    endtask
    always @(posedge clk)if(rst && !done_o)begin
        if(qv && qready && rv && rready)simultaneous++;
        if(rv && rready)begin
            check(expected.size()!=0,"no unexpected/duplicate result");head=expected.pop_front();
            check({rs,rerror,rclip,rl,rr}==head,"exact queued completion and error/dry semantics");
            check(rkey==key && rrate==rate,"result context and rate");received++;
        end
        if(!lease)check(!ev && !ecfg && !qready && !rv,"no work without exclusive lease");
    end
    task automatic send(input integer seq,input bit good,input bit err=0,input bit release_result=0);
        integer watchdog;
        @(negedge clk);qv=1;qs=32'(seq);ql=32'(seq*33333+7);qr=-32'(seq*777+9);
        if(release_result)rready=1;
        watchdog=0;
        do begin @(posedge clk);watchdog++;end while(!qready && watchdog<100);
        check(qready,"bounded request admission in directed test");
        if(good)expected.push_back({32'(seq),err,err ? 1'b0 : ql[0],
            err ? ql : (ql^32'sh01000311),err ? qr : (qr^32'sh02000713)});
        @(negedge clk);qv=0;
    endtask
    task automatic drain;
        integer watchdog;
        watchdog=0;
        while(expected.size()!=0 && watchdog<400)begin @(negedge clk);watchdog++;end
        check(expected.size()==0,"all completions drain within bound");
        repeat(3)@(negedge clk);
    endtask
    task automatic fresh;
        @(negedge clk);key[31:0]++;qkey=key;qrate=rate;repeat(3)@(negedge clk);
    endtask
    integer old_count,old_clears;
    initial begin
        #25;rst=1;repeat(3)@(negedge clk);check(claim && !qready,"claim before grant");
        lease=1;qkey=key;repeat(3)@(negedge clk);
        for(integer field=0;field<6;field++)begin
            qkey=key^(192'd1<<(field*32));old_count=int'(rejected);send(10,0);
            check(rejected==32'(old_count+1),"wrong request key drained");
        end
        qkey=key;qrate=1;old_count=int'(rejected);send(10,0);
        check(rejected==32'(old_count+1),"wrong request rate drained");qrate=rate;
        send(10,1);drain();old_clears=clears;send(11,1);drain();
        check(clears==old_clears,"consecutive work preserves history");
        old_count=int'(rejected);send(11,0);send(9,0);
        check(rejected==32'(old_count+2),"duplicate and decreasing sequences drained");
        send(13,1);drain();check(clears>old_clears,"sequence gap clears history");
        old_clears=clears;qe=0;send(14,1);drain();
        check(clears>old_clears,"enable transition clears history");
        // Each fault phase has an independent bound including configuration.
        for(integer mode=1;mode<=4;mode++)begin
            fault=mode;fresh();old_count=int'(timeouts);send(mode,1,1);drain();
            check(timeouts==32'(old_count+1),"stuck engine/config returns timed error");
        end
        fault=0;fresh();rready=0;
        for(integer seq=0;seq<8;seq++)begin send(seq,1);repeat(20)@(negedge clk);end
        qs=8;@(negedge clk); // query admission for new work, not duplicate7
        old_count=engine_count;check(!qready,"full request/result queues apply bounded backpressure");
        repeat(80)@(negedge clk);
        check(engine_count==old_count && old_count>0,"full results stop engine before starting more work");
        // Simultaneous full-queue pop/push exercises pointer reuse.
        send(8,1,0,1);drain();
        check(simultaneous>0,"full-queue request admission and result release on same edge");
        send(32'hffffffff,1);drain();old_count=int'(rejected);send(0,0);
        check(rejected==32'(old_count+1),"sequence wrap refused");
        // Cancel an in-flight job; an old completion cannot escape on reacquire.
        fresh();fault=1;send(0,1,1);repeat(6)@(negedge clk);
        lease=0;expected.delete();repeat(3)@(negedge clk);lease=1;
        repeat(40)@(negedge clk);check(!claim && !qready && !rv,"lease reacquire needs fresh key");
        fault=0;fresh();send(0,1);drain();
        clear=1;repeat(3)@(negedge clk);clear=0;repeat(3)@(negedge clk);
        check(!claim && !qready,"clear cannot rearm same key");
        fresh();send(0,1);drain();
        rate=1;repeat(3)@(negedge clk);
        check(!claim && !qready,"rate-only change needs fresh key");
        rate=0;repeat(3)@(negedge clk);
        check(!claim && !qready,"returning to old rate cannot rearm old key");
        rate=1;fresh();send(0,1);drain();check(erate,"rate configuration follows committed context");
        check(configs>=8 && received>=20,"directed fault and queue cases executed");done_o=1;
    end
endmodule

module tb_remote_effect_stream_boundaries;
    wire mdone,wdone;wire [31:0] mchecks,wchecks;
    remote_effect_m_boundary m(mdone,mchecks);
    remote_effect_w_boundary w(wdone,wchecks);
    initial begin
        wait(mdone && wdone);
        $display("REMOTE_EFFECT_RESULT {\"passed\":true,\"kind\":\"directed_boundaries\",\"M_checks\":%0d,\"W_checks\":%0d}",mchecks,wchecks);
        $finish;
    end
    initial begin #200000;$fatal(1,"boundary timeout");end
endmodule
