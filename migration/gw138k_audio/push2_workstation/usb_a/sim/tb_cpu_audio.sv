`timescale 1ns/1ps
module tb_cpu_audio;
    reg usb_clk=0,clk_50m=0,audio_clk=0,reset_n=0;
    always #(1000.0/96)usb_clk=~usb_clk;
    always #(1000.0/153.6)audio_clk=~audio_clk;
    always #10 clk_50m=~clk_50m;
    wire select,write,ready;wire [7:0] address;wire [31:0] wd,rd;
    wire av,ar;wire [17:0] ae;wire [223:0] telemetry;wire [447:0] performance;
    tri dp,dn;
    iosys2 host(.clk(usb_clk),.resetn(reset_n),.uart_rx(1'b1),.uart_tx(),.usb_dp(dp),.usb_dm(dn),
        .mmio_select(select),.mmio_write(write),.mmio_address(address),.mmio_wdata(wd),.mmio_ready(ready),.mmio_rdata(rd));
    push2_usb_a_control push(.clk(usb_clk),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(reset_n),
        .feedback_clk(audio_clk),.feedback_reset_n(reset_n),.performance_words(performance),
        .select(select),.write(write),.address(address),.wdata(wd),.ready(ready),.rdata(rd),
        .audio_valid(av),.audio_ready(ar),.audio_event(ae),.telemetry(telemetry));
    wire tick,valid;wire signed [31:0] left,right;
    wire [31:0] deadlines,overflow,drops,underruns,cdc_drop;
    // AE350 bus deliberately stopped for the entire test.
    gw138k_usb_controlled_audio audio(.usb_event_valid(av),.usb_event_ready(ar),.usb_event_data(ae),
        .clk_50m(clk_50m),.audio_clk(audio_clk),.reset_n(reset_n),.midi_rx_i(1'b1),.pc_uart_rx_i(1'b1),
        .performance_words_o(performance),.pclk(1'b0),.preset_n(reset_n),.psel(1'b0),.penable(1'b0),
        .pwrite(1'b0),.paddr(12'd0),.pwdata(32'd0),.pstrb(4'd0),
        .sample_ce_o(tick),.sample_valid_o(valid),.audio_left_o(left),.audio_right_o(right),
        .deadline_miss_o(deadlines),.midi_overflow_o(overflow),.note_drop_o(drops),
        .underrun_count_o(underruns),.midi_cdc_drop_o(cdc_drop));
    integer cycles=0,last_tick=0,frames=0,nonzero=0,lc=0,rc=0;
    always @(posedge audio_clk)if(reset_n)begin
        cycles++;
        if(tick)begin
            if(last_tick && cycles-last_tick!=1600)$fatal(1,"48k cadence changed");last_tick=cycles;
        end
        if(valid)begin frames++;if(left || right)nonzero++;if(left)lc++;if(right)rc++;end
        if(deadlines || overflow || drops || underruns || cdc_drop)$fatal(1,"audio fault");
    end
    task phase(input integer n);
        integer target;
        begin wait(push.frames==n);target=frames+24;wait(frames>=target);@(negedge audio_clk);end
    endtask
    initial begin
        #250;reset_n=1;
        phase(1);
        if(!audio.held_notes[60] || !nonzero || audio.control_state[9:0]!==10'h007 ||
           audio.u_audio.u_workstation.vibrato_depth!=63 || audio.u_audio.u_workstation.glide_cc!=63 ||
           audio.u_audio.u_workstation.bend_index!=130)$fatal(1,"CPU MMIO -> Push -> actual synth/expression failed");
        phase(2);if(left || right)$fatal(1,"mute route");
        phase(3);if(right || !left)$fatal(1,"left route");
        phase(4);if(left || !right)$fatal(1,"right route");
        phase(5);if(audio.control_state[4:3]!=1)$fatal(1,"mode B");
        phase(6);if(audio.control_state[4:3]!=2)$fatal(1,"mode C");
        for(integer i=0;i<5;i++)begin phase(10+i);if(audio.control_state[9:7]!=i)$fatal(1,"timbre %0d",i);end
        phase(20);if(audio.held_notes)$fatal(1,"release/panic stuck notes");
        phase(21);if(push.out_errors!=32'h600d)$fatal(1,"Vex MMIO reads failed: %h",push.out_errors);
        $display("PASS Vex CPU/RAM/MMIO -> Push map/async FIFO -> original synth/effects/PCM: %0d frames, %0d nonzero, ABC/5 sounds/FX7/vibrato/glide/bend/routes/release; AE350 clock stopped; exact 48k, no audio fault",frames,nonzero);
        $finish;
    end
    initial begin #1200000000;$fatal(1,"timeout phase=%d PC=%h",push.frames,host.ibus_cmd_pc);end
endmodule
