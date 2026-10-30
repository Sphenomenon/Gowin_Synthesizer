`timescale 1ns/1ps
module tb_workstation_no_cnn_owner;
    reg clk=0,aclk=0,rn=0,sel=0,wr=0;
    always #(1000.0/96)clk=~clk;
    always #(1000.0/153.6)aclk=~aclk;
    reg [7:0] addr=0;reg [31:0] wd=0;wire [31:0] rd;
    reg [33:0] service=0;reg service_valid=0,pv=0;
    reg [15:0] pw=0;
    wire ready,av,sr,launch,life,cancel;wire [17:0] ae;wire [3:0] track;
    push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0),.STOP_CLOCK_QUEUE_FENCE(1)) dut (
        .clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),.feedback_clk(aclk),.feedback_reset_n(rn),
        .performance_words(448'd0),.display_meta_data(64'd0),.display_meta_valid(1'b0),
        .service_state_data(service),.service_state_valid(service_valid),
        .score_valid(1'b1),.score_ready(sr),.score_note(7'd69),.analysis_done(1'b1),
        .playlist_valid(pv),.playlist_ready(),.playlist_word(pw),.track_launch(launch),.track_index(track),
        .select(sel),.write(wr),.address(addr),.wdata(wd),.ready(ready),.rdata(rd),
        .audio_valid(av),.audio_ready(1'b1),.audio_event(ae),.audio_lifecycle(life),.audio_cancel(cancel),.telemetry());
    reg [17:0] expected[0:63];integer wp=0,rp=0,attaches=0,detaches=0,barriers=0,cancels=0;
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
        button(85,6,0,0);button(86,6,1,0);button(44,2,108,0);button(45,2,108,127);button(48,2,90,64);
        expected_event(1,36,30);push(9,36,2);expected_event(0,36,0);push(9,36,0);wait(rp==wp);
        push(11,27,127);push(11,27,0);repeat(15000)@(negedge clk);
        put(0,0);repeat(30)@(negedge clk);put(0,1);repeat(15000)@(negedge clk);
        expected_event(1,37,30);push(9,37,2);expected_event(0,37,0);push(9,37,0);wait(rp==wp);
        if(rp!=13 || attaches<4 || detaches<3 || barriers<4 || cancels<1)
            $fatal(1,"disabled owner coverage missing rp=%0d attach=%0d detach=%0d barrier=%0d cancel=%0d",rp,attaches,detaches,barriers,cancels);
        $display("PASS no CNN owner events=%0d attaches=%0d detaches=%0d barriers=%0d cancels=%0d",rp,attaches,detaches,barriers,cancels);
        $finish;
    end
    initial begin #10000000;$fatal(1,"no CNN owner timeout rp=%0d wp=%0d",rp,wp);end
endmodule
