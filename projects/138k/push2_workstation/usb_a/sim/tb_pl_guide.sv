`timescale 1ns/1ps
// Exercises the production MMIO, MIDI decoder/mapper, song menu, score queue,
// asynchronous audio FIFO and feedback registers together, with no stubs.
module tb_pl_guide;
    reg clk=0,aclk=0,rn=0,sel=0,wr=0,consume=1;
    always #(1000.0/96)clk=~clk;
    always #(1000.0/153.6)aclk=~aclk;
    reg [7:0] addr=0;reg [31:0] wd=0;wire [31:0] rd;
    wire ready,av;wire [17:0] ae;
    reg sv=0,pv=0,analysis_done=0;
    reg [6:0] sn=0;reg [15:0] pw=0;
    wire sr,pr,launch;wire [3:0] track;
    reg [33:0] service=0;reg service_valid=0;
    push2_usb_a_control dut(.clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),
        .feedback_clk(aclk),.feedback_reset_n(rn),.performance_words(448'd0),
        .display_meta_data(64'd0),.display_meta_valid(1'b0),
        .service_state_data(service),.service_state_valid(service_valid),
        .score_valid(sv),.score_ready(sr),.score_note(sn),.analysis_done(analysis_done),
        .playlist_valid(pv),.playlist_ready(pr),.playlist_word(pw),
        .track_launch(launch),.track_index(track),
        .select(sel),.write(wr),.address(addr),.wdata(wd),.ready(ready),.rdata(rd),
        .audio_valid(av),.audio_ready(consume),.audio_event(ae),.telemetry());
    reg [17:0] expected[0:255];integer wp=0,rp=0,launches=0;
    always @(posedge aclk)if(rn && av && consume && ae[17:14]!=4'd15)begin
        if(rp>=wp || ae!==expected[rp])
            $fatal(1,"audio event %0d got=%h expected=%h",rp,ae,expected[rp]);
        rp++;
    end
    always @(posedge clk)if(rn && launch)launches++;
    task expect_event(input [17:0] e);begin expected[wp]=e;wp++;end endtask
    task put(input [7:0] address,input [31:0] data);
        begin
            @(negedge clk);sel=1;wr=1;addr=address;wd=data;
            do @(posedge clk);while(!ready);
            @(negedge clk);sel=0;
        end
    endtask
    task get(input [7:0] address,output [31:0] value);
        begin
            @(negedge clk);sel=1;wr=0;addr=address;
            do @(posedge clk);while(!ready);
            value=rd;@(negedge clk);sel=0;
        end
    endtask
    task generic_event(input [3:0] k,input [6:0] a,b);
        begin expect_event({k,a,b});put('h54,{14'd0,k,a,b});end
    endtask
    task guide_cc(input [6:0] a,b);begin put('h54,{14'd0,4'd2,a,b});end endtask
    task push_midi(input [3:0] k,input [6:0] a,b);
        begin put(4,{1'b0,b,1'b0,a,k,4'd0,4'd0,k});end
    endtask
    task score(input [6:0] note);
        begin
            @(negedge clk);sn=note;sv=1;
            do @(posedge clk);while(!sr);
            @(negedge clk);sv=0;
        end
    endtask
    task check_progress(input [15:0] count,cursor,wrong);
        reg [31:0] value;
        begin
            get('h68,value);if(value!=={count,cursor})$fatal(1,"progress %h expected %h mode=%b chosen=%b launch=%b flush=%d",value,{count,cursor},dut.guide_mode,dut.guide_chosen,launch,dut.score_flush_count);
            get('h6c,value);if(value!=={16'd0,wrong})$fatal(1,"wrong count %h",value);
        end
    endtask
    reg [31:0] value,before_received;integer fill;
    initial begin
        #250;rn=1;repeat(20)@(negedge clk);put(0,3);
        @(negedge clk);pw=16'hff03;pv=1;
        service={2'b11,32'h80001001};service_valid=1;analysis_done=1;
        @(negedge clk);pv=0;service_valid=0;
        repeat(4)@(negedge clk);
        get('h64,value);if(value!==32'h80001001)$fatal(1,"raw score note mask %h",value);
        guide_cc(110,127);guide_cc(110,127);
        get('h60,value);
        if(!value[8] || value[9] || !value[10] || value[12:11]!=3 ||
           value[16:13]!=0 || value[21:17]!=3)$fatal(1,"initial guide feedback %h",value);
        guide_cc(111,0);guide_cc(111,127);guide_cc(111,127);guide_cc(111,127);
        get('h60,value);if(value[16:13]!=2)$fatal(1,"browse clamp");
        guide_cc(111,0);guide_cc(112,127);guide_cc(112,127);
        guide_cc(111,127); // Browsing while a track is selected is ignored.
        repeat(3)@(negedge clk);
        get('h60,value);
        if(!value[9] || value[25:22]!=1 || value[16:13]!=1 || launches!=1)
            $fatal(1,"select edge/launch/feedback %h launches %0d",value,launches);
        guide_cc(112,0);
        wait(!dut.score_flushing);
        score(60);score(62);score(64);score(64);
        get('h60,value);if(!value[7] || value[6:0]!=60)$fatal(1,"raw guide target %h",value);
        generic_event(1,61,100);check_progress(4,0,1);
        generic_event(5,60,99);generic_event(1,60,0);check_progress(4,0,1);
        generic_event(1,60,17);check_progress(4,1,1);
        get('h24,value);if(value!={18'd0,7'd17,7'd60})$fatal(1,"generic last note %h",value);
        generic_event(5,60,19);
        get('h24,value);if(value!={18'd0,7'd19,7'd60})$fatal(1,"generic pressure telemetry");
        generic_event(0,60,0);
        get('h24,value);if(value!={18'd0,7'd0,7'd60})$fatal(1,"generic release telemetry");
        generic_event(2,1,83);generic_event(2,11,92);generic_event(3,73,0);
        check_progress(4,1,1);
        generic_event(1,62,21);check_progress(4,2,1);
        wait(rp==wp);@(negedge aclk);consume=0;
        fill=0;
        while(dut.fifo_ready)begin generic_event(2,7,100);fill++;end
        if(fill<64 || fill>66)$fatal(1,"FIFO depth not exercised %0d",fill);
        guide_cc(110,127); // Local control remains live with a full audio FIFO.
        get('h38,before_received);
        // A correct repeated-target note held during backpressure must not
        // advance until accepted, and must advance exactly once on release.
        expect_event({4'd1,7'd64,7'd23});
        @(negedge clk);sel=1;wr=1;addr='h54;wd={14'd0,4'd1,7'd64,7'd23};
        repeat(12)begin
            @(posedge clk);
            if(ready || dut.guide_cursor!=2 || dut.received!=before_received ||
               dut.generic_note!=62)$fatal(1,"unaccepted note had a side effect");
        end
        @(negedge aclk);consume=1;
        do @(posedge clk);while(!ready);
        @(negedge clk);sel=0;
        repeat(12)@(negedge clk);check_progress(4,3,1);
        get('h38,value);if(value!=before_received+1)$fatal(1,"repeated MMIO acceptance");
        generic_event(1,64,24);check_progress(4,4,1);
        get('h60,value);if(value[7])$fatal(1,"completed target remains active");
        // Button release gates a second select. Returning to the menu then
        // closing is idempotent; dedicated CCs never leak into audio events.
        guide_cc(112,127);guide_cc(112,127);
        get('h60,value);if(value[9] || !value[8] || launches!=1)$fatal(1,"return menu edge");
        guide_cc(110,0);guide_cc(110,0);
        get('h60,value);if(value[8])$fatal(1,"absolute guide disable");
        wait(rp==wp);
        // Preserve Push decoding, button bindings, target progression and
        // force curve after disconnect/reconnect to its original mode.
        put(0,0);wait(rp==wp);
        repeat(20)@(negedge clk);put(0,1);
        push_midi(11,85,127);push_midi(11,85,0);
        push_midi(11,48,127);push_midi(11,48,0);
        repeat(8)@(negedge clk);
        wait(!dut.score_flushing);score(65);score(67);
        expect_event({4'd1,7'd65,7'd30});push_midi(9,65,2);
        repeat(6)@(negedge clk);check_progress(2,1,0);
        expect_event({4'd5,7'd65,7'd31});push_midi(10,65,3);
        repeat(6)@(negedge clk);check_progress(2,1,0);
        expect_event({4'd0,7'd65,7'd0});push_midi(9,65,0);
        expect_event({4'd1,7'd67,7'd30});push_midi(9,67,2);
        repeat(6)@(negedge clk);check_progress(2,2,0);
        get('h24,value);if(value!={18'd0,7'd30,7'd67})$fatal(1,"Push force telemetry changed");
        wait(rp==wp);
        // Keep an active Push target across device replacement. A GW25K
        // correct or wrong key, and its reserved guide CCs, must leave it alone.
        score(69);score(71);check_progress(4,2,0);
        put(0,0);repeat(20)@(negedge clk);put(0,7);
        get('h60,before_received);
        guide_cc(110,0);guide_cc(111,127);guide_cc(112,127);guide_cc(112,0);
        generic_event(1,69,100);generic_event(1,68,100);
        generic_event(0,69,0);generic_event(0,68,0);
        check_progress(4,2,0);get('h60,value);
        if(value!=before_received)$fatal(1,"GW25K changed active Push guide");
        wait(rp==wp);
        $display("PASS PL guide RTL: generic correct/wrong/pressure/vel0, real FIFO backpressure once, reserved CC controls, full feedback, unchanged Push guide/force, GW25K cannot alter an active Push target (%0d audio events)",rp);
        $finish;
    end
    initial begin #30000000;$fatal(1,"timeout rp=%0d wp=%0d",rp,wp);end
endmodule
