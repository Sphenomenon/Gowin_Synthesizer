`timescale 1ns/1fs
// Installed official Gowin primitives; run scripts/check_tmds_clock.py.
module tmds_clock_case #(parameter real PCLK_ROUTE_NS=0.0) (input wire gsr_n, output reg finished=0);
    localparam real UI=1000.0/1485.0;
    reg control_clk=0, oscillator=0, reset_n=0, qualified=0, gate=0;
    always #10 control_clk=~control_clk;
    always #UI oscillator=~oscillator;
    wire reset_low, serializer_reset, enable, fclk, raw_pclk;
    reg pclk;
    wire [1:0] clock_pair, blue_pair, green_pair, red_pair;
    video_serializer_startup startup(control_clk,reset_n,qualified,reset_low,enable,serializer_reset);
    always @(negedge oscillator or negedge enable) if(!enable) gate<=0; else gate<=1;
    assign fclk=oscillator & gate;
    CLKDIV #(.DIV_MODE("5")) divider(raw_pclk,1'b0,fclk,reset_low);
    // Ideal and typ/max routed PCLK phases of the first board image.
    // This is a phase sweep, not a full SDF/analog board simulation.
    // Transport every edge; an inertial continuous assignment would suppress
    // the 2.694ns low pulse when the routed delay is 2.775ns.
    always @(raw_pclk) pclk <= #(PCLK_ROUTE_NS) raw_pclk;
    reg [3:0] pixel_reset_pipe=0;
    always @(posedge pclk or negedge enable)
        if(!enable) pixel_reset_pipe<=0;
        else pixel_reset_pipe<={pixel_reset_pipe[2:0],1'b1};
    wire encoder_reset=!pixel_reset_pipe[3];
    reg den=0, hs=0, vs=0;
    reg [23:0] rgb=24'h13579b;
    dvi_tx_top dut(pclk,fclk,encoder_reset,serializer_reset,den,hs,vs,rgb,
                   clock_pair,blue_pair,green_pair,red_pair);
    integer stimulus=0;
    always @(negedge pclk or posedge encoder_reset)
        if(encoder_reset) begin stimulus=0;den=0;hs=0;vs=0;rgb=24'h13579b; end
        else begin
            stimulus=stimulus+1; den=(stimulus%9>=4); {vs,hs}=stimulus%4;
            rgb={rgb[22:0],rgb[23]^rgb[22]^rgb[21]^rgb[16]};
        end
    // Independent bit-by-bit TMDS reference; no DUT encoder signals are used.
    task reference_encode(input bit active,input [7:0] value,input [1:0] control,
                          inout integer disparity,output reg [9:0] result);
        integer ones,j,balance;
        reg [8:0] qm;
        begin
            if(!active) begin
                case(control)
                    0:result=10'b1101010100; 1:result=10'b0010101011;
                    2:result=10'b0101010100; 3:result=10'b1010101011;
                endcase
                disparity=0;
            end else begin
                ones=0; for(j=0;j<8;j=j+1) ones=ones+value[j];
                qm[8]=!(ones>4 || (ones==4 && !value[0])); qm[0]=value[0];
                for(j=1;j<8;j=j+1) qm[j]=qm[j-1]^value[j]^!qm[8];
                ones=0; for(j=0;j<8;j=j+1) ones=ones+qm[j]; balance=2*ones-8;
                if(disparity==0 || balance==0) begin
                    result={~qm[8],qm[8],qm[8]?qm[7:0]:~qm[7:0]};
                    disparity=disparity+(qm[8]?balance:-balance);
                end else if((disparity>0 && balance>0)||(disparity<0 && balance<0)) begin
                    result={1'b1,qm[8],~qm[7:0]}; disparity=disparity+2*qm[8]-balance;
                end else begin
                    result={1'b0,qm[8],qm[7:0]}; disparity=disparity-2*(!qm[8])+balance;
                end
            end
        end
    endtask
    reg [9:0] expected[0:2][0:511];
    integer disparity[0:2];
    integer pixel_count=0,lane;
    reg [3:0] controls_seen=0;
    always @(posedge pclk or posedge encoder_reset)
        if(encoder_reset) begin
            pixel_count=0;controls_seen=0;
            for(lane=0;lane<3;lane=lane+1) disparity[lane]=0;
        end else begin
            if(pixel_count>=512) $fatal(1,"golden queue overflow");
            for(lane=0;lane<3;lane=lane+1)
                reference_encode(den,rgb[lane*8+:8],lane==0?{vs,hs}:2'b00,
                                 disparity[lane],expected[lane][pixel_count]);
            if(!den) controls_seen[{vs,hs}]=1;
            pixel_count=pixel_count+1;
        end
    reg previous_clock=0;
    integer bit_position=-1,checked=0,source_index,k,decoded_words=0;
    reg [9:0] decoded[0:2];
    // A single physical clock-lane falling edge establishes D0 for all lanes.
    // No bit-phase/per-lane search or data-dependent alignment is used.
    always @(fclk or posedge serializer_reset)
        if(serializer_reset) begin previous_clock=0;bit_position=-1;checked=0;decoded_words=0; end
        else if(enable) begin
            #0.0001;
            if(clock_pair[0]!==~clock_pair[1] || blue_pair[0]!==~blue_pair[1] ||
               green_pair[0]!==~green_pair[1] || red_pair[0]!==~red_pair[1])
                $fatal(1,"TMDS differential polarity mismatch");
            if(previous_clock===1'b1 && clock_pair[1]===1'b0) begin
                if(bit_position!=-1 && bit_position!=10) $fatal(1,"TMDS period is not 10 UI");
                bit_position=0;
            end
            if(bit_position>=0 && bit_position<10) begin
                if(clock_pair[1] !== (bit_position>=5)) $fatal(1,"TMDS clock is not five low/five high UI");
                decoded[0][bit_position]=blue_pair[1];
                decoded[1][bit_position]=green_pair[1];
                decoded[2][bit_position]=red_pair[1];
                if(bit_position==9) begin
                    // With the documented common stopped-clock startup:
                    // FCLK edges n1,n6,... are raw PCLK rising edges; the
                    // first forwarded-clock falling edge is n15. Four PCLK
                    // reset stages admit the first source at n21 (+route).
                    // Encoder N->N+3, next PCLK OSER capture, and two OSER
                    // word stages emit its D0 at n50: clock word index 7.
                    // Thus discard exactly seven complete startup words.
                    // No search or per-phase latency adjustment is allowed.
                    source_index=decoded_words-7;
                    if(source_index>=0) begin
                        for(k=0;k<3;k=k+1)
                            if(decoded[k]!==expected[k][source_index])
                                $fatal(1,"TMDS word mismatch delay=%0.3f lane=%0d source=%0d got=%03h expected=%03h",PCLK_ROUTE_NS,k,source_index,decoded[k],expected[k][source_index]);
                        checked=checked+1;
                    end
                    decoded_words=decoded_words+1;
                end
                bit_position=bit_position+1;
            end
            previous_clock=clock_pair[1];
        end
    task check_interval(input real actual, expected_value,input [255:0] label_text);
        begin
            if(actual<expected_value-0.00005 || actual>expected_value+0.00005)
                $fatal(1,"%0s %.9f ns, expected %.9f ns",label_text,actual,expected_value);
        end
    endtask
    integer run;
    realtime edge_time,raw_high,raw_low,clock_high,clock_low;
    initial begin
        wait(!gsr_n);wait(gsr_n); #13;reset_n=1;
        for(run=0;run<3;run=run+1) begin
            #17;qualified=1; wait(checked>=10);
            @(posedge pclk);edge_time=$realtime;
            @(negedge pclk);raw_high=$realtime-edge_time;edge_time=$realtime;
            @(posedge pclk);raw_low=$realtime-edge_time;
            check_interval(raw_high,6*UI,"CLKDIV /5 high"); check_interval(raw_low,4*UI,"CLKDIV /5 low");
            @(posedge clock_pair[1]);edge_time=$realtime;
            @(negedge clock_pair[1]);clock_high=$realtime-edge_time;edge_time=$realtime;
            @(posedge clock_pair[1]);clock_low=$realtime-edge_time;
            check_interval(clock_high,5*UI,"TMDS high"); check_interval(clock_low,5*UI,"TMDS low");
            check_interval(clock_high+clock_low,10*UI,"TMDS period");
            wait(checked>=120);
            if(controls_seen!=4'b1111) $fatal(1,"missing blue-channel sync control cases");
            $display("PASS TMDS run=%0d PCLK_delay=%0.3f ns: CLKDIV 60/40, output 50/50, 10 UI, 120 RGB words at fixed clock edge",run,PCLK_ROUTE_NS);
            if(run==0) qualified=0; else reset_n=0;
            #41;
            if(enable!==0 || serializer_reset!==1 || clock_pair[1]!==0) $fatal(1,"clock/reset did not stop during restart");
            reset_n=1;
        end
        finished=1;
    end
endmodule
module tb_tmds_clock;
    reg gsr_n=1;
    GSR GSR(gsr_n);
    wire [2:0] finished;
    tmds_clock_case #(.PCLK_ROUTE_NS(0.000)) ideal(gsr_n,finished[0]);
    tmds_clock_case #(.PCLK_ROUTE_NS(2.041)) routed_typ(gsr_n,finished[1]);
    tmds_clock_case #(.PCLK_ROUTE_NS(2.775)) routed_max(gsr_n,finished[2]);
    initial begin
        // Explicit assertion edge initializes the clock-stopped official
        // primitive models; a time-zero constant alone leaves reset_0 X.
        #1;gsr_n=0;#20;gsr_n=1;wait(&finished);
        $display("PASS official Gowin TMDS clock: all 9 startup/phase cases");$finish;
    end
    initial begin #100000;$fatal(1,"TMDS primitive test timed out");end
endmodule
