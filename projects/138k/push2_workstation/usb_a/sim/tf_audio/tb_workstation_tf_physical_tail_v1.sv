`timescale 1ns/1ps
// Bounded endpoint protocol tests. Public tags are synthetic here; the separate
// native fixture proves real SPI/FAT/WAV/router/serializer/observation wiring.
module tb_workstation_tf_physical_tail_v1 #(
    parameter bit LOCAL_RESET=0
);
    reg rst=0,cc=0,sc=0,serial_run=1,compute_run=1;
    always #5 if(compute_run)cc=!cc;
    always #7 if(serial_run)sc=!sc;
    reg [1:0] compute_startup,serial_startup;
    reg [2:0] compute_release,serial_release;
    always @(posedge cc or negedge rst)
        if(!rst)begin compute_startup<=0;compute_release<=0;end
        else begin
            compute_startup<={compute_startup[0],rst};
            compute_release<=compute_startup[1] ? {compute_release[1:0],1'b1}:3'd0;
        end
    always @(posedge sc or negedge rst)
        if(!rst)begin serial_startup<=0;serial_release<=0;end
        else begin
            serial_startup<={serial_startup[0],rst};
            serial_release<=serial_startup[1] ? {serial_release[1:0],1'b1}:3'd0;
        end
    reg fence=0,arm=0,rate=0;
    reg [31:0] generation=3,session=7,epoch=11;
    wire ready,armed,pending,closed,admit,quiet,eos,cancelled,failed,busy;
    wire [3:0] code;
    wire [31:0] te,ts,baseline,prefix;
    reg fire=0,last=0,tf_error=0;
    reg [31:0] render_seq=0;
    reg router_valid=0,router_error=0,transport_error=0;
    reg [31:0] router_sequence=0;
    reg ov=0,oe=0,og=0,od=0;
    reg [31:0] os=0,oepoch=11;
    reg pv=0,pe=0;
    reg [31:0] ps=0,pepoch=11,drops=0;
    integer eos_count=0,cancel_count=0,tests=0;
    workstation_tf_physical_tail_v1 #(.SEPARATE_DOMAIN_RESET(LOCAL_RESET)) dut(
        .rst_ni(rst),.compute_clk_i(cc),.serial_clk_i(sc),.fence_i(fence),
        .compute_reset_ni(compute_release[2]),.serial_reset_ni(serial_release[2]),
        .arm_valid_i(arm),.arm_ready_o(ready),.arm_44k1_i(rate),
        .arm_generation_i(generation),.arm_session_i(session),.arm_epoch_i(epoch),
        .armed_o(armed),.tail_pending_o(pending),.tail_closed_o(closed),.tf_admit_o(admit),.quiescent_o(quiet),
        .tf_fire_i(fire),.tf_last_i(last),.tf_error_i(tf_error),.tf_44k1_i(rate),
        .tf_generation_i(generation),.tf_session_i(session),.render_epoch_i(epoch),.render_sequence_i(render_seq),
        .router_valid_i(router_valid),.router_error_i(router_error),.router_source_tf_i(1'b1),.router_44k1_i(rate),
        .router_epoch_i(epoch),.router_sequence_i(router_sequence),.transport_fault_i(transport_error),
        .observation_valid_i(ov),.observation_error_i(oe),.observation_44k1_i(rate),
        .observation_gap_i(og),.observation_drop_event_i(od),.observation_epoch_i(oepoch),.observation_sequence_i(os),
        .physical_valid_i(pv),.physical_error_i(pe),.physical_44k1_i(rate),
        .physical_epoch_i(pepoch),.physical_sequence_i(ps),.observation_source_drops_i(drops),
        .physical_eos_o(eos),.tail_cancelled_o(cancelled),.failed_o(failed),.failure_code_o(code),
        .tail_epoch_o(te),.tail_sequence_o(ts),.baseline_drops_o(baseline),.tail_drops_o(prefix),.mailbox_busy_o(busy));
    always @(posedge cc)begin
        if(eos)eos_count=eos_count+1;
        if(cancelled)cancel_count=cancel_count+1;
    end
    task cycles(input integer n);repeat(n)@(negedge cc);endtask
    task reset_case(input [31:0] count);
        begin
            @(negedge cc);rst=0;serial_run=1;fence=0;arm=0;fire=0;last=0;tf_error=0;
            router_valid=0;router_error=0;transport_error=0;ov=0;oe=0;og=0;od=0;pv=0;pe=0;
            drops=count;generation=3;session=7;epoch=11;oepoch=11;pepoch=11;rate=0;eos_count=0;cancel_count=0;
            cycles(4);rst=1;cycles(LOCAL_RESET ? 9:4);
        end
    endtask
    task arm_session;
        integer n;
        begin
            n=0;while(!ready && n<100)begin cycles(1);n=n+1;end
            if(!ready)$fatal(1,"arm ready timeout");
            arm=1;cycles(1);arm=0;n=0;
            while(!armed && !failed && n<100)begin cycles(1);n=n+1;end
            if(!armed || failed)$fatal(1,"arm failed code=%0d",code);
        end
    endtask
    task accept_frame(input [31:0] seq,input bit is_last);
        begin
            if(!admit)$fatal(1,"TF before real ARM acknowledgement");
            render_seq=seq;last=is_last;fire=1;cycles(1);fire=0;last=0;
        end
    endtask
    task observe(input [31:0] seq);
        begin os=seq;ov=1;cycles(1);ov=0;end
    endtask
    task physical(input [31:0] seq);
        begin @(negedge sc);ps=seq;pv=1;@(negedge sc);pv=0;end
    endtask
    task wait_token;
        // Covers request CDC and VALIDATE before a physical completion pulse.
        begin cycles(16);if(!busy)$fatal(1,"tail token retired before physical completion");end
    endtask
    task expect_success;
        integer n;
        begin
            n=0;while(eos_count==0 && n<100)begin cycles(1);n=n+1;end
            if(eos_count!=1 || failed || pending)$fatal(1,"missing successful physical EOS code=%0d",code);
            cycles(30);if(eos_count!=1)$fatal(1,"duplicate EOS");tests=tests+1;
        end
    endtask
    task expect_fail(input [3:0] expected);
        integer n;
        begin
            n=0;while(!failed && n<100)begin cycles(1);n=n+1;end
            if(!failed || code!=expected || eos_count!=0)$fatal(1,"expected failure %0d actual %0d eos=%0d",expected,code,eos_count);
            tests=tests+1;
        end
    endtask
    initial begin
        // A matching compute observation alone cannot stand in for serial
        // completion; wrong physical sequence and epoch cannot retire LAST.
        reset_case(0);arm_session();accept_frame(32'hffffffff,1);wait_token();observe(32'hffffffff);
        cycles(30);if(eos_count || failed)$fatal(1,"local/observation-only early EOS");
        physical(0);cycles(30);if(eos_count || failed)$fatal(1,"wrong sequence accepted");
        pepoch=epoch+1;physical(32'hffffffff);cycles(30);if(eos_count || failed)$fatal(1,"wrong epoch accepted");
        pepoch=epoch;physical(32'hffffffff);expect_success();
        // The reverse arrival order also needs both endpoints; wrapped zero is
        // an exact tail identity, independently of source FIFO/EOS timing.
        reset_case(9);rate=1;arm_session();accept_frame(32'hfffffffe,0);accept_frame(0,1);wait_token();physical(0);
        cycles(30);if(eos_count || failed)$fatal(1,"receipt-only early EOS");observe(0);expect_success();
        // Relevant router errors still classify as current across sequence wrap.
        reset_case(0);arm_session();accept_frame(32'hfffffffe,0);router_sequence=1;router_error=1;router_valid=1;
        cycles(1);router_valid=0;router_error=0;expect_fail(2);
        // Saturated ARM baseline must not authorize consumption.
        reset_case(32'hffffffff);arm=1;cycles(1);arm=0;expect_fail(6);if(armed || admit)$fatal(1,"saturated baseline armed");
        // Tail source-prefix loss, saturation and rollback each fail closed.
        reset_case(2);arm_session();accept_frame(5,1);wait_token();observe(5);drops=3;physical(5);expect_fail(6);
        reset_case(32'hfffffffe);arm_session();accept_frame(5,1);wait_token();observe(5);drops=32'hffffffff;physical(5);expect_fail(6);
        reset_case(32'hfffffffe);arm_session();accept_frame(5,1);wait_token();observe(5);drops=1;physical(5);expect_fail(6);
        // The watermark must include a drop registered on the physical edge.
        reset_case(0);arm_session();accept_frame(5,1);wait_token();observe(5);
        @(negedge sc);ps=5;pv=1;@(posedge sc);#1;drops=1;@(negedge sc);pv=0;expect_fail(6);
        reset_case(0);arm_session();accept_frame(5,1);wait_token();observe(5);pe=1;physical(5);expect_fail(5);
        reset_case(0);arm_session();accept_frame(5,1);oe=1;observe(5);oe=0;expect_fail(4);
        // Stop the actual serial clock with a pending tail. Cancellation must
        // withdraw success immediately, retain mailbox ownership until real
        // retirement, and reject a late old-session observation/completion.
        reset_case(4);arm_session();accept_frame(12,1);wait_token();
        @(negedge sc);serial_run=0;fence=1;cycles(1);fence=0;cycles(8);
        if(pending || armed || admit || !busy || quiet || cancel_count!=1)$fatal(1,"cancel erased pending mailbox or eligibility");
        observe(12);pv=1;ps=12;cycles(20);if(eos_count || ready || failed)$fatal(1,"stopped serial clock manufactured retirement");
        serial_run=1;cycles(40);pv=0;
        if(!quiet || busy || eos_count || failed)$fatal(1,"old reply affected cancelled session");
        generation=4;session=8;epoch=12;oepoch=12;pepoch=12;drops=6;
        arm_session();if(baseline!=6)$fatal(1,"new ARM reused old baseline");accept_frame(0,1);wait_token();observe(0);physical(0);expect_success();
        if(LOCAL_RESET)begin
            // A reset pulse shorter than either clock period still revokes
            // eligibility with both clocks stopped. Deassertion cannot act
            // as a clock edge or release either endpoint.
            @(negedge sc);serial_run=0;
            @(negedge cc);compute_run=0;
            #1;rst=0;eos_count=0;cancel_count=0;#1;
            if(armed || pending || admit || ready || eos || busy)$fatal(1,"short common reset did not assert asynchronously");
            rst=1;#50;
            if(ready || quiet || armed || eos || compute_release || serial_release)$fatal(1,"stopped clock manufactured reset release");
            compute_run=1;
            cycles(4);
            if(ready || quiet)$fatal(1,"compute reset bypassed local release chain");
            cycles(4);
            if(!ready || serial_release)$fatal(1,"compute release waits on remote clock");
            arm=1;cycles(1);arm=0;cycles(8);
            if(!busy || armed || eos || ready)$fatal(1,"ARM acknowledged with stopped serial clock");
            begin: held_when_stopped
                reg [161:0] saved;
                saved=dut.held_request;cycles(12);
                if(dut.held_request!==saved)$fatal(1,"outstanding token overwritten during stopped clock");
            end
            fence=1;cycles(1);fence=0;
            serial_run=1;
            repeat(4)@(posedge sc);#1;
            if(dut.reply_toggle!==0 || dut.serial_state!==0 || dut.request_sync!==0)
                $fatal(1,"serial state bypassed its local release chain");
            cycles(50);
            if(!quiet || busy || eos || failed)$fatal(1,"post-reset cancelled ARM did not drain");
            session=10;epoch=15;oepoch=15;pepoch=15;generation=5;drops=8;
            arm_session();accept_frame(1,1);wait_token();observe(1);physical(1);expect_success();
        end
        $display("PASS physical_tail_endpoint tests=%0d exact_sequence_wrap=1 saturation_rollback=1 stopped_serial_late_reply=1",tests);$finish;
    end
    initial begin #1000000;$fatal(1,"endpoint watchdog");end
endmodule
