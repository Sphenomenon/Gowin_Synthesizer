`timescale 1ns/1ps
module tb_workstation_tf_runtime_clear #(parameter integer USE_COMMAND_BUFFER=0);
    tb_workstation_tf_runtime_service #(.USE_COMMAND_BUFFER(USE_COMMAND_BUFFER),.RUN_SCENARIOS(0)) f();
    integer cases=0,paused_high=0,paused_low=0,first_capture=0,first_playback=0;
    integer ack_changes=0,nonunit_zero=0,token_changes=0,analysis_restarts=0;
    reg capture_first_pending=1,playback_first_pending=1;
    reg previous_token=0,pre_token,pre_clear_done;
    reg [3:0] previous_path_track=0;
    reg [12:0] previous_cwr=0,previous_crd=0,previous_pwr=0,previous_prd=0;
    reg [3:0] previous_ack=0;
    function integer ones(input [12:0] value);integer i;begin ones=0;for(i=0;i<13;i=i+1)ones=ones+value[i];end endfunction
    always @(posedge f.source_clk)begin
        pre_token=f.dut.path_clear_toggle;pre_clear_done=f.dut.path_clear_done;
        if(f.rst_n)begin
            if(f.dut.path.soft_restart && !f.dut.path_restart)$fatal(1,"track/fault bypassed controlled restart");
            if(f.dut.path.g_runtime_capture.u_capture_fifo.wr_en && !f.dut.path.in_full && capture_first_pending)begin
                if(f.dut.path.file_byte!==8'h52)$fatal(1,"new capture did not begin at RIFF byte");
                capture_first_pending=0;first_capture=first_capture+1;
            end
            if(f.dut.path.g_runtime_capture.u_capture_fifo.wr_clear_ack_o!=previous_ack[0])begin
                if(f.dut.path.runtime_capture_wr_ack!=f.dut.path_clear_toggle ||
                   f.dut.path.g_runtime_capture.u_capture_fifo.clear_wr_sync!=f.dut.path_clear_toggle)$fatal(1,"capture writer ACK did not bind current token");
                if(f.dut.path.g_runtime_capture.u_capture_fifo.wr_bin!=0 ||
                   f.dut.path.g_runtime_capture.u_capture_fifo.rd_gray_w2!=0)$fatal(1,"capture writer ACK before zero proof");
                ack_changes=ack_changes+1;
            end
            if(f.dut.path.g_runtime_playback.u_playback_fifo.rd_clear_ack_o!=previous_ack[3])begin
                if(f.dut.path.runtime_playback_rd_ack!=f.dut.path_clear_toggle ||
                   f.dut.path.g_runtime_playback.u_playback_fifo.clear_rd_sync!=f.dut.path_clear_toggle)$fatal(1,"playback reader ACK did not bind current token");
                if(f.dut.path.g_runtime_playback.u_playback_fifo.rd_bin!=0 || f.dut.path.out_rd_valid ||
                   f.dut.path.g_runtime_playback.u_playback_fifo.wr_gray_r2!=0)$fatal(1,"playback reader ACK before zero proof");
                ack_changes=ack_changes+1;
            end
            previous_ack[0]=f.dut.path.runtime_capture_wr_ack;previous_ack[3]=f.dut.path.runtime_playback_rd_ack;
            if((ones(previous_cwr^f.dut.path.g_runtime_capture.u_capture_fifo.wr_gray)>1 ||
                ones(previous_prd^f.dut.path.g_runtime_playback.u_playback_fifo.rd_gray)>1) &&
                (!f.dut.path.native_source_hold || f.dut.path_clear_done))$fatal(1,"source pointer nonunit jump escaped clear isolation");
            if(previous_cwr!=0 && f.dut.path.g_runtime_capture.u_capture_fifo.wr_gray==0 && ones(previous_cwr)>1)nonunit_zero=nonunit_zero+1;
            if(previous_prd!=0 && f.dut.path.g_runtime_playback.u_playback_fifo.rd_gray==0 && ones(previous_prd)>1)nonunit_zero=nonunit_zero+1;
            previous_cwr=f.dut.path.g_runtime_capture.u_capture_fifo.wr_gray;previous_prd=f.dut.path.g_runtime_playback.u_playback_fifo.rd_gray;
        end
        #0.001;
        if(f.rst_n && f.dut.path_clear_toggle!=pre_token)begin
            if(!pre_clear_done || !f.dut.memory_gate || f.dut.memory_read_pending)$fatal(1,"new token before previous ACK/read drain");
            capture_first_pending=1;playback_first_pending=1;token_changes=token_changes+1;
        end
        if(f.rst_n && f.dut.path_track!=previous_path_track && !f.dut.path_restart)$fatal(1,"track snapshot changed outside controlled restart");
        previous_path_track=f.dut.path_track;previous_token=f.dut.path_clear_toggle;
    end
    always @(posedge f.memory_clk)if(f.rst_n)begin
        if(f.dut.path.out_wr_en && !f.dut.path.out_full)begin
            if(f.dut.memory_gate || !f.dut.path_clear_done)$fatal(1,"FIFO emitted before all clear ACKs");
            if(playback_first_pending)begin
                if(f.dut.path.out_wr_data!==8'h52)$fatal(1,"old byte preceded new playback RIFF");
                playback_first_pending=0;first_playback=first_playback+1;
            end
        end
        if(f.dut.path.g_runtime_dma.u_dma.restart_event && f.dut.path.out_wr_en)$fatal(1,"old private buffer emitted on restart");
        if(!f.dut.memory_gate && f.dut.path.g_runtime_dma.u_dma.restart_seen!=f.dut.path_clear_toggle)
            $fatal(1,"gate reopened before DMA processed token");
        if(f.dut.path.runtime_capture_rd_ack!=previous_ack[1])begin
            if(f.dut.path.runtime_capture_rd_ack!=f.dut.path_clear_toggle ||
               f.dut.path.g_runtime_capture.u_capture_fifo.clear_rd_sync!=f.dut.path_clear_toggle)$fatal(1,"capture reader ACK did not bind current token");
            if(f.dut.path.g_runtime_capture.u_capture_fifo.rd_bin!=0 || f.dut.path.in_rd_valid ||
               f.dut.path.g_runtime_capture.u_capture_fifo.wr_gray_r2!=0)$fatal(1,"capture reader ACK before zero proof");
            ack_changes=ack_changes+1;
        end
        if(f.dut.path.runtime_playback_wr_ack!=previous_ack[2])begin
            if(f.dut.path.runtime_playback_wr_ack!=f.dut.path_clear_toggle ||
               f.dut.path.g_runtime_playback.u_playback_fifo.clear_wr_sync!=f.dut.path_clear_toggle)$fatal(1,"playback writer ACK did not bind current token");
            if(f.dut.path.g_runtime_playback.u_playback_fifo.wr_bin!=0 ||
               f.dut.path.g_runtime_playback.u_playback_fifo.rd_gray_w2!=0)$fatal(1,"playback writer ACK before zero proof");
            ack_changes=ack_changes+1;
        end
        previous_ack[1]=f.dut.path.runtime_capture_rd_ack;previous_ack[2]=f.dut.path.runtime_playback_wr_ack;
        if((ones(previous_crd^f.dut.path.g_runtime_capture.u_capture_fifo.rd_gray)>1 ||
            ones(previous_pwr^f.dut.path.g_runtime_playback.u_playback_fifo.wr_gray)>1) &&
            (!f.dut.memory_gate || f.dut.path_clear_done))$fatal(1,"memory pointer nonunit jump escaped clear isolation");
        if(previous_crd!=0 && f.dut.path.g_runtime_capture.u_capture_fifo.rd_gray==0 && ones(previous_crd)>1)nonunit_zero=nonunit_zero+1;
        if(previous_pwr!=0 && f.dut.path.g_runtime_playback.u_playback_fifo.wr_gray==0 && ones(previous_pwr)>1)nonunit_zero=nonunit_zero+1;
        previous_crd=f.dut.path.g_runtime_capture.u_capture_fifo.rd_gray;previous_pwr=f.dut.path.g_runtime_playback.u_playback_fifo.wr_gray;
    end
    task cancel_file;
        begin f.checking=0;@(negedge f.source_clk);f.cancel=1;@(negedge f.source_clk);f.cancel=0;f.await_quiet();end
    endtask
    task pause_after_clear(input bit high);
        reg old_token;
        begin
            old_token=f.dut.path_clear_toggle;wait(f.dut.path_clear_toggle!=old_token);
            if(high)begin @(posedge f.memory_clk);#0.001;paused_high=paused_high+1;end
            else begin @(negedge f.memory_clk);paused_low=paused_low+1;end
            f.memory_run=0;
        end
    endtask
    task paused_restart(input bit high,input bit change_track,input bit repeat_request);
        reg old_token;
        reg [31:0] generation;
        begin
            cancel_file();@(negedge f.source_clk);f.runtime_rate=0;f.runtime_epoch=f.runtime_epoch+1;f.track=0;
            f.pulse_restart();wait(f.dut.path.g_runtime_dma.u_dma.read_buf_valid && f.dut.path.g_runtime_dma.u_dma.emit_bytes_left>20);
            f.checking=0;
            fork
                begin
                    @(negedge f.source_clk);
                    if(change_track)f.track=1;
                    f.restart=1;@(negedge f.source_clk);f.restart=0;
                    f.runtime_rate=change_track;f.runtime_epoch=f.runtime_epoch+1;
                end
                begin pause_after_clear(high);end
            join
            old_token=f.dut.path_clear_toggle;
            repeat(32)@(negedge f.source_clk);
            if(!f.busy50 || !f.dut.memory_gate || f.dut.path_clear_done || f.tf_active || f.dut.path.out_wr_en)
                $fatal(1,"paused memory released clear without local ACK");
            if(repeat_request)begin
                @(negedge f.source_clk);f.track=1;
                f.pulse_restart();f.pulse_restart();repeat(8)@(negedge f.source_clk);
                if(f.dut.path_clear_toggle!=old_token || f.dut.path_track!=0)$fatal(1,"overlapping request overwrote in-flight token/track");
                f.runtime_rate=1;f.runtime_epoch=f.runtime_epoch+1;
            end
            generation=f.source_generation;f.expected_track=change_track || repeat_request;f.session_index=0;
            f.memory_run=1;f.await_active(f.expected_track[3:0],generation);f.await_frames(64);cases=cases+1;
        end
    endtask
    reg [31:0] saved_generation;
    initial begin
        repeat(6)@(negedge f.source_clk);f.rst_n=1;repeat(30)@(negedge f.source_clk);
        paused_restart(0,0,0);paused_restart(1,1,0);paused_restart(0,0,1);
        // Cancel also clears, times out explicitly with a stopped backend,
        // and stays stopped after the backend returns. It cannot auto-rearm.
        f.begin_file(1);f.await_frames(3);f.checking=0;
        fork
            begin @(negedge f.source_clk);f.cancel=1;@(negedge f.source_clk);f.cancel=0;end
            begin pause_after_clear(1);end
        join
        repeat(1100)@(negedge f.source_clk);
        if(!f.failed || f.failure!=8 || !f.busy50 || f.quiet50 || !f.dut.memory_gate)$fatal(1,"clear timeout invented stop completion");
        f.memory_run=1;f.await_quiet();repeat(80)@(negedge f.source_clk);
        if(f.tf_active || f.busy50 || !f.failed)$fatal(1,"cancel timeout resumed automatically");cases=cases+1;
        // Reader fault must first enter the service hold/drain path; internal
        // soft_restart cannot bypass it, even after the card comes back.
        f.runtime_rate=0;f.runtime_epoch=f.runtime_epoch+1;f.begin_file(0);f.await_frames(3);f.checking=0;
        @(negedge f.source_clk);f.dut.path.u_file_reader.present=0;f.fail_expected(4);
        f.dut.path.u_file_reader.present=1;repeat(120)@(negedge f.source_clk);
        if(f.tf_active || !f.failed || f.busy50)$fatal(1,"card return rearmed failed TF");cases=cases+1;
        // Analysis uses the same clear transaction and its first real PCM
        // oracle, with ready withheld throughout a paused memory restart.
        @(negedge f.source_clk);f.mode=0;f.track=0;f.analysis_enable=1;f.analysis_ready=0;
        fork
            begin f.reader_restart=1;@(negedge f.source_clk);f.reader_restart=0;end
            begin pause_after_clear(0);end
        join
        repeat(32)@(negedge f.source_clk);
        if(f.analysis_frames!=0 || !f.dut.memory_gate || f.dut.path_clear_done)$fatal(1,"analysis consumed during incomplete clear");
        f.memory_run=1;f.await_quiet();wait(f.dut.format_ready_o);repeat(40)@(negedge f.source_clk);
        if(f.analysis_frames!=0)$fatal(1,"analysis ready hold lost first frame");
        f.analysis_ready=1;wait(f.analysis_frames==64);analysis_restarts=analysis_restarts+1;cases=cases+1;
        if(paused_high<2 || paused_low<3 || ack_changes<20 || nonunit_zero<8 || first_capture<5 || first_playback<5 || token_changes<8)
            $fatal(1,"missing clear protocol coverage");
        $display("PASS tf_runtime_clear: buffered=%0d cases=%0d paused_high=%0d paused_low=%0d ack_changes=%0d nonunit_zero=%0d first_capture=%0d first_playback=%0d token_changes=%0d analysis_restarts=%0d delivered=%0d",USE_COMMAND_BUFFER,cases,paused_high,paused_low,ack_changes,nonunit_zero,first_capture,first_playback,token_changes,analysis_restarts,f.delivered);
        $finish;
    end
endmodule
