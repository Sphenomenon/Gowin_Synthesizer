`timescale 1ns/1ps
`include "basic_pitch_ddr_map.svh"

// Cross-storage comparison of the same maintained CQT engine. This fixture
// deliberately does not instantiate the frontend, task owner, or DDR fabric.
module tb_cqt_storage_equivalence;
    parameter integer NEGATIVE = 0;
    localparam integer N=512, OCTAVES=2, FRAMES=2, PER_OCT=36, KTAPS=256;
    localparam integer NMAG=OCTAVES*FRAMES*PER_OCT;
    localparam integer NDEC=N/2, NWRITE=N+NDEC;
    localparam integer S_MAC_WAIT=12, S_DEC_WAIT=13, S_DEC_STORE=16;
    reg clk=0, rstn=0, start=0, win_we=0, monitor_active=0;
    reg [15:0] win_addr=0;
    reg signed [15:0] win_data=0;
    always #10 clk=~clk;
    integer cycles=0, window_number=0, pattern_number=0;
    integer i,j,cfg,fd,nonzero,input_sensitive;
    reg [2:0] finished=0;
    wire [2:0] ready,done,busy,overflow,mag_we;
    wire [15:0] mag_addr[0:2],mag_data[0:2];
    wire [13:0] kre_addr[0:2],kim_addr[0:2];
    wire [7:0] lp_addr[0:2];
    wire [8:0] norm_addr[0:2],log_addr[0:2];
    wire [15:0] kre_data[0:2],kim_data[0:2];
    wire [2:0] coeff_req,coeff_valid,coeff_mem_req,coeff_mem_ready;
    wire [31:0] coeff_mem_addr[0:2];
    reg [2:0] coeff_rsp=0;
    reg [15:0] coeff_rdata[0:2];
    wire [2:0] sig_req,sig_write,sig_ready;
    wire [31:0] sig_addr[0:2];
    wire [15:0] sig_wdata[0:2];
    reg [2:0] sig_rsp=0;
    reg [15:0] sig_rdata[0:2];
    wire [2:0] local_we;
    wire [17:0] local_waddr[0:2];
    wire [15:0] local_wdata[0:2];
    wire [4:0] state[0:2],octave[0:2];
    wire [16:0] dec_index[0:2];
    wire [15:0] dec_value[0:2];
    integer sig_timer[0:2],coeff_timer[0:2];
    integer nm[0:2],nw[0:2],nd[0:2];
    integer sig_reads[0:2],sig_writes[0:2],coeff_reads[0:2];
    integer sig_stalls[0:2],coeff_stalls[0:2],started_cycle;
    integer frame_nonzero[0:2][0:OCTAVES*FRAMES-1];
    reg [15:0] signal_memory[0:N-1];
    reg [15:0] model[0:52238],real_rom[0:9215],imag_rom[0:9215];
    reg [15:0] lowpass_rom[0:255],norm_rom[0:308],log_rom[0:255];
    reg [31:0] magnitudes[0:2][0:NMAG-1];
    reg [33:0] signal_writes[0:2][0:NWRITE-1];
    reg [37:0] decimated[0:2][0:NDEC-1];
    reg [31:0] extreme_magnitudes[0:NMAG-1],random_magnitudes[0:NMAG-1];
    reg [33:0] random_writes[0:NWRITE-1];
    reg [37:0] random_decimated[0:NDEC-1];
    string trace_directory;

    function automatic [15:0] pcm(input integer pattern,input integer index);
        reg [31:0] x;
        begin
            if(pattern==0) begin
                case(index%8)
                    0,2: pcm=16'h7fff;
                    1,3: pcm=16'h8000;
                    4: pcm=16'h0000;
                    5: pcm=16'h0001;
                    6: pcm=16'hffff;
                    default: pcm=16'(index*313-24000);
                endcase
            end else begin
                x=32'(index)^32'h91be753d;
                x=x^(x<<13);x=x^(x>>17);x=x^(x<<5);
                pcm=(index==0) ? 16'h7fff : (index==1) ? 16'h8000 : x[15:0];
            end
        end
    endfunction

    function automatic integer expected_mag_addr(input integer index);
        integer octave_number,frame_number,bin_number;
        begin
            octave_number=index/(FRAMES*PER_OCT);
            frame_number=(index/PER_OCT)%FRAMES;
            bin_number=index%PER_OCT;
            expected_mag_addr=frame_number*309+(8-octave_number)*36+bin_number-15;
        end
    endfunction

    function automatic integer expected_signal_reads;
        integer output_index,tap_index,raw_index,total;
        begin
            total=NMAG*KTAPS;
            for(output_index=0;output_index<N/2;output_index=output_index+1)
                for(tap_index=0;tap_index<256;tap_index=tap_index+1) begin
                    raw_index=2*output_index+tap_index-127;
                    if(raw_index>=0 && raw_index<N) total=total+1;
                end
            expected_signal_reads=total;
        end
    endfunction

    always @(posedge clk) begin
        cycles<=cycles+1;
        if(!rstn) finished<=0;
        else begin
            finished<=finished|done;
            if(|overflow) $fatal(1,"PROTOCOL signal pending write overflow");
        end
    end

    for(genvar g=0;g<3;g=g+1) begin: modes
        if(g<2) begin: ddr_coefficients
            basic_pitch_ddr_coeff_pair #(.FIRST_WORD(33807),.SECOND_WORD(43023),.STRIDE(1)) pair(
                .clk_i(clk),.rst_ni(rstn),.req_i(coeff_req[g]),.index_i(kre_addr[g]),
                .valid_o(coeff_valid[g]),.first_o(kre_data[g]),.second_o(kim_data[g]),
                .mem_req_o(coeff_mem_req[g]),.mem_addr_o(coeff_mem_addr[g]),
                .mem_ready_i(coeff_mem_ready[g]),.mem_rsp_valid_i(coeff_rsp[g]),
                .mem_rdata_i(coeff_rdata[g]));
        end else begin: local_coefficients
            reg [15:0] real_q,imag_q;
            always @(posedge clk) begin
                real_q<=real_rom[kre_addr[g]];
                imag_q<=imag_rom[kim_addr[g]];
            end
            assign kre_data[g]=(NEGATIVE==1) ? 16'd0 : real_q;
            assign kim_data[g]=(NEGATIVE==1) ? 16'd0 : imag_q;
            assign coeff_valid[g]=1'b1;
            assign coeff_mem_req[g]=1'b0;
            assign coeff_mem_addr[g]=32'd0;
        end
        basic_pitch_cqt_engine #(.WIN_LEN(N),.PER_OCT(PER_OCT),.KTAPS(KTAPS),
            .HOP_NUMERATOR(513),.HOP_DENOMINATOR(2),
            .USE_DDR_SIGNAL(g==0),.USE_DDR_COEFF(g<2)) engine(
            .clk_i(clk),.rst_ni(rstn),.start_i(start),
            .octave_limit_i(5'(OCTAVES)),.frame_limit_i(9'(FRAMES)),
            .win_we_i(win_we),.win_addr_i(win_addr),.win_data_i(win_data),.win_ready_o(ready[g]),
            .kre_addr_o(kre_addr[g]),.kre_data_i(kre_data[g]),
            .kim_addr_o(kim_addr[g]),.kim_data_i(kim_data[g]),
            .coeff_req_o(coeff_req[g]),.coeff_valid_i(coeff_valid[g]),
            .klp_addr_o(lp_addr[g]),.klp_data_i(lowpass_rom[lp_addr[g]]),
            .norm_addr_o(norm_addr[g]),.norm_log_data_i(norm_rom[norm_addr[g]]),
            .loglut_addr_o(log_addr[g]),.loglut_data_i(log_rom[log_addr[g]]),
            .mag_we_o(mag_we[g]),.mag_addr_o(mag_addr[g]),.mag_data_o(mag_data[g]),
            .busy_o(busy[g]),.done_o(done[g]),
            .sig_mem_req_o(sig_req[g]),.sig_mem_write_o(sig_write[g]),
            .sig_mem_addr_o(sig_addr[g]),.sig_mem_wdata_o(sig_wdata[g]),
            .sig_mem_ready_i(sig_ready[g]),.sig_mem_rsp_valid_i(sig_rsp[g]),
            .sig_mem_rdata_i(sig_rdata[g]),.sig_overflow_o(overflow[g]));
        assign local_we[g]=engine.sig_we;
        assign local_waddr[g]=engine.sig_waddr;
        assign local_wdata[g]=engine.sig_wdata;
        assign state[g]=engine.state;
        assign octave[g]=engine.oct;
        assign dec_index[g]=engine.dec_i;
        assign dec_value[g]=engine.sat15(engine.dec_acc);
        // Different ready blackouts and read-return delays for each independent
        // memory client. Neither accepted commands nor returns are inferred
        // from a consumer's request without the actual ready/valid handshake.
        assign sig_ready[g]=(sig_timer[g]==0) && !sig_rsp[g] &&
                            cycles%(5+g*2)!=0 && cycles%43>=4;
        assign coeff_mem_ready[g]=(coeff_timer[g]==0) && !coeff_rsp[g] &&
                                  (cycles+g*3)%(7+g*2)!=0 && cycles%47>=5;
        always @(posedge clk) begin: memory_model
            integer index;
            if(!rstn) begin
                sig_timer[g]<=0;coeff_timer[g]<=0;
                sig_rsp[g]<=0;coeff_rsp[g]<=0;
                sig_rdata[g]<=0;coeff_rdata[g]<=0;
            end else begin
                sig_rsp[g]<=0;coeff_rsp[g]<=0;
                if(sig_req[g] && sig_ready[g]) begin
                    if(g!=0 || sig_addr[g]<`BP_DDR_CQT_SIGNAL_BYTE_BASE ||
                       sig_addr[g]>=`BP_DDR_CQT_SIGNAL_BYTE_BASE+N*2 || sig_addr[g][0])
                        $fatal(1,"PROTOCOL invalid signal DDR address cfg=%0d address=%h",g,sig_addr[g]);
                    index=(sig_addr[g]-`BP_DDR_CQT_SIGNAL_BYTE_BASE)>>1;
                    if(sig_write[g]) begin
                        signal_memory[index]<=sig_wdata[g];
                        if(monitor_active) sig_writes[g]=sig_writes[g]+1;
                    end else begin
                        sig_rdata[g]<=signal_memory[index]^((NEGATIVE==2) ? 16'h4000 : 16'd0);
                        sig_timer[g]<=2+(cycles%9);
                        if(monitor_active) sig_reads[g]=sig_reads[g]+1;
                    end
                end else if(sig_timer[g]>0) begin
                    sig_timer[g]<=sig_timer[g]-1;
                    if(sig_timer[g]==1) sig_rsp[g]<=1;
                end
                if(coeff_mem_req[g] && coeff_mem_ready[g]) begin
                    index=(coeff_mem_addr[g]-`BP_DDR_NN_MODEL_BYTE_BASE)>>1;
                    if(g==2 || coeff_mem_addr[g][0] || index<33807 || index>52238)
                        $fatal(1,"PROTOCOL invalid coefficient DDR address cfg=%0d address=%h",g,coeff_mem_addr[g]);
                    coeff_rdata[g]<=model[index];
                    coeff_timer[g]<=1+((cycles+3*g)%7);
                    if(monitor_active) coeff_reads[g]=coeff_reads[g]+1;
                end else if(coeff_timer[g]>0) begin
                    coeff_timer[g]<=coeff_timer[g]-1;
                    if(coeff_timer[g]==1) coeff_rsp[g]<=1;
                end
                if(monitor_active) begin
                    if(sig_req[g] && !sig_ready[g]) sig_stalls[g]=sig_stalls[g]+1;
                    if(coeff_mem_req[g] && !coeff_mem_ready[g]) coeff_stalls[g]=coeff_stalls[g]+1;
                    if((g==0 && sig_req[g] && sig_ready[g] && sig_write[g]) ||
                       (g!=0 && local_we[g])) begin
                        if(nw[g]>=NWRITE) $fatal(1,"PROTOCOL extra signal write cfg=%0d",g);
                        signal_writes[g][nw[g]]=(g==0) ?
                            {18'((sig_addr[g]-`BP_DDR_CQT_SIGNAL_BYTE_BASE)>>1),sig_wdata[g]} :
                            {local_waddr[g],local_wdata[g]};
                        nw[g]=nw[g]+1;
                    end
                    if(state[g]==S_DEC_STORE) begin
                        if(nd[g]>=NDEC) $fatal(1,"PROTOCOL extra decimation result cfg=%0d",g);
                        decimated[g][nd[g]]={octave[g],dec_index[g],dec_value[g]};
                        nd[g]=nd[g]+1;
                    end
                    if(mag_we[g]) begin
                        if(nm[g]>=NMAG) $fatal(1,"PROTOCOL extra magnitude cfg=%0d",g);
                        magnitudes[g][nm[g]]={mag_addr[g],mag_data[g]};
                        if(mag_data[g]!==16'd0)
                            frame_nonzero[g][nm[g]/PER_OCT]=frame_nonzero[g][nm[g]/PER_OCT]+1;
                        nm[g]=nm[g]+1;
                    end
                end
            end
        end
    end

    task automatic begin_window(input integer selected_pattern);
        integer c,n,f;
        begin
            @(negedge clk);rstn=0;start=0;win_we=0;monitor_active=0;
            repeat(4) @(negedge clk);
            for(c=0;c<3;c=c+1) begin
                nm[c]=0;nw[c]=0;nd[c]=0;
                sig_reads[c]=0;sig_writes[c]=0;coeff_reads[c]=0;
                sig_stalls[c]=0;coeff_stalls[c]=0;
                for(f=0;f<OCTAVES*FRAMES;f=f+1) frame_nonzero[c][f]=0;
            end
            if(done!==3'b000 || ready!==3'b111 || finished!==3'b000)
                $fatal(1,"PROTOCOL engine run-reset did not clear completion/state");
            window_number=window_number+1;pattern_number=selected_pattern;
            started_cycle=cycles;rstn=1;monitor_active=1;
            for(n=0;n<N;n=n+1) begin
                wait(&ready);
                wait(!modes[0].engine.sig_write_pending);
                @(negedge clk);win_we=1;win_addr=16'(n);win_data=pcm(selected_pattern,n);
                @(negedge clk);win_we=0;
            end
            wait(!modes[0].engine.sig_write_pending);
            @(negedge clk);start=1;
            @(negedge clk);start=0;
        end
    endtask

    task automatic complete_and_compare(input string label,input integer replay_random);
        integer c,n,f,expected_write_address,changed_bins;
        begin
            wait(&finished);
            @(negedge clk);
            for(c=0;c<3;c=c+1) begin
                if(nm[c]!=NMAG || nw[c]!=NWRITE || nd[c]!=NDEC)
                    $fatal(1,"COVERAGE counts cfg=%0d mag=%0d writes=%0d decim=%0d",c,nm[c],nw[c],nd[c]);
                if(sig_reads[c]!=((c==0) ? expected_signal_reads() : 0) ||
                   sig_writes[c]!=((c==0) ? NWRITE : 0) ||
                   coeff_reads[c]!=((c<2) ? NMAG*KTAPS*2 : 0))
                    $fatal(1,"COVERAGE actual accepted DDR counts cfg=%0d signal R/W=%0d/%0d coeff R=%0d",c,sig_reads[c],sig_writes[c],coeff_reads[c]);
                if((c==0 && sig_stalls[c]==0) || (c<2 && coeff_stalls[c]==0))
                    $fatal(1,"COVERAGE independent DDR backpressure missing cfg=%0d",c);
            end
            for(n=0;n<NMAG;n=n+1) begin
                for(c=0;c<3;c=c+1) begin
                    if(magnitudes[c][n][31:16]!==16'(expected_mag_addr(n)))
                        $fatal(1,"MISMATCH magnitude address cfg=%0d item=%0d actual=%h",c,n,magnitudes[c][n]);
                    if((^magnitudes[c][n])===1'bx)
                        $fatal(1,"MISMATCH unknown magnitude cfg=%0d item=%0d",c,n);
                    if(magnitudes[c][n]!==magnitudes[0][n])
                        $fatal(1,"MISMATCH magnitude label=%s cfg=%0d item=%0d DDR=%h local=%h",label,c,n,magnitudes[0][n],magnitudes[c][n]);
                end
                if(replay_random && magnitudes[0][n]!==random_magnitudes[n])
                    $fatal(1,"MISMATCH restart magnitude label=%s item=%0d",label,n);
            end
            for(c=0;c<3;c=c+1)
                for(f=0;f<OCTAVES*FRAMES;f=f+1)
                    if(frame_nonzero[c][f]==0) $fatal(1,"COVERAGE all-zero octave/frame cfg=%0d group=%0d",c,f);
            for(n=0;n<NWRITE;n=n+1) begin
                expected_write_address=(n<N) ? n : (n-N<NDEC-128) ? n-N+128 : n-N-(NDEC-128);
                for(c=0;c<3;c=c+1) begin
                    if(signal_writes[c][n][33:16]!==18'(expected_write_address))
                        $fatal(1,"MISMATCH signal write address cfg=%0d item=%0d",c,n);
                    if(signal_writes[c][n]!==signal_writes[0][n])
                        $fatal(1,"MISMATCH ordered signal write label=%s cfg=%0d item=%0d",label,c,n);
                end
                if(replay_random && signal_writes[0][n]!==random_writes[n])
                    $fatal(1,"MISMATCH restart signal write label=%s item=%0d",label,n);
            end
            for(n=0;n<NDEC;n=n+1) begin
                for(c=0;c<3;c=c+1) begin
                    if((^decimated[c][n])===1'bx)
                        $fatal(1,"MISMATCH unknown internal decimation cfg=%0d item=%0d",c,n);
                    if(decimated[c][n][37:16]!==22'(n))
                        $fatal(1,"MISMATCH internal decimation index cfg=%0d item=%0d",c,n);
                    if(decimated[c][n]!==decimated[0][n])
                        $fatal(1,"MISMATCH internal decimation label=%s cfg=%0d item=%0d",label,c,n);
                end
                if(replay_random && decimated[0][n]!==random_decimated[n])
                    $fatal(1,"MISMATCH restart internal decimation label=%s item=%0d",label,n);
            end
            for(n=0;n<N;n=n+1)
                if(signal_memory[n]!==modes[1].engine.g_local_signal.u_sig_ram.mem[n] ||
                   signal_memory[n]!==modes[2].engine.g_local_signal.u_sig_ram.mem[n])
                    $fatal(1,"MISMATCH final signal RAM item=%0d",n);
            if(label=="extremes")
                for(n=0;n<NMAG;n=n+1) extreme_magnitudes[n]=magnitudes[0][n];
            if(label=="random") begin
                changed_bins=0;
                for(n=0;n<NMAG;n=n+1) begin
                    if(magnitudes[0][n][15:0]!==extreme_magnitudes[n][15:0]) changed_bins=changed_bins+1;
                    random_magnitudes[n]=magnitudes[0][n];
                end
                if(changed_bins==0) $fatal(1,"COVERAGE magnitudes not input-sensitive");
                for(n=0;n<NWRITE;n=n+1) random_writes[n]=signal_writes[0][n];
                for(n=0;n<NDEC;n=n+1) random_decimated[n]=decimated[0][n];
                $display("INPUT_SENSITIVITY changed_magnitudes=%0d total=%0d",changed_bins,NMAG);
            end
            for(c=0;c<3;c=c+1) begin
                nonzero=0;
                for(f=0;f<OCTAVES*FRAMES;f=f+1) nonzero=nonzero+frame_nonzero[c][f];
                $display("WINDOW name=%s pattern=%0d cfg=%0d mag=%0d writes=%0d decim=%0d signal_reads=%0d signal_writes=%0d coeff_reads=%0d signal_stalls=%0d coeff_stalls=%0d nonzero=%0d cycles=%0d",label,pattern_number,c,nm[c],nw[c],nd[c],sig_reads[c],sig_writes[c],coeff_reads[c],sig_stalls[c],coeff_stalls[c],nonzero,cycles-started_cycle);
                fd=$fopen($sformatf("%s/%s_cfg%0d.csv",trace_directory,label,c),"w");
                if(!fd) $fatal(1,"TRACE cannot open ordered evidence");
                for(n=0;n<NMAG;n=n+1)
                    $fdisplay(fd,"magnitude,%0d,%0d,%04h",n,magnitudes[c][n][31:16],magnitudes[c][n][15:0]);
                for(n=0;n<NWRITE;n=n+1)
                    $fdisplay(fd,"signal_write,%0d,%0d,%04h",n,signal_writes[c][n][33:16],signal_writes[c][n][15:0]);
                for(n=0;n<NDEC;n=n+1)
                    $fdisplay(fd,"decimation,%0d,%0d,%04h",n,decimated[c][n][32:16],decimated[c][n][15:0]);
                $fclose(fd);
            end
            monitor_active=0;
        end
    endtask

    initial begin
        if(!$value$plusargs("TRACE_DIR=%s",trace_directory)) trace_directory=".";
        $readmemh("rtl/music/weights/cnn_ddr_blob.mem",model);
        $readmemh("rtl/music/weights/cqt_real.mem",real_rom);
        $readmemh("rtl/music/weights/cqt_imag.mem",imag_rom);
        $readmemh("rtl/music/weights/cqt_lowpass.mem",lowpass_rom);
        $readmemh("rtl/music/weights/cqt_norm_log.mem",norm_rom);
        $readmemh("rtl/music/weights/log2_lut.mem",log_rom);
        for(i=0;i<N;i=i+1) signal_memory[i]=0;
        for(i=0;i<3;i=i+1) begin
            sig_timer[i]=0;coeff_timer[i]=0;nm[i]=0;nw[i]=0;nd[i]=0;
            sig_reads[i]=0;sig_writes[i]=0;coeff_reads[i]=0;
            sig_stalls[i]=0;coeff_stalls[i]=0;
            for(j=0;j<OCTAVES*FRAMES;j=j+1) frame_nonzero[i][j]=0;
        end
        begin_window(0);complete_and_compare("extremes",0);
        begin_window(1);complete_and_compare("random",0);
        begin_window(1);
        wait(coeff_timer[0]>0);
        @(negedge clk);
        $display("ENGINE_CANCEL phase=coefficient_return outstanding=%0d magnitudes=%0d",coeff_timer[0],nm[0]);
        begin_window(1);
        wait(sig_timer[0]>0 && state[0]==S_MAC_WAIT);
        @(negedge clk);
        $display("ENGINE_CANCEL phase=signal_return outstanding=%0d magnitudes=%0d",sig_timer[0],nm[0]);
        begin_window(1);complete_and_compare("restart_reads",1);
        begin_window(1);
        wait(sig_timer[0]>0 && state[0]==S_DEC_WAIT && dec_index[0]>=128);
        @(negedge clk);
        $display("ENGINE_CANCEL phase=decimation_return outstanding=%0d magnitudes=%0d decimation=%0d",sig_timer[0],nm[0],nd[0]);
        begin_window(1);complete_and_compare("restart_decimation",1);
        $display("PASS CQT cross-storage exact: same engine DDR-all/signal-local/signal-coeff-local; 4 complete windows; 3 engine-reset cancellations; real coefficients; ordered magnitudes/writes/decimation");
        $finish;
    end
    initial begin
        repeat(12000000) @(posedge clk);
        $fatal(1,"TIMEOUT CQT cross-storage equivalence");
    end
endmodule
