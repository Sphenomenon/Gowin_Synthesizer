`timescale 1ns/1ps
module tb_cnn_demo_audio;
    reg ref50=0,compute=0,dac=0,reset_n=0;
    always #10 ref50=~ref50;
    always #6.510416667 compute=~compute;
    always #40.690104167 dac=~dac;
    reg valid=0,lifecycle=0,cancel=0;reg [17:0] event_data=0;
    wire ready,tick,rendered;wire signed [31:0] left,right;
    wire [31:0] pcm,seq;wire frame;wire [15:0] volume;
    wire [447:0] performance;
    wire bck,ws,din,pa,mclk,i2s_bck,i2s_ws,i2s_data,pdn,smute;
    wire [31:0] frame_pcm;wire physical;
    integer clocks=0,last_tick=0,ticks=0,renders=0,nonzero=0,physical_nonzero=0;
    integer initial_epoch;
    workstation_cnn_demo_audio #(.EXTERNAL_MASTER_VOLUME(1)) dut(
        .usb_event_valid(valid),.usb_lifecycle(lifecycle),.usb_cancel(cancel),.usb_event_data(event_data),.usb_event_ready(ready),
        .clk_50m(ref50),.audio_clk(compute),.reset_n(reset_n),.midi_rx_i(1'b1),.pc_uart_rx_i(1'b1),
        .pclk(ref50),.preset_n(reset_n),.psel(1'b0),.penable(1'b0),.pwrite(1'b0),.paddr(12'd0),.pwdata(32'd0),.pstrb(4'd0),
        .performance_words_o(performance),.master_volume_o(volume),
        .hp_bck(bck),.hp_ws(ws),.hp_din(din),.pa_en(pa),
        .sample_ce_o(tick),.sample_valid_o(rendered),.audio_left_o(left),.audio_right_o(right),
        .delay_mem_clk_i(ref50),.delay_mem_rst_ni(reset_n),.delay_dwr_pop_i(1'b0),.delay_drd_push_i(1'b0),.delay_drd_data_i(65'd0));
    // Observe actual reference serial bits, then feed the maintained board DAC
    // adapter; no synthetic replacement for the serialized sample is used.
    pt8211_observer serial_pcm(.clk(compute),.reset_n(reset_n),.bck(bck),.ws(ws),.din(din),
        .frame_reference(32'd0),.pcm_pair(pcm),.sample_valid(frame),.trigger_reference());
    workstation_fpc_audio physical_audio(
        .clk_50m_i(ref50),.dac_reference_clk_i(dac),.audio_clk_i(compute),.rst_ni(reset_n),.audio_rst_ni(reset_n),
        .master_volume_i(volume),.sample_valid_i(frame),.enable_i(!pa),.pcm_pair_i(pcm),
        .mclk_o(mclk),.bck_o(i2s_bck),.lrck_o(i2s_ws),.data_o(i2s_data),.pdn_no(pdn),.smute_o(smute),
        .frame_valid_o(physical),.frame_pcm_o(frame_pcm),.frame_sequence_o(seq));
    always @(posedge compute)if(reset_n)begin
        clocks=clocks+1;
        if(tick)begin
            if(ticks>0 && clocks-last_tick!=1600)$fatal(1,"sample schedule stalled delta=%0d",clocks-last_tick);
            ticks=ticks+1;last_tick=clocks;
        end
        if(rendered)begin renders=renders+1;if(left!==0 || right!==0)nonzero=nonzero+1;end
    end
    always @(posedge dac)if(physical && frame_pcm!=0 && !smute)physical_nonzero=physical_nonzero+1;
    task send(input [17:0] value,input life);
        begin
            @(negedge compute);event_data=value;valid=1;lifecycle=life;cancel=life;
            do @(posedge compute);while(!ready);
            @(negedge compute);valid=0;lifecycle=0;cancel=0;
        end
    endtask
    initial begin
        #1000;reset_n=1;
        send({4'd15,7'd1,7'd1},1);
        repeat(3000)@(posedge compute);
        initial_epoch=performance[287:278];
        send({4'd1,7'd60,7'd100},0);
        // Retired vector/mode controls must not redirect or silence this
        // candidate's authoritative basic-instrument state.
        send({4'd2,7'd90,7'd127},0);
        send({4'd2,7'd80,7'd0},0);
        wait(ticks>=1200);
        if(nonzero<100 || physical_nonzero<20)$fatal(1,"missing real synth/DAC audio n=%0d dac=%0d",nonzero,physical_nonzero);
        send({4'd0,7'd60,7'd0},0);
        send({4'd2,7'd120,7'd0},0);
        repeat(4000)@(posedge compute);
        if(performance[287:278]==initial_epoch)$fatal(1,"PANIC epoch did not advance");
        if(performance[223:96]!==128'd0)$fatal(1,"PANIC did not clear original held state");
        wait(ticks>=1240);
        if(left!==0 || right!==0)$fatal(1,"PANIC replayed old audio");
        send({4'd1,7'd64,7'd100},0);
        wait(ticks>=1300);
        send({4'd15,7'd0,7'd0},1);
        wait(ticks>=1340);
        if(performance[223:96]!==128'd0)$fatal(1,"detach did not clear held notes");
        $display("PASS CNN demo audio: ticks=%0d renders=%0d nonzero=%0d DAC_nonzero=%0d PANIC/detach/sample_schedule",ticks,renders,nonzero,physical_nonzero);
        $finish;
    end
    initial begin #40000000;$fatal(1,"timeout");end
endmodule
