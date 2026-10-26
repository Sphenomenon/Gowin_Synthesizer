`timescale 1ns/1ps
// Bit-exact equivalence TB for the DDR delay migration (Plan B).
// The frozen serial_delay_effect runs as the reference; the DDR path
// (serial_delay_effect_ddr + delay_ddr_dma + a behavioral DDR model) must
// produce identical valid/ready/left/right/clip on every cycle.
//
// Scenario timeline (samples counted on the shared valid_i schedule):
//   1. 0..11999   steady stream, pseudo-random audio, enabled toggling
//   2. @12000     clear_i pulse (flush machinery must resync both streams)
//   3. ..29999    continue, with a 60us DDR read stall @20000 (absorbed
//                 by the ~448-entry prefetch plateau; no underrun allowed)
//   4. @30000     rst_ni pulse on both sides, then 13000 more samples
//   5. @43000     500us DDR stall with 2000 more samples driven: the
//                 plateau drains, underrun must occur (wet=0, no hang);
//                 output comparison stops here (stream shift is expected)
module tb_delay_ddr_equivalence;
`ifdef WORKSTATION_DELAY_BLOCK_FIFOS
    defparam u_dut.u_write_fifo.RAM_STYLE="block_ram";
    defparam u_dut.u_read_fifo.RAM_STYLE="block_ram";
