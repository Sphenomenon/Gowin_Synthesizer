`timescale 1ns/1ps
// Real MMIO -> mapper/FIFO/CDC -> audio core. No renderer/frame completion.
module tb_workstation_attach;
    reg clk=0,aclk=0,rn=0,sel=0,wr=0,consume=1;
    always #(1000.0/96)clk=~clk;
    always #(1000.0/153.6)aclk=~aclk;
    reg [7:0] addr=0;reg [31:0] wd=0;wire [31:0] rd;wire ready,av,ar;
    wire audio_lifecycle,audio_cancel;
    wire [17:0] ae,merged_event;wire merged_valid,core_ready;wire [127:0] held;wire [9:0] epoch;
    wire [15:0] gain;wire [5:0] voices;wire [2:0] profile,fx;
    wire [1:0] mode,route;wire [31:0] options,tf_control;
    reg [447:0] feedback;
    always @* begin
        feedback=0;feedback[63:32]={gain,voices,profile,route,mode,fx};
        feedback[255:224]=options;feedback[287:278]=epoch;feedback[223:96]=held;
    end
    push2_usb_a_control dut(.clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),
        .feedback_clk(aclk),.feedback_reset_n(rn),.performance_words(feedback),
        .display_meta_data(64'd0),.display_meta_valid(1'b0),
        .service_state_data(34'd0),.service_state_valid(1'b0),
        .score_valid(1'b0),.analysis_done(1'b0),.score_note(7'd0),
        .playlist_valid(1'b0),.playlist_word(16'd0),
        .select(sel),.write(wr),.address(addr),.wdata(wd),.ready(ready),.rdata(rd),
        .audio_valid(av),.audio_ready(ar && consume),.audio_event(ae),.audio_lifecycle(audio_lifecycle),.audio_cancel(audio_cancel),.telemetry());
    // Match the actual workstation's additional USB/CPU registered merge.
    gw138k_usb_lifecycle_merge #(.EXPLICIT_LIFECYCLE(1)) outer_merge(.clk(aclk),.reset_n(rn),
        .g1_valid(av && consume),.g1_lifecycle(audio_lifecycle),.g1_cancel(audio_cancel),.g1_data(ae),.g1_ready(ar),
        .pc_valid(1'b0),.pc_data(18'd0),.pc_ready(),
        .cpu_valid(1'b0),.cpu_data(18'd0),.cpu_ready(),
        .event_valid(merged_valid),.event_data(merged_event),.event_ready(core_ready));
    reg sample_ce=0;integer divider=0,frames=0,nonzero=0,left_nonzero=0,right_nonzero=0;
    wire sample_valid;wire signed [31:0] left,right;
    wire [31:0] active,deadline,overflow,drops;
    gw138k_event_workstation audio(.clk_i(aclk),.rst_ni(rn),
        .midi_byte_valid_i(1'b0),.midi_byte_i(8'd0),.pc_byte_valid_i(1'b0),.pc_byte_i(8'd0),
        .held_notes_o(held),.applied_events_o(),.pc_overflow_o(),.control_options_o(options),.panic_epoch_o(epoch),
        .cpu_event_valid_i(merged_valid),.cpu_event_i(merged_event),.cpu_event_ready_o(core_ready),
        .sample_ce_i(sample_ce),.pcm_left_i(32'sd0),.pcm_right_i(32'sd0),
        .sample_valid_o(sample_valid),.left_o(left),.right_o(right),.synth_valid_o(),.synth_o(),
        .active_mask_o(active),.active_voice_count_o(voices),.mode_o(mode),.pitch_q20_o(),
        .deadline_miss_o(deadline),.midi_overflow_o(overflow),.note_drop_o(drops),.clip_o(),
        .synth_gain_o(gain),.pcm_gain_o(),.route_o(route),.profile_o(profile),.effect_mask_o(fx),.effect_order_o(),
        .panel_event_valid_o(),.panel_command_o(),.tf_scope_control_o(tf_control),
        .delay_mem_clk_i(aclk),.delay_mem_rst_ni(rn),.delay_dwr_pop_i(1'b0),
        .delay_drd_push_i(1'b0),.delay_drd_data_i(65'd0));
    always @(posedge aclk)if(rn)begin
        sample_ce<=0;
        if(divider==1599)begin divider<=0;sample_ce<=1;end else divider<=divider+1;
        if(sample_valid)begin
            frames++;if(left || right)nonzero++;
            if(left)left_nonzero++;if(right)right_nonzero++;
        end
        if(deadline || overflow || drops)$fatal(1,"audio fault deadline=%0d overflow=%0d drops=%0d",deadline,overflow,drops);
    end
    reg check_defaults_on_note=0,watch_order=0;
    reg [17:0] expected[0:31];integer wp=0,rp=0,starts=0,initializations=0;
    reg [31:0] mapped_before;
    always @(posedge aclk)if(rn && av && ar && consume && ae[17:14]!=15)begin
        if(audio.attach_initializing)$fatal(1,"device event passed initialization");
        if(watch_order)begin
            if(rp>=wp || ae!==expected[rp])$fatal(1,"mixed order %0d got=%h expected=%h",rp,ae,expected[rp]);
            rp++;
        end
    end
    always @(posedge aclk)if(rn && audio.core_event_valid && audio.core_event_ready && audio.core_note_on)begin
        starts++;
        if(check_defaults_on_note)begin defaults();initializations++;end
        if(audio.attach_initializing)$fatal(1,"note reached engine during initialization");
    end
    task automatic defaults;
        if(mode!=2 || profile!=0 || gain!=32768 || fx!=0 || !audio.effect_master ||
           audio.bend_index!=128 || audio.sustain || audio.expression_gain!=32768 ||
           audio.vibrato_depth || audio.glide_cc || route || audio.scope_enable ||
           tf_control[13:12] || audio.cue_running || audio.mode_pending)
            $fatal(1,"attach defaults incomplete mode=%0d profile=%0d gain=%0d fx=%0d master=%0d tf=%h scope=%0d",
                mode,profile,gain,fx,audio.effect_master,tf_control,audio.scope_enable);
    endtask
    task automatic put(input [7:0] address,input [31:0] data);
        @(negedge clk);sel=1;wr=1;addr=address;wd=data;
        @(posedge clk);while(!ready)@(posedge clk);
        @(negedge clk);sel=0;
    endtask
    task automatic midi(input integer kind,a,b);
        put('h54,{14'd0,4'(kind),7'(a),7'(b)});
    endtask
    task automatic want(input integer kind,a,b);
        expected[wp]={4'(kind),7'(a),7'(b)};wp++;
    endtask
    task automatic samples(input integer n);
        integer target;target=frames+n;wait(frames>=target);@(negedge aclk);
    endtask
    task automatic detached;
        integer old_epoch;old_epoch=epoch;put(0,0);wait(epoch!=old_epoch);
        repeat(8)@(negedge aclk);
        if(held || audio.sustain || audio.deferred || audio.event_valid)$fatal(1,"stale event survived detach");
    endtask
    task automatic dirty(input integer source);
        // A plain generic device preserves existing functionality/defaults.
        put(0,3);wait(dut.input_settled);samples(2);
        midi(2,80,0);midi(3,0,0);midi(2,7,19);midi(2,11,23);
        midi(4,13,9);midi(2,64,127);midi(2,1,77);midi(2,5,51);
        midi(2,82,3);midi(2,81,7);midi(2,88,127);
        samples(2);
        if(mode!=0 || profile!=4 || route!=3 || audio.effect_master)$fatal(1,"dirty setup");
        if(source==1)midi(2,104,127); // playing TF, or live vector/cue
        else begin midi(2,90,127);midi(2,96,127);end
        samples(2);
        if(source==1 ? !tf_control[13] : !audio.cue_running)$fatal(1,"source setup");
        detached();
    endtask
    integer feedback_file,feedback_rows=0;
    task automatic get(input [7:0] address,output [31:0] value);
        @(negedge clk);sel=1;wr=0;addr=address;
        @(posedge clk);while(!ready)@(posedge clk);
        value=rd;@(negedge clk);sel=0;
    endtask
    task automatic feedback_row(input integer expected_mode,expected_voices,expected_route,expected_glide,expected_sustain);
        reg [31:0] cs,op,nv;
        // Let the real 4096-cycle audio->USB feedback mailbox publish the
        // applied state. Reading through the physical MMIO bridge is required.
        samples(10);get('h10,cs);get('h14,op);get('h24,nv);
        if(mode!=expected_mode || voices!=expected_voices || route!=expected_route ||
           audio.glide_cc!=expected_glide || audio.sustain!=expected_sustain)
            $fatal(1,"audio feedback scenario state mismatch row=%0d",feedback_rows);
        if(cs!={gain,voices,profile,route,mode,fx} || op!=options)
            $fatal(1,"audio feedback has not reached real MMIO row=%0d cs=%h",feedback_rows,cs);
        $fwrite(feedback_file,"%0d %08h %08h %08h %0d %0d %0d %0d %0d\n",
            feedback_rows,cs,op,nv,expected_mode,expected_voices,expected_route,expected_glide,expected_sustain);
        feedback_rows++;
    endtask
    task automatic feedback_scenarios;
        integer release_frames;
        feedback_file=$fopen("audio_feedback.txt","w");if(!feedback_file)$fatal(1,"feedback file open");
        put(0,7);wait(dut.input_settled);feedback_row(2,0,0,0,0);
        midi(2,80,0);feedback_row(0,0,0,0,0);
        midi(1,48,100);midi(1,52,100);feedback_row(0,2,0,0,0);
        // CC89 is a request. Until real voices release, the page must still
        // show A even though the pending target is B.
        midi(2,89,1);feedback_row(0,2,0,0,0);
        if(!audio.mode_pending || audio.requested_mode!=1)$fatal(1,"mode did not remain pending");
        midi(2,5,73);midi(2,64,127);midi(0,48,0);feedback_row(0,2,0,73,1);
        if(held[48] || !held[52] || !audio.deferred[48])$fatal(1,"sustain-held voice vs physical held state");
        for(integer r=0;r<4;r++)begin
            midi(2,82,7'(r));samples(2);left_nonzero=0;right_nonzero=0;
            feedback_row(0,2,r,73,1);
            if((r==0 && (!left_nonzero || !right_nonzero)) ||
               (r==1 && (!left_nonzero || right_nonzero)) ||
               (r==2 && (left_nonzero || !right_nonzero)) ||
               (r==3 && (left_nonzero || right_nonzero)))
                $fatal(1,"reported route does not match actual PCM r=%0d L=%0d R=%0d",r,left_nonzero,right_nonzero);
        end
        midi(2,82,0);midi(2,64,0);midi(0,52,0);
        // At first both envelopes are still releasing; held=0 is not ACTIVE=0.
        feedback_row(0,2,0,73,0);if(held)$fatal(1,"held did not release");
        release_frames=0;
        while(mode!=1 && release_frames<2000)begin samples(1);release_frames++;end
        if(mode!=1 || audio.mode_pending)$fatal(1,"pending mode failed actual commit after release");
        feedback_row(1,0,0,73,0);
        detached();put(0,7);wait(dut.input_settled);feedback_row(2,0,0,0,0);
        if(feedback_rows!=12)$fatal(1,"unexpected feedback row count %0d",feedback_rows);
        $fclose(feedback_file);detached();
        $display("PASS audio feedback: 12 real MMIO snapshots, active/release-tail voices, requested vs committed mode, four routes checked against PCM, glide/sustain, reconnect defaults");
    endtask
    initial begin
        #250;rn=1;repeat(20)@(negedge clk);
        dirty(1);
        // Hold audio acceptance while packets arrive: short taps and controls
        // must share the one FIFO, then begin only after actual default commit.
        consume=0;put(0,7);watch_order=1;check_defaults_on_note=1;
        want(1,48,100);midi(1,48,100);
        want(0,48,0);midi(0,48,0);
        want(2,7,33);midi(2,7,33);want(3,40,0);midi(3,40,0);
        want(4,0,72);midi(4,0,72);
        want(2,88,127);midi(2,88,127);want(2,89,1);midi(2,89,1);
        consume=1;wait(rp==wp);check_defaults_on_note=0;samples(3);watch_order=0;
        if(held || audio.volume!=16'd8448 || profile!=1 || audio.bend_index!=144 ||
           audio.effect_master || mode!=0)$fatal(1,"queued control/tap result");
        // No PL draw/end acknowledgement or first frame was supplied above.
        if(dut.frames)$fatal(1,"test unexpectedly depended on screen");
        detached();dirty(0); // live vector/demo are stopped too
        put(0,7);wait(dut.input_settled);defaults();initializations++;
        // Disconnect midway through a real initialization (hold sample/mix),
        // including events already retained, then reconnect immediately.
        detached();consume=0;put(0,7);
        midi(1,60,100);midi(2,7,1);midi(3,0,0);midi(4,0,1);
        put(0,0);consume=1;repeat(8)@(negedge aclk);put(0,7);
        wait(dut.input_settled);samples(3);defaults();initializations++;
        if(held || audio.volume!=32768)$fatal(1,"old queued input replayed after reconnect");
        // Now detach while the init sequence itself is active, not merely
        // pending in the transport. Its held controls must be canceled too.
        detached();put(0,7);wait(audio.attach_initializing);
        midi(1,61,100);midi(2,7,2);detached();put(0,7);
        wait(dut.input_settled);samples(3);defaults();initializations++;
        if(held)$fatal(1,"mid-init old note replayed");
        // An emergency PANIC bypasses a full queue and discards its tail.
        midi(1,62,100);samples(3);if(!held[62])$fatal(1,"panic setup");
        consume=0;
        for(integer i=0;i<64;i++)midi(2,7,4);
        midi(2,120,0);consume=1;wait(!held);samples(3);
        if(audio.volume!=32768)$fatal(1,"panic failed to discard queued control");
        // PANIC mid-init restarts all defaults and still permits new input.
        detached();put(0,7);wait(audio.attach_initializing);midi(2,120,0);
        wait(dut.input_settled);samples(2);defaults();initializations++;
        midi(1,63,100);samples(5);if(!held[63] || !nonzero)$fatal(1,"no PCM after init");
        midi(0,63,0);samples(3);
        // A GW25K must not drive the generic song/guide entry points.
        midi(2,110,127);midi(2,111,127);midi(2,112,127);midi(2,112,0);
        samples(1);if(dut.guide_mode)$fatal(1,"GW25K enabled guide");
        detached();dirty(1);put(0,1);check_defaults_on_note=1;
        // The first Push turn sees volume=127; repeated press/release must not
        // be cleared by a late CDC panic epoch. No renderer readiness needed.
        put(4,32'h023c9009);samples(3);check_defaults_on_note=0;
        if(!held[60] || dut.velocity!=30)$fatal(1,"first Push note lost");
        put(4,32'h003c8008);samples(2);if(held)$fatal(1,"first Push release lost");
        put(4,32'h7f47b00b);samples(1);
        if(audio.volume!=32256)$fatal(1,"first Push decrement did not start at 127");
        put(4,32'h023d9009);samples(2);
        put(4,32'h7f1bb00b);wait(!held);samples(2);
        if(dut.held)$fatal(1,"Push panic failed");
        put(4,32'h001bb00b);put(4,32'h023e9009);samples(2);
        put(4,32'h003e8008);samples(2);if(held)$fatal(1,"Push release after panic lost");
        mapped_before=dut.total_mapped;detached();samples(1);
        if(dut.total_mapped<=mapped_before)$fatal(1,"lifetime mapped diagnostic reset on detach");
        feedback_scenarios();
        $display("PASS attach: %0d default boundaries, ordered tap/CC7/program/bend/CC88/89, detach/reconnect cancellation, full-queue and init PANIC, TF/live/cue exit, no first-frame wait, GW25K guide isolation, Push epoch/volume/release, PCM=%0d",initializations,nonzero);
        $finish;
    end
    initial begin #100000000;$fatal(1,"timeout frame=%0d init=%0d step=%0d pending=%0d mode=%0d",frames,audio.attach_initializing,audio.attach_step,audio.mode_pending,mode);end
endmodule
