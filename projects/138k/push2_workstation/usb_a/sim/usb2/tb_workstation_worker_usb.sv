`timescale 1ns/1ps
// Real W owner, CDC and event FIFO, reached through the production bus adapter.
module tb_workstation_worker_usb;
    reg clk=0,aclk=0,rn=0,session=1,sv=0,sw=0,consume=1;
    always #5 clk=~clk;
    always #3 aclk=~aclk;
    reg [7:0] sa=0;
    reg [31:0] sd=0;
    wire sr,se,os,ow,orr;
    wire [7:0] oa;
    wire [31:0] od,rd,srdata;
    wire av,al,ac,sready,pready,launch;
    wire [17:0] ae;
    wire [3:0] track;
    wire [223:0] telemetry;
    reg [447:0] feedback=0;
    workstation_usb2_service_adapter #(.WORKER_DEMO(1)) services(
        .clk_cpu(clk),.reset_n(rn),.session_valid_i(session),.owner_connected_i(telemetry[1]),
        .service_valid_i(sv),.service_write_i(sw),.service_address_i(sa),.service_write_data_i(sd),
        .service_mask_i(4'hf),.service_ready_o(sr),.service_error_o(se),.service_read_data_o(srdata),
        .owner_select_o(os),.owner_write_o(ow),.owner_address_o(oa),.owner_write_data_o(od),
        .owner_ready_i(orr),.owner_read_data_i(rd),.canceled_requests_o());
    push2_usb_a_control #(.CNN_FOLLOW_ENABLE(0),.WORKER_DEMO(1),.STOP_CLOCK_QUEUE_FENCE(1)) dut(
        .clk(clk),.reset_n(rn),.audio_clk(aclk),.audio_reset_n(rn),
        .feedback_clk(aclk),.feedback_reset_n(rn),.performance_words(feedback),
        .display_meta_data(64'd0),.display_meta_valid(1'b0),
        .service_state_data(34'd0),.service_state_valid(1'b0),
        .score_valid(1'b1),.analysis_done(1'b1),.score_ready(sready),.score_note(7'd60),
        .playlist_valid(1'b1),.playlist_ready(pready),.playlist_word(16'hff10),
        .track_launch(launch),.track_index(track),.select(os),.write(ow),.address(oa),.wdata(od),
        .ready(orr),.rdata(rd),.audio_valid(av),.audio_ready(consume),.audio_event(ae),
        .audio_lifecycle(al),.audio_cancel(ac),.telemetry(telemetry));
    reg [17:0] expected[0:15];
    integer sent=0,received=0,lifecycle=0;
    always @(posedge aclk)if(rn && av && consume)begin
        if(ae[17:14]==15)lifecycle=lifecycle+1;
        else begin
            if(received>=sent || ae!==expected[received])
                $fatal(1,"W USB unexpected event %h at %d",ae,received);
            received=received+1;
        end
    end
    task access_bus(input bit wr,input [7:0] addr,input [31:0] data,input bit error_expected);
        begin
            @(negedge clk);sv=1;sw=wr;sa=addr;sd=data;
            do @(posedge clk);while(!sr);
            if(se!==error_expected)$fatal(1,"MMIO %h error=%b expected=%b",addr,se,error_expected);
            @(negedge clk);sv=0;
            repeat(2)@(negedge clk);
        end
    endtask
    task event_cc(input [6:0] cc,input [6:0] value);
        begin
            expected[sent]={4'd2,cc,value};sent=sent+1;
            access_bus(1,8'h54,{14'd0,4'd2,cc,value},0);
        end
    endtask
    initial begin
        #50;rn=1;repeat(20)@(negedge clk);
        access_bus(1,8'h00,1,1); // Push attach is retired, not silently accepted.
        access_bus(1,8'h00,7,0);
        repeat(60)@(negedge clk);
        event_cc(20,100);event_cc(87,1);wait(received==sent);
        access_bus(1,8'h04,32'h64609009,1);
        access_bus(1,8'h08,1,1);access_bus(1,8'h28,0,1);
        access_bus(1,8'h30,1,1);access_bus(1,8'h34,1,1);
        access_bus(1,8'h44,1,1);access_bus(1,8'h48,0,1);
        access_bus(0,8'h2c,0,1);access_bus(0,8'h40,0,1);
        access_bus(0,8'h4c,0,1);access_bus(0,8'h5c,0,1);
        access_bus(0,8'h60,0,1);access_bus(0,8'h64,0,1);
        access_bus(0,8'h68,0,1);access_bus(0,8'h6c,0,1);
        consume=0;
        access_bus(1,8'h54,{14'd0,4'd2,7'd21,7'd100},0);
        access_bus(1,8'h00,0,0);
        repeat(25)@(negedge clk);consume=1;
        repeat(25)@(negedge clk);
        access_bus(1,8'h00,7,0);repeat(60)@(negedge clk);
        event_cc(22,77);wait(received==sent);
        if(!sready || !pready || launch || track || lifecycle<5)
            $fatal(1,"retired guide/lifecycle contract");
        access_bus(0,8'h10,0,0);access_bus(0,8'h14,0,0);access_bus(0,8'h58,0,0);
        $display("PASS W-DEMO RTL: actual FIFO/CDC, retired Push MMIO rejected, 25K controls ordered and stale detach input canceled");
        $finish;
    end
    initial begin #100000;$fatal(1,"worker USB timeout");end
endmodule
