`timescale 1ns/1ps
module tb_task3_lcd_transport #(
    parameter bit TEST_ALLOW_BUSINESS=1'b1
);
    reg mc=0,wc=0,w_run=1;
    always #5 mc=~mc;
    always #7 if(w_run)wc=~wc;
    reg reset_n=0,enable_m=0,enable_w=0,panic_m=0,panic_w=0,budget=0,corrupt=0;
    reg [31:0] session=1;
    reg mtv=0,wtv=0,mrr=1,wrr=1;
    reg [3:0] mtch=0,wtch=0;
    reg [5:0] mtlen=0,wtlen=0;
    reg [255:0] mtdata=0,wtdata=0;
    wire mtr,wtr,mrv,wrv,mlive,wlive,mbusiness,wbusiness,mfault,wfault;
    wire [3:0] mrch,wrch,mfailure,wfailure,md,wd;
    wire [5:0] mrlen,wrlen;
    wire [255:0] mrdata,wrdata;
    wire mq,wq,ma,wa,mp,wp;
    wire [31:0] mcrc,wcrc,mseq,wseq,moverflow,woverflow,mcongest,wcongest,mrtt,wrtt,mprobes,wprobes;
    integer checks=0,mreceived=0,wreceived=0,age;
    reg [3:0] mlastch,wlastch;
    reg [5:0] mlastlen,wlastlen;
    reg [255:0] mlastdata,wlastdata;
    workstation_task3_lcd_transport #(.EXPERIMENT_ENABLE(1),.ALLOW_BUSINESS(TEST_ALLOW_BUSINESS),
        .PHY_STALL_TIMEOUT_CYCLES(20000),.HEARTBEAT_INTERVAL_CYCLES(50000),
        .PROBE_INTERVAL_CYCLES(80000),.LINK_TIMEOUT_CYCLES(300000)) m(
        .clk_i(mc),.reset_ni(reset_n),.enable_i(enable_m),.panic_i(panic_m),.budget_validated_i(budget),
        .local_boot_i(32'd1),.peer_boot_i(32'd2),.session_i(session),
        .tx_valid_i(mtv),.tx_ready_o(mtr),.tx_channel_i(mtch),.tx_payload_i(mtdata),.tx_length_i(mtlen),
        .rx_valid_o(mrv),.rx_ready_i(mrr),.rx_channel_o(mrch),.rx_payload_o(mrdata),.rx_length_o(mrlen),
        .link_ready_o(mlive),.business_ready_o(mbusiness),.pad_drive_o(),.fault_o(mfault),.failure_code_o(mfailure),.peer_panic_o(),
        .phy_tx_data_o(md),.phy_tx_req_o(mq),.phy_rx_ack_o(ma),.phy_panic_o(mp),
        .phy_rx_data_i(wd),.phy_rx_req_i(wq),.phy_tx_ack_i(wa),.phy_peer_panic_i(wp),
        .tx_packets_o(),.rx_packets_o(),.crc_errors_o(mcrc),.sequence_errors_o(mseq),.rejected_packets_o(),
        .overflow_count_o(moverflow),.congestion_cycles_o(mcongest),.last_rtt_cycles_o(mrtt),.max_rtt_cycles_o(),
        .probe_results_o(mprobes),.link_timeouts_o());
    workstation_task3_lcd_transport #(.EXPERIMENT_ENABLE(1),.ALLOW_BUSINESS(TEST_ALLOW_BUSINESS),
        .PHY_STALL_TIMEOUT_CYCLES(20000),.HEARTBEAT_INTERVAL_CYCLES(50000),
        .PROBE_INTERVAL_CYCLES(80000),.LINK_TIMEOUT_CYCLES(300000)) w(
        .clk_i(wc),.reset_ni(reset_n),.enable_i(enable_w),.panic_i(panic_w),.budget_validated_i(budget),
        .local_boot_i(32'd2),.peer_boot_i(32'd1),.session_i(session),
        .tx_valid_i(wtv),.tx_ready_o(wtr),.tx_channel_i(wtch),.tx_payload_i(wtdata),.tx_length_i(wtlen),
        .rx_valid_o(wrv),.rx_ready_i(wrr),.rx_channel_o(wrch),.rx_payload_o(wrdata),.rx_length_o(wrlen),
        .link_ready_o(wlive),.business_ready_o(wbusiness),.pad_drive_o(),.fault_o(wfault),.failure_code_o(wfailure),.peer_panic_o(),
        .phy_tx_data_o(wd),.phy_tx_req_o(wq),.phy_rx_ack_o(wa),.phy_panic_o(wp),
        .phy_rx_data_i(md ^ (corrupt && w.rx_index==20?4'h1:4'h0)),
        .phy_rx_req_i(mq),.phy_tx_ack_i(ma),.phy_peer_panic_i(mp),
        .tx_packets_o(),.rx_packets_o(),.crc_errors_o(wcrc),.sequence_errors_o(wseq),.rejected_packets_o(),
        .overflow_count_o(woverflow),.congestion_cycles_o(wcongest),.last_rtt_cycles_o(wrtt),.max_rtt_cycles_o(),
        .probe_results_o(wprobes),.link_timeouts_o());
    // Unconfigured production defaults MUST remain inert even if external
    // software presents enable/budget/transactions. No hardware is involved.
    wire default_drive,default_ready,default_business;
    workstation_task3_lcd_transport disabled(
        .clk_i(mc),.reset_ni(reset_n),.enable_i(1'b1),.panic_i(1'b0),.budget_validated_i(1'b1),
        .local_boot_i(32'd1),.peer_boot_i(32'd2),.session_i(32'd1),
        .tx_valid_i(1'b1),.tx_ready_o(default_ready),.tx_channel_i(4'd1),.tx_payload_i(256'd1),.tx_length_i(6'd1),
        .rx_valid_o(),.rx_ready_i(1'b1),.rx_channel_o(),.rx_payload_o(),.rx_length_o(),
        .link_ready_o(),.business_ready_o(default_business),.pad_drive_o(default_drive),.fault_o(),.failure_code_o(),.peer_panic_o(),
        .phy_tx_data_o(),.phy_tx_req_o(),.phy_rx_ack_o(),.phy_panic_o(),
        .phy_rx_data_i(4'd0),.phy_rx_req_i(1'b0),.phy_tx_ack_i(1'b0),.phy_peer_panic_i(1'b0),
        .tx_packets_o(),.rx_packets_o(),.crc_errors_o(),.sequence_errors_o(),.rejected_packets_o(),
        .overflow_count_o(),.congestion_cycles_o(),.last_rtt_cycles_o(),.max_rtt_cycles_o(),.probe_results_o(),.link_timeouts_o());
    always @(posedge mc)if(mrv&&mrr)begin mreceived=mreceived+1;mlastch=mrch;mlastlen=mrlen;mlastdata=mrdata;end
    always @(posedge wc)if(wrv&&wrr)begin wreceived=wreceived+1;wlastch=wrch;wlastlen=wrlen;wlastdata=wrdata;end
    task automatic require(input reg ok,input string text);
        begin checks=checks+1;if(!ok)$fatal(1,"LCD check%0d %s Mfault%0d/%0d Wfault%0d/%0d",checks,text,mfault,mfailure,wfault,wfailure);end
    endtask
    task automatic arm_pair;
        begin
            @(negedge mc);enable_m=0;enable_w=0;panic_m=0;panic_w=0;corrupt=0;budget=0;mtv=0;wtv=0;mrr=1;wrr=1;w_run=1;
            repeat(20)@(negedge mc);session=session+1;enable_m=1;enable_w=1;
            age=0;while(!(mlive&&wlive)&&age<20000)begin @(negedge mc);age=age+1;end
            require(mlive&&wlive,"valid heartbeat establishes logical peer");
            require(!mfault&&!wfault,"clean arm");
        end
    endtask
    task automatic send_m(input [3:0] channel,input [5:0] length,input [255:0] data);
        begin
            @(negedge mc);mtch=channel;mtlen=length;mtdata=data;mtv=1;age=0;
            while(!mtr&&age<20000)begin @(negedge mc);age=age+1;end
            require(mtr,"M typed transaction admitted");@(posedge mc);@(negedge mc);mtv=0;
        end
    endtask
    task automatic send_w(input [3:0] channel,input [5:0] length,input [255:0] data);
        begin
            @(negedge wc);wtch=channel;wtlen=length;wtdata=data;wtv=1;age=0;
            while(!wtr&&age<20000)begin @(negedge wc);age=age+1;end
            require(wtr,"W typed transaction admitted");@(posedge wc);@(negedge wc);wtv=0;
        end
    endtask
    integer before_m,before_w;
    initial begin
        repeat(5)@(negedge mc);reset_n=1;arm_pair();
        require(!default_drive&&!default_ready&&!default_business,"default compile policy inert");
        require(!mbusiness&&!wbusiness,"logical link never self grants business budget");
        mtch=1;mtlen=4;mtdata=256'd42;mtv=1;
        repeat(100)@(negedge mc);
        require(!mtr&&mcongest>=90,"unqualified business is bounded backpressure and counted");mtv=0;
        before_w=wreceived;send_m(0,4,256'hdeadbeef);
        age=0;while(wreceived==before_w&&age<20000)begin @(negedge mc);age=age+1;end
        require(wreceived==before_w+1&&wlastch==0&&wlastlen==4&&wlastdata==256'hdeadbeef,"control exact CRC/sequence/padding");
        before_m=mreceived;send_w(0,1,256'hff);
        age=0;while(mreceived==before_m&&age<20000)begin @(negedge mc);age=age+1;end
        require(mreceived==before_m+1&&mlastlen==1&&mlastdata==256'hff,"reverse control exact");
        budget=1;#1;
        if(TEST_ALLOW_BUSINESS)begin
            require(mbusiness&&wbusiness,"only external qualification releases explicit business configuration");
            before_w=wreceived;send_m(8,32,256'h0123456789abcdef0000111122223333444455556666777788889999aaaabbbb);
            age=0;while(wreceived==before_w&&age<20000)begin @(negedge mc);age=age+1;end
            require(wreceived==before_w+1&&wlastch==8&&wlastlen==32&&wlastdata==mtdata,"actual typed business channel8 payload");
        end else begin
            require(!mbusiness&&!wbusiness,"runtime qualification cannot bypass compile business denial");
            mtv=1;mtch=8;repeat(100)@(negedge mc);
            require(!mtr&&!mfault&&!wfault,"probe-only compile rejects business without stopping control");mtv=0;
        end
        age=0;while((mprobes==0||wprobes==0)&&age<180000)begin @(negedge mc);age=age+1;end
        require(mprobes!=0&&wprobes!=0&&mrtt!=0&&wrtt!=0&&!mfault&&!wfault,"automatic echo RTT in independent local clock cycles");
        $display("CASE duplex_control_business_probe PASS M_RTT=%0d W_RTT=%0d",mrtt,wrtt);
        if(TEST_ALLOW_BUSINESS)begin
            arm_pair();budget=1;wrr=0;send_m(8,1,9);
            age=0;while(!wrv&&age<20000)begin @(negedge mc);age=age+1;end
            require(wrv,"business result held at bounded receiver");
            budget=0;#1;require(!wrv&&!mtr,"budget revocation immediately revokes business handshakes");
            repeat(10)@(negedge mc);
            require(wfault&&wfailure==9,"budget revocation cancels held business and requires rearm");
            budget=1;repeat(10)@(negedge mc);require(!wrv,"requalification never replays canceled business");
            $display("CASE budget_revocation PASS");
        end
        arm_pair();corrupt=1;before_w=wreceived;send_m(0,32,{256{1'b1}});
        age=0;while(!wfault&&age<20000)begin @(negedge mc);age=age+1;end
        require(wfault&&wfailure==6&&wcrc!=0&&wreceived==before_w,"corrupt payload CRC rejected before publication");
        $display("CASE bad_crc PASS");
        arm_pair();
        // Rearm just M without a new shared session. Its CRC-valid sequence0
        // cannot be mistaken for a current W receive continuation.
        age=0;while((m.tx_state!=0||m.phy.tx_state!=0||w.rx_index!=0)&&age<20000)begin @(negedge mc);age=age+1;end
        enable_m=0;repeat(20)@(negedge mc);enable_m=1;
        age=0;while(!wfault&&age<20000)begin @(negedge mc);age=age+1;end
        require(wfault&&wfailure==5&&wseq!=0,"CRC-valid replay/out-of-order sequence fenced");
        $display("CASE stale_sequence PASS");
        arm_pair();wrr=0;send_m(0,1,1);
        age=0;while(!wrv&&age<20000)begin @(negedge mc);age=age+1;end
        require(wrv,"one bounded receiver holding slot");send_m(0,1,2);
        age=0;while(!wfault&&age<20000)begin @(negedge mc);age=age+1;end
        require(wfault&&wfailure==8&&woverflow!=0,"receiver congestion fails and counts overflow");
        $display("CASE bounded_receiver_congestion PASS");
        arm_pair();wrr=0;send_m(0,1,3);
        age=0;while(!wrv&&age<20000)begin @(negedge mc);age=age+1;end
        @(negedge mc);panic_m=1;#1;require(!mtr&&!mrv,"local PANIC revokes typed handshakes immediately");
        repeat(10)@(negedge mc);
        require(mfault&&wfault&&mfailure==2&&wfailure==2&&!wrv,"dedicated peer PANIC outranks held payload");
        $display("CASE panic_priority PASS");
        arm_pair();w_run=0;age=0;
        while(!mfault&&age<400000)begin @(negedge mc);age=age+1;end
        require(mfault&&(mfailure==3||mfailure==4)&&!mlive,"stopped peer clock loses handshake or heartbeat qualification");
        $display("CASE peer_clock_stop PASS cycles=%0d failure=%0d",age,mfailure);
        require(!default_drive&&!default_ready&&!default_business,"default remains inert throughout");
        $display("PASS task3_lcd_transport checks=%0d",checks);$finish;
    end
    initial begin #20000000;$fatal(1,"LCD test timeout");end
endmodule
