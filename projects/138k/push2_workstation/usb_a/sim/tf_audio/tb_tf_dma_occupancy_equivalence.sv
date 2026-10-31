`timescale 1ns/1ps
module tb_tf_dma_occupancy_equivalence;
    parameter [31:0] BANK_BYTES = 64;
    reg clk=0;
    always #5 clk=~clk;
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
    integer checks=0,simultaneous=0,partial=0,holds=0,restarts=0,zero_response=0,overflow_checks=0;
    reg [31:0] rng=32'h37a8b251;
    function [31:0] random_word;
        input [31:0] v;
        reg [31:0] t;
        begin t=v^(v<<13);t=t^(t>>17);random_word=t^(t<<5);end
    endfunction
    task compare;
        begin
            if (dut.available_bytes !== reference.write_total_bytes-reference.read_total_bytes ||
                dut.accepted_used !== reference.capture_byte_count-reference.read_total_bytes)
                $fatal(1,"occupancy invariant differs checks=%0d",checks);
            if ({fifo_in_rd_en,playback_start_toggle,playback_done_toggle,fifo_out_wr_en,
                 fifo_out_wr_data,app_cmd,app_en,app_addr,app_wdata,app_wren,app_wend,
                 capacity_error,bank0_valid,bank1_valid,file_size_valid,staged_file_size,runtime_restart_ack_o}
             !=={r_fifo_in_rd_en,r_playback_start_toggle,r_playback_done_toggle,r_fifo_out_wr_en,
                 r_fifo_out_wr_data,r_app_cmd,r_app_en,r_app_addr,r_app_wdata,r_app_wren,r_app_wend,
                 r_capacity_error,r_bank0_valid,r_bank1_valid,r_file_size_valid,r_staged_file_size,r_runtime_restart_ack_o})
                $fatal(1,"public DMA output differs checks=%0d",checks);
            if ({dut.state,dut.capture_byte_count,dut.write_total_bytes,dut.read_total_bytes,
                 dut.write_ring_offset,dut.read_ring_offset,dut.write_count,dut.pending_bytes,
                 dut.read_pending_bytes,dut.emit_index,dut.emit_bytes_left,dut.write_pending,
                 dut.read_pending,dut.read_buf_valid,dut.in_read_wait,dut.capture_overflow,
                 dut.eof_seen,dut.eof_finalized,dut.stream_started,dut.end_reported,dut.read_buf}
             !=={reference.state,reference.capture_byte_count,reference.write_total_bytes,reference.read_total_bytes,
                 reference.write_ring_offset,reference.read_ring_offset,reference.write_count,reference.pending_bytes,
                 reference.read_pending_bytes,reference.emit_index,reference.emit_bytes_left,reference.write_pending,
                 reference.read_pending,reference.read_buf_valid,reference.in_read_wait,reference.capture_overflow,
                 reference.eof_seen,reference.eof_finalized,reference.stream_started,reference.end_reported,reference.read_buf})
                $fatal(1,"legacy DMA state differs checks=%0d",checks);
            checks=checks+1;
        end
    endtask
    always @(posedge clk) if(rst_n)begin
        if(dut.write_accept && dut.read_response)simultaneous=simultaneous+1;
        if(dut.read_response && dut.read_response_bytes<32)partial=partial+1;
        if(runtime_hold_i)holds=holds+1;
        if(dut.restart_event)restarts=restarts+1;
        if(dut.read_accept && app_rvalid)zero_response=zero_response+1;
    end
    integer i,k,upper_case,low_case,delta_case,delta_checks=0,commit_checks=0;
    reg [25:0] test_upper;
    reg [31:0] test_occupancy;
    reg [6:0] test_delta;
    reg [32:0] oracle_sum;
    initial begin
        #1;compare();
        // Independent full-width signed-add oracle. Exhaust every low-six
        // input and every signed-seven delta, using each upper carry-chain
        // boundary in both polarities plus zero/all-ones wrap boundaries.
        for(upper_case=0;upper_case<54;upper_case=upper_case+1)begin
            if(upper_case==0)test_upper=0;
            else if(upper_case==1)test_upper=26'h3ffffff;
            else if(upper_case<28)test_upper=26'd1<<(upper_case-2);
            else test_upper=~(26'd1<<(upper_case-28));
            for(low_case=0;low_case<64;low_case=low_case+1)
                for(delta_case=0;delta_case<128;delta_case=delta_case+1)begin
                    test_occupancy={test_upper,6'(low_case)};
                    test_delta=7'(delta_case);
                    oracle_sum={1'b0,test_occupancy}+{{26{test_delta[6]}},test_delta};
                    if(dut.add_occupancy_delta(test_occupancy,test_delta)!==oracle_sum[31:0])
                        $fatal(1,"small-delta arithmetic differs base=%h delta=%h",test_occupancy,test_delta);
                    delta_checks=delta_checks+1;
                end
        end
        // The capacity oracle forms the original full-width modulo sum.
        // Exhaust all low bits and pending values around every upper carry
        // boundary, including capacity +/-1 and the 2^32 wrap boundary.
        for(upper_case=0;upper_case<60;upper_case=upper_case+1)begin
            if(upper_case==0)test_upper=0;
            else if(upper_case==1)test_upper=26'h3ffffff;
            else if(upper_case<28)test_upper=26'd1<<(upper_case-2);
            else if(upper_case<54)test_upper=~(26'd1<<(upper_case-28));
            else if(upper_case==54)test_upper=26'((BANK_BYTES+BANK_BYTES)>>6)-26'd1;
            else if(upper_case==55)test_upper=26'((BANK_BYTES+BANK_BYTES)>>6);
            else if(upper_case==56)test_upper=26'((BANK_BYTES+BANK_BYTES)>>6)+26'd1;
            else if(upper_case==57)test_upper=26'h3fffffe;
            else if(upper_case==58)test_upper=1;
            else test_upper=2;
            for(low_case=0;low_case<64;low_case=low_case+1)
                for(delta_case=0;delta_case<64;delta_case=delta_case+1)begin
                    test_occupancy={test_upper,6'(low_case)};
                    oracle_sum={1'b0,test_occupancy}+33'(delta_case);
                    if(dut.pending_fits_ring(test_occupancy,6'(delta_case))!==
                       (oracle_sum[31:0]<=32'(BANK_BYTES+BANK_BYTES)))
                        $fatal(1,"pending capacity arithmetic differs base=%h pending=%0d",test_occupancy,delta_case);
                    commit_checks=commit_checks+1;
                end
        end
        repeat(4)@(negedge clk);
        rst_n=1;
        // Seed a consistent reachable counter relation near the 32-bit file
        // limit. This covers the explicit fifth-gigabyte overflow branch
        // without pretending a short simulation physically transferred 4GiB.
        dut.capture_byte_count=32'hffff_fffe; reference.capture_byte_count=32'hffff_fffe;
        dut.write_total_bytes=32'hffff_ffe0;reference.write_total_bytes=32'hffff_ffe0;
        dut.read_total_bytes=32'hffff_ffc0;reference.read_total_bytes=32'hffff_ffc0;
        dut.available_bytes=32'd32;dut.accepted_used=32'd62;
        fifo_in_rd_valid=1;
        repeat(5)begin @(posedge clk);#1;compare();overflow_checks=overflow_checks+1;end
        if(!capacity_error)$fatal(1,"counter limit was not covered");
        @(negedge clk);rst_n=0;fifo_in_rd_valid=0;
        #1;compare();@(negedge clk);rst_n=1;
        for(i=0;i<200000;i=i+1)begin
            @(negedge clk);
            rng=random_word(rng);mem_ready=rng[0] || rng[1];
            fifo_in_empty=rng[2]&&rng[3];fifo_in_rd_valid=rng[4];fifo_out_full=rng[5]&&rng[6];
            fifo_in_rd_data=rng[15:8];app_rdy=rng[16]||rng[17];app_wrdy=rng[18]||rng[19];
            app_rvalid=rng[20];runtime_hold_i=rng[21]&&rng[22]&&rng[23];
            if(rng[31:24]==0)capture_done_toggle=~capture_done_toggle;
            if(rng[31:23]==511)restart_toggle=~restart_toggle;
            for(k=0;k<8;k=k+1)begin rng=random_word(rng);app_rdata[k*32+:32]=rng;end
            file_size_bytes=rng;
            #1;compare();@(posedge clk);#1;compare();
        end
        if(simultaneous<10 || partial<10 || holds<1000 || restarts<100 || zero_response<100)
            $fatal(1,"coverage insufficient simultaneous=%0d partial=%0d hold=%0d restart=%0d zero=%0d",
                   simultaneous,partial,holds,restarts,zero_response);
        $display("PASS DMA occupancy: bank=%0d checks=%0d simultaneous=%0d partial=%0d holds=%0d restarts=%0d zero=%0d overflow=%0d delta_checks=%0d commit_checks=%0d",
                 BANK_BYTES,checks,simultaneous,partial,holds,restarts,zero_response,overflow_checks,delta_checks,commit_checks);
        $finish;
    end
endmodule
