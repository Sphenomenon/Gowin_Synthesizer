`timescale 1ns/1ps
module tb_generic_midi;
    reg clk=0,aclk=0,rn=0,sel=0,wr=0,consume=1;
    always #(1000.0/96)clk=~clk;
    always #(1000.0/153.6)aclk=~aclk;
    reg [7:0] addr=0;reg [31:0] wd=0;wire [31:0] rd;wire ready,av,ar;
    wire [17:0] ae;wire [223:0] telemetry;
    wire [127:0] held;wire [9:0] epoch;
    reg [447:0] feedback;
    always @* begin feedback=0;feedback[287:278]=epoch;feedback[223:96]=held;end
    push2_usb_a_control dut(.clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),
        .feedback_clk(aclk),.feedback_reset_n(rn),.performance_words(feedback),
        .display_meta_data(64'd0),.display_meta_valid(1'b0),
        .service_state_data(34'd0),.service_state_valid(1'b0),
        .select(sel),.write(wr),.address(addr),.wdata(wd),.ready(ready),.rdata(rd),
        .audio_valid(av),.audio_ready(ar && consume),.audio_event(ae),.telemetry(telemetry));
    reg sample_ce=0;integer divider=0,frames=0,nonzero=0;
    wire sample_valid;wire signed [31:0] left,right;
    wire [31:0] active,deadline,overflow,drops;
    gw138k_event_workstation audio(.clk_i(aclk),.rst_ni(rn),
        .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
        .held_notes_o(held),.applied_events_o(),.pc_overflow_o(),.control_options_o(),.panic_epoch_o(epoch),
        .cpu_event_valid_i(av && consume),.cpu_event_i(ae),.cpu_event_ready_o(ar),
        .sample_ce_i(sample_ce),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
        .sample_valid_o(sample_valid),.left_o(left),.right_o(right),.synth_valid_o(),.synth_o(),
        .active_mask_o(active),.active_voice_count_o(),.mode_o(),.pitch_q20_o(),
        .deadline_miss_o(deadline),.midi_overflow_o(overflow),.note_drop_o(drops),.clip_o(),
        .synth_gain_o(),.pcm_gain_o(),.route_o(),.profile_o(),.effect_mask_o(),.effect_order_o(),
        .panel_event_valid_o(),.panel_command_o());
    reg silence=0;
    always @(posedge aclk)if(rn)begin
        sample_ce<=0;
        if(divider==1599)begin divider<=0;sample_ce<=1;end else divider<=divider+1;
        if(sample_valid)begin
            frames++;if(left || right)nonzero++;
            if(silence && (left || right))$fatal(1,"PCM after disconnect PANIC");
        end
        if(deadline || overflow || drops)$fatal(1,"audio fault");
    end
    reg [17:0] expected[0:1023],vectors[0:7];integer wp=0,rp=0,stalls=0,starts=0;
    always @(posedge aclk)if(rn && av && ar && consume)begin
        if(rp>=wp || ae!==expected[rp])$fatal(1,"event %0d got=%h wanted=%h",rp,ae,expected[rp]);
        rp++;
    end
    // Check the actual synth boundary, not just the input FIFO.
    always @(posedge aclk)if(rn && audio.core_event_valid && audio.core_event_ready && audio.core_note_on && starts<4)begin
        if({audio.core_note,audio.core_velocity}!==vectors[starts][13:0])
            $fatal(1,"core changed generic note/velocity %0d",starts);
        starts++;
    end
    task expect_event(input [17:0] e);begin expected[wp]=e;wp++;end endtask
    task put(input [7:0] address,input [31:0] data);
        @(negedge clk);sel=1;wr=1;addr=address;wd=data;
        @(posedge clk);while(!ready)begin stalls++;@(posedge clk);end
        @(negedge clk);sel=0;
    endtask
    task generic_event(input [17:0] e);begin expect_event(e);put('h54,{14'd0,e});end endtask
    task wait_frames(input integer n);
        integer target;begin target=frames+n;wait(frames>=target);@(negedge aclk);end
    endtask
    initial begin
        $readmemh("generic_events.mem",vectors);
        #250;rn=1;repeat(20)@(negedge clk);put(0,3);
        for(integer i=0;i<4;i++)generic_event(vectors[i]);
        wait_frames(32);
        if(starts!=4 || !held[0] || !held[24] || !held[100] || !held[127] || !nonzero)
            $fatal(1,"generic notes did not reach synth/PCM");
        if(dut.packet_valid || dut.cv || dut.commands || dut.held || dut.frames)
            $fatal(1,"generic mode activated Push render/LED/map");
        for(integer i=4;i<8;i++)generic_event(vectors[i]);
        wait_frames(2);if(held)$fatal(1,"normal/velocity-zero note release failed");
        // Queue full must backpressure MMIO, preserve every event and allow a
        // queued disconnect PANIC to drain after pending generic notes.
        @(negedge aclk);consume=0;
        fork
            begin
                for(integer i=0;i<80;i++)begin
                    generic_event({4'd1,7'd24,7'd2});generic_event({4'd0,7'd24,7'd0});
                end
            end
            begin repeat(10000)@(negedge clk);consume=1;end
        join
        wait(rp==wp);if(stalls<100)$fatal(1,"FIFO backpressure not exercised");
        generic_event({4'd2,7'd64,7'd127}); // sustain must not retain disconnected notes
        generic_event({4'd1,7'd100,7'd2});wait_frames(4);
        if(!held[100] || !audio.sustain)$fatal(1,"disconnect setup");
        @(negedge aclk);consume=0;
        for(integer i=0;i<64;i++)generic_event({4'd2,7'd7,7'd100});
        expect_event({4'd2,7'd120,7'd0});put(0,0);
        repeat(20)@(negedge clk);consume=1;
        wait(rp==wp);wait(epoch==1);wait_frames(2);
        if(held || active || audio.sustain || audio.deferred)$fatal(1,"disconnect left notes");
        silence=1;wait_frames(8);silence=0;
        repeat(5000)@(negedge clk);put(0,3);
        generic_event({4'd1,7'd0,7'd1});wait_frames(3);
        if(!held[0])$fatal(1,"generic reconnect");
        expect_event({4'd2,7'd120,7'd0});put(0,0);wait(epoch==2);
        repeat(5000)@(negedge clk);put(0,1);repeat(20)@(negedge clk);
        if(!dut.packet_valid || dut.packet_length!=12 ||
           dut.led.bytes_q[95:0]!==96'hf7000a0701011d042100f004)$fatal(1,"Push init not restored");
        expect_event({4'd1,7'd60,7'd30});put(4,32'h023c9009);wait_frames(3);
        if(!held[60] || dut.velocity!=30)$fatal(1,"Push velocity curve changed");
        expect_event({4'd5,7'd60,7'd31});put(4,32'h033ca00a);
        expect_event({4'd0,7'd60,7'd0});put(4,32'h003c9009);wait_frames(3);
        if(held)$fatal(1,"Push velocity zero release changed");
        wait(rp==wp);
        $display("PASS generic MMIO/CDC/audio: %0d ordered events, %0d stalls, exact low/high note velocities at synth, PCM, release, sustain disconnect, reconnect, Push init/force/aftertouch preserved",rp,stalls);
        $finish;
    end
    initial begin #100000000;$fatal(1,"timeout frames=%0d rp=%0d wp=%0d",frames,rp,wp);end
endmodule
