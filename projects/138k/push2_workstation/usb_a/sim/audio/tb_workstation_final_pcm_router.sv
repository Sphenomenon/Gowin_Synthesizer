`timescale 1ns/1ps
module tb_workstation_final_pcm_router;
    reg clk=0,rst=0,request=0,rate=0,active_rate=0,scope=1,tf_active=1,mute=0;
    always #5 clk=!clk;
    reg [31:0] epoch=7,active_epoch=7,sequence_number=0,cancel_epoch=0,generation=1,expected_generation=1;
    reg [15:0] volume=32768;
    reg tf_valid=1,tf_error=0,render_ready=1,render_done=0,render_error=0;
    reg signed [15:0] tf_left=20000,tf_right=-12345;
    reg signed [31:0] render_left=32'h3456789a,render_right=32'h87654321;
    reg [19:0] tf_rate=48000;
    wire ready,tf_ready,render_request,render_rate,valid,error,frame_rate,source_tf,quiet;
    wire [31:0] frame_epoch,frame_sequence,pcm,rejected,underruns,mismatches,stale,cancelled,unexpected,clips;
    wire [7:0] errors;
    wire [15:0] gain;
    workstation_final_pcm_router dut(
        .clk_i(clk),.rst_ni(rst),.request_i(request),.request_44k1_i(rate),.request_epoch_i(epoch),
        .request_sequence_i(sequence_number),.request_ready_o(ready),.active_44k1_i(active_rate),
        .active_epoch_i(active_epoch),.cancel_epoch_i(cancel_epoch),.scope_enable_i(scope),.tf_active_i(tf_active),
        .master_volume_i(volume),.mute_i(mute),.tf_valid_i(tf_valid),.tf_error_i(tf_error),
        .tf_left_i(tf_left),.tf_right_i(tf_right),.tf_sample_rate_i(tf_rate),.tf_generation_i(generation),
        .expected_tf_generation_i(expected_generation),.tf_ready_o(tf_ready),
        .render_ready_i(render_ready),.render_done_i(render_done),.render_error_i(render_error),
        .render_left_i(render_left),.render_right_i(render_right),.render_request_o(render_request),.render_44k1_o(render_rate),
        .frame_valid_o(valid),.frame_error_o(error),.frame_44k1_o(frame_rate),.frame_source_tf_o(source_tf),
        .frame_epoch_o(frame_epoch),.frame_sequence_o(frame_sequence),.frame_pcm_o(pcm),.frame_error_bits_o(errors),
        .frame_gain_o(gain),.quiescent_o(quiet),.rejected_request_count_o(rejected),.tf_underrun_count_o(underruns),
        .rate_mismatch_count_o(mismatches),.stale_source_count_o(stale),.cancelled_frame_count_o(cancelled),
        .unexpected_render_count_o(unexpected),.clipped_frame_count_o(clips));
    integer accepted=0,responses=0,tf_consumed=0,cases=0;
    integer model_gain=0,model_remainder=73;
    reg pending=0;
    reg [64:0] identity;
    always @(posedge clk)if(rst)begin
        if(request && ready)begin
            if(pending)$fatal(1,"request identity overwrite");
            pending=1;accepted=accepted+1;identity={rate,epoch,sequence_number};
        end
        if(tf_ready && tf_valid)tf_consumed=tf_consumed+1;
        if(valid)begin
            if(!pending || {frame_rate,frame_epoch,frame_sequence}!==identity)$fatal(1,"response identity/duplication");
            pending=0;responses=responses+1;
        end
    end
    function automatic integer quant(input signed [31:0] value);
        reg signed [63:0] n;
        begin
            n=value;
            if(n>=0)n=(n+32768)/65536;
            else n=-((-n+32768)/65536);
            if(n>32767)n=32767;if(n< -32768)n=-32768;quant=32'(n);
        end
    endfunction
    function automatic [15:0] scaled(input integer value,input integer current_gain);
        reg signed [63:0] n;
        begin
            n=64'(value)*64'(current_gain);n=n>>>15;
            if(n>32767)n=32767;if(n< -32768)n=-32768;scaled=16'(n);
        end
    endfunction
    task automatic offer;
        integer target,step,total;
        begin
            @(negedge clk);while(!ready)@(negedge clk);
            target=mute ? 0:volume;
            total=40960+model_remainder;step=rate ? total/147:256;
            if(rate && target!=0)model_remainder=total%147;
            if(target==0)model_gain=0;
            else if(target>model_gain)model_gain=model_gain+((target-model_gain>step)?step:target-model_gain);
            else model_gain=model_gain-((model_gain-target>step)?step:model_gain-target);
            request=1;@(negedge clk);request=0;
        end
    endtask
    task automatic finish(input [7:0] expected_errors,input [31:0] expected_pcm,input bit tf_selected);
        integer n;
        begin
            n=0;while(!valid)begin @(negedge clk);n=n+1;if(n>50)$fatal(1,"bounded completion");end
            if(errors!==expected_errors || error!==(expected_errors!=0) || pcm!==expected_pcm ||
                source_tf!==tf_selected || gain!==16'(model_gain))
                $fatal(1,"case%0d result errors=%h/%h pcm=%h/%h source=%b gain=%0d/%0d",cases,errors,expected_errors,pcm,expected_pcm,source_tf,gain,model_gain);
            cases=cases+1;@(negedge clk);sequence_number=sequence_number+1;
        end
    endtask
    task automatic render_case(input signed [31:0] l,r);
        begin
            scope=1;render_left=l;render_right=r;offer();
            if(!render_request || render_rate!==rate)$fatal(1,"render request not issued");
            render_done=1;@(negedge clk);render_done=0;
            finish(0,{scaled(quant(l),model_gain),scaled(quant(r),model_gain)},0);
        end
    endtask
    task automatic tf_case;
        begin scope=0;offer();finish(0,{scaled(tf_left,model_gain),scaled(tf_right,model_gain)},1);end
    endtask
    reg [31:0] random_word=32'h4e2a1897;
    integer consumed_before,ramp48,ramp44;
    initial begin
        repeat(4)@(negedge clk);rst=1;
        // A reference model uses sign/magnitude rounding rather than the RTL
        // add/shift implementation; both signs and exact ties are checked.
        for(integer i=0;i<128;i=i+1)render_case(32'h40000000,32'h80000000);
        if(gain!=32768)$fatal(1,"legacy48 slew did not reach unity in128 slots");
        render_case(0,1);render_case(32767,-32767);render_case(32768,-32768);
        render_case(32769,-32769);render_case(98304,-98304);render_case(32'h7fffffff,32'h80000000);
        for(integer i=0;i<1024;i=i+1)begin
            random_word={random_word[30:0],random_word[31]^random_word[21]^random_word[1]^random_word[0]};
            volume=16'((i*997)%65536);render_case($signed(random_word),-$signed(random_word));
        end
        volume=0;render_case(32'h7fffffff,32'h80000000);
        if(pcm || gain)$fatal(1,"zero volume not immediate");
        volume=32768;rate=1;active_rate=1;active_epoch=8;epoch=8;tf_rate=44100;sequence_number=0;
        ramp44=0;while(model_gain<32768)begin tf_case();ramp44=ramp44+1;end
        if(ramp44!=118)$fatal(1,"44k1 slew physical time differs slots=%0d",ramp44);
        // Requested source and volume are frozen for an entire stereo frame.
        scope=1;offer();scope=0;volume=0;render_done=1;render_left=32'h40000000;render_right=-32'sh40000000;
        @(negedge clk);render_done=0;finish(0,{16'h4000,16'hc000},0);tf_case();
        volume=32768;mute=1;tf_case();if(pcm)$fatal(1,"mute not exact zero");mute=0;
        // Ready is sampled before the registered render request is visible.
        // If it closes on that next edge, valid must remain until accepted.
        scope=1;offer();render_ready=0;
        repeat(4)begin
            @(negedge clk);
            if(!render_request || valid || ready)$fatal(1,"registered request lost across render backpressure");
        end
        render_ready=1;@(negedge clk);
        if(render_request)$fatal(1,"accepted render request was repeated");
        render_left=32'h40000000;render_right=-32'sh40000000;render_done=1;
        @(negedge clk);render_done=0;
        finish(0,{scaled(quant(render_left),model_gain),scaled(quant(render_right),model_gain)},0);
        scope=0;
        consumed_before=tf_consumed;tf_rate=48000;offer();finish(8'h04,0,1);
        if(tf_consumed!=consumed_before)$fatal(1,"different-rate TF was consumed");
        tf_rate=44100;generation=0;offer();finish(8'h08,0,1);
        if(tf_consumed!=consumed_before)$fatal(1,"stale TF was consumed");generation=1;
        tf_valid=0;offer();finish(8'h02,0,1);tf_valid=1;tf_error=1;offer();finish(8'h01,0,1);tf_error=0;
        scope=1;render_ready=0;offer();finish(8'h20,0,0);render_ready=1;
        offer();render_error=1;render_done=1;@(negedge clk);render_done=0;render_error=0;finish(8'h01,0,0);
        offer();cancel_epoch=cancel_epoch+1;render_done=1;@(negedge clk);render_done=0;finish(8'h10,0,0);
        offer();active_epoch=9;render_done=1;@(negedge clk);render_done=0;finish(8'h10,0,0);epoch=9;
        scope=0;consumed_before=tf_consumed;epoch=8;offer();finish(8'h18,0,1);epoch=9;
        rate=0;offer();finish(8'h18,0,1);rate=1;
        if(tf_consumed!=consumed_before)$fatal(1,"old output identity consumed TF");
        offer();expected_generation=2;finish(8'h10,0,1);generation=2;scope=1;
        // A busy slot never overwrites the held tag; late results cannot be
        // assigned to the rejected request or a different selected source.
        offer();request=1;sequence_number=sequence_number+1;
        @(negedge clk);request=0;sequence_number=sequence_number-1;
        render_done=1;render_left=0;render_right=0;@(negedge clk);render_done=0;finish(0,0,0);
        render_done=1;@(negedge clk);render_done=0;repeat(3)@(negedge clk);
        if(rejected!=1 || unexpected!=1 || mismatches!=1 || underruns!=1 || stale!=3 || cancelled!=5 || clips==0)
            $fatal(1,"diagnostic counters did not preserve faults");
        if(accepted!=responses || pending)$fatal(1,"request ledger incomplete");
        $display("PASS final_pcm_router: cases=%0d accepted=%0d responses=%0d tf_consumed=%0d ramp44=%0d clipped=%0d",cases,accepted,responses,tf_consumed,ramp44,clips);
        $finish;
    end
    initial begin #10000000;$fatal(1,"timeout");end
endmodule
