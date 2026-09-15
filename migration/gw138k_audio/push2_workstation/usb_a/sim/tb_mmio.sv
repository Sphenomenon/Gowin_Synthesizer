`timescale 1ns/1ps
module tb_mmio;
    reg clk=0,aclk=0,fclk=0,rn=0,sel=0,wr=0,ar=1;
    always #(1000.0/96)clk=~clk;
    always #(1000.0/153.6)aclk=~aclk;
    always #10 fclk=~fclk;
    reg [7:0] addr=0;reg [31:0] wd=0;wire [31:0] rd;wire ready,av;
    wire [17:0] ae;wire [223:0] telemetry;
    reg [447:0] feedback=0;
    push2_usb_a_control dut(.clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),
        .feedback_clk(fclk),.feedback_reset_n(rn),.performance_words(feedback),
        .select(sel),.write(wr),.address(addr),.wdata(wd),.ready(ready),.rdata(rd),
        .audio_valid(av),.audio_ready(ar),.audio_event(ae),.telemetry(telemetry));
    reg [17:0] expected[0:2047];integer wp=0,rp=0,stalled=0;
    always @(posedge aclk)if(rn && av && ar)begin
        if(rp>=wp || ae!==expected[rp])$fatal(1,"event %0d got=%h expected=%h",rp,ae,expected[rp]);
        rp=rp+1;
    end
    task bus(input bit write,input [7:0] address,input [31:0] data,output [31:0] value);
        begin
            @(negedge clk);sel=1;wr=write;addr=address;wd=data;
            @(posedge clk);while(!ready)begin stalled++;@(posedge clk);end
            value=rd;@(negedge clk);sel=0;
        end
    endtask
    reg [31:0] discard;
    task put(input [7:0] address,input [31:0] data);begin bus(1,address,data,discard);end endtask
    task midi(input [3:0] kind,input [6:0] a,b,input bit emits,input [17:0] expected_event);
        begin
            if(emits)begin expected[wp]=expected_event;wp++;end
            put(4,{1'b0,b,1'b0,a,kind,4'd0,4'd0,kind});
        end
    endtask
    reg [31:0] value;reg [127:0] led_packet;integer fd;
    initial begin
        feedback[63:32]=32'h64000010;feedback[255:224]=32'h02000000;
        #200;rn=1;repeat(20)@(negedge clk);put(0,1);
        // Leave LED packet unacknowledged throughout MIDI tests.
        for(integer n=36;n<100;n++)begin
            midi(9,7'(n),100,1,{4'd1,7'(n),7'd127});
            midi(9,7'(n),100,0,0);
            midi(9,7'(n),0,1,{4'd0,7'(n),7'd0});
        end
        put(4,32'h64409109);put(4,32'h64409019); // other channel/cable ignored
        for(integer n=102;n<105;n++)begin
            midi(11,7'(n),127,1,{4'd2,7'd80,7'(n-102)});
            midi(11,7'(n),127,0,0);midi(11,7'(n),0,0,0);
        end
        midi(11,105,127,1,{4'd3,7'd73,7'd0});midi(11,106,127,1,{4'd3,7'd40,7'd0});
        midi(11,107,127,1,{4'd3,7'd56,7'd0});midi(11,108,127,1,{4'd3,7'd12,7'd0});midi(11,109,127,1,{4'd3,7'd0,7'd0});
        midi(11,20,127,1,{4'd2,7'd81,7'd1});midi(11,21,127,1,{4'd2,7'd81,7'd3});midi(11,22,127,1,{4'd2,7'd81,7'd7});
        for(integer n=23;n<27;n++)midi(11,7'(n),127,1,{4'd2,7'd82,7'(n-23)});
        midi(11,71,1,1,{4'd2,7'd7,7'd101});midi(11,72,63,1,{4'd2,7'd1,7'd63});midi(11,73,63,1,{4'd2,7'd5,7'd63});
        midi(14,1,65,1,{4'd4,7'd1,7'd65});midi(8,12,0,1,{4'd4,7'd0,7'd64});
        // Saturate the 64-entry asynchronous queue. All releases must survive.
        @(negedge aclk);ar=0;
        fork
            begin for(integer n=0;n<150;n++)begin
                midi(9,60,88,1,{4'd1,7'd60,7'd116});midi(8,60,0,1,{4'd0,7'd60,7'd0});
            end end
            begin repeat(3000)@(negedge aclk);ar=1;end
        join
        wait(rp==wp);if(stalled<100)$fatal(1,"queue pressure not exercised");
        midi(9,60,88,1,{4'd1,7'd60,7'd116});
        expected[wp]={4'd2,7'd123,7'd0};wp++;put(0,0);
        wait(rp==wp);repeat(20)@(negedge clk);if(dut.held)$fatal(1,"disconnect stuck notes");
        put(0,1);repeat(12)@(negedge clk);
        bus(0,'h40,0,value);if(value!==32'h8000000c)$fatal(1,"startup LED packet size");
        put('h48,0);led_packet=0;
        for(integer n=0;n<12;n++)begin bus(0,'h4c,0,value);led_packet[n*8+:8]=value[7:0];end
        if(led_packet[95:0]!==96'hf7000a0701011d042100f004)$fatal(1,"Live mode bytes %h",led_packet);
        // Unacknowledged packet is immutable, and only an ACK advances it.
        bus(0,'h40,0,value);if(value!==32'h8000000c)$fatal(1,"LED consumed without ACK");
        put('h44,1);repeat(12)@(negedge clk);
        put('h48,0);for(integer n=0;n<12;n++)begin bus(0,'h4c,0,value);led_packet[n*8+:8]=value[7:0];end
        if(led_packet[95:0]!==96'hf740060701011d042100f004)$fatal(1,"brightness bytes");
        repeat(5000)@(negedge clk);put(8,1);
        fd=$fopen("push_screen.rgb565","wb");
        for(integer y=0;y<160;y++)for(integer x=0;x<1024;x++)begin
            bus(0,'h2c,0,value);
            if(x>=960 && value!==0)$fatal(1,"display row padding");
            if(x<960)$fwrite(fd,"%c%c",value[7:0],value[15:8]);
        end
        $fclose(fd);
        $display("PASS MMIO: %0d ordered events, %0d stall cycles, 64 pads/zero-velocity/dedup/channel/cable, all mappings, LED ACK, 960x160 pixels + padding",rp,stalled);
        $finish;
    end
    initial begin #30000000;$fatal(1,"timeout");end
endmodule
