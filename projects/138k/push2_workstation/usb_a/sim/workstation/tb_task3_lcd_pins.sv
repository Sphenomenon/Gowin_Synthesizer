`timescale 1ns/1ps
// Four-state simulation is intentional: a two-state test cannot prove Z.
module tb_task3_lcd_pins;
    reg me=0,we=0;
    reg [6:0] mv=0,wv=0;
    tri [4:0] r,b;
    tri [5:0] g;
    tri pclk,hs,vs,de,bl,cr,cs,cc,ci;
    wire [3:0] md,wd;
    wire mr,ma,mp,wr,wa,wp;
    workstation_task3_lcd_pins #(.EXPERIMENT_ENABLE(1),.ROLE_M(1)) m(
        .drive_enable_i(me),.tx_data_i(mv[3:0]),.tx_req_i(mv[4]),.rx_ack_i(mv[5]),.panic_i(mv[6]),
        .rx_data_o(md),.rx_req_o(mr),.tx_ack_o(ma),.peer_panic_o(mp),
        .lcd_r(r),.lcd_g(g),.lcd_b(b),.lcd_pclk(pclk),.lcd_hsync(hs),.lcd_vsync(vs),.lcd_de(de),.lcd_bl(bl),
        .lcd_ctp_rst(cr),.lcd_ctp_sda(cs),.lcd_ctp_scl(cc),.lcd_ctp_int(ci));
    workstation_task3_lcd_pins #(.EXPERIMENT_ENABLE(1),.ROLE_M(0)) w(
        .drive_enable_i(we),.tx_data_i(wv[3:0]),.tx_req_i(wv[4]),.rx_ack_i(wv[5]),.panic_i(wv[6]),
        .rx_data_o(wd),.rx_req_o(wr),.tx_ack_o(wa),.peer_panic_o(wp),
        .lcd_r(r),.lcd_g(g),.lcd_b(b),.lcd_pclk(pclk),.lcd_hsync(hs),.lcd_vsync(vs),.lcd_de(de),.lcd_bl(bl),
        .lcd_ctp_rst(cr),.lcd_ctp_sda(cs),.lcd_ctp_scl(cc),.lcd_ctp_int(ci));
    tri [4:0] dr,db;
    tri [5:0] dg;
    tri dpclk,dhs,dvs,dde,dbl,dcr,dcs,dcc,dci;
    // Both unconfigured roles must remain Z despite enable and opposite data.
    workstation_task3_lcd_pins default_m(
        .drive_enable_i(1'b1),.tx_data_i(4'hf),.tx_req_i(1'b1),.rx_ack_i(1'b1),.panic_i(1'b1),
        .rx_data_o(),.rx_req_o(),.tx_ack_o(),.peer_panic_o(),
        .lcd_r(dr),.lcd_g(dg),.lcd_b(db),.lcd_pclk(dpclk),.lcd_hsync(dhs),.lcd_vsync(dvs),.lcd_de(dde),.lcd_bl(dbl),
        .lcd_ctp_rst(dcr),.lcd_ctp_sda(dcs),.lcd_ctp_scl(dcc),.lcd_ctp_int(dci));
    workstation_task3_lcd_pins #(.ROLE_M(0)) default_w(
        .drive_enable_i(1'b1),.tx_data_i(4'h0),.tx_req_i(1'b0),.rx_ack_i(1'b0),.panic_i(1'b0),
        .rx_data_o(),.rx_req_o(),.tx_ack_o(),.peer_panic_o(),
        .lcd_r(dr),.lcd_g(dg),.lcd_b(db),.lcd_pclk(dpclk),.lcd_hsync(dhs),.lcd_vsync(dvs),.lcd_de(dde),.lcd_bl(dbl),
        .lcd_ctp_rst(dcr),.lcd_ctp_sda(dcs),.lcd_ctp_scl(dcc),.lcd_ctp_int(dci));
    integer checks=0,i;
    task automatic require(input reg ok,input string message);
        begin checks=checks+1;if(!ok)$fatal(1,"pins check%0d %s",checks,message);end
    endtask
    task automatic reserved_z;
        begin
            require({b[4:3],pclk,hs,vs,de,bl,cr,cs,cc,ci}==={11{1'bz}},"all eleven reserved lines high impedance");
            require({dr,dg,db,dpclk,dhs,dvs,dde,dbl,dcr,dcs,dcc,dci}==={25{1'bz}},"default recipes never drive");
        end
    endtask
    initial begin
        #1;require({r,g,b,pclk,hs,vs,de,bl,cr,cs,cc,ci}==={25{1'bz}},"runtime disabled all pads high impedance");
        reserved_z();
        for(i=0;i<128;i=i+1)begin
            mv=7'(i);wv=~7'(i);me=1;we=0;#1;
            require(r===mv[4:0] && g===6'bzzzzzz && b==={3'bzzz,mv[6],mv[5]},"M fixed output ownership");
            require({wd,wr,wa,wp}==={mv[3:0],mv[4],mv[5],mv[6]},"M to W same-number nets");reserved_z();
            me=0;we=1;#1;
            require(r===5'bzzzzz && g==={wv[4:0],wv[5]} && b==={2'bzz,wv[6],2'bzz},"W fixed output ownership");
            require({md,mr,ma,mp}==={wv[3:0],wv[4],wv[5],wv[6]},"W to M same-number nets");reserved_z();
            me=1;#1;
            require(r===mv[4:0] && g==={wv[4:0],wv[5]} && b==={2'bzz,wv[6],mv[6],mv[5]},"complementary roles have no contested signal");
            require({wd,wr,wa,wp}==={mv[3:0],mv[4],mv[5],mv[6]} &&
                {md,mr,ma,mp}==={wv[3:0],wv[4],wv[5],wv[6]},"duplex input mapping exact");reserved_z();
            me=0;we=0;#1;require({r,g,b,pclk,hs,vs,de,bl,cr,cs,cc,ci}==={25{1'bz}},"disarm releases every programmable pad");
        end
        $display("PASS task3_lcd_pins checks=%0d",checks);$finish;
    end
endmodule
