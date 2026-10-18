`timescale 1ns/1ps
module tb_panel_display_endpoint;
    reg clk=0;always #5 clk=~clk;
    reg reset=1,link_reset=0,rx_valid=0,tx_ready=1,settings_toggle=0;
    reg [7:0] rx_data=0;
    wire rx_ready,tx_valid;wire [7:0]tx_data;
    wire remote_enable,manual_settings,redraw_required;wire[15:0]protocol_errors;
    wire tile_valid;reg tile_ready=0,tile_done=0;
    wire[8:0]tile_x,tile_width;wire[7:0]tile_y,tile_height;
    reg[7:0]tile_read_addr=0;wire[15:0]tile_read_data;
    panel_display_endpoint #(.CLK_HZ(1000),.HEARTBEAT_MS(2000)) dut(.*);
    reg[7:0]payload[0:511];reg[7:0]response[0:63];
    integer response_count=0,checks=0,i,guard,n;reg[7:0]version=1;
    reg[7:0]held;integer handshakes=0;
    always @(posedge clk) begin
        if(tx_valid&&tx_ready) begin
            if(response_count>=64) $fatal(1,"response overflow");
            response[response_count]=tx_data;response_count=response_count+1;
        end
        if(tile_valid&&tile_ready)handshakes=handshakes+1;
    end
    task check;input condition;input[511:0]message;
        begin checks=checks+1;if(!condition)$fatal(1,"%0s",message);end
    endtask
    task clocks;input integer count;integer k;
        begin for(k=0;k<count;k=k+1)@(negedge clk);end
    endtask
    task byte_in;input[7:0]value;integer k;
        begin
            @(negedge clk);rx_data=value;rx_valid=1;k=0;
            while(!rx_ready) begin @(negedge clk);k=k+1;if(k>1000)$fatal(1,"RX stalled");end
            @(posedge clk);@(negedge clk);rx_valid=0;
        end
    endtask
    task put16;input integer at;input[15:0]value;
        begin payload[at]=value[7:0];payload[at+1]=value[15:8];end
    endtask
    task put32;input integer at;input[31:0]value;
        begin put16(at,value[15:0]);put16(at+2,value[31:16]);end
    endtask
    task packet;
        input[7:0]kind;input[31:0]session;input[15:0]seq;
        input[7:0]flags;input integer length;integer k;
        begin
            response_count=0;
            byte_in(8'h50);byte_in(8'h4c);byte_in(version);byte_in(kind);
            byte_in(session[7:0]);byte_in(session[15:8]);byte_in(session[23:16]);byte_in(session[31:24]);
            byte_in(seq[7:0]);byte_in(seq[15:8]);byte_in(0);byte_in(0);
            byte_in(length&255);byte_in((length>>8)&255);byte_in(flags);byte_in(1);
            for(k=0;k<length;k=k+1)byte_in(payload[k]);
        end
    endtask
    task reply;input[7:0]kind;input[7:0]status;input[15:0]seq;integer k,len;
        begin
            k=0;while(response_count<16)begin clocks(1);k=k+1;if(k>2500)$fatal(1,"no reply header");end
            len=16+response[12]+256*response[13];
            while(response_count<len)begin clocks(1);k=k+1;if(k>2500)$fatal(1,"short reply");end
            check(response[0]==8'h50&&response[1]==8'h4c&&response[2]==1,"reply header");
            check(response[3]==kind,"reply type");
            check({response[9],response[8]}==seq&&{response[11],response[10]}==seq,"seq and ack echo");
            if(kind!=8'h81)check(response[16]==status,"reply status");
            clocks(2);check(response_count==len&&!tx_valid,"exactly one complete reply");
        end
    endtask
    task tile;
        input[31:0]frame;input[15:0]x,y,w,h;
        begin
            for(i=0;i<512;i=i+1)payload[i]=0;
            put16(0,7);put32(4,frame);put16(8,x);put16(10,y);put16(12,w);put16(14,h);
            put16(16,16'hf800);put16(18,16'h07e0);put16(20,16'h001f);put16(22,16'ha55a);
        end
    endtask
    task end_frame;input[31:0]frame;
        begin put16(0,7);put16(2,0);put32(4,frame);end
    endtask
    task read_pixel;input[7:0]addr;input[15:0]value;
        begin @(negedge clk);tile_read_addr=addr;@(posedge clk);@(negedge clk);
            check(tile_read_data==value,"synchronous immutable RGB565 tile RAM");end
    endtask
    task toggle_settings;
        begin @(negedge clk);settings_toggle=1;@(negedge clk);settings_toggle=0;clocks(1);end
    endtask
    task start_tile;
        begin @(negedge clk);tile_ready=1;@(negedge clk);tile_ready=0;clocks(1);
            check(!tile_valid,"tile valid drops after handshake");end
    endtask
    task finish_tile;
        begin @(negedge clk);tile_done=1;@(negedge clk);tile_done=0;clocks(1);end
    endtask
    initial begin
        clocks(4);reset=0;clocks(2);
        check(!remote_enable&&!manual_settings&&redraw_required,"reset local page");
        toggle_settings;check(!manual_settings,"local long press is harmless");
        tile(1,10,20,2,2);packet(8'h20,32'h12345678,0,3,24);reply(8'hff,4,0);
        check(!remote_enable&&!tile_valid,"no pixels without session");
        packet(1,32'h12345678,10,1,0);reply(8'h81,0,10);
        check({response[17],response[16]}==428&&{response[19],response[18]}==142,"CAPS dimensions");
        check(response[20]==1&&{response[23],response[22]}==248,"CAPS pixel format and limit");
        packet(1,32'h12345678,10,1,0);reply(8'h81,0,10);
        packet(2,32'h12345678,11,1,0);reply(8'h82,0,11);
        check(!remote_enable,"HELLO and HEALTH never open input page");
        packet(2,32'h12345678,13,1,0);reply(8'hff,5,13);
        packet(2,32'h12345678,12,1,0);reply(8'h82,0,12);
        version=2;packet(2,32'h12345678,13,1,0);reply(8'hff,3,13);version=1;
        tile(1,427,141,2,2);packet(8'h20,32'h12345678,0,3,24);reply(8'hff,7,0);
        tile(1,420,140,2,2);payload[2]=1;packet(8'h20,32'h12345678,0,3,24);reply(8'hff,6,0);
        payload[2]=0;packet(8'h20,32'h12345678,0,3,23);reply(8'hff,6,0);
        packet(8'h20,32'h12345678,0,3,24);reply(8'ha0,0,0);
        check(remote_enable&&tile_valid&&redraw_required,"validated tile opens input page");
        check(tile_x==420&&tile_y==140&&tile_width==2&&tile_height==2,"tile geometry");
        check(response[15]==0,"display credit while locked");
        read_pixel(0,16'hf800);read_pixel(1,16'h07e0);read_pixel(2,16'h001f);read_pixel(3,16'ha55a);
        packet(8'h20,32'h12345678,0,3,24);reply(8'ha0,0,0);
        check(handshakes==0&&tile_valid,"duplicate does not requeue");
        payload[16]=8'h34;packet(8'h20,32'h12345678,0,3,24);reply(8'hff,5,0);
        packet(8'h20,32'h12345678,1,3,24);reply(8'ha0,2,1);read_pixel(0,16'hf800);
        // Control traffic is independent of tile backpressure; TX must hold.
        tx_ready=0;packet(2,32'h12345678,13,1,0);
        guard=0;while(!tx_valid)begin clocks(1);guard=guard+1;if(guard>100)$fatal(1,"no stalled response");end
        held=tx_data;clocks(20);check(tx_valid&&tx_data==held,"TX stable under backpressure");
        tx_ready=1;reply(8'h82,0,13);
        end_frame(1);packet(8'h21,32'h12345678,1,3,8);reply(8'ha0,2,1);
        check(tile_valid,"boot-pending FRAME_END returns BUSY without cancelling tile");
        start_tile;packet(8'h21,32'h12345678,1,3,8);clocks(20);
        check(response_count==0&&!tx_valid,"FRAME_END waits for started tile physical done");
        clocks(10);check(response_count==0,"handshake alone is not DRAWN");
        finish_tile;reply(8'ha1,0,1);check(response[15]==1,"DRAWN releases display credit");
        check(!redraw_required,"completed initial canvas clears redraw flag");
        packet(8'h21,32'h12345678,1,3,8);reply(8'ha1,0,1);
        check(handshakes==1,"duplicate frame end has no tile side effect");
        end_frame(2);packet(8'h21,32'h12345678,2,3,8);reply(8'hff,7,2);
        toggle_settings;check(manual_settings&&!remote_enable&&redraw_required,"long press opens settings");
        end_frame(1);packet(8'h21,32'h12345678,1,3,8);reply(8'ha0,1,1);
        check(response[17]==5,"old DRAWN duplicate cannot revive hidden canvas");
        tile(2,0,0,2,2);packet(8'h20,32'h12345678,2,3,24);reply(8'ha0,1,2);
        check(!tile_valid&&!remote_enable,"incoming pixels cannot escape settings");
        end_frame(2);packet(8'h21,32'h12345678,3,3,8);reply(8'ha0,1,3);
        packet(2,32'h12345678,14,1,0);reply(8'h82,0,14);
        check(response[17]==5,"HEALTH reports manual settings and redraw");
        toggle_settings;check(!manual_settings&&!remote_enable&&redraw_required,"exit waits for fresh pixels");
        packet(2,32'h12345678,15,1,0);reply(8'h82,0,15);check(response[17]==4,"resume flag visible to host");
        tile(3,0,0,2,2);packet(8'h20,32'h12345678,4,3,24);reply(8'ha0,0,4);
        start_tile;read_pixel(3,16'ha55a);
        // Soft link reset must preserve the serializer's live buffer.
        @(negedge clk);link_reset=1;@(negedge clk);link_reset=0;clocks(2);
        check(!remote_enable&&redraw_required,"link reset returns local");read_pixel(0,16'hf800);
        packet(1,32'h87654321,100,1,0);reply(8'h81,0,100);
        tile(4,1,1,2,2);payload[16]=8'h34;packet(8'h20,32'h87654321,0,3,24);reply(8'ha0,2,0);
        read_pixel(0,16'hf800);finish_tile;
        packet(8'h20,32'h87654321,0,3,24);reply(8'ha0,0,0);read_pixel(0,16'hf834);
        start_tile;end_frame(4);packet(8'h21,32'h87654321,1,3,8);clocks(2005);
        reply(8'ha0,1,1);
        check(!remote_enable&&redraw_required,"heartbeat expiry returns local");
        read_pixel(0,16'hf834);end_frame(4);
        packet(8'h21,32'h87654321,1,3,8);reply(8'hff,4,1);
        finish_tile;
        // Bounded recovery from an incomplete header, then a fresh session.
        response_count=0;byte_in(8'h50);byte_in(8'h4c);byte_in(1);clocks(55);reply(8'hff,6,0);
        packet(1,32'h11223344,5,1,0);reply(8'h81,0,5);
        tile(10,0,0,0,1);packet(8'h20,32'h11223344,0,3,18);reply(8'hff,7,0);
        packet(2,32'h11223344,6,5,0);reply(8'hff,6,6);
        // Largest legal payload exercises the complete staging RAM and bounds.
        tile(20,180,141,248,1);
        for(i=0;i<248;i=i+1)put16(16+2*i,16'h4000+i);
        packet(8'h20,32'h11223344,0,3,512);reply(8'ha0,0,0);
        read_pixel(0,16'h4000);read_pixel(247,16'h40f7);
        // Correctly sequenced boot BUSY traffic keeps a slow-starting LCD alive.
        end_frame(20);clocks(1800);packet(8'h21,32'h11223344,1,3,8);reply(8'ha0,2,1);
        clocks(1800);packet(8'h21,32'h11223344,1,3,8);reply(8'ha0,2,1);
        check(remote_enable&&tile_valid,"BUSY retries keep boot-pending session alive");
        start_tile;finish_tile;check(redraw_required,"tile_done alone does not certify full redraw");
        end_frame(20);packet(8'h21,32'h11223344,1,3,8);reply(8'ha1,0,1);
        check(!redraw_required&&response[17]==2,"only matching FRAME_END clears redraw");
        // Settings survive both expiry and reconnection; no unsolicited output.
        toggle_settings;clocks(2005);check(manual_settings&&!remote_enable,"expiry preserves manual override");
        packet(1,32'h55667788,9,1,0);reply(8'h81,0,9);
        check(manual_settings,"new session preserves manual override");
        tile(21,0,0,1,1);packet(8'h20,32'h55667788,0,3,18);reply(8'ha0,1,0);
        check(!tile_valid&&!remote_enable,"reconnected host remains hidden");
        check(protocol_errors>=10,"malformed and stale requests counted");
        response_count=0;byte_in(8'h50);byte_in(8'h4c);
        @(negedge clk);reset=1;@(negedge clk);reset=0;clocks(70);
        check(response_count==0&&!tx_valid&&!remote_enable&&!manual_settings,"hard reset aborts partial frame");
        $display("PASS tb_panel_display_endpoint checks=%0d",checks);$finish;
    end
    initial begin #1000000;$fatal(1,"watchdog");end
endmodule
