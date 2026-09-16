`timescale 1ns/1ps
module tb_keyboard_audio;
    reg clk_50m=0,audio_clk=0,reset_n=0,pc_rx=1,g1_rx=1;
    always #10 clk_50m=~clk_50m;
    always #(1000.0/153.6) audio_clk=~audio_clk;
    reg usb_valid=0; reg [17:0] usb_event=0; wire usb_ready;
    wire tick,valid; wire signed [31:0] left,right;
    wire [31:0] deadlines,overflow,drops,underruns,cdc_drop,active;
    wire [447:0] performance;
    gw138k_usb_controlled_audio dut(
        .usb_event_valid(usb_valid),.usb_event_data(usb_event),.usb_event_ready(usb_ready),
        .clk_50m(clk_50m),.audio_clk(audio_clk),.reset_n(reset_n),.midi_rx_i(g1_rx),.pc_uart_rx_i(pc_rx),
        .performance_words_o(performance),.pclk(1'b0),.preset_n(reset_n),.psel(1'b0),.penable(1'b0),
        .pwrite(1'b0),.paddr(12'd0),.pwdata(32'd0),.pstrb(4'd0),
        .sample_ce_o(tick),.sample_valid_o(valid),.audio_left_o(left),.audio_right_o(right),
        .deadline_miss_o(deadlines),.midi_overflow_o(overflow),.note_drop_o(drops),
        .underrun_count_o(underruns),.midi_cdc_drop_o(cdc_drop),.active_mask_o(active));
    integer cycles=0,last_tick=0,frames=0,nonzero=0,expected=0,pc_stalls=0,max_pc_queue=0;
    integer core_on=0,core_off=0,max_active=0;
    always @(posedge audio_clk) if(reset_n) begin
        cycles++;
        if(tick) begin
            if(last_tick && cycles-last_tick!=1600) $fatal(1,"48k cadence");
            last_tick=cycles;
        end
        if(valid) begin frames++; if(left || right) nonzero++; end
        if(deadlines || overflow || drops || underruns || cdc_drop || dut.pc_health)
            $fatal(1,"audio/PC fault: deadline=%0d overflow=%0d drops=%0d underrun=%0d PC=%0h", deadlines,overflow,drops,underruns,dut.pc_health);
        if(dut.u_audio.u_workstation.pc_valid && !dut.u_audio.u_workstation.pc_ready) pc_stalls++;
        if(dut.u_audio.u_workstation.pc_decoder.count>max_pc_queue)
            max_pc_queue=dut.u_audio.u_workstation.pc_decoder.count;
        if(dut.u_audio.voice_count>max_active) max_active=dut.u_audio.voice_count;
        if(dut.u_audio.u_workstation.core_event_valid && dut.u_audio.u_workstation.core_event_ready) begin
            if(dut.u_audio.u_workstation.core_note_on) core_on++; else core_off++;
        end
    end
    task pc_byte(input [7:0] data);
        pc_rx=0; #(1000000000.0/115200);
        for(integer j=0;j<8;j++) begin pc_rx=data[j]; #(1000000000.0/115200); end
        pc_rx=1; #(1000000000.0/115200);
    endtask
    task pc_message(input [7:0] status,input [6:0] a,input [6:0] b);
        pc_byte(status); pc_byte({1'b0,a}); pc_byte({1'b0,b}); expected++;
    endtask
    task g1_message(input [7:0] status,input [6:0] a,input [6:0] b);
        for(integer i=0;i<3;i++) begin
            reg [7:0] value;
            value=i==0?status:i==1?{1'b0,a}:{1'b0,b};
            g1_rx=0; #32000;
            for(integer j=0;j<8;j++) begin g1_rx=value[j]; #32000; end
            g1_rx=1; #32000;
        end
        expected++;
    endtask
    task push_event(input [3:0] kind,input [6:0] a,input [6:0] b);
        @(negedge audio_clk); usb_event={kind,a,b}; usb_valid=1;
        do @(posedge audio_clk); while(!usb_ready);
        @(negedge audio_clk); usb_valid=0; expected++;
    endtask
    task settle;
        #100000;
        if(dut.applied_events!=expected) $fatal(1,"event lost/duplicated expected=%0d actual=%0d",expected,dut.applied_events);
    endtask
    task chord(input bit on);
        pc_message(on?8'h90:8'h80,60,on?100:0);
        pc_message(on?8'h90:8'h80,64,on?100:0);
        pc_message(on?8'h90:8'h80,67,on?100:0);
    endtask
    task drain_voices;
        integer remaining,target,steps;
        remaining=0;
        if(dut.held_notes) $fatal(1,"held notes remain after final Off");
        for(integer i=0;i<32;i++) begin
            if(dut.u_audio.u_workstation.allocated[i]) begin
                if(dut.u_audio.u_workstation.engine.envelope_state[i]!=4 &&
                   dut.u_audio.u_workstation.engine.envelope_state[i]!=0)
                    $fatal(1,"voice %0d not releasing after Off, state=%0d",i,dut.u_audio.u_workstation.engine.envelope_state[i]);
                steps=dut.u_audio.u_workstation.engine.release_step_q24[i];
                target=steps==0?1:(dut.u_audio.u_workstation.engine.envelope_level_q24[i]+steps-1)/steps;
                if(target>remaining) remaining=target;
            end
        end
        // Wait the unchanged envelope's actual remaining samples, not an
        // arbitrary 100 ms silence deadline (flute full release is ~209 ms).
        target=frames+remaining+4;
        wait(frames>=target);@(negedge audio_clk);
        if(active || dut.u_audio.u_workstation.allocated) $fatal(1,"voice failed to retire after release envelope");
    endtask
    initial begin
        #250;reset_n=1;#2000;
        // Existing serial effect order stays active throughout keyboard traffic.
        pc_message(8'hb0,81,7);pc_message(8'hb0,84,2);pc_message(8'hb0,85,0);pc_message(8'hb0,86,1);
        for(integer mode=0;mode<3;mode++) begin
            integer start_on,start_off;
            pc_message(8'hb0,80,mode);settle();
            if(dut.u_audio.mode!=mode) $fatal(1,"mode transition");
            start_on=core_on;start_off=core_off;
            // Genuine short tap: one UART Note On and one Off, no repeat source in FPGA.
            pc_message(8'h90,72,100);#10000000;pc_message(8'h80,72,0);#60000000;
            if(core_on!=start_on+1 || core_off!=start_off+1 || dut.held_notes || active)
                $fatal(1,"short tap/stale voices");
            // Distinct Push and G1 held notes must survive PC repeats and pressure changes.
            fork
                g1_message(8'h90,48,100);
                push_event(1,36,100);
                chord(1);
            join
            #300000000;
            for(integer k=0;k<12;k++) begin
                // Same per-key Off/On ordering as Notes.retrigger, at 80 ms cadence.
                pc_message(8'h80,60,0);pc_message(8'h90,60,100);
                pc_message(8'h80,64,0);pc_message(8'h90,64,100);
                pc_message(8'h80,67,0);pc_message(8'h90,67,100);
                push_event(5,36,k[0]?127:30);
                settle();
                if(!dut.held_notes[36] || !dut.held_notes[48] || !dut.held_notes[60] ||
                   !dut.held_notes[64] || !dut.held_notes[67]) $fatal(1,"held state changed");
                if(dut.u_audio.u_workstation.effect_mask_o!=7 ||
                   dut.u_audio.u_workstation.effect_order_o!=6'b01_00_10) $fatal(1,"effect chain state changed");
                #78337300;
            end
            chord(0);settle();
            if(dut.held_notes!=(128'd1<<36 | 128'd1<<48)) $fatal(1,"PC release affected independent sources");
            push_event(0,36,0);g1_message(8'h80,48,0);settle();
            drain_voices();
            if(dut.held_notes || active || dut.u_audio.u_workstation.allocated)
                $fatal(1,"repeat leaked voices mode=%0d allocated=%h",mode,dut.u_audio.u_workstation.allocated);
            if(core_on!=start_on+42 || core_off!=start_off+42)
                $fatal(1,"note count mode=%0d on=%0d off=%0d",mode,core_on-start_on,core_off-start_off);
            $display("PASS mode=%0d 39 chord note allocations, short tap, independent Push/G1, final allocated=0",mode);
        end
        // Keep the old shared PANIC path, including release-scan backpressure.
        pc_message(8'hb0,64,127);pc_message(8'h90,60,100);#10000000;
        pc_message(8'h80,60,0);pc_message(8'hb0,64,0);settle();drain_voices();
        pc_message(8'h90,60,100);#10000000;pc_message(8'hb0,123,0);settle();drain_voices();
        if(dut.held_notes || active || dut.u_audio.u_workstation.allocated) $fatal(1,"pedal/panic left voices");
        if(nonzero==0) $fatal(1,"no audible digital PCM");
        $display("PASS keyboard UART/CDC/queue/audio frames=%0d nonzero=%0d applied=%0d note_on=%0d note_off=%0d max_active=%0d max_pc_queue=%0d pc_backpressure_cycles=%0d; AE350 stopped, 48k exact, no faults",frames,nonzero,expected,core_on,core_off,max_active,max_pc_queue,pc_stalls);
        $finish;
    end
    initial begin #6000000000; $fatal(1,"timeout"); end
endmodule