`endif
    reg aclk=0; always #7 aclk=~aclk;
    reg mclk=0; always #10 mclk=~mclk;
    reg arst_n=0,mrst_n=0;

    reg valid_i=0,enabled_i=1,clear_i=0;
    reg signed [31:0] left_i=0,right_i=0;
    integer sample_count=0;
    integer errors=0;
    integer compare_on=1;
    integer underrun_seen_expected=0;

    // ---------------- reference (frozen RTL) ----------------
    wire ref_ready,ref_valid,ref_active,ref_clip;
    wire signed [31:0] ref_left,ref_right;
    serial_delay_effect #(.DELAY_BITS(14),.ECHO_SAMPLES(9600)) u_ref(
        .clk_i(aclk),.rst_ni(arst_n),.clear_i(clear_i),.valid_i(valid_i),.enabled_i(enabled_i),
        .left_i(left_i),.right_i(right_i),
        .ready_o(ref_ready),.valid_o(ref_valid),.active_o(ref_active),
        .left_o(ref_left),.right_o(ref_right),.clip_o(ref_clip));

    // ---------------- DUT ----------------
    wire dut_ready,dut_valid,dut_active,dut_clip;
    wire signed [31:0] dut_left,dut_right;
    wire dwr_valid;
    wire [64:0] dwr_data,drd_data;
    wire dwr_pop;
    wire drd_push,drd_ready;
    wire ddr_req,ddr_write;
    wire [28:0] ddr_address;
    wire [255:0] ddr_wdata;
    wire [31:0] ddr_mask;
    reg [255:0] ddr_rdata=0;
    reg ddr_response=0;
    reg ddr_ready_r=0;
    wire [7:0] dut_status,dma_status;

    serial_delay_effect_ddr #(.DELAY_BITS(14),.ECHO_SAMPLES(9600)) u_dut(
        .clk_i(aclk),.rst_ni(arst_n),.clear_i(clear_i),.valid_i(valid_i),.enabled_i(enabled_i),
        .left_i(left_i),.right_i(right_i),
        .ready_o(dut_ready),.valid_o(dut_valid),.active_o(dut_active),
        .left_o(dut_left),.right_o(dut_right),.clip_o(dut_clip),
        .mem_clk_i(mclk),.mem_rst_ni(mrst_n),
        .dwr_valid_o(dwr_valid),.dwr_data_o(dwr_data),.dwr_pop_i(dwr_pop),
        .drd_push_i(drd_push),.drd_data_i(drd_data),.drd_ready_o(drd_ready),
        .debug_status_o(dut_status));

    delay_ddr_dma #(.DELAY_BITS(14),.ECHO_SAMPLES(9600)) u_dma(
        .clk_i(mclk),.rst_ni(mrst_n),
        .dwr_valid_i(dwr_valid),.dwr_data_i(dwr_data),.dwr_pop_o(dwr_pop),
        .drd_push_o(drd_push),.drd_data_o(drd_data),.drd_ready_i(drd_ready),
        .ddr_req_o(ddr_req),.ddr_write_o(ddr_write),.ddr_address_o(ddr_address),
        .ddr_data_o(ddr_wdata),.ddr_mask_o(ddr_mask),
        .ddr_ready_i(ddr_ready_r),.ddr_response_i(ddr_response),.ddr_read_data_i(ddr_rdata),
        .debug_status_o(dma_status));

    // ---------------- behavioral DDR ----------------
    localparam [28:0] RING_BASE=29'h0c00_0000;
    reg [255:0] ddr_mem [0:4095];
    reg [287:0] wr_log [0:8191];
    integer wr_idx=0;
    reg [28:0] rsp_addr=0;
    integer rsp_wait=0;
    integer stall_until=0;
    reg [31:0] mclk_count=0;
    // app_addr = RING_BASE + chunk*8 (word units); ring chunk index:
    wire [12:0] mem_idx=ddr_address[15:3]-RING_BASE[15:3];

    wire ddr_stall=(mclk_count<=stall_until);
    always @(posedge mclk or negedge mrst_n) begin
        if(!mrst_n) begin
            ddr_response<=0;rsp_wait<=0;ddr_ready_r<=0;mclk_count<=0;
        end else begin
            mclk_count<=mclk_count+1;
            ddr_response<=0;
            // toggle ready for mild backpressure; frozen low during a stall -
            // asserted ready MUST mean acceptance (arbiter contract)
            ddr_ready_r<=!ddr_stall && ~ddr_ready_r;
            if(ddr_req && ddr_ready_r && !ddr_stall) begin
                if(ddr_write) begin
                    ddr_mem[mem_idx]<=ddr_wdata;
                    wr_log[wr_idx]={mem_idx,ddr_wdata};
                    if(wr_idx<8191) wr_idx=wr_idx+1;
                end else begin
                    rsp_addr<=ddr_address;
                    rsp_wait<=3+({$random} % 5);
                end
            end
            if(rsp_wait>0) begin
                rsp_wait<=rsp_wait-1;
                if(rsp_wait==1) begin
                    ddr_response<=1;
                    ddr_rdata<=ddr_mem[(rsp_addr[15:3]-RING_BASE[15:3])];
                end
            end
            // a request accepted right before the stall still completes
        end
    end

    // ---------------- corruption localization ----------------
    reg [63:0] pushed_entry [0:65535];
    reg [63:0] popped_entry [0:65535];
    reg [64:0] push_log [0:65535];
    reg [64:0] pop_log [0:65535];
    integer push_idx=0, pop_idx=0, diverge_at=-1;
    wire dut_wrpush=(u_dut.wr_data_push||u_dut.wr_flush_push) && u_dut.wr_fifo_ready;
    wire dma_wrpop=u_dma.dwr_pop_o && dwr_valid;
    always @(posedge aclk) if(arst_n && dut_wrpush) begin push_log[push_idx]=u_dut.u_write_fifo.write_data_i; push_idx=push_idx+1; end
    always @(posedge mclk) if(mrst_n && dma_wrpop) begin pop_log[pop_idx]=dwr_data; pop_idx=pop_idx+1; end
    integer pop_count=0;
    wire dut_s4 = u_dut.state==3'd4 && !u_dut.clear_i;
    wire dut_usepop = u_dut.use_pop;
    always @(posedge aclk) begin
        if(arst_n && dut_s4) pushed_entry[u_dut.frames]={u_dut.feedback_r,u_dut.feedback_l};
        if(arst_n && dut_usepop) begin
            popped_entry[pop_count]=u_dut.rd_head[63:0];
            pop_count=pop_count+1;
        end
        if(!arst_n) pop_count=0;
    end

    // ---------------- checks ----------------
    always @(posedge aclk) begin
        if(arst_n) begin
            if(ref_ready!==dut_ready) begin
                errors=errors+1;
                if(errors<20) $display("READY mismatch t=%0t ref=%b dut=%b",$time,ref_ready,dut_ready);
            end
            if(ref_valid!==dut_valid) begin
                errors=errors+1;
                if(errors<20) $display("VALID mismatch t=%0t ref=%b dut=%b sample=%0d",$time,ref_valid,dut_valid,sample_count);
            end
            if(ref_valid && compare_on) begin
                if(ref_left!==dut_left || ref_right!==dut_right) begin
                    errors=errors+1;
                    if(errors<20) begin
                        $display("DATA mismatch t=%0t sample=%0d ref={%h,%h} dut={%h,%h} dma_state=%0d wptr=%0d rptr=%0d frames=%0d underrun=%b ddr_req=%b ddr_ready=%b stall=%b mclk=%0d stall_until=%0d",
                            $time,sample_count,ref_left,ref_right,dut_left,dut_right,
                            u_dma.state,u_dma.wptr,u_dma.rptr,u_dut.frames,
                            u_dut.underflow_sticky,ddr_req,ddr_ready_r,ddr_stall,mclk_count,stall_until);
                        begin : probe
                            integer idx, chunk, k;
                            if(diverge_at<0) begin
                                for(k=0;k<pop_idx;k=k+1)
                                    if(push_log[k]!==pop_log[k]) begin diverge_at=k; k=pop_idx; end
                            end
                            idx = u_dut.frames-1-9600;
                            chunk = (idx % 16384)/4;
                            $display("   entry[%0d] pushed=%h popped_at_head=%h ddr_mem_chunk[%0d]=%h",
                                idx, pushed_entry[idx],
                                u_dut.rd_head[63:0], chunk, ddr_mem[chunk]);
                            if(diverge_at>=0)
                                $display("   wrFIFO diverge at idx %0d: pushed=%h popped=%h",
                                    diverge_at, push_log[diverge_at], pop_log[diverge_at]);
                            begin : scan_writes
                                integer w, hits;
                                hits=0;
                                for(w=0;w<wr_idx;w=w+1)
                                    if(wr_log[w][287:256]==chunk) begin
                                        if(hits<3) $display("   write to chunk %0d: log[%0d] data=%h", chunk, w, wr_log[w][255:0]);
                                        hits=hits+1;
                                    end
                                $display("   total writes to chunk %0d: %0d (wr_idx=%0d)", chunk, hits, wr_idx);
                            end
                        end
                    end
                end
                if(ref_clip!==dut_clip) begin
                    errors=errors+1;
                    if(errors<20) $display("CLIP mismatch t=%0t sample=%0d",$time,sample_count);
                end
            end
        end
    end

    // ---------------- stimulus ----------------
    reg [31:0] lfsr=32'h1234_5678;
    task step_lfsr; begin
        lfsr={lfsr[0],lfsr[31:1]}^(lfsr[0]?32'h8020_0003:32'h0);
    end endtask

    integer i;
    initial begin
        for(i=0;i<4096;i=i+1) ddr_mem[i]=256'h0;
        repeat(20) @(posedge aclk);
        arst_n=1;mrst_n=1;
        repeat(20) @(posedge aclk);

        // phases 1-4: drive one sample every 20 aclk cycles
        while(sample_count<45000) begin
            step_lfsr;
            left_i=$signed(lfsr[31:0]);
            step_lfsr;
            right_i=$signed(lfsr[31:0]);
            enabled_i=lfsr[7];
            valid_i=1;
            sample_count=sample_count+1;
            @(posedge aclk);
            valid_i=0;
            repeat(19) @(posedge aclk);
            if(sample_count==12000) begin
                clear_i=1;
                @(posedge aclk);
                clear_i=0;
                $display("[%0t] clear pulse at sample %0d",$time,sample_count);
            end
            if(sample_count==20000) begin
                // ~60us DDR stall: prefetch plateau must absorb it silently
                stall_until=mclk_count+6000;
                $display("[%0t] DDR stall injected at sample %0d",$time,sample_count);
            end
            if(sample_count==30000) begin
                arst_n=0;mrst_n=0;
                stall_until=0;
                repeat(10) @(posedge aclk);
                arst_n=1;mrst_n=1;
                $display("[%0t] reset pulse at sample %0d",$time,sample_count);
            end
            if(sample_count==43000) begin
                // long stall: force underrun; comparison stops being meaningful
                compare_on=0;
                stall_until=mclk_count+50000;
                underrun_seen_expected=1;
                $display("[%0t] long DDR stall: underrun expected",$time);
            end
        end
        repeat(30000) @(posedge aclk);

        if(errors==0) $display("EQUIVALENCE PASS: 45000 samples compared, underrun_flag=%b dut_status=%b dma_status=%b",
            u_dut.underflow_sticky,dut_status,dma_status);
        else $display("EQUIVALENCE FAIL: %0d errors",errors);
        if(underrun_seen_expected && !u_dut.underflow_sticky) begin
            $display("FAIL: expected underrun flag after long stall");
            errors=errors+1;
        end
        if(errors==0) $finish;
        else $fatal(1,"tb failed");
    end

    // watchdog
    initial begin
        #800_000_000;
        $display("FAIL: watchdog timeout at sample %0d",sample_count);
        $fatal(1,"hang");
    end
endmodule
