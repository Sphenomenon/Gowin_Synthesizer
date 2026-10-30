`timescale 1ns/1ps
module tb_workstation_tf_direct_ingress;
    reg clk=0;always #5 clk=~clk;
    reg rst=0,start=0,cancel=0,pause=0;
    reg [31:0] generation=32'hffffffff;
    reg [19:0] rate=48000;
    reg sector_start=0,byte_valid=0,file_eof=0,file_error=0;
    reg [7:0] byte_data=0;
    wire allow,valid,last,active,prefill,eos,drained,empty,failed;
    wire [15:0] left_pcm,right_pcm;
    wire [3:0] failure,file_failure;
    wire [31:0] byte_level,pcm_level,byte_max,pcm_max,output_generation;
    wire [19:0] output_rate,file_rate;
    wire [5:0] bits;
    wire format_ready,stereo;
    integer cycles=0,deadlines=0,received=0,transfers=0,launches=0,checks=0;
    integer length,frames,mode,expected_fail,expected_rate,source_limit;
    integer ready_hold=0,abort_source=0;
    wire tick=(cycles%17==0);
    wire sample_request=tick && !ready_hold;
    wire ready=sample_request;
    reg [7:0] bytes[0:200000];
    reg [31:0] oracle[0:20000];
    reg [2047:0] input_path,oracle_path;
    workstation_tf_direct_ingress_v1 dut(
        .clk_i(clk),.rst_ni(rst),.start_i(start),.cancel_i(cancel),.pause_i(pause),
        .generation_i(generation),.expected_rate_i(rate),.data_sector_start_i(sector_start),.sector_allow_o(allow),
        .file_byte_valid_i(byte_valid),.file_byte_i(byte_data),.file_eof_i(file_eof),.file_error_i(file_error),.file_error_code_i(4'd3),
        .sample_request_i(sample_request),.pcm_valid_o(valid),.pcm_ready_i(ready),.pcm_left_o(left_pcm),.pcm_right_o(right_pcm),.pcm_last_o(last),
        .generation_o(output_generation),.session_rate_o(output_rate),.active_o(active),.prefill_ready_o(prefill),.decoded_eos_o(eos),
        .local_tail_drained_o(drained),.empty_o(empty),.failed_o(failed),.failure_code_o(failure),.file_failure_code_o(file_failure),
        .byte_level_o(byte_level),.pcm_level_o(pcm_level),.byte_high_water_o(byte_max),.pcm_high_water_o(pcm_max),
        .format_ready_o(format_ready),.file_rate_o(file_rate),.file_bits_o(bits),.file_stereo_o(stereo));
    reg previous_stall=0,previous_byte_stall=0,first_transfer=1;
    reg [7:0] previous_byte;
    reg [32:0] previous_pair;
    always @(posedge clk)begin
        cycles<=cycles+1;
        if(rst)begin
            if(sample_request)deadlines=deadlines+1;
            if(start && !cancel)begin received=0;first_transfer=1;end
            if(previous_byte_stall && !start && !cancel && !failed)
                if(!dut.byte_held_valid || dut.byte_held!==previous_byte)$fatal(1,"decoder byte changed while ready low");
            previous_byte_stall=dut.byte_held_valid && !dut.decoder_ready;previous_byte=dut.byte_held;
            if(previous_stall && !start && !cancel && !pause && !failed)
                if(!valid || {last,right_pcm,left_pcm}!==previous_pair)$fatal(1,"held PCM changed under backpressure");
            previous_stall=valid && !ready && !pause;
            previous_pair={last,right_pcm,left_pcm};
            if(valid && ready)begin
                if(first_transfer && pcm_level<3072 && !eos)$fatal(1,"prefill released before threshold or real EOS");
                first_transfer=0;
                if(received>=frames)$fatal(1,"extra PCM");
                if({right_pcm,left_pcm}!==oracle[received])$fatal(1,"PCM oracle index=%0d got=%08x expected=%08x",received,{right_pcm,left_pcm},oracle[received]);
                if(last !== (received==frames-1))$fatal(1,"ordered PCM last index=%0d",received);
                if(output_generation!==generation || output_rate!==rate)$fatal(1,"session identity changed");
                received=received+1;transfers=transfers+1;
            end
            if(byte_level>4096 || pcm_level>4096)$fatal(1,"bounded capacity exceeded");
            if(sector_start && allow)begin
                if(byte_level>3582)$fatal(1,"sector was not fully reserved with margin");
                launches=launches+1;
            end
        end
    end
    task check(input reg ok,input string message);begin checks=checks+1;if(!ok)$fatal(1,"%s",message);end endtask
    task clocks(input integer n);begin repeat(n)@(negedge clk);end endtask
    task launch_session;begin
        @(negedge clk);start=1;clocks(1);start=0;clocks(2);
        check((!failed || ((rate!=48000 && rate!=44100) && failure==5) || (mode==7 && failure==1)) && output_generation==generation && output_rate==rate,"new session snapshot");
    end endtask
    task send_file(input integer count,input integer send_eof);
        integer i;
        begin : sending
            for(i=0;i<count;i=i+1)begin
                if(abort_source || failed)disable sending;
                if(i%512==0)begin
                    byte_valid=0;
                    while(!allow && !failed && !abort_source)@(negedge clk);
                    if(failed || abort_source)disable sending;
                    sector_start=1;@(negedge clk);sector_start=0;
                end
                byte_valid=1;byte_data=bytes[i];@(negedge clk);
            end
            byte_valid=0;sector_start=0;
            if(send_eof!=0)begin clocks(5);file_eof=1;clocks(1);file_eof=0;end
        end
    endtask
    task complete_success;integer before_ticks,timeout;begin
        for(timeout=0;timeout<frames*20+20000 && !drained && !failed;timeout=timeout+1)clocks(1);
        clocks(4);
        check(!failed && eos && drained && received==frames,"valid file did not drain exact oracle");
        check((frames==0)==empty,"empty data status");
        before_ticks=deadlines;clocks(100);
        check(!failed && !valid && deadlines>before_ticks,"post-last requests misreported underrun or stopped deadline clock");
    end endtask
    integer saved_received,saved_ticks,i;
    initial begin
        if(!$value$plusargs("input=%s",input_path) || !$value$plusargs("oracle=%s",oracle_path) ||
           !$value$plusargs("length=%d",length) || !$value$plusargs("frames=%d",frames) ||
           !$value$plusargs("rate=%d",expected_rate) || !$value$plusargs("mode=%d",mode) ||
           !$value$plusargs("failure=%d",expected_fail))$fatal(1,"missing test arguments");
        if(length!=0)$readmemh(input_path,bytes,0,length-1);
        if(frames!=0)$readmemh(oracle_path,oracle,0,frames-1);
        rate=20'(expected_rate);clocks(4);rst=1;if(mode==7)file_error=1;launch_session();
        case(mode)
        0:begin
            send_file(length,1);
            if(expected_fail==0)complete_success();
            else begin clocks(5000);check(failed && failure==expected_fail,"malformed/rate failure code");clocks(30);check(failed && !valid && !allow,"failure was not sticky");end
        end
        1:begin
            fork
                send_file(length,1);
                begin
                    wait(received>=5);@(negedge clk);pause=1;saved_received=received;saved_ticks=deadlines;
                    clocks(22000);check(received==saved_received && !failed && deadlines>saved_ticks,"pause consumed head or stopped sample schedule");
                    check(pcm_max==4096 && byte_max>3000 && !allow,"bounded PCM/byte backpressure not exercised");
                    pause=0;
                end
            join
            complete_success();
        end
        2:begin
            fork
                send_file(length,0);
                begin wait(received>=5);clocks(4);cancel=1;abort_source=1;clocks(2);end
            join
            byte_valid=0;sector_start=0;check(!valid && !allow,"cancel did not revoke output/admission");
            cancel=0;
            // Late events while inactive cannot enter a new decoder session.
            byte_valid=1;byte_data=8'hde;clocks(12);byte_valid=0;
            start=1;cancel=1;file_error=1;clocks(1);check(!active && !allow && !failed,"cancel did not win simultaneous start/error");start=0;cancel=0;file_error=0;
            generation=0;abort_source=0;launch_session();send_file(length,1);complete_success();
        end
        3:begin
            send_file(32768,0);clocks(80000);check(failed && failure==6,"true exhausted PCM did not latch underrun");
            saved_received=received;saved_ticks=deadlines;byte_valid=1;byte_data=8'h81;clocks(100);byte_valid=0;
            check(failed && received==saved_received && deadlines>saved_ticks && !allow,"failed stream auto-revived or stopped schedule");
            generation=32'd22;launch_session();send_file(length,1);complete_success();
        end
        4:begin
            ready_hold=1;
            fork
                send_file(length,0);
                begin wait(byte_level>3500 && !allow);abort_source=1;end
            join
            byte_valid=0;sector_start=0;clocks(4);check(!allow && !failed,"full-sector guard not exercised");
            sector_start=1;clocks(1);sector_start=0;wait(failed);check(failure==2,"unreserved sector was not rejected");
        end
        7:begin
            check(failed && failure==1 && file_failure==3 && !allow && !active,"start ignored simultaneous file failure");
            file_error=0;clocks(30);check(failed && !allow,"file failure cleared without explicit start");
        end
        6:begin
            ready_hold=1;
            fork
                send_file(length,0);
                begin wait(byte_level>3500 && !allow);abort_source=1;end
            join
            byte_valid=0;sector_start=0;clocks(4);
            // Explicit corruption of the reservation ledger exercises the
            // independent overflow fence; honest owner admission cannot do this.
            force dut.reserved_bytes=10'd512;
            byte_valid=1;byte_data=0;
            for(i=0;i<600 && !failed;i=i+1)clocks(1);
            byte_valid=0;release dut.reserved_bytes;clocks(2);
            check(failed && failure==3,"byte overflow did not fail closed");
        end
        5:begin
            file_error=1;clocks(1);file_error=0;clocks(1);
            check(failed && failure==1 && file_failure==3,"file owner failure was not preserved");
        end
        default:$fatal(1,"unknown mode");
        endcase
        $display("PASS direct_ingress mode=%0d frames=%0d transfers=%0d sectors=%0d checks=%0d deadlines=%0d byte_high=%0d pcm_high=%0d failure=%0d",mode,frames,transfers,launches,checks,deadlines,byte_max,pcm_max,failure);
        $finish;
    end
    initial begin #50000000;$fatal(1,"direct ingress watchdog mode=%0d received=%0d live=%0d failed=%0d code=%0d bytes=%0d pcm=%0d parser=%0d",mode,received,dut.live,failed,failure,byte_level,pcm_level,dut.decoder.u_parser.st);end
endmodule
