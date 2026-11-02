`timescale 1ns/1ps
// Full four-state pair: APB CDC -> F808 -> transport -> PHY -> same-number pads.
module tb_task3_paired_link #(
    parameter bit TEST_ALLOW_BUSINESS=1'b1
);
    reg mc=0,wc=0,mpc=0,wpc=0,dpc=0,w_run=1;
    always #10 mc=~mc;
    always #13 if(w_run)wc=~wc;
    always #7 mpc=~mpc;
    always #11 wpc=~wpc;
    always #17 dpc=~dpc;
    wire [2:0] pc={dpc,wpc,mpc};
    wire [1:0] lc={wc,mc};
    reg reset_n=0;
    reg [1:0] external_panic=0;
    reg [2:0] owner_n=0,select=0,enable=0,write=0;
    reg [35:0] address=0;reg [95:0] data=0;reg [11:0] strobes=12'hfff;
    wire [2:0] ready,error;
    wire [95:0] response;
    wire [2:0] probe,budget,business,live,panic,arm,cancel;
    wire [95:0] local_boot,peer_boot,sessions,generations;
    reg [1:0] tv=0,rr=3;reg [7:0] tch=0;reg [11:0] tlen=0;reg [511:0] tdata=0;
    wire [1:0] tr,rv;wire [7:0] rch;wire [11:0] rlen;wire [511:0] rdata;
    tri [4:0] r,b;tri [5:0] g;
    tri pclk_pad,hs,vs,de,bl,cr,cs,cc,ci;
    tri [4:0] dr,db;tri [5:0] dg;
    tri dpclk,dhs,dvs,dde,dbl,dcr,dcs,dcc,dci;
    workstation_task3_paired_link #(.ROLE_M(1),.EXPERIMENT_ENABLE(1),.ALLOW_BUSINESS(TEST_ALLOW_BUSINESS)) m(
        .clk_i(mc),.reset_ni(reset_n),.pclk(mpc),.preset_n(owner_n[0]),.external_panic_i(external_panic[0]),
        .psel(select[0]),.penable(enable[0]),.pwrite(write[0]),.paddr(address[11:0]),.pwdata(data[31:0]),.pstrb(strobes[3:0]),
        .pready(ready[0]),.pslverr(error[0]),.prdata(response[31:0]),
        .local_boot_o(local_boot[31:0]),.peer_boot_o(peer_boot[31:0]),.session_o(sessions[31:0]),.generation_o(generations[31:0]),
        .probe_enable_o(probe[0]),.budget_validated_o(budget[0]),.business_enable_o(business[0]),
        .link_ready_o(live[0]),.panic_o(panic[0]),.record_arm_o(arm[0]),.record_cancel_o(cancel[0]),
        .tx_valid_i(tv[0]),.tx_ready_o(tr[0]),.tx_channel_i(tch[3:0]),.tx_payload_i(tdata[255:0]),.tx_length_i(tlen[5:0]),
        .rx_valid_o(rv[0]),.rx_ready_i(rr[0]),.rx_channel_o(rch[3:0]),.rx_payload_o(rdata[255:0]),.rx_length_o(rlen[5:0]),
        .lcd_r(r),.lcd_g(g),.lcd_b(b),.lcd_pclk(pclk_pad),.lcd_hsync(hs),.lcd_vsync(vs),.lcd_de(de),.lcd_bl(bl),
        .lcd_ctp_rst(cr),.lcd_ctp_sda(cs),.lcd_ctp_scl(cc),.lcd_ctp_int(ci));
    workstation_task3_paired_link #(.ROLE_M(0),.EXPERIMENT_ENABLE(1),.ALLOW_BUSINESS(TEST_ALLOW_BUSINESS)) w(
        .clk_i(wc),.reset_ni(reset_n),.pclk(wpc),.preset_n(owner_n[1]),.external_panic_i(external_panic[1]),
        .psel(select[1]),.penable(enable[1]),.pwrite(write[1]),.paddr(address[23:12]),.pwdata(data[63:32]),.pstrb(strobes[7:4]),
        .pready(ready[1]),.pslverr(error[1]),.prdata(response[63:32]),
        .local_boot_o(local_boot[63:32]),.peer_boot_o(peer_boot[63:32]),.session_o(sessions[63:32]),.generation_o(generations[63:32]),
        .probe_enable_o(probe[1]),.budget_validated_o(budget[1]),.business_enable_o(business[1]),
        .link_ready_o(live[1]),.panic_o(panic[1]),.record_arm_o(arm[1]),.record_cancel_o(cancel[1]),
        .tx_valid_i(tv[1]),.tx_ready_o(tr[1]),.tx_channel_i(tch[7:4]),.tx_payload_i(tdata[511:256]),.tx_length_i(tlen[11:6]),
        .rx_valid_o(rv[1]),.rx_ready_i(rr[1]),.rx_channel_o(rch[7:4]),.rx_payload_o(rdata[511:256]),.rx_length_o(rlen[11:6]),
        .lcd_r(r),.lcd_g(g),.lcd_b(b),.lcd_pclk(pclk_pad),.lcd_hsync(hs),.lcd_vsync(vs),.lcd_de(de),.lcd_bl(bl),
        .lcd_ctp_rst(cr),.lcd_ctp_sda(cs),.lcd_ctp_scl(cc),.lcd_ctp_int(ci));
    // Production defaults cannot drive pads, even through real CPU config writes.
    workstation_task3_paired_link disabled(
        .clk_i(mc),.reset_ni(reset_n),.pclk(dpc),.preset_n(owner_n[2]),.external_panic_i(1'b0),
        .psel(select[2]),.penable(enable[2]),.pwrite(write[2]),.paddr(address[35:24]),.pwdata(data[95:64]),.pstrb(strobes[11:8]),
        .pready(ready[2]),.pslverr(error[2]),.prdata(response[95:64]),
        .local_boot_o(local_boot[95:64]),.peer_boot_o(peer_boot[95:64]),.session_o(sessions[95:64]),.generation_o(generations[95:64]),
        .probe_enable_o(probe[2]),.budget_validated_o(budget[2]),.business_enable_o(business[2]),
        .link_ready_o(live[2]),.panic_o(panic[2]),.record_arm_o(arm[2]),.record_cancel_o(cancel[2]),
        .tx_valid_i(1'b1),.tx_ready_o(),.tx_channel_i(4'd8),.tx_payload_i(256'd42),.tx_length_i(6'd1),
        .rx_valid_o(),.rx_ready_i(1'b1),.rx_channel_o(),.rx_payload_o(),.rx_length_o(),
        .lcd_r(dr),.lcd_g(dg),.lcd_b(db),.lcd_pclk(dpclk),.lcd_hsync(dhs),.lcd_vsync(dvs),.lcd_de(dde),.lcd_bl(dbl),
        .lcd_ctp_rst(dcr),.lcd_ctp_sda(dcs),.lcd_ctp_scl(dcc),.lcd_ctp_int(dci));
    integer checks=0,received[0:1],panic_width=0,last_panic_width=0;
    reg [3:0] last_channel[0:1];reg [5:0] last_length[0:1];reg [255:0] last_payload[0:1];
    always @(posedge mc)begin
        if(rv[0] && rr[0])begin received[0]=received[0]+1;last_channel[0]=rch[3:0];last_length[0]=rlen[5:0];last_payload[0]=rdata[255:0];end
        if(b[1]===1'b1)panic_width=panic_width+1;
        else if(panic_width!=0)begin last_panic_width=panic_width;panic_width=0;end
    end
    always @(posedge wc)if(rv[1] && rr[1])begin
        received[1]=received[1]+1;last_channel[1]=rch[7:4];last_length[1]=rlen[11:6];last_payload[1]=rdata[511:256];
    end
    task automatic require(input reg condition,input string message);
        begin checks=checks+1;if(condition!==1'b1)$fatal(1,"pair check%0d %s probe%b budget%b business%b live%b panic%b",checks,message,probe,budget,business,live,panic);end
    endtask
    task automatic pads_z;
        begin
            require({r,g,b,pclk_pad,hs,vs,de,bl,cr,cs,cc,ci}==={25{1'bz}},"same-number cable all-Z without runtime enable");
            require({dr,dg,db,dpclk,dhs,dvs,dde,dbl,dcr,dcs,dcc,dci}==={25{1'bz}},"default compile pads all-Z");
        end
    endtask
    task automatic reserved_z;
        begin require({b[4:3],pclk_pad,hs,vs,de,bl,cr,cs,cc,ci}==={11{1'bz}},"all eleven reserved wires remain Z");end
    endtask
    reg [31:0] rd;
    task automatic apb(input integer board,input reg wr,input [11:0] at,input [31:0] value,input [3:0] mask,input reg expect_error);
        integer age;
        begin
            @(negedge pc[board]);select[board]=1;enable[board]=0;write[board]=wr;
            address[board*12+:12]=at;data[board*32+:32]=value;strobes[board*4+:4]=mask;
            @(negedge pc[board]);enable[board]=1;age=0;
            while(ready[board]!==1'b1 && age<100)begin @(negedge pc[board]);age=age+1;end
            require(ready[board]===1'b1 && error[board]===expect_error,"actual APB CDC bounded response/error");
            rd=response[board*32+:32];
            @(posedge pc[board]);@(negedge pc[board]);select[board]=0;enable[board]=0;
        end
    endtask
    task automatic put(input integer board,input [11:0] at,input [31:0] value,input reg expect_error);
        begin apb(board,1,at,value,15,expect_error);end
    endtask
    task automatic get(input integer board,input [11:0] at,input [31:0] expected);
        begin apb(board,0,at,0,0,0);require(rd===expected,"actual F808 diagnostic readback");end
    endtask
    task automatic stage(input integer board,input [31:0] gen);
        begin
            put(board,'h010,board==1?32'h44556677:32'h11223344,0);
            put(board,'h014,board==1?32'h11223344:32'h44556677,0);
            put(board,'h018,32'ha1590000+gen,0);put(board,'h01c,gen,0);
        end
    endtask
    task automatic qualify_pair(input [31:0] gen);
        integer age;reg [31:0] ms,ws;
        begin
            stage(0,gen);stage(1,gen);pads_z();put(0,'h020,1,0);put(1,'h020,1,0);
            ms=0;ws=0;age=0;
            while((!ms[5] || !ws[5]) && age<500)begin
                apb(0,0,'h004,0,0,0);ms=rd;apb(1,0,'h004,0,0,0);ws=rd;age=age+1;
            end
            require(ms[5]&&ws[5]&&probe[1:0]==3,"physical model heartbeat qualifies probe via APB status");
            require(budget[1:0]==0&&business[1:0]==0&&live[1:0]==0,"probe cannot grant business authority");reserved_z();
        end
    endtask
    task automatic enable_business;
        begin
            put(0,'h024,1,0);put(1,'h024,1,0);
            require(budget[1:0]==3&&business[1:0]==0&&live[1:0]==0,"budget assertion remains independent of business enable");
            @(negedge mc);tch[3:0]=8;tlen[5:0]=1;tv[0]=1;repeat(20)@(negedge mc);
            require(tr[0]===1'b0,"business payload cannot handshake after budget alone");tv[0]=0;
            put(0,'h028,1,0);put(1,'h028,1,0);#1;
            require(business[1:0]==3&&live[1:0]==3,"both explicit grants release business on both roles");
        end
    endtask
    task automatic send(input integer board,input [3:0] channel,input [5:0] length,input [255:0] payload);
        integer age;
        begin
            @(negedge lc[board]);tch[board*4+:4]=channel;tlen[board*6+:6]=length;tdata[board*256+:256]=payload;tv[board]=1;age=0;
            while(tr[board]!==1'b1 && age<100000)begin @(negedge lc[board]);age=age+1;end
            require(tr[board]===1'b1,"typed transaction admitted by the same valid/ready gate");
            @(posedge lc[board]);@(negedge lc[board]);tv[board]=0;
        end
    endtask
    task automatic receive_exact(input integer board,input integer before_count,input [3:0] channel,input [5:0] length,input [255:0] payload);
        integer age;
        begin
            age=0;while(received[board]==before_count && age<100000)begin @(negedge lc[board]);age=age+1;end
            require(received[board]==before_count+1&&last_channel[board]===channel&&last_length[board]===length&&last_payload[board]===payload,"full pins/PHY/CRC path publishes exact typed packet once");
        end
    endtask
    integer before_m,before_w,age;
    initial begin
        received[0]=0;received[1]=0;#1;pads_z();repeat(8)@(negedge mc);reset_n=1;owner_n=7;repeat(16)@(negedge mc);pads_z();
        @(negedge mc);external_panic[0]=1;#1;require(panic[0],"standalone performance PANIC remains local");pads_z();
        @(negedge mc);external_panic[0]=0;repeat(2)@(negedge mc);pads_z();
        get(0,'h000,32'h54335001);apb(0,1,'h010,32'h12345678,3,1);put(0,'h020,1,1);pads_z();
        tv[0]=1;tch[3:0]=0;tlen[5:0]=1;repeat(20)@(negedge mc);require(tr[0]===1'b0,"no optimistic ready before probe");tv[0]=0;
        stage(2,1);put(2,'h020,1,0);put(2,'h024,1,1);
        require({dr,dg,db,dpclk,dhs,dvs,dde,dbl,dcr,dcs,dcc,dci}==={25{1'bz}}&&!live[2],"default experiment/compile policy cannot be bypassed through CPU");
        qualify_pair(1);put(0,'h010,32'hdeadbeef,1);get(0,'h010,32'h11223344);
        before_w=received[1];send(0,0,1,256'hff);receive_exact(1,before_w,0,1,256'hff);
        before_m=received[0];send(1,0,3,{256{1'b1}});receive_exact(0,before_m,0,3,256'hffffff);
        $display("CASE probe_control_duplex PASS");
        if(TEST_ALLOW_BUSINESS)begin
            enable_business();
            before_w=received[1];send(0,8,32,256'h0123456789abcdef0000111122223333444455556666777788889999aaaabbbb);
            receive_exact(1,before_w,8,32,256'h0123456789abcdef0000111122223333444455556666777788889999aaaabbbb);
            before_m=received[0];send(1,3,3,256'habcdef);receive_exact(0,before_m,3,3,256'habcdef);
            get(0,'h058,0);get(1,'h058,0);get(0,'h05c,0);get(1,'h05c,0);
            rr[0]=0;before_m=received[0];send(1,8,1,7);age=0;
            while(rv[0]!==1'b1&&age<100000)begin @(negedge mc);age=age+1;end
            require(rv[0]===1'b1,"business result held across actual receiver backpressure");put(0,'h024,0,0);#1;
            require(!live[0]&&!budget[0]&&!probe[0]&&!rv[0],"budget revocation withdraws held business through real CPU path");
            put(1,'h020,0,0);rr[0]=1;repeat(10)@(negedge mc);pads_z();get(0,'h038,1);put(0,'h01c,1,1);
            qualify_pair(2);enable_business();require(received[0]==before_m&&!rv[0],"fresh generation never replays revoked held result");
            $display("CASE business_budget_revoke_and_rearm PASS");
        end else begin
            put(0,'h024,1,1);put(1,'h024,1,1);put(0,'h028,1,1);
            require(probe[1:0]==3&&budget[1:0]==0&&business[1:0]==0,"compile denial preserves probe/control only");
        end
        // No reduced hold parameter: exercise all 50,000 production cycles.
        put(0,'h034,1,0);require(panic[0]&&b[1]===1'b1&&!probe[0]&&!live[0],"dedicated PANIC survives immediate config disable");
        age=0;while(probe[1]!==1'b0&&age<100)begin @(negedge wc);age=age+1;end
        require(probe[1]===1'b0&&!live[1],"peer dedicated PANIC fences through asynchronous pins");get(0,'h048,6);get(1,'h048,5);
        w_run=0;repeat(100)@(negedge mc);require(b[1]===1'b1,"dedicated local PANIC does not wait for peer clock");w_run=1;
        age=0;while(b[1]===1'b1&&age<51000)begin @(negedge mc);age=age+1;end
        repeat(3)@(negedge mc);require(last_panic_width>=50000&&last_panic_width<=50002,"actual dedicated PANIC high for at least 50,000 local cycles");
        pads_z();reserved_z();
        $display("CASE independent_panic_hold PASS local_cycles=%0d",last_panic_width);
        get(0,'h038,TEST_ALLOW_BUSINESS?2:1);put(0,'h020,0,0);put(1,'h020,0,0);
        qualify_pair(3);if(TEST_ALLOW_BUSINESS)enable_business();last_panic_width=0;
        @(negedge mc);external_panic[0]=1;#1;
        require(panic[0]&&!live[0]&&!budget[0]&&b[1]===1'b1,"external performance PANIC immediately revokes business and drives authorized dedicated line");
        @(negedge mc);external_panic[0]=0;#1;
        require(!probe[0]&&!business[0]&&local_boot[31:0]==0,"one external pulse revokes probe and identity at service owner");
        age=0;while(probe[1]!==1'b0&&age<100)begin @(negedge wc);age=age+1;end
        require(!probe[1]&&!live[1],"external performance PANIC reaches peer independently of packets");get(0,'h048,5);
        age=0;while(b[1]===1'b1&&age<51000)begin @(negedge mc);age=age+1;end
        repeat(3)@(negedge mc);require(last_panic_width>=50000&&last_panic_width<=50002,"external pulse offers the same full production PANIC hold");pads_z();
        $display("CASE external_performance_panic_hold PASS local_cycles=%0d",last_panic_width);
        qualify_pair(4);owner_n[0]=0;#1;require(!probe[0]&&!live[0],"actual CPU/APB reset immediately revokes grants");
        repeat(8)@(negedge mc);owner_n[0]=1;repeat(16)@(negedge mc);get(0,'h038,4);put(0,'h01c,4,1);
        put(1,'h020,0,0);pads_z();
        $display("PASS task3_paired_link ALLOW=%0d checks=%0d",TEST_ALLOW_BUSINESS,checks);$finish;
    end
    initial begin #20000000;$fatal(1,"full pair test timeout");end
endmodule
