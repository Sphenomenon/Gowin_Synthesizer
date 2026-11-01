`timescale 1ns/1ps
// Actual link, actual CQT/six CNN layers/Viterbi, actual two CDC FIFOs and
// native DDR16 port. Small analysis dimensions test lifecycle, not accuracy.
module tb_bp_link_restart #(
    parameter bit DRAIN_ENABLE=1,
    parameter integer MAX_CYCLES=400000000
);
    localparam WIN_LEN=2048,FRAMES=2,TOTAL_SAMPLES=WIN_LEN+FRAMES*255+4096;
    reg clk=0,raw_mclk=0,rstn=0,mrstn=0,calibrated=0,memory_clock_run=1;
    wire mclk=raw_mclk && memory_clock_run;
    always #10 clk=~clk;
    always #7 raw_mclk=~raw_mclk;
    reg [19:0] pcm_rate=48000;
    reg restart=0,drive=0,allow_native=1,allow_response=1,source_clock_run=1;
    wire sclk=clk && source_clock_run;
    integer sent=0,cycles=0;
    reg [15:0] lfsr=16'hbeef;
    function automatic [15:0] lfsr_next(input [15:0] value);
        lfsr_next={value[14:0],value[15]^value[12]^value[10]^value[8]};
    endfunction
    wire pcm_ready;
    wire pcm_valid=drive && sent<TOTAL_SAMPLES;
    wire pcm_end=drive && sent>=TOTAL_SAMPLES;
    wire req,wr,ready,response;
    wire [28:0] addr;
    wire [255:0] data;
    wire [31:0] mask;
    reg [255:0] response_data=0;
    reg response_q=0;
    wire restart_ready,restart_busy,restart_done,restart_fault;
    wire [1:0] failure;
    wire score_valid,result_valid,analysis_done;
    wire [6:0] score_note;
    basic_pitch_workstation_link #(.DRAIN_RESTART_ENABLE(DRAIN_ENABLE),
        .RESTART_TIMEOUT_CYCLES(512)) dut(
        .clk_50m(sclk),.reset_n(rstn),.memory_clk(mclk),.memory_reset_n(mrstn),
        .memory_calibrated(calibrated),.model_serial(1'b1),.flash_miso(1'b1),
        .flash_cs_n(),.flash_clk(),.flash_mosi(),.analysis_enable(1'b1),
        .analysis_restart(restart),.pcm_valid(pcm_valid),.pcm_end(pcm_end),
        .pcm_left(lfsr_next(lfsr)),.pcm_right(lfsr_next(lfsr_next(lfsr))),.sample_rate(pcm_rate),
        .format_ready(1'b1),.source_active(drive),.hotplug_debug(11'd0),
        .pcm_ready(pcm_ready),.model_status(),.result_valid(result_valid),
        .result_note(),.result_frame(),.score_valid(score_valid),
        .score_ready(1'b1),.score_note(score_note),.analysis_done(analysis_done),
        .report_sending(),.report_serial(),.ddr_req(req),.ddr_write(wr),
        .ddr_address(addr),.ddr_data(data),.ddr_mask(mask),
        .ddr_ready(ready),.ddr_response(response),.ddr_read_data(response_data),
        .restart_ready_o(restart_ready),.restart_busy_o(restart_busy),
        .restart_done_o(restart_done),.restart_fault_o(restart_fault),
        .restart_failure_code_o(failure));

    function automatic integer gmap(input [11:0] g);
        case(g)
            12'h100:gmap=0;12'h101:gmap=1;12'h102:gmap=2;12'h103:gmap=3;
            12'h104:gmap=4;12'h105:gmap=5;12'h106:gmap=6;12'h107:gmap=7;
            12'h108:gmap=8;12'h304:gmap=9;12'h301:gmap=10;12'h302:gmap=11;
            12'h303:gmap=12;default:gmap=-1;
        endcase
    endfunction
    reg [15:0] mem[0:13*524288-1],blob[0:52238];
    integer native_cycles=0,read_timer=0,pending_index=0,native_writes=0,native_reads=0;
    integer k,lane,index;
    reg pending_read=0;
    // Jitter, write congestion and one delayed native read response.
    assign ready=rstn && mrstn && calibrated && allow_native &&
                 !pending_read && !response_q && native_cycles%11!=0;
    assign response=response_q;
    always @(posedge mclk)begin
        native_cycles<=native_cycles+1;
        response_q<=0;
        if(!rstn || !mrstn)begin pending_read<=0;read_timer<=0;end
        else begin
            if(req && ready)begin
                index=gmap({1'b0,addr[28:18]})*524288+{addr[17:3],4'b0000};
                if(gmap({1'b0,addr[28:18]})<0)$fatal(1,"invalid native address %h",addr);
                if(wr)begin
                    native_writes<=native_writes+1;
                    for(lane=0;lane<16;lane=lane+1)begin
                        if(!mask[2*lane])mem[index+lane][7:0]<=data[16*lane+:8];
                        if(!mask[2*lane+1])mem[index+lane][15:8]<=data[16*lane+8+:8];
                    end
                end else begin
                    native_reads<=native_reads+1;
                    pending_read<=1;pending_index<=index;
                    read_timer<=3+native_cycles%7;
                end
            end
            if(pending_read && allow_response)begin
                if(read_timer>0)read_timer<=read_timer-1;
                else begin
                    for(lane=0;lane<16;lane=lane+1)
                        response_data[16*lane+:16]<=mem[pending_index+lane];
                    response_q<=1;pending_read<=0;
                end
            end
        end
    end
    // Model is preloaded exactly as in the existing real-model A/B test.
    // UART/flash boot acceptance is separately covered by test_cnn_flash_boot.
    always @(posedge sclk)if(rstn)
        dut.u_basic_pitch.g_model_boot.g_uart.u_model_loader.state=4'd14;
    integer notes=0,writes[0:5];
    reg [6:0] note_sequence[0:31];
    reg measure=0;
    always @(posedge sclk)begin
        if(rstn)begin
            cycles<=cycles+1;
            if(cycles>MAX_CYCLES)$fatal(1,"simulation timeout progress=%h",dut.debug_progress);
            if(pcm_valid && pcm_ready)begin
                sent<=sent+1;
                lfsr<=lfsr_next(lfsr_next(lfsr));
            end
            if(measure)begin
                if(score_valid)begin note_sequence[notes]<=score_note;notes<=notes+1;end
                if(dut.u_basic_pitch.contour_act_valid)writes[0]<=writes[0]+1;
                if(dut.u_basic_pitch.reduce_act_valid)writes[1]<=writes[1]+1;
                if(dut.u_basic_pitch.notes_act_valid)writes[2]<=writes[2]+1;
                if(dut.u_basic_pitch.note_out_act_valid)writes[3]<=writes[3]+1;
                if(dut.u_basic_pitch.onset_act_valid)writes[4]<=writes[4]+1;
                if(dut.u_basic_pitch.onset_out_act_valid)writes[5]<=writes[5]+1;
            end
        end
    end
    wire [15:0] accepted_writes,committed_writes;
    generate if(DRAIN_ENABLE)begin:g_assertions
        assign accepted_writes=dut.g_drain_restart.writes_accepted;
        assign committed_writes=dut.g_drain_restart.committed_sync;
        always @(negedge sclk)if(rstn)begin
            if(restart_busy || restart_fault || (restart && dut.g_drain_restart.armed))begin
                if(pcm_ready || score_valid || result_valid || analysis_done || dut.bp_mem_ready)
                    $fatal(1,"task I/O leaked while cancel/fault");
            end
            if(dut.pipeline_restart && !dut.g_drain_restart.drained)
                $fatal(1,"pipeline reset before actual DDR drain");
            if(restart_done && (pending_read || dut.u_ddr16.read_pending ||
                               dut.ddr_fifo_valid || dut.ddr_cmd_valid || dut.ddr_rsp_fifo_valid))
                $fatal(1,"restart done with stale transport state");
        end
    end else begin:g_default_assertions
        assign accepted_writes=0;
        assign committed_writes=0;
        always @(negedge sclk)if(rstn)begin
            if(dut.pipeline_restart!==restart || !dut.task_io_enable || !dut.request_admit ||
               restart_busy || restart_fault || !restart_ready || restart_done!==restart)
                $fatal(1,"default restart compatibility changed");
        end
    end endgenerate
    task start_pcm;
        begin
            @(negedge clk);sent=0;lfsr=16'hbeef;drive=1;
        end
    endtask
    task cancel_now;
        begin
            @(negedge clk);restart=1;
            #1;if(pcm_ready || dut.bp_mem_ready || result_valid || score_valid || analysis_done)
                $fatal(1,"cancel did not immediately fence task I/O");
        end
    endtask
    task finish_cancel(input integer case_number);
        integer waited;
        begin
            waited=0;
            while(!restart_done && !restart_fault && waited<600)begin
                @(negedge clk);waited=waited+1;
            end
            if(!restart_done || restart_fault)$fatal(1,"cancel %0d failed code=%0d",case_number,failure);
            // Holding request high must not restart again or pulse done again.
            drive=0;
            repeat(4)@(negedge clk);
            if(restart_busy || restart_done)$fatal(1,"held cancel request retriggered");
            restart=0;repeat(4)@(negedge clk);
            if(!restart_ready)$fatal(1,"cancel did not rearm");
            $display("CASE %0d drain PASS clocks=%0d",case_number,waited);$fflush();
        end
    endtask
    task global_reset;
        begin
            @(negedge clk);drive=0;restart=0;rstn=0;mrstn=0;calibrated=0;
            allow_native=1;allow_response=1;memory_clock_run=1;pcm_rate=48000;
            repeat(8)@(negedge clk);
            rstn=1;mrstn=1;calibrated=1;
            repeat(8)@(negedge clk);
        end
    endtask
    integer j;
    initial begin
        for(j=0;j<13*524288;j=j+1)mem[j]=0;
        $readmemh("rtl/music/weights/cnn_ddr_blob.mem",blob);
        for(j=0;j<52239;j=j+1)mem[524288+j]=blob[j];
        for(j=0;j<6;j=j+1)writes[j]=0;
        global_reset();
        if(DRAIN_ENABLE)begin
            // Source FIFO/command-buffer write cannot be discarded on cancel.
            start_pcm();wait(dut.bp_mem_req && dut.bp_mem_write);allow_native=0;
            wait(accepted_writes!=committed_writes);
            cancel_now();repeat(20)@(negedge clk);
            if(dut.pipeline_restart || restart_done)$fatal(1,"queued write discarded");
            allow_native=1;finish_cancel(1);

            // Native read is accepted but its delayed response is outstanding.
            pcm_rate=44100;allow_response=0;start_pcm();wait(pending_read && dut.converted_valid);
            cancel_now();repeat(20)@(negedge clk);
            if(dut.pipeline_restart || restart_done)$fatal(1,"pending read discarded");
            if(!dut.converted_valid)$fatal(1,"cancel silently consumed queued 44.1k PCM");
            allow_response=1;finish_cancel(2);
            if(dut.converted_valid || dut.u_44100_to_48000.phase!=0)
                $fatal(1,"delayed restart failed to clear 44.1k converter");
            pcm_rate=48000;

            // Pause source clock with a response inside the real response CDC.
            allow_response=0;start_pcm();wait(pending_read);
            cancel_now();@(negedge clk);source_clock_run=0;allow_response=1;
            wait(dut.u_ddr_rsp_cdc.write_binary!=dut.u_ddr_rsp_cdc.read_binary);
            repeat(8)@(negedge clk);
            if(dut.pipeline_restart || restart_done)$fatal(1,"response CDC discarded");
            source_clock_run=1;finish_cancel(3);
        end
        // Fresh task after three cancelled jobs must match the default build
        // running the same real model, PCM and native-memory behavior.
        measure=1;start_pcm();wait(dut.bp_done);
        repeat(20000)@(negedge clk);
        drive=0;measure=0;
        if(notes<1)$fatal(1,"no real Viterbi score");
        for(j=0;j<6;j=j+1)if(writes[j]==0 || dut.layer_hashes[j*32+:32]==0)
            $fatal(1,"CNN layer %0d did not compute",j);
        $display("INFERENCE hashes=%048h notes=%0d",dut.layer_hashes,notes);
        for(j=0;j<notes;j=j+1)$display("NOTE %0d %0d",j,note_sequence[j]);
        for(j=0;j<6;j=j+1)$display("LAYER %0d writes=%0d",j,writes[j]);
        $fflush();
        if(DRAIN_ENABLE)begin
            // Never claim an empty transport when a native response is lost.
            global_reset();allow_response=0;start_pcm();wait(pending_read);
            cancel_now();wait(restart_fault);@(negedge clk);
            if(failure!=1 || restart_done)$fatal(1,"missing sticky drain timeout");
            allow_response=1;restart=0;
            repeat(600)@(negedge clk);
            if(!restart_fault || restart_done || restart_ready)$fatal(1,"timeout escaped quarantine");
            $display("CASE 4 timeout PASS");
            // Local memory reset and calibration loss fault instead of
            // resetting the write ledger to an apparently empty transport.
            global_reset();start_pcm();wait(dut.bp_mem_req && dut.bp_mem_write);allow_native=0;
            wait(accepted_writes!=committed_writes);
            cancel_now();@(negedge mclk);mrstn=0;
            repeat(8)@(negedge clk);mrstn=1;allow_native=1;
            repeat(20)@(negedge clk);
            if(!restart_fault || failure!=2 || restart_done)$fatal(1,"memory reset falsely drained");
            $display("CASE 5 memory reset PASS");
            global_reset();@(negedge mclk);calibrated=0;
            repeat(8)@(negedge clk);calibrated=1;
            repeat(20)@(negedge clk);
            if(!restart_fault || failure!=2 || restart_done)$fatal(1,"calibration loss falsely drained");
            $display("CASE 6 calibration loss PASS");
            global_reset();@(negedge raw_mclk);memory_clock_run=0;mrstn=0;
            repeat(8)@(negedge clk);
            if(!restart_fault || failure!=2 || restart_done || pcm_ready)
                $fatal(1,"stopped memory clock prevented reset-loss quarantine");
            @(negedge raw_mclk);memory_clock_run=1;mrstn=1;
            repeat(20)@(negedge clk);
            if(!restart_fault || restart_done)$fatal(1,"memory clock resume escaped quarantine");
            $display("CASE 7 stopped memory clock PASS");
            for(j=0;j<52239;j=j+1)if(mem[524288+j]!==blob[j])
                $fatal(1,"real model changed at %0d",j);
        end else begin
            @(negedge clk);restart=1;repeat(3)@(negedge clk);restart=0;
        end
        $display("PASS actual Basic Pitch link restart enabled=%0d cycles=%0d native_reads=%0d native_writes=%0d",
                 DRAIN_ENABLE,cycles,native_reads,native_writes);
        $finish;
    end
endmodule
