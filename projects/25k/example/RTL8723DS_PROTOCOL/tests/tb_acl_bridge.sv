`timescale 1ns/1ps
module tb_acl_bridge;
    reg clk=0;always #5 clk=~clk;
    reg resetn=0,connected=1,tx_start=0,rx_consume=0;
    reg [3:0] tx_type=2;
    reg [8:0] tx_length=255,rx_addr=0;
    wire [8:0] tx_addr,rx_length;
    reg [7:0] tx_data=0;
    wire [7:0] rx_data;
    wire tx_ready,tx_done,tx_error,rx_valid;
    wire [3:0] rx_type;
    wire hs;
    wire [3:0] ht;
    wire [8:0] hl,ha;
    reg [8:0] ta=0;
    wire [7:0] td;
    reg hr=1,hd=0,he=0,rv=0;
    reg [3:0] rt=4;
    reg [8:0] rl=0;
    reg [7:0] rd=0;
    wire rc;
    wire [31:0] errors;
    reg [7:0] source[0:263],incoming[0:263],frame[0:263];
    integer sent=0,total=0,i,j,k,n,off,old_errors;
    bt_acl_bridge #(.CLK_HZ(100000),.REASSEMBLY_MS(20)) dut(
        .clk(clk),.resetn(resetn),.enable(1'b1),.connected(connected),.connection_handle(12'h234),.acl_packet_count(8'd2),
        .app_tx_start(tx_start),.app_tx_type(tx_type),.app_tx_length(tx_length),.app_tx_addr(tx_addr),.app_tx_data(tx_data),
        .app_tx_ready(tx_ready),.app_tx_done(tx_done),.app_tx_error(tx_error),
        .app_rx_valid(rx_valid),.app_rx_type(rx_type),.app_rx_length(rx_length),.app_rx_addr(rx_addr),.app_rx_data(rx_data),.app_rx_consume(rx_consume),
        .h5_tx_start(hs),.h5_tx_type(ht),.h5_tx_length(hl),.h5_tx_addr(ta),.h5_tx_data(td),.h5_tx_ready(hr),.h5_tx_done(hd),.h5_tx_error(he),
        .h5_rx_valid(rv),.h5_rx_type(rt),.h5_rx_length(rl),.h5_rx_addr(ha),.h5_rx_data(rd),.h5_rx_consume(rc),.errors(errors)
    );
    always @(posedge clk)begin tx_data<=source[tx_addr];rd<=incoming[ha];end
    // H5 copies each source byte with the actual transport's synchronous latency.
    initial forever begin
        wait(hs);@(negedge clk);hr=0;
        for(j=0;j<hl;j=j+1)begin ta=j;repeat(2)@(negedge clk);frame[j]=td;end
        if(ht==2)begin
            if(hl>31 || frame[2]!=hl-4 || frame[3]!=0 || frame[0]!=8'h34 || frame[1]!=(sent==0 ? 2 : 8'h12))$fatal(1,"TX ACL fragment framing");
            for(j=4;j<hl;j=j+1)begin
                if(frame[j]!=source[4+total])$fatal(1,"TX segment payload at %0d",total);
                total=total+1;
            end
            sent=sent+1;
        end else begin
            if(hl!=4)$fatal(1,"HCI command length changed");
            for(j=0;j<hl;j=j+1)if(frame[j]!=source[j])$fatal(1,"HCI command changed");
        end
        hd=1;@(negedge clk);hd=0;hr=1;
    end
    task send_rx;
        input [3:0] kind;input integer length;
        begin
            rt=kind;rl=length;rv=1;
            wait(rc);@(negedge clk);rv=0;
            repeat(4)@(negedge clk);
        end
    endtask
    task consume;
        begin rx_consume=1;@(negedge clk);rx_consume=0;repeat(4)@(negedge clk);end
    endtask
    task completion;
        input integer handle;input integer count;
        begin
            incoming[0]=8'h13;incoming[1]=5;incoming[2]=1;
            incoming[3]=handle;incoming[4]=handle>>8;incoming[5]=count;incoming[6]=count>>8;
            send_rx(4,7);wait(rx_valid);consume();
        end
    endtask
    task fragment;
        input integer offset;input integer size;
        begin
            incoming[0]=8'h34;incoming[1]=offset==0 ? 8'h22 : 8'h12;
            incoming[2]=size;incoming[3]=0;
            for(k=0;k<size;k=k+1)incoming[4+k]=source[4+offset+k];
            send_rx(2,size+4);
        end
    endtask
    initial begin
        for(i=0;i<264;i=i+1)source[i]=(i*19)^8'h5a;
        source[0]=8'h34;source[1]=2;source[2]=251;source[3]=0;
        source[4]=247;source[5]=0;source[6]=4;source[7]=0;
        repeat(5)@(negedge clk);resetn=1;repeat(5)@(negedge clk);
        tx_start=1;@(negedge clk);tx_start=0;
        wait(sent==2);repeat(20)@(negedge clk);
        if(tx_done || dut.credits!=0)$fatal(1,"Credits must count physical ACL packets");
        completion(16'h111,100);repeat(20)@(negedge clk);
        if(sent!=2)$fatal(1,"Foreign completion replenished ACL credits");
        // One completion event contains a foreign handle and our handle.
        incoming[0]=8'h13;incoming[1]=9;incoming[2]=2;
        incoming[3]=8'h11;incoming[4]=1;incoming[5]=8'hff;incoming[6]=8'hff;
        incoming[7]=8'h34;incoming[8]=2;incoming[9]=2;incoming[10]=0;
        send_rx(4,11);wait(rx_valid);consume();repeat(200)@(negedge clk);
        if(sent!=4)$fatal(1,"Multi-handle credit accounting");
        while(sent<10)begin
            completion(16'h234,2);repeat(200)@(negedge clk);
        end
        wait(tx_ready);if(total!=251 || tx_error)$fatal(1,"Full TX PDU not preserved");
        // Complete 247-byte ATT PDU over ten ACL packets, with an HCI event
        // interleaved while the assembly memory contains a partial message.
        fragment(0,27);if(rx_valid)$fatal(1,"Partial ACL exposed upstream");
        completion(16'h234,1);
        off=27;
        while(off<251)begin n=251-off>27 ? 27 : 251-off;fragment(off,n);off=off+n;end
        wait(rx_valid);
        if(rx_type!=2 || rx_length!=255)$fatal(1,"RX complete PDU length");
        for(i=0;i<255;i=i+1)begin rx_addr=i;repeat(2)@(negedge clk);if(rx_data!=source[i])$fatal(1,"RX normalized PDU byte %0d",i);end
        // A full upstream mailbox backpressures H5 without overwriting it.
        incoming[0]=8'h0e;incoming[1]=4;incoming[2]=1;incoming[3]=0;incoming[4]=0;incoming[5]=0;
        rt=4;rl=6;rv=1;repeat(20)@(negedge clk);
        if(rc || !rx_valid)$fatal(1,"Full mailbox was overwritten");
        consume();wait(rc);@(negedge clk);rv=0;wait(rx_valid);
        if(rx_type!=4 || rx_length!=6)$fatal(1,"Backpressured event lost");consume();
        old_errors=errors;fragment(27,27);if(errors<=old_errors || rx_valid)$fatal(1,"Orphan continuation accepted");
        fragment(0,27);repeat(2100)@(negedge clk);
        if(dut.partial)$fatal(1,"Incomplete PDU did not expire");
        old_errors=errors;fragment(27,27);if(errors<=old_errors)$fatal(1,"Continuation survived timeout");
        fragment(0,27);connected=0;repeat(4)@(negedge clk);connected=1;
        if(dut.partial)$fatal(1,"Disconnect retained partial PDU");
        source[4]=8;source[5]=0;fragment(0,8);
        old_errors=errors;fragment(8,8);
        if(errors<=old_errors || dut.partial || rx_valid)$fatal(1,"Overlong continuation accepted");
        source[4]=247;
        completion(16'h234,65535);if(dut.credits!=2)$fatal(1,"Credits exceeded controller capacity");
        // HCI passthrough does not spend ACL credits.
        source[0]=8'h0a;source[1]=8'h20;source[2]=1;source[3]=1;tx_type=1;tx_length=4;
        tx_start=1;@(negedge clk);tx_start=0;wait(tx_ready);repeat(10)@(negedge clk);
        if(tx_error)$fatal(1,"HCI passthrough error");
        $display("PASS: ACL 27-byte TX segmentation, physical credit exhaustion/replenishment and foreign handle, 247-byte RX with interleaved event, orphan/timeout/disconnect, synchronous RAM, HCI passthrough");$finish;
    end
    initial begin #2000000;$fatal(1,"ACL bridge watchdog sent=%0d total=%0d state=%0d",sent,total,dut.r_state);end
endmodule
