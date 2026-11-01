`timescale 1ns/1ps
module tb_tf_read_preload_four;
    parameter [31:0] BANK_BYTES = 64;
    localparam [31:0] TEST_CAPACITY = BANK_BYTES + BANK_BYTES;
    reg clk=0;
    reg rst_n=0,mem_ready=0,capture_done_toggle=0,restart_toggle=0;
    reg [31:0] file_size_bytes=0;
    reg fifo_in_empty=1,fifo_in_rd_valid=0,fifo_out_full=0;
    reg [7:0] fifo_in_rd_data=0;
    reg app_rdy=0,app_wrdy=0,app_rvalid=0,runtime_hold_i=0;
    reg [255:0] app_rdata=0;
    wire fifo_in_rd_en,playback_start_toggle,playback_done_toggle;
    wire fifo_out_wr_en,app_en,app_wren,app_wend,capacity_error;
    wire bank0_valid,bank1_valid,file_size_valid,runtime_restart_ack_o;
    wire [7:0] fifo_out_wr_data;
    wire [2:0] app_cmd;
    wire [28:0] app_addr;
    wire [255:0] app_wdata;
    wire [31:0] staged_file_size;
    wire r_fifo_in_rd_en,r_playback_start_toggle,r_playback_done_toggle;
    wire r_fifo_out_wr_en,r_app_en,r_app_wren,r_app_wend,r_capacity_error;
    wire r_bank0_valid,r_bank1_valid,r_file_size_valid,r_runtime_restart_ack_o;
    wire [7:0] r_fifo_out_wr_data;
    wire [2:0] r_app_cmd;
    wire [28:0] r_app_addr;
    wire [255:0] r_app_wdata;
    wire [31:0] r_staged_file_size;
    workstation_tf_runtime_dma #(.AUDIO_BANK_BYTES(BANK_BYTES),.AUDIO_STREAM_START_BYTES(32)) dut(.*);
    reference_workstation_tf_runtime_dma #(.AUDIO_BANK_BYTES(BANK_BYTES),.AUDIO_STREAM_START_BYTES(32)) reference(
        .clk(clk),.rst_n(rst_n),.mem_ready(mem_ready),.capture_done_toggle(capture_done_toggle),
        .restart_toggle(restart_toggle),.file_size_bytes(file_size_bytes),.fifo_in_empty(fifo_in_empty),
        .fifo_in_rd_valid(fifo_in_rd_valid),.fifo_in_rd_data(fifo_in_rd_data),
        .fifo_out_full(fifo_out_full),.app_rdy(app_rdy),.app_wrdy(app_wrdy),
        .app_rvalid(app_rvalid),.app_rdata(app_rdata),.runtime_hold_i(runtime_hold_i),
        .fifo_in_rd_en(r_fifo_in_rd_en),.playback_start_toggle(r_playback_start_toggle),
        .playback_done_toggle(r_playback_done_toggle),.fifo_out_wr_en(r_fifo_out_wr_en),
        .fifo_out_wr_data(r_fifo_out_wr_data),.app_cmd(r_app_cmd),.app_en(r_app_en),
        .app_addr(r_app_addr),.app_wdata(r_app_wdata),.app_wren(r_app_wren),.app_wend(r_app_wend),
        .capacity_error(r_capacity_error),.bank0_valid(r_bank0_valid),.bank1_valid(r_bank1_valid),
        .file_size_valid(r_file_size_valid),.staged_file_size(r_staged_file_size),
        .runtime_restart_ack_o(r_runtime_restart_ack_o));

    integer pattern,control,k,checks=0,skipped_illegal=0,responses=0,immediate=0,
            emitted=0,held=0,restarts=0,unknown_valid=0,invalid_different=0;
    reg [31:0] probe_available,probe_accepted;
    reg [5:0] probe_pending,probe_response;
    reg probe_read_pending,probe_valid;
    reg [255:0] seed_data;
    function quad(input integer v);begin case(v&3)0:quad=0;1:quad=1;2:quad=1'bx;3:quad=1'bz;endcase end endfunction
    task compare;
        begin
            if({fifo_in_rd_en,playback_start_toggle,playback_done_toggle,fifo_out_wr_en,app_cmd,app_en,app_addr,app_wdata,app_wren,app_wend,capacity_error,bank0_valid,bank1_valid,file_size_valid,staged_file_size,runtime_restart_ack_o} !== {r_fifo_in_rd_en,r_playback_start_toggle,r_playback_done_toggle,r_fifo_out_wr_en,r_app_cmd,r_app_en,r_app_addr,r_app_wdata,r_app_wren,r_app_wend,r_capacity_error,r_bank0_valid,r_bank1_valid,r_file_size_valid,r_staged_file_size,r_runtime_restart_ack_o})
                $fatal(1,"preload public control differs pattern=%0d control=%0d",pattern,control);
            if({dut.state,dut.capture_meta,dut.capture_sync,dut.capture_seen,dut.restart_meta,dut.restart_sync,dut.restart_seen,dut.size_meta,dut.size_sync,dut.capture_byte_count,dut.write_total_bytes,dut.read_total_bytes,dut.available_bytes,dut.accepted_used,dut.write_ring_offset,dut.read_ring_offset,dut.write_buf,dut.write_count,dut.pending_bytes,dut.read_pending_bytes,dut.emit_index,dut.emit_bytes_left,dut.write_pending,dut.read_pending,dut.read_buf_valid,dut.in_read_wait,dut.capture_overflow,dut.eof_seen,dut.eof_finalized,dut.stream_started,dut.end_reported,dut.capacity_error,dut.file_size_valid,dut.staged_file_size,dut.fifo_in_rd_en,dut.playback_start_toggle,dut.playback_done_toggle,dut.runtime_restart_ack_o,dut.restart_zero_count} !== {reference.state,reference.capture_meta,reference.capture_sync,reference.capture_seen,reference.restart_meta,reference.restart_sync,reference.restart_seen,reference.size_meta,reference.size_sync,reference.capture_byte_count,reference.write_total_bytes,reference.read_total_bytes,reference.available_bytes,reference.accepted_used,reference.write_ring_offset,reference.read_ring_offset,reference.write_buf,reference.write_count,reference.pending_bytes,reference.read_pending_bytes,reference.emit_index,reference.emit_bytes_left,reference.write_pending,reference.read_pending,reference.read_buf_valid,reference.in_read_wait,reference.capture_overflow,reference.eof_seen,reference.eof_finalized,reference.stream_started,reference.end_reported,reference.capacity_error,reference.file_size_valid,reference.staged_file_size,reference.fifo_in_rd_en,reference.playback_start_toggle,reference.playback_done_toggle,reference.runtime_restart_ack_o,reference.restart_zero_count})
                $fatal(1,"preload nonprivate state differs pattern=%0d control=%0d",pattern,control);
            if(fifo_out_wr_en === 1'b1 && fifo_out_wr_data !== r_fifo_out_wr_data)
                $fatal(1,"preload valid FIFO payload differs pattern=%0d control=%0d",pattern,control);
            if(dut.read_buf_valid === 1'b1 && dut.read_buf !== reference.read_buf)
                $fatal(1,"preload published buffer differs pattern=%0d control=%0d",pattern,control);
            if(dut.read_response === 1'b1 && dut.read_buf_valid === 1'b1)
                $fatal(1,"preload response overlapped valid buffer pattern=%0d control=%0d",pattern,control);
            if(dut.read_pending === 1'b1 && dut.read_buf_valid === 1'b1)
                $fatal(1,"preload pending/valid invariant violated pattern=%0d control=%0d",pattern,control);
        end
    endtask
    initial begin
      #1;
      for(pattern=0;pattern<12;pattern=pattern+1)begin
        probe_available=32'(pattern*31);probe_accepted=32'hffffffe0+32'(pattern);
        probe_pending=6'(pattern*3);probe_response=6'(pattern*7);
        case(pattern)
          0:begin probe_available=32;probe_accepted=0;probe_pending=63;probe_response=0;end
          1:begin probe_available=7;probe_accepted=32'hffffffff;probe_pending=3;probe_response=31;end
          2:begin probe_available=32'hxxxxxx80;probe_accepted=32'h0000000x;probe_pending=6'b00000z;probe_response=6'bx00000;end
          6:begin probe_available=32'hffffffff;probe_accepted=32'hzzzzzzzz;end
          8:begin probe_available=32'hzzzzzzzz;probe_accepted=32'hxxxxxxxx;end
        endcase
        for(control=0;control<65536;control=control+1)begin
          probe_valid=quad(control);probe_read_pending=quad(control>>2);
          // This single excluded known combination is not assumed: it is
          // separately proved unreachable from reset under every priority.
          if(probe_valid===1'b1 && probe_read_pending===1'b1)skipped_illegal=skipped_illegal+1;
          else begin
            clk=0;rst_n=(pattern==7)?0:1;capture_done_toggle=0;restart_toggle=0;
            mem_ready=quad(control>>10);app_rdy=quad(control>>6);app_wrdy=quad(control>>8);
            app_rvalid=quad(control>>4);runtime_hold_i=quad(control>>12);fifo_out_full=quad(control>>14);
            fifo_in_empty=1;fifo_in_rd_valid=(pattern&1);fifo_in_rd_data=8'(pattern);file_size_bytes=32'hf1230000+pattern;
            seed_data={8{32'h13579000+32'(pattern)}};
            app_rdata={8{32'hacf00000+32'(control)}};
            if(pattern==6)app_rdata[39:32]=8'hxz;
            if(pattern==8)app_rdata[31:0]=32'hzzzzzzzz;
            dut.state=(pattern==3 || pattern==4) ? 2'd2 : (pattern==10 ? 2'bxx : 2'd0);reference.state=(pattern==3 || pattern==4) ? 2'd2 : (pattern==10 ? 2'bxx : 2'd0);
            dut.capture_meta=0;reference.capture_meta=0;
            dut.capture_sync=pattern==4;reference.capture_sync=pattern==4;
            dut.capture_seen=0;reference.capture_seen=0;
            dut.restart_meta=0;reference.restart_meta=0;
            dut.restart_sync=pattern==5;reference.restart_sync=pattern==5;
            dut.restart_seen=0;reference.restart_seen=0;
            dut.size_meta=32'hfede0000+pattern;reference.size_meta=32'hfede0000+pattern;
            dut.size_sync=16+pattern;reference.size_sync=16+pattern;
            dut.capture_byte_count=32'hffff0000+pattern;reference.capture_byte_count=32'hffff0000+pattern;
            dut.write_total_bytes=32+pattern;reference.write_total_bytes=32+pattern;
            dut.read_total_bytes=pattern;reference.read_total_bytes=pattern;
            dut.available_bytes=probe_available;reference.available_bytes=probe_available;
            dut.accepted_used=probe_accepted;reference.accepted_used=probe_accepted;
            dut.write_ring_offset=0;reference.write_ring_offset=0;
            dut.read_ring_offset=32;reference.read_ring_offset=32;
            dut.write_buf={8{32'h3c000000+32'(pattern)}};reference.write_buf={8{32'h3c000000+32'(pattern)}};
            dut.write_count=pattern;reference.write_count=pattern;
            dut.pending_bytes=probe_pending;reference.pending_bytes=probe_pending;
            dut.read_pending_bytes=probe_response;reference.read_pending_bytes=probe_response;
            dut.emit_index=pattern;reference.emit_index=pattern;
            dut.emit_bytes_left=pattern==1 ? 6'd1 : 6'd32;reference.emit_bytes_left=pattern==1 ? 6'd1 : 6'd32;
            dut.write_pending=pattern==1 || pattern==2;reference.write_pending=pattern==1 || pattern==2;
            dut.read_pending=probe_read_pending;reference.read_pending=probe_read_pending;
            dut.read_buf_valid=probe_valid;reference.read_buf_valid=probe_valid;
            dut.in_read_wait=0;reference.in_read_wait=0;
            dut.capture_overflow=0;reference.capture_overflow=0;
            dut.eof_seen=pattern==1;reference.eof_seen=pattern==1;
            dut.eof_finalized=pattern==1 ? 1'b1 : (pattern==11 ? 1'bx:1'b0);reference.eof_finalized=pattern==1 ? 1'b1 : (pattern==11 ? 1'bx:1'b0);
            dut.stream_started=pattern==9 ? 1'bx:1'b1;reference.stream_started=pattern==9 ? 1'bx:1'b1;
            dut.end_reported=0;reference.end_reported=0;
            dut.capacity_error=0;reference.capacity_error=0;
            dut.file_size_valid=0;reference.file_size_valid=0;
            dut.staged_file_size=65535;reference.staged_file_size=65535;
            dut.fifo_in_rd_en=0;reference.fifo_in_rd_en=0;
            dut.playback_start_toggle=0;reference.playback_start_toggle=0;
            dut.playback_done_toggle=0;reference.playback_done_toggle=0;
            dut.runtime_restart_ack_o=0;reference.runtime_restart_ack_o=0;
            dut.restart_zero_count=0;reference.restart_zero_count=0;
            reference.read_buf=seed_data;
            dut.read_buf=(probe_valid===1'b1)?seed_data:~seed_data;
            #1;compare();
            if(dut.read_response===1'b1)responses=responses+1;
            if(dut.read_accept===1'b1 && app_rvalid===1'b1)immediate=immediate+1;
            if(fifo_out_wr_en===1'b1)emitted=emitted+1;
            if(runtime_hold_i===1'b1)held=held+1;
            if(dut.restart_event===1'b1)restarts=restarts+1;
            if(probe_valid===1'bx || probe_valid===1'bz)unknown_valid=unknown_valid+1;
            if(probe_valid!==1'b1 && dut.read_buf!==reference.read_buf)invalid_different=invalid_different+1;
            clk=1;#1;compare();checks=checks+1;clk=0;
          end
        end
      end
      if(responses<100 || immediate<10 || emitted<100 || held<100 || restarts<100 || unknown_valid<100 || invalid_different<100)
        $fatal(1,"preload four-state coverage insufficient");
      $display("PASS actual twin preload four-state: bank=%0d checks=%0d excluded_proved_illegal=%0d responses=%0d immediate=%0d emitted=%0d hold=%0d restart=%0d unknown_valid=%0d private_different=%0d",BANK_BYTES,checks,skipped_illegal,responses,immediate,emitted,held,restarts,unknown_valid,invalid_different);
      $finish;
    end
endmodule
