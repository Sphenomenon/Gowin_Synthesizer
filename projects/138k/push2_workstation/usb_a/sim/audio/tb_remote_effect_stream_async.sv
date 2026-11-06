`timescale 1ns/1ps
module tb_remote_effect_stream_async;
    localparam integer DELAY=64;
    reg mc=0,w25=0,w50=0,fast=0,rst=0,clear=0,admit=1,lease=1,rate=0,enable=1;
    always #6.510 mc=~mc;
    always #20 w25=~w25;
    always #10 w50=~w50;
    wire wc=fast ? w50 : w25;
    reg [191:0] key={32'd1,32'd2,32'd3,32'd4,32'd0,32'd5};
    reg valid=0;
    reg signed [31:0] left=0,right=0;
    wire ready,outvalid,outclip,revoked,exhausted;
    wire signed [31:0] outleft,outright;
    wire [31:0] overflows,expired,fallbacks,rejected,wrejected,timeouts;
    wire qv,qr,rv,rr;
    wire [289:0] qdata;
    wire [290:0] rdata;
    wire qfv,qfr,rfv,rfr,qwrite_ready,rwrite_ready;
    wire [289:0] qhead;
    wire [290:0] rhead;
    reg stop_up=0,stop_down=0;
    realtime sent_at[integer],result_at[integer];
    realtime up_delay=30000.0,down_delay=30000.0;
    // Timestamp lookup is a test-only pipelined delay model; the actual
    // crossings and finite storage are the maintained Gray-pointer FIFOs.
    reg up_due=0,down_due=0;
    always @(negedge wc)up_due=qfv && sent_at.exists(int'(qhead[95:64]))!=0 &&
        $realtime>=sent_at[int'(qhead[95:64])]+up_delay+real'(qhead[66:64])*900.0;
    always @(negedge mc)down_due=rfv && result_at.exists(int'(rhead[95:64]))!=0 &&
        $realtime>=result_at[int'(rhead[95:64])]+down_delay+real'(rhead[66:64])*700.0;
    assign qr=qwrite_ready && !stop_up;
    assign qfr=up_due && !stop_up && wready;
    assign rv=down_due && !stop_down;
    assign rdata=rhead;
    assign rfr=rv && rr;
    music_async_fifo #(.WIDTH(290),.ADDRESS_BITS(5)) requests(
        .write_clk_i(mc),.write_rst_ni(rst),.write_valid_i(qv && !stop_up),
        .write_ready_o(qwrite_ready),.write_data_i(qdata),
        .read_clk_i(wc),.read_rst_ni(rst),.read_valid_o(qfv),
        .read_ready_i(qfr),.read_data_o(qhead));
    wire wvalid,wready,wrspvalid,wrspready;
    wire [290:0] wrsp;
    assign wvalid=up_due && !stop_up;
    assign wrspready=rwrite_ready;
    music_async_fifo #(.WIDTH(291),.ADDRESS_BITS(5)) responses(
        .write_clk_i(wc),.write_rst_ni(rst),.write_valid_i(wrspvalid),
        .write_ready_o(rwrite_ready),.write_data_i(wrsp),
        .read_clk_i(mc),.read_rst_ni(rst),.read_valid_o(rfv),
        .read_ready_i(rfr),.read_data_o(rhead));
    workstation_remote_effect_stream_m m(
        .clk_i(mc),.reset_ni(rst),.clear_i(clear),.admitted_i(admit),
        .rate_44100_i(rate),.enabled_i(enable),.key_i(key),
        .valid_i(valid),.left_i(left),.right_i(right),.ready_o(ready),
        .valid_o(outvalid),.left_o(outleft),.right_o(outright),.clip_o(outclip),
        .req_valid_o(qv),.req_ready_i(qr),.req_key_o(qdata[289:98]),
        .req_rate_44100_o(qdata[97]),.req_enabled_o(qdata[96]),
        .req_sequence_o(qdata[95:64]),.req_left_o(qdata[63:32]),.req_right_o(qdata[31:0]),
        .rsp_valid_i(rv),.rsp_ready_o(rr),.rsp_key_i(rdata[290:99]),
        .rsp_rate_44100_i(rdata[98]),.rsp_error_i(rdata[97]),.rsp_clip_i(rdata[96]),
        .rsp_sequence_i(rdata[95:64]),.rsp_left_i(rdata[63:32]),.rsp_right_i(rdata[31:0]),
        .overflow_count_o(overflows),.expired_count_o(expired),.fallback_count_o(fallbacks),
        .rejected_count_o(rejected),.revoked_o(revoked),.exhausted_o(exhausted));
    wire claim,eclear,ecfg,erate,ecfgready,ecfgdone,ev,ee,eready,eoutv,eclip;
    wire signed [31:0] el,er,eol,eor;
    workstation_remote_effect_stream_w w(
        .clk_i(wc),.reset_ni(rst),.clear_i(clear),.admitted_i(admit),.engine_lease_i(lease),
        .rate_44100_i(rate),.key_i(key),.req_valid_i(wvalid),.req_ready_o(wready),
        .req_key_i(qhead[289:98]),.req_rate_44100_i(qhead[97]),.req_enabled_i(qhead[96]),
        .req_sequence_i(qhead[95:64]),.req_left_i(qhead[63:32]),.req_right_i(qhead[31:0]),
        .rsp_valid_o(wrspvalid),.rsp_ready_i(wrspready),.rsp_key_o(wrsp[290:99]),
        .rsp_rate_44100_o(wrsp[98]),.rsp_error_o(wrsp[97]),.rsp_clip_o(wrsp[96]),
        .rsp_sequence_o(wrsp[95:64]),.rsp_left_o(wrsp[63:32]),.rsp_right_o(wrsp[31:0]),
        .engine_claim_o(claim),.engine_clear_o(eclear),.engine_config_valid_o(ecfg),
        .engine_rate_44100_o(erate),.engine_config_ready_i(ecfgready),.engine_config_applied_i(ecfgdone),
        .engine_valid_o(ev),.engine_enabled_o(ee),.engine_left_o(el),.engine_right_o(er),
        .engine_ready_i(eready),.engine_result_valid_i(eoutv),.engine_clip_i(eclip),
        .engine_left_i(eol),.engine_right_i(eor),.rejected_count_o(wrejected),.timeout_count_o(timeouts));
    workstation_runtime_spatial_reverb engine(
        .clk_i(wc),.rst_ni(rst),.clear_i(eclear),.valid_i(ev),.enabled_i(ee),
        .left_i(el),.right_i(er),.ready_o(eready),.active_o(),.valid_o(eoutv),
        .left_o(eol),.right_o(eor),.clip_o(eclip),.config_valid_i(ecfg),.rate_44100_i(erate),
        .history_clear_i(1'b0),.config_ready_o(ecfgready),.config_applied_o(ecfgdone),
        .history_ready_o(),.history_done_o(),.quiescent_o(),.applied_rate_44100_o());

    typedef struct packed {bit enabled;logic signed [31:0] l,r;} frame_t;
    typedef struct packed {bit clip;logic signed [31:0] l,r;} result_t;
    frame_t inputs[integer],pending[$];
    result_t received[integer],computed[integer];
    bit sent[integer];
    integer frame_index=0,output_index=0,checks=0,frames=0,wet_frames=0,different=0;
    integer engine_frames=0,transported=0,epoch=0;
    integer active_seq=0;
    integer pending_seq[$];
    bit engine_busy=0;
    reg [191:0] mkey=0,wkey=0;
    reg mrate=0,wrate=0;
    frame_t expected_frame,accepted_frame;
    result_t expected;
    reg expected_valid;
    integer ix;
    task automatic check(input bit ok,input string message);
        checks++;
        if(!ok)$fatal(1,"%s time=%0t frame=%0d epoch=%0d",message,$time,frame_index,epoch);
    endtask
    always @(posedge mc)if(rst)begin
        expected_valid=valid && !clear;
        expected='0;
        if(clear || key!=mkey || rate!=mrate)begin
            inputs.delete();received.delete();sent.delete();frame_index=0;output_index=0;
            if(!clear)begin mkey=key;mrate=rate;end
        end else begin
            if(qv && qr)begin
                ix=int'(qdata[95:64]);
                check(inputs.exists(ix)!=0,"request must belong to an input");
                check(qdata[96:0]=={inputs[ix].enabled,32'(ix),inputs[ix].l,inputs[ix].r},
                    "full32 request association");
                check(!sent.exists(ix),"request transmitted once");
                sent[ix]=1;sent_at[ix]=$realtime;transported++;
            end
            if(rv && rr && rdata[290:99]==key && rdata[98]==rate && !rdata[97])begin
                ix=int'(rdata[95:64]);
                if(sent.exists(ix) && ix>=output_index && !received.exists(ix))begin
                    check(computed.exists(ix)!=0,"response has real engine completion");
                    check({rdata[96],rdata[63:0]}==computed[ix],"worker result equals full32 real engine result");
                    received[ix]=result_t'({rdata[96],rdata[63:0]});
                end
            end
            if(valid)begin
                if(frame_index>=DELAY)begin
                    ix=frame_index-DELAY;expected_frame=inputs[ix];
                    expected={1'b0,expected_frame.l,expected_frame.r};
                    if(admit && !revoked && enable && expected_frame.enabled && received.exists(ix))begin
                        expected=received[ix];wet_frames++;
                        if(expected.l!=expected_frame.l || expected.r!=expected_frame.r)different++;
                    end
                    output_index=ix+1;
                end
                inputs[frame_index]={enable,left,right};frame_index++;frames++;
            end
        end
        #0.001;
        check(ready && rr,"M input and response never backpressure audio");
        check(outvalid==expected_valid,"fixed next-edge output valid");
        if(expected_valid)check({outclip,outleft,outright}==expected,"fixed64 dry/wet aligned output");
    end
    always @(posedge wc)if(rst)begin
        if(clear || key!=wkey || rate!=wrate || !admit || !lease)begin
            pending.delete();pending_seq.delete();engine_busy=0;
            if(!clear)begin wkey=key;wrate=rate;end
        end else begin
            if(wvalid && wready && qhead[289:98]==key && qhead[97]==rate)begin
                pending.push_back(frame_t'({qhead[96],qhead[63:0]}));
                pending_seq.push_back(int'(qhead[95:64]));
            end
            if(eclear)engine_busy=0;
            if(ev && eready)begin
                check(lease && claim,"exclusive engine lease required");
                check(pending.size()!=0 && !engine_busy,"one real engine request in flight");
                accepted_frame=pending.pop_front();active_seq=pending_seq.pop_front();
                check({ee,el,er}==accepted_frame,"worker preserves request PCM/order/enable");
                engine_busy=1;engine_frames++;
            end
            if(eoutv)begin
                check(engine_busy,"real engine completion belongs to work");
                computed[active_seq]={eclip,eol,eor};engine_busy=0;
            end
            if(wrspvalid && wrspready)begin
                ix=int'(wrsp[95:64]);
                check(!wrsp[97] && computed.exists(ix)!=0,"no unexpected engine error");
                check({wrsp[96],wrsp[63:0]}==computed[ix],"worker wraps exact engine output");
                result_at[ix]=$realtime;
            end
        end
    end
    task automatic sample(input integer n);
        @(negedge mc);valid=1;
        // Both channels include low bits that a PCM16 transport would lose.
        left=32'sh08000007+32'(n*53177);right=-32'sh0400000b-32'(n*9127);
        @(negedge mc);valid=0;
        if(rate)#22650;else #20800;
    endtask
    task automatic fresh;
        @(negedge mc);key[31:0]=key[31:0]+1'b1;epoch++;
        // Let stale FIFO contents drain under their original key.
        #150000;
    endtask
    integer worker_mhz,initial_rate,before_count,start_wet;
    initial begin
        if(!$value$plusargs("W_MHZ=%d",worker_mhz))worker_mhz=25;
        if(!$value$plusargs("RATE44=%d",initial_rate))initial_rate=0;
        fast=worker_mhz==50;rate=1'(initial_rate);
        #200;rst=1;#300;start_wet=wet_frames;
        for(integer n=0;n<2500;n++)sample(n);
        check(wet_frames-start_wet>2300,"sustained actual processed results");
        check(different>1200,"real wet contribution after delay history primes");
        check(overflows==0 && expired==0 && timeouts==0,"nominal asynchronous capacity");
        enable=0;for(integer n=0;n<70;n++)sample(n);
        enable=1;for(integer n=0;n<100;n++)sample(n);
        stop_up=1;for(integer n=0;n<100;n++)sample(n);
        check(overflows>0 && expired>0,"bounded request overflow and expiration");
        stop_up=0;for(integer n=0;n<100;n++)sample(n);
        stop_down=1;for(integer n=0;n<180;n++)sample(n);
        stop_down=0;for(integer n=0;n<180;n++)sample(n);
        check(rejected>0 && fallbacks>0,"late returns drain and dry fallback stays scheduled");
        admit=0;for(integer n=0;n<80;n++)sample(n);
        before_count=transported;admit=1;for(integer n=0;n<80;n++)sample(n);
        check(revoked && transported==before_count,"reconnect cannot reuse old key");
        fresh();for(integer n=0;n<100;n++)sample(n);
        clear=1;#500;clear=0;before_count=transported;
        for(integer n=0;n<80;n++)sample(n);
        check(revoked && transported==before_count,"PANIC cannot reuse old key");
        fresh();for(integer n=0;n<100;n++)sample(n);
        lease=0;#1000;lease=1;#100000;
        check(!claim && !wready,"lease loss requires a new key");
        fresh();for(integer n=0;n<100;n++)sample(n);
        // Revision, media, boot/session and sample-rate fences use the same
        // complete key/rate boundary; stale packets remain in both FIFOs.
        for(integer field=1;field<6;field++)begin
            @(negedge mc);key[field*32+:32]=key[field*32+:32]+1'b1;epoch++;
            for(integer n=0;n<80;n++)sample(n);
        end
        @(negedge mc);rate=!rate;key[31:0]++;epoch++;
        for(integer n=0;n<100;n++)sample(n);
        #100000;
        check(timeouts==0,"real engine meets its processing bound at both clocks");
        $display("REMOTE_EFFECT_RESULT {\"passed\":true,\"kind\":\"async_real_engine\",\"worker_mhz\":%0d,\"initial_rate44\":%0d,\"checks\":%0d,\"frames\":%0d,\"wet_frames\":%0d,\"wet_different\":%0d,\"engine_frames\":%0d,\"overflow\":%0d,\"expired\":%0d,\"fallback\":%0d,\"rejected\":%0d}",worker_mhz,initial_rate,checks,frames,wet_frames,different,engine_frames,overflows,expired,fallbacks,rejected);
        $finish;
    end
    initial begin #250000000;$fatal(1,"test timeout");end
endmodule
