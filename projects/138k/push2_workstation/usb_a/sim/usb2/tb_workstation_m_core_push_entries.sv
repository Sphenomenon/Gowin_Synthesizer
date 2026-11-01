`timescale 1ns/1ps
module tb_workstation_m_core_push_entries;
    reg clk=0,aclk=0,rn=0,sel=0,wr=0;
    always #(1000.0/96)clk=~clk;
    always #(1000.0/153.6)aclk=~aclk;
    reg [7:0] addr=0;reg [31:0] wd=0;wire [31:0] rd;
    reg [33:0] service=0;reg service_valid=0,pv=0;
    reg [15:0] pw=0;
    wire ready,av,sr,launch,life,cancel;wire [17:0] ae;wire [3:0] track;
    push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0),.MEDIA_CONTROLS_ENABLE(0),.STOP_CLOCK_QUEUE_FENCE(1)) dut (
        .clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),.feedback_clk(aclk),.feedback_reset_n(rn),
        .performance_words(448'd0),.display_meta_data(64'd0),.display_meta_valid(1'b0),
        .service_state_data(service),.service_state_valid(service_valid),
        .score_valid(1'b1),.score_ready(sr),.score_note(7'd69),.analysis_done(1'b1),
        .playlist_valid(pv),.playlist_ready(),.playlist_word(pw),.track_launch(launch),.track_index(track),
        .select(sel),.write(wr),.address(addr),.wdata(wd),.ready(ready),.rdata(rd),
        .audio_valid(av),.audio_ready(1'b1),.audio_event(ae),.audio_lifecycle(life),.audio_cancel(cancel),.telemetry());
    reg [17:0] expected[0:127];integer wp=0,rp=0,attaches=0,detaches=0,barriers=0,cancels=0;
    always @(posedge aclk)if(rn)begin
        if(cancel)cancels++;
        if(av)begin
            if(life)begin
                case(ae[6:0])
                    0:detaches++;
                    1:attaches++;
                    3:barriers++;
                endcase
            end else begin
                if(rp>=wp || ae!==expected[rp])$fatal(1,"no CNN audio mapping changed rp=%0d got=%h",rp,ae);
                rp++;
            end
        end
    end
    always @(negedge clk)if(rn)begin
        if(!sr || launch || track || dut.guide_mode || dut.guide_target_valid || dut.guide_mask ||
            dut.guide_score_count || dut.guide_cursor || dut.guide_wrong_count || dut.analysis_done_sync)
            $fatal(1,"disabled CNN follow remained active");
    end
    task put(input [7:0] address,input [31:0] data);
        begin @(negedge clk);sel=1;wr=1;addr=address;wd=data;
            do @(posedge clk);while(!ready);@(negedge clk);sel=0;end
    endtask
    task get(input [7:0] address,output [31:0] value);
        begin @(negedge clk);sel=1;wr=0;addr=address;
            do @(posedge clk);while(!ready);value=rd;@(negedge clk);sel=0;end
    endtask
    task expected_event(input [3:0] k,input [6:0] a,b);
        begin expected[wp]={k,a,b};wp++;end
    endtask
    task generic(input [3:0] k,input [6:0] a,b);
        begin put('h54,{14'd0,k,a,b});end
    endtask
    task push(input [3:0] k,input [6:0] a,b);
        begin put(4,{1'b0,b,1'b0,a,k,4'd0,4'd0,k});end
    endtask
    task button(input [6:0] key,input [3:0] k,input [6:0] a,b);
        begin expected_event(k,a,b);push(11,key,127);push(11,key,0);end
    endtask
    task reserved;
        begin generic(2,110,127);generic(2,111,127);generic(2,112,127);generic(2,112,0);end
    endtask
    task retired_button(input [6:0] key);
        begin push(11,key,127);push(11,key,96);push(11,key,0);end
    endtask
    integer ui_x;
    reg [31:0] value;
    initial begin
        #250;rn=1;repeat(30)@(negedge clk);put(0,3);
        @(negedge clk);pw=16'hff03;pv=1;service={2'b11,32'h80001001};service_valid=1;
        @(negedge clk);pv=0;service_valid=0;repeat(5)@(negedge clk);
        get('h60,value);if(value!={6'd0,4'd0,5'd3,4'd0,2'b11,11'd0})
            $fatal(1,"disabled MMIO lost non CNN fields got=%h",value);
        get('h64,value);if(value!=32'h80001001)$fatal(1,"local score/REC mask lost");
        get('h5c,value);if(value)$fatal(1,"stale CNN target");
        get('h68,value);if(value)$fatal(1,"stale CNN progress");
        get('h6c,value);if(value)$fatal(1,"stale CNN wrong count");
        reserved();expected_event(1,60,99);generic(1,60,99);expected_event(0,60,0);generic(0,60,0);wait(rp==wp);
        put(0,0);repeat(30)@(negedge clk);put(0,7);reserved();
        expected_event(1,69,100);generic(1,69,100);expected_event(0,69,0);generic(0,69,0);wait(rp==wp);
        put(0,0);repeat(30)@(negedge clk);put(0,1);repeat(15000)@(negedge clk);
        // Retired physical entries must never create a queued TF/service
        // request, even with a duplicate held press and a live USB session.
        retired_button(85);retired_button(86);retired_button(44);retired_button(45);
        retired_button(51);retired_button(87);retired_button(88);
        repeat(40)@(negedge clk);
        if(rp!=wp || dut.controls.ignored!=7)$fatal(1,"retired Push entry was exposed");
        button(48,2,90,64);
        // Keep actual instrument actions through the same USB FIFO.
        button(102,2,80,0);button(103,2,80,1);button(104,2,80,2);
        button(105,3,73,0);button(106,3,40,0);button(107,3,56,0);
        button(108,3,12,0);button(109,3,0,0);
        button(20,2,87,0);button(21,2,87,1);button(22,2,87,2);
        button(23,2,82,0);button(24,2,82,1);button(25,2,82,2);button(26,2,82,3);
        button(28,2,88,0);button(62,2,89,0);button(63,2,89,1);
        expected_event(2,7,127);push(11,71,1);
        expected_event(2,1,1);push(11,72,1);
        expected_event(2,5,1);push(11,73,1);
        expected_event(4,0,64);push(14,0,64);wait(rp==wp);
        // Inspect the actual owner-composed display and lights: no inactive
        // service labels or dim service buttons survive this configuration.
        if(dut.controls.MEDIA_CONTROLS_ENABLE || dut.pixels.MEDIA_CONTROLS_ENABLE || dut.lights.MEDIA_CONTROLS_ENABLE)
            $fatal(1,"M core surface policy disconnected");
        for(ui_x=0;ui_x<240;ui_x=ui_x+1)begin
            force dut.pixel_index={8'd30,10'(ui_x)};#1;
            if(dut.pixels.draw || dut.pixels.active)$fatal(1,"retired Push label still rendered");
        end
        release dut.pixel_index;
        force dut.lights.scan=81;#1;if(dut.lights.color!=0)$fatal(1,"retired score button lit");
        force dut.lights.scan=82;#1;if(dut.lights.color!=0)$fatal(1,"retired record button lit");
        release dut.lights.scan;
        expected_event(1,36,30);push(9,36,2);expected_event(0,36,0);push(9,36,0);wait(rp==wp);
        push(11,27,127);push(11,27,0);repeat(15000)@(negedge clk);
        put(0,0);repeat(30)@(negedge clk);put(0,1);repeat(15000)@(negedge clk);
        expected_event(1,37,30);push(9,37,2);expected_event(0,37,0);push(9,37,0);wait(rp==wp);
        if(rp!=31 || attaches<4 || detaches<3 || barriers<4 || cancels<1)
            $fatal(1,"disabled owner coverage missing rp=%0d attach=%0d detach=%0d barrier=%0d cancel=%0d",rp,attaches,detaches,barriers,cancels);
        $display("PASS M core Push entry retirement events=%0d attaches=%0d detaches=%0d barriers=%0d cancels=%0d",rp,attaches,detaches,barriers,cancels);
        $finish;
    end
    initial begin #10000000;$fatal(1,"no CNN owner timeout rp=%0d wp=%0d",rp,wp);end
endmodule
