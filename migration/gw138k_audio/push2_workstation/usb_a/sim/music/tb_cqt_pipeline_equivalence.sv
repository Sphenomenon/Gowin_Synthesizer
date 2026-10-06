`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"
module tb_cqt_pipeline_equivalence;
    parameter integer DDR = 1;
    localparam integer N = 512;
    reg clk=0,rstn=0,start=0,we=0;
    reg [15:0] wa=0;
    reg signed [15:0] wd=0;
    always #10 clk=~clk;
    integer cycles=0,round=0,i=0,j=0;
    wire [1:0] done,ready,req,wr,mw,overflow;
    wire [31:0] addr[0:1];
    wire [15:0] wdata[0:1];
    wire [15:0] ma[0:1];
    wire signed [15:0] md[0:1];
    wire [13:0] kr[0:1],ki[0:1];
    wire [7:0] lp[0:1];
    reg signed [15:0] krd[0:1],kid[0:1],lpd[0:1];
    reg [1:0] rsp=0;
    reg [15:0] rd[0:1];
    wire [1:0] mr;
    wire [1:0] local_we;
    wire [17:0] local_addr[0:1];
    wire signed [15:0] local_data[0:1];
    reg [15:0] memory[0:1][0:N-1];
    reg [33:0] writes[0:1][0:2047];
    reg [31:0] mags[0:1][0:511];
    integer nw[0:1],nm[0:1],timer[0:1],clipped[0:1];
    reg [1:0] finished=0;
    function automatic signed [15:0] pcm(input integer r, input integer n);
        case(r)
            0: pcm=n[0] ? -16'sd32768 : 16'sd32767;
            1: pcm=16'((n*7919) ^ (n<<7) ^ 32'h956ab234);
            default: pcm=n%5==0 ? 16'sd0 : 16'(n*101-26000);
        endcase
    endfunction
    function automatic signed [15:0] lowpass(input [7:0] n);
        case(n[1:0])
            0: lowpass=16'sd32767;
            1: lowpass=-16'sd32768;
            2: lowpass=-16'sd900;
            3: lowpass=16'sd2000;
        endcase
    endfunction
    basic_pitch_cqt_engine_reference #(.WIN_LEN(N),.USE_DDR_SIGNAL(DDR),.USE_DDR_COEFF(0)) dut_0(
        .clk_i(clk),.rst_ni(rstn),.start_i(start),.octave_limit_i(5'd3),.frame_limit_i(9'd2),
        .win_we_i(we),.win_addr_i(wa),.win_data_i(wd),.win_ready_o(ready[0]),
        .kre_addr_o(kr[0]),.kre_data_i(krd[0]),.kim_addr_o(ki[0]),.kim_data_i(kid[0]),
        .coeff_req_o(),.coeff_valid_i(1'b1),.klp_addr_o(lp[0]),.klp_data_i(lpd[0]),
        .norm_addr_o(),.norm_log_data_i(16'sd0),.loglut_addr_o(),.loglut_data_i(16'sd17),
        .mag_we_o(mw[0]),.mag_addr_o(ma[0]),.mag_data_o(md[0]),.done_o(done[0]),.busy_o(),
        .sig_mem_req_o(req[0]),.sig_mem_write_o(wr[0]),.sig_mem_addr_o(addr[0]),
        .sig_mem_wdata_o(wdata[0]),.sig_mem_ready_i(mr[0]),.sig_mem_rsp_valid_i(rsp[0]),
        .sig_mem_rdata_i(rd[0]),.sig_overflow_o(overflow[0]));
    basic_pitch_cqt_engine #(.WIN_LEN(N),.USE_DDR_SIGNAL(DDR),.USE_DDR_COEFF(0)) dut_1(
        .clk_i(clk),.rst_ni(rstn),.start_i(start),.octave_limit_i(5'd3),.frame_limit_i(9'd2),
        .win_we_i(we),.win_addr_i(wa),.win_data_i(wd),.win_ready_o(ready[1]),
        .kre_addr_o(kr[1]),.kre_data_i(krd[1]),.kim_addr_o(ki[1]),.kim_data_i(kid[1]),
        .coeff_req_o(),.coeff_valid_i(1'b1),.klp_addr_o(lp[1]),.klp_data_i(lpd[1]),
        .norm_addr_o(),.norm_log_data_i(16'sd0),.loglut_addr_o(),.loglut_data_i(16'sd17),
        .mag_we_o(mw[1]),.mag_addr_o(ma[1]),.mag_data_o(md[1]),.done_o(done[1]),.busy_o(),
        .sig_mem_req_o(req[1]),.sig_mem_write_o(wr[1]),.sig_mem_addr_o(addr[1]),
        .sig_mem_wdata_o(wdata[1]),.sig_mem_ready_i(mr[1]),.sig_mem_rsp_valid_i(rsp[1]),
        .sig_mem_rdata_i(rd[1]),.sig_overflow_o(overflow[1]));
    assign local_we={dut_1.sig_we,dut_0.sig_we};
    assign local_addr[0]=dut_0.sig_waddr;
    assign local_addr[1]=dut_1.sig_waddr;
    assign local_data[0]=dut_0.sig_wdata;
    assign local_data[1]=dut_1.sig_wdata;
    always @(posedge clk) if(rstn) begin
        cycles <= cycles+1;
        finished <= finished | done;
        if(|overflow) $fatal(1,"signal pending write overflow");
    end
    for(genvar g=0;g<2;g=g+1) begin: model
        assign mr[g]=timer[g]==0 && !rsp[g] && cycles%(5+g)!=0;
        always @(posedge clk) begin
            krd[g] <= 16'((kr[g]*313) ^ 16'h7961);
            kid[g] <= 16'((ki[g]*229) ^ 16'hbc17);
            lpd[g] <= lowpass(lp[g]);
            if(rstn) begin
                rsp[g] <= 0;
                if(req[g] && mr[g]) begin
                    if(addr[g] < `BP_DDR_CQT_SIGNAL_BYTE_BASE ||
                       addr[g]>=`BP_DDR_CQT_SIGNAL_BYTE_BASE+N*2 || addr[g][0])
                        $fatal(1,"invalid signal DDR address %h",addr[g]);
                    if(wr[g]) begin
                        memory[g][(addr[g]-`BP_DDR_CQT_SIGNAL_BYTE_BASE)>>1] <= wdata[g];
                        writes[g][nw[g]]={18'((addr[g]-`BP_DDR_CQT_SIGNAL_BYTE_BASE)>>1),wdata[g]};
                        nw[g]=nw[g]+1;
                        if(wdata[g]==16'h7fff || wdata[g]==16'h8000) clipped[g]=clipped[g]+1;
                    end else begin
                        rd[g] <= memory[g][(addr[g]-`BP_DDR_CQT_SIGNAL_BYTE_BASE)>>1];
                        timer[g] <= 1+cycles%(3+g);
                    end
                end else if(timer[g]>0) begin
                    timer[g] <= timer[g]-1;
                    if(timer[g]==1) rsp[g] <= 1;
                end
                if(!DDR && local_we[g]) begin
                    writes[g][nw[g]]={local_addr[g],local_data[g]};
                    nw[g]=nw[g]+1;
                    if(local_data[g]==16'h7fff || local_data[g]==16'h8000) clipped[g]=clipped[g]+1;
                end
                if(mw[g]) begin
                    mags[g][nm[g]]={ma[g],md[g]};
                    nm[g]=nm[g]+1;
                end
            end
        end
    end
    initial begin
        for(i=0;i<2;i=i+1) begin
            nw[i]=0;nm[i]=0;timer[i]=0;clipped[i]=0;rd[i]=0;
            for(j=0;j<N;j=j+1) memory[i][j]=0;
        end
        repeat(4) @(negedge clk);rstn=1;
        for(round=0;round<3;round=round+1) begin
            @(negedge clk);finished=0;
            for(i=0;i<2;i=i+1) begin nw[i]=0;nm[i]=0;clipped[i]=0;end
            for(i=0;i<N;i=i+1) begin
                wait(&ready);
                if(DDR) wait(!dut_0.sig_write_pending && !dut_1.sig_write_pending);
                @(negedge clk);we=1;wa=i;wd=pcm(round,i);
                @(negedge clk);we=0;
            end
            if(DDR) wait(!dut_0.sig_write_pending && !dut_1.sig_write_pending);
            @(negedge clk);start=1;
            @(negedge clk);start=0;
            wait(&finished);
            @(negedge clk);
            if(nm[0]!=216 || nm[0]!=nm[1]) $fatal(1,"CQT bin coverage %0d/%0d",nm[0],nm[1]);
            for(i=0;i<nm[0];i=i+1)
                if(mags[0][i]!==mags[1][i]) $fatal(1,"CQT bin mismatch round=%0d item=%0d",round,i);
            if(nw[0]!=896 || nw[0]!=nw[1] || clipped[0]==0)
                $fatal(1,"signal writes/clip coverage %0d/%0d clip=%0d",nw[0],nw[1],clipped[0]);
            for(i=0;i<nw[0];i=i+1)
                if(writes[0][i]!==writes[1][i])
                    $fatal(1,"decimation write mismatch round=%0d item=%0d old=%h new=%h",round,i,writes[0][i],writes[1][i]);
            if(DDR) begin
                for(i=0;i<N;i=i+1)
                    if(memory[0][i]!==memory[1][i]) $fatal(1,"final signal mismatch index=%0d",i);
            end
            $display("round=%0d DDR=%0d exact bins=%0d signal writes=%0d",round,DDR,nm[0],nw[0]);
            wait(&ready);
        end
        $display("PASS CQT pipeline/reference: local/DDR=%0d, 3 windows x 3 octaves, saturation, head 127/128, variable DDR stalls, exact signal writes and bins",DDR);
        $finish;
    end
    initial begin
        repeat(5000000) @(posedge clk);
        $fatal(1,"CQT equivalence timeout");
    end
endmodule
