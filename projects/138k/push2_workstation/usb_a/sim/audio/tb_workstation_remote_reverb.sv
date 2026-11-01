`timescale 1ns/1ps
module tb_workstation_remote_reverb;
    reg clk=0,rst=0;
    always #5 clk=~clk;
    reg clear=0,valid=0,enabled=1,config_valid=0,rate=0,history=0;
    reg signed [31:0] left_in=0,right_in=0;
    reg link_ready=0;
    reg [31:0] link_session=32'h11223344;
    reg block_request=0,drop_result=0,wrong_session=0,wrong_generation=0,wrong_sequence=0,wrong_rate=0,error_result=0;
    reg inject_valid=0;
    reg [31:0] inject_session=0,inject_generation=0,inject_sequence=0;
    reg inject_rate=0;
    wire ready,active,out_valid,clip,config_ready,config_applied,history_ready,history_done,quiet,applied_rate;
    wire signed [31:0] left_out,right_out;
    wire req_valid,req_ready,req_rate,req_enabled,req_reset_gain,rsp_valid,rsp_ready,rsp_rate,rsp_active,rsp_clip,rsp_error;
    wire [31:0] req_session,req_generation,req_sequence,rsp_session,rsp_generation,rsp_sequence;
    wire signed [31:0] req_left,req_right,rsp_left,rsp_right;
    wire [31:0] fallbacks,rejected,w_rejected,w_timeouts;
    wire ref_ready,ref_valid,ref_clip,ref_active,ref_cfg_ready,ref_cfg_applied;
    wire signed [31:0] ref_left,ref_right;
    reg watchdog_request=0,watchdog_pop=0;
    wire watchdog_ready,watchdog_result,watchdog_error;
    wire [31:0] watchdog_timeouts,watchdog_rejected;
    integer checked=0,wet_frames=0,fault_cases=0;
    workstation_remote_reverb_m #(.DEADLINE_CYCLES(512)) m(
        .clk_i(clk),.rst_ni(rst),.clear_i(clear),.valid_i(valid),.enabled_i(enabled),.left_i(left_in),.right_i(right_in),
        .ready_o(ready),.active_o(active),.valid_o(out_valid),.left_o(left_out),.right_o(right_out),.clip_o(clip),
        .config_valid_i(config_valid),.rate_44100_i(rate),.history_clear_i(history),.config_ready_o(config_ready),
        .config_applied_o(config_applied),.history_ready_o(history_ready),.history_done_o(history_done),
        .quiescent_o(quiet),.applied_rate_44100_o(applied_rate),.link_ready_i(link_ready),.link_session_i(link_session),
        .req_valid_o(req_valid),.req_ready_i(req_ready && !block_request),.req_session_o(req_session),
        .req_generation_o(req_generation),.req_sequence_o(req_sequence),.req_rate_44100_o(req_rate),
        .req_enabled_o(req_enabled),.req_reset_gain_o(req_reset_gain),.req_left_o(req_left),.req_right_o(req_right),
        .rsp_valid_i(rsp_valid && !drop_result),.rsp_ready_o(rsp_ready),
        .rsp_session_i(wrong_session ? rsp_session^32'h01000000 : rsp_session),
        .rsp_generation_i(wrong_generation ? rsp_generation^32'h00010000 : rsp_generation),
        .rsp_sequence_i(wrong_sequence ? rsp_sequence^32'h00000001 : rsp_sequence),
        .rsp_rate_44100_i(rsp_rate^wrong_rate),.rsp_active_i(rsp_active),.rsp_clip_i(rsp_clip),
        .rsp_error_i(rsp_error|error_result),.rsp_left_i(rsp_left),.rsp_right_i(rsp_right),
        .fallback_count_o(fallbacks),.rejected_count_o(rejected));
    workstation_remote_reverb_w w(
        .clk_i(clk),.rst_ni(rst),.link_ready_i(link_ready),.link_session_i(link_session),
        .req_valid_i((req_valid && !block_request) || inject_valid),.req_ready_o(req_ready),
        .req_session_i(inject_valid ? inject_session : req_session),
        .req_generation_i(inject_valid ? inject_generation : req_generation),
        .req_sequence_i(inject_valid ? inject_sequence : req_sequence),
        .req_rate_44100_i(inject_valid ? inject_rate : req_rate),.req_enabled_i(req_enabled),.req_reset_gain_i(req_reset_gain),.req_left_i(req_left),.req_right_i(req_right),
        .rsp_valid_o(rsp_valid),.rsp_ready_i(rsp_ready && !drop_result),
        .rsp_session_o(rsp_session),.rsp_generation_o(rsp_generation),.rsp_sequence_o(rsp_sequence),
        .rsp_rate_44100_o(rsp_rate),.rsp_active_o(rsp_active),.rsp_clip_o(rsp_clip),.rsp_error_o(rsp_error),
        .rsp_left_o(rsp_left),.rsp_right_o(rsp_right),.rejected_count_o(w_rejected),.timeout_count_o(w_timeouts));
    workstation_runtime_spatial_reverb reference_reverb(
        .clk_i(clk),.rst_ni(rst),.clear_i(clear),.valid_i(valid),.enabled_i(enabled),.left_i(left_in),.right_i(right_in),
        .ready_o(ref_ready),.active_o(ref_active),.valid_o(ref_valid),.left_o(ref_left),.right_o(ref_right),.clip_o(ref_clip),
        .config_valid_i(config_valid),.rate_44100_i(rate),.history_clear_i(history),
        .config_ready_o(ref_cfg_ready),.config_applied_o(ref_cfg_applied),.history_ready_o(),.history_done_o(),
        .quiescent_o(),.applied_rate_44100_o());
    // Deliberately impossible compute budget proves the W watchdog produces
    // a held failure result and retains replay fencing after engine reset.
    workstation_remote_reverb_w #(.PROCESS_TIMEOUT_CYCLES(8)) watchdog_worker(
        .clk_i(clk),.rst_ni(rst),.link_ready_i(1'b1),.link_session_i(32'hdeadbeef),
        .req_valid_i(watchdog_request),.req_ready_o(watchdog_ready),
        .req_session_i(32'hdeadbeef),.req_generation_i(32'd1),.req_sequence_i(32'd0),
        .req_rate_44100_i(1'b0),.req_enabled_i(1'b1),.req_reset_gain_i(1'b1),
        .req_left_i(32'sh12345678),.req_right_i(-32'sh23456789),
        .rsp_valid_o(watchdog_result),.rsp_ready_i(watchdog_pop),
        .rsp_session_o(),.rsp_generation_o(),.rsp_sequence_o(),.rsp_rate_44100_o(),
        .rsp_active_o(),.rsp_clip_o(),.rsp_error_o(watchdog_error),.rsp_left_o(),.rsp_right_o(),
        .rejected_count_o(watchdog_rejected),.timeout_count_o(watchdog_timeouts));
    task automatic tick;
        @(posedge clk);#1;
    endtask
    task automatic reset_case(input bit rate44);
        @(negedge clk);rst=0;valid=0;clear=0;config_valid=0;history=0;link_ready=0;
        block_request=0;drop_result=0;wrong_session=0;wrong_generation=0;wrong_sequence=0;wrong_rate=0;error_result=0;
        inject_valid=0;
        watchdog_request=0;watchdog_pop=0;
        enabled=1;repeat(4)tick();
        @(negedge clk);rst=1;link_ready=1;rate=rate44;
        repeat(3)tick();
        if(!config_ready || !ref_cfg_ready)$fatal(1,"configuration not ready");
        @(negedge clk);config_valid=1;tick();
        if(!config_applied || !ref_cfg_applied)$fatal(1,"bounded local config ACK absent");
        @(negedge clk);config_valid=0;repeat(3)tick();
        if(applied_rate!=rate44)$fatal(1,"local rate mismatch");
    endtask
    task automatic reject_request(input [31:0] sid,gen,seq,input bit rate44);
        reg [31:0] previous_rejected;
        integer n;
        begin
            while(!req_ready)tick();previous_rejected=w_rejected;
            @(negedge clk);inject_session=sid;inject_generation=gen;inject_sequence=seq;inject_rate=rate44;inject_valid=1;
            tick();@(negedge clk);inject_valid=0;
            for(n=0;n<300;n=n+1)begin tick();if(rsp_valid)$fatal(1,"stale/duplicate request revived W work");end
            if(w_rejected!=previous_rejected+1'b1)$fatal(1,"stale/duplicate request not counted");
            fault_cases++;
        end
    endtask
    // Compare a real W result to an independent local instance, not a mock.
    task automatic frame(input integer number,input bit fallback_expected);
        integer elapsed;
        reg have_ref;
        reg signed [31:0] saved_left,saved_right;
        reg saved_clip;
        begin
            while(!ready || !ref_ready)tick();
            @(negedge clk);
            left_in=number==0 ? 32'sh20001234 : number%257==0 ? -32'sh10005678 : 32'sd0;
            right_in=number==0 ? -32'sh08004321 : number%263==0 ? 32'sh10008765 : 32'sd0;
            valid=1;tick();
            @(negedge clk);valid=0;have_ref=0;elapsed=0;
            while(!out_valid && elapsed<520)begin
                tick();elapsed=elapsed+1;
                if(ref_valid)begin have_ref=1;saved_left=ref_left;saved_right=ref_right;saved_clip=ref_clip;end
            end
            if(elapsed!=512)$fatal(1,"variable/unbounded local deadline frame%0d elapsed%0d",number,elapsed);
            if(fallback_expected)begin
                if(left_out!==left_in || right_out!==right_in || clip!==0)
                    $fatal(1,"dry fallback changed precision");
            end else begin
                if(!have_ref || left_out!==saved_left || right_out!==saved_right || clip!==saved_clip)
                    $fatal(1,"real W mismatch frame%0d got%h/%h expected%h/%h have%0d",number,left_out,right_out,saved_left,saved_right,have_ref);
                if(left_out!=left_in || right_out!=right_in)wet_frames=wet_frames+1;
                checked=checked+1;
            end
            tick();
        end
    endtask
    task automatic cancellation(input bit use_history);
        integer n;
        begin
            while(!ready)tick();
            @(negedge clk);valid=1;left_in=32'sh12345678;right_in=-32'sh23456789;tick();
            @(negedge clk);valid=0;clear=1;tick();
            @(negedge clk);clear=0;
            for(n=0;n<520;n=n+1)begin tick();if(out_valid)$fatal(1,"PANIC leaked cancelled audio");end
            if(!quiet)$fatal(1,"PANIC not quiescent");
            if(use_history)begin
                while(!history_ready)tick();
                @(negedge clk);history=1;tick();if(!history_done)$fatal(1,"history local ACK missing");
                @(negedge clk);history=0;tick();
            end
        end
    endtask
    integer i,r;
    reg [31:0] saved_session,saved_generation,saved_sequence;
    initial begin
        // Config/history clear RAM validity but preserve the real wet slew.
        // The chain consults active before its next sample/maintenance call,
        // so checking only a post-clear zero-valued PCM frame misses this.
        reset_case(0);
        for(i=0;i<64;i=i+1)frame(i,0);
        enabled=0;tick();
        if(!active || active!==ref_active)$fatal(1,"wet slew not active before history");
        @(negedge clk);history=1;tick();
        if(!history_done || !active || active!==ref_active)
            $fatal(1,"normal history ACK lost active wet slew");
        @(negedge clk);history=0;repeat(3)tick();frame(64,0);
        @(negedge clk);rate=1;config_valid=1;tick();
        if(!config_applied || !active || active!==ref_active)
            $fatal(1,"normal rate ACK lost active wet slew");
        @(negedge clk);config_valid=0;repeat(3)tick();frame(65,0);
        for(r=0;r<2;r=r+1)begin
            reset_case(r!=0);
            for(i=0;i<6000;i=i+1)begin enabled=i<4800;frame(i,0);end
            if(fallbacks!=0 || rejected!=0 || w_timeouts!=0 || w_rejected!=0)$fatal(1,"healthy transport fault");
        end
        if(wet_frames<1000)$fatal(1,"comparison failed to exercise actual reverb wet history");
        reset_case(0);block_request=1;frame(0,1);if(fallbacks!=1)$fatal(1,"request backpressure missing fallback");fault_cases++;
        reset_case(0);drop_result=1;frame(0,1);
        if(req_ready || !rsp_valid)$fatal(1,"W result slot not held under backpressure");
        drop_result=0;repeat(4)tick();if(rejected!=1)$fatal(1,"late result not rejected");fault_cases++;
        reset_case(0);wrong_session=1;frame(0,1);if(rejected!=1)$fatal(1,"wrong session accepted");fault_cases++;
        reset_case(0);wrong_generation=1;frame(0,1);if(rejected!=1)$fatal(1,"wrong generation accepted");fault_cases++;
        reset_case(0);wrong_sequence=1;frame(0,1);if(rejected!=1)$fatal(1,"wrong sequence accepted");fault_cases++;
        reset_case(0);wrong_rate=1;frame(0,1);if(rejected!=1)$fatal(1,"wrong rate accepted");fault_cases++;
        reset_case(0);error_result=1;frame(0,1);if(rejected!=1)$fatal(1,"transport error accepted");fault_cases++;
        reset_case(0);link_ready=0;repeat(3)tick();frame(0,1);fault_cases++;
        reset_case(0);
        fork
            frame(0,1);
            begin repeat(200)tick();@(negedge clk);link_ready=0;end
        join
        if(fallbacks!=1)$fatal(1,"midframe disconnect retained cached remote audio");fault_cases++;
        reset_case(0);
        fork
            frame(0,1);
            begin repeat(200)tick();@(negedge clk);link_session=32'h99aabbcc;end
        join
        if(fallbacks!=1)$fatal(1,"midframe session fence retained cached remote audio");fault_cases++;
        reset_case(0);cancellation(1);frame(0,0);fault_cases++;
        // A locally ready rate change fences W history on its next frame.
        reset_case(0);frame(0,0);rate=1;
        @(negedge clk);config_valid=1;tick();
        if(!config_applied)$fatal(1,"rate local ACK missing");
        @(negedge clk);config_valid=0;repeat(3)tick();frame(0,0);fault_cases++;
        // Independent W link-session restart, no old RESULT replay.
        reset_case(0);frame(0,0);link_session=32'h55667788;
        @(negedge clk);clear=1;tick();@(negedge clk);clear=0;repeat(3)tick();frame(0,0);fault_cases++;
        // Reject replay before it reaches the real W engine; following valid
        // samples must still match the uninterrupted local history exactly.
        reset_case(0);for(i=0;i<3000;i=i+1)frame(i,0);
        saved_session=req_session;saved_generation=req_generation;saved_sequence=req_sequence;
        reject_request(saved_session,saved_generation,saved_sequence,0);
        frame(3000,0);
        reject_request(saved_session,saved_generation,saved_sequence-32'd1,0);
        frame(3001,0);
        reject_request(saved_session,saved_generation,req_sequence+32'd1,1);
        frame(3002,0);
        @(negedge clk);history=1;tick();if(!history_done)$fatal(1,"history ACK absent");
        @(negedge clk);history=0;repeat(3)tick();frame(3003,0);
        reject_request(saved_session,saved_generation,32'd99999,0);
        frame(3004,0);
        if(!watchdog_ready)$fatal(1,"watchdog test worker not ready");
        @(negedge clk);watchdog_request=1;tick();@(negedge clk);watchdog_request=0;
        for(i=0;i<16 && !watchdog_result;i=i+1)tick();
        if(!watchdog_result || !watchdog_error || watchdog_timeouts!=1)$fatal(1,"W work not bounded");
        repeat(4)begin tick();if(!watchdog_result || !watchdog_error)$fatal(1,"W failure result not held");end
        @(negedge clk);watchdog_pop=1;tick();@(negedge clk);watchdog_pop=0;tick();
        @(negedge clk);watchdog_request=1;tick();@(negedge clk);watchdog_request=0;repeat(20)tick();
        if(watchdog_rejected!=1 || watchdog_timeouts!=1 || watchdog_result)
            $fatal(1,"W timeout erased replay fence");
        fault_cases++;
        $display("REMOTE_REVERB_RESULT {\"passed\":true,\"exact_frames\":%0d,\"wet_frames\":%0d,\"fault_cases\":%0d,\"deadline_clocks\":512,\"rates_hz\":[48000,44100]}",checked,wet_frames,fault_cases);
        $finish;
    end
    initial begin #100000000;$fatal(1,"test timeout");end
endmodule
