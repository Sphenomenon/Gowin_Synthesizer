`timescale 1ns/1ps
module tb_workstation_i2s_source_hold;
    reg clk=0,rst_n=0,mode=0,hold_source=0,quiesce=1,resume_output=0;
    reg [31:0] epoch=17;
    real half_period=40.690;
    always begin #(half_period);clk=!clk;end
    wire quiet,running,prefill,request,request_mode,ready;
    wire [31:0] request_epoch,request_seq;
    reg valid=0;
    reg [31:0] sample_seq=0,sample_pcm=0;
    wire bck,lrck,sd,frame_valid,frame_error;
    wire [31:0] frame_pcm,frame_seq,underruns,rejected,source_errors;
    workstation_i2s_serializer #(.PDN_HOLD_FRAMES(1),.STARTUP_MUTE_FRAMES(3),
        .SAMPLE_ERROR_ENABLE(1),.SOURCE_HOLD_ENABLE(1)) dut(
        .clk_i(clk),.rst_ni(rst_n),.rate_44k1_i(mode),.epoch_i(epoch),
        .quiesce_i(quiesce),.resume_i(resume_output),.source_hold_i(hold_source),
        .serial_quiescent_o(quiet),.output_running_o(running),.prefill_ready_o(prefill),
        .request_o(request),.request_sequence_o(request_seq),.request_44k1_o(request_mode),
        .request_epoch_o(request_epoch),.sample_valid_i(valid),.sample_ready_o(ready),
        .sample_44k1_i(mode),.sample_error_i(1'b0),.sample_epoch_i(epoch),
        .sample_sequence_i(sample_seq),.sample_pcm_i(sample_pcm),
        .mclk_o(),.bck_o(bck),.lrck_o(lrck),.data_o(sd),.pdn_no(),.smute_o(),
        .frame_valid_o(frame_valid),.frame_error_o(frame_error),.frame_pcm_o(frame_pcm),
        .frame_sequence_o(frame_seq),.frame_44k1_o(),.frame_epoch_o(),
        .underrun_count_o(underruns),.rejected_sample_count_o(rejected),.source_error_count_o(source_errors));
    function automatic [31:0] pcm(input [31:0] seq,input integer generation);
        pcm={16'h6741 ^ seq[15:0] ^ 16'(generation*91),16'ha35e ^ seq[15:0] ^ 16'(generation*131)};
    endfunction
    integer generation=1,response_delay=0,pending_generation=0;
    integer requested_generation[0:4095];
    reg [31:0] pending_seq=0;
    reg drop_next=0;
    always @(negedge clk)begin
        valid=0;
        if(!rst_n)response_delay=0;
        else if(request)begin
            if(response_delay!=0 || request_mode!==mode || request_epoch!==epoch)
                $fatal(1,"source-hold request overlap/identity");
            if(hold_source)$fatal(1,"source-hold issued a new render");
            pending_seq=request_seq;pending_generation=generation;
            requested_generation[request_seq[11:0]]=generation;
            if(drop_next)begin drop_next=0;response_delay=0;end
            else response_delay=12;
        end else if(response_delay>1)response_delay=response_delay-1;
        else if(response_delay==1 && ready)begin
            valid=1;sample_seq=pending_seq;sample_pcm=pcm(pending_seq,pending_generation);
            response_delay=0;
        end
    end
    integer position=0,checked=0,good=0,errors=0,physical=0;
    reg [31:0] decoded=0,last_decoded=0;
    reg hold_first_complete=0,recovery_armed=0;
    realtime previous_bck=0,last_lrck_rise=0;
    always @(posedge bck)begin
        #0.1;
        if(rst_n)begin
            if(lrck!==(position>=32))$fatal(1,"source-hold LRCK slot");
            if(position>=1 && position<=16)decoded[32-position]=sd;
            else if(position>=33 && position<=48)decoded[48-position]=sd;
            else if(sd!==0)$fatal(1,"source-hold I2S padding");
            if(position==63)begin last_decoded=decoded;decoded=0;position=0;physical=physical+1;end
            else position=position+1;
        end
    end
    always @(bck)if(rst_n && dut.configured && $time>1)begin
        if(previous_bck!=0 &&
           (($realtime-previous_bck)<(mode ? 3.0:2.0)*2*half_period-0.01 ||
            ($realtime-previous_bck)>(mode ? 3.0:2.0)*2*half_period+0.01))
            $fatal(1,"source-hold stopped/changed BCK");
        previous_bck=$realtime;
    end
    always @(posedge lrck)if(rst_n)begin
        if(last_lrck_rise!=0 &&
           (($realtime-last_lrck_rise)<(mode ? 384.0:256.0)*2*half_period-0.01 ||
            ($realtime-last_lrck_rise)>(mode ? 384.0:256.0)*2*half_period+0.01))
            $fatal(1,"source-hold stopped/changed LRCK");
        last_lrck_rise=$realtime;
    end
    always @(posedge clk)begin
        #0.2;
        if(rst_n && hold_source && (running || prefill))$fatal(1,"source-hold exposed running/prefill");
        if(rst_n && frame_valid)begin
            if(frame_seq!==32'(checked) || frame_pcm!==last_decoded)
                $fatal(1,"source-hold sequence/tap diverged from physical pins");
            if(frame_error)begin
                if(frame_pcm!==0)$fatal(1,"source-hold error did not serialize zero");
                errors=errors+1;
            end else begin
                if(frame_pcm!==pcm(frame_seq,requested_generation[frame_seq[11:0]]))
                    $fatal(1,"source-hold corrupted PCM");
                if(recovery_armed && requested_generation[frame_seq[11:0]]!=generation)
                    $fatal(1,"source-hold replayed prefence PCM");
                good=good+1;
            end
            if(hold_source)begin
                if(hold_first_complete)hold_first_complete=0;
                else if(!frame_error)$fatal(1,"source-hold failed to publish cancelled zero/error slot");
            end
            checked=checked+1;
        end
    end
    task hold_at(input integer bit_phase);
        integer errors_before,checked_before,good_before;begin
        wait(position==bit_phase);@(negedge clk);#1;
        hold_first_complete=1;hold_source=1;recovery_armed=0;generation=generation+1;
        errors_before=errors;checked_before=checked;
        wait(checked>=checked_before+6);@(negedge clk);#1;
        if(errors<errors_before+5 || underruns!=0 || !hold_source)
            $fatal(1,"source-hold did not keep continuous explicit cancellation slots");
        hold_source=0;recovery_armed=1;good_before=good;
        wait(good>=good_before+5);@(negedge clk);#1;
        if(underruns!=0 || source_errors!=32'(errors))
            $fatal(1,"source-hold source errors/underruns not distinct u=%0d source=%0d errors=%0d",underruns,source_errors,errors);
    end endtask
    task run_mode(input bit target);
        integer good_before,errors_before;begin
        rst_n=0;hold_source=0;quiesce=1;resume_output=0;recovery_armed=0;drop_next=0;
        repeat(4)@(negedge clk);mode=target;epoch=target ? 18:17;half_period=target ? 29.526:40.690;
        position=0;checked=0;good=0;errors=0;physical=0;decoded=0;last_decoded=0;
        previous_bck=0;last_lrck_rise=0;generation=1;
        @(negedge clk);rst_n=1;repeat(2)@(negedge clk);quiesce=0;
        wait(prefill);@(negedge clk);resume_output=1;
        wait(good>=5);
        hold_at(3);hold_at(24);hold_at(51);
        // Genuine absent render remains a deadline underrun after recovery.
        good_before=good;errors_before=errors;@(negedge clk);#1;drop_next=1;
        wait(underruns==1);wait(errors==errors_before+1);wait(good>=good_before+5);
        @(negedge clk);#1;
        if(underruns!=1 || source_errors!=32'(errors-1))
            $fatal(1,"source hold hid real deadline underrun");
        $display("SOURCE_HOLD MODE %0d physical=%0d checked=%0d good=%0d zero_errors=%0d source_errors=%0d underruns=%0d",target,physical,checked,good,errors,source_errors,underruns);
        end
    endtask
    initial begin
        run_mode(0);run_mode(1);
        $display("PASS dual-rate source hold: continuous pins/slots, zero-error fences, new PCM recovery and distinct actual underrun");
        $finish;
    end
    initial begin #6000000;$fatal(1,"source-hold timeout");end
endmodule
