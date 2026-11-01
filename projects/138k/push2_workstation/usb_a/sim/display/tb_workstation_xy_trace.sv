`timescale 1ns/1ps
module tb_workstation_xy_trace #(
    parameter integer FRAMES=1,POINTS=1
);
    reg clk=0,reset_n=0,frame_start=0,point_valid=0,point_nonzero=0;
    reg[2:0]gain=0;reg[7:0]x=0,y=0;
    always #5 clk=~clk;
    wire frame_ready,point_ready,idle,write_enable,write_pixel;
    wire[15:0]write_address;
    workstation_xy_trace dut(.clk,.reset_n,.frame_start_i(frame_start),.gain_i(gain),
        .frame_ready_o(frame_ready),.point_valid_i(point_valid),.point_nonzero_i(point_nonzero),
        .point_x_i(x),.point_y_i(y),.point_ready_o(point_ready),.idle_o(idle),
        .write_enable_o(write_enable),.write_address_o(write_address),.write_pixel_o(write_pixel));
    reg [19:0]meta[0:FRAMES-1];reg[16:0]points[0:POINTS-1];reg expected[0:FRAMES*65536-1];
    reg bitmap[0:65535];
    integer writes=0,clears=0,draws=0,compared=0,point_count=0,max_wait=0;
    always @(posedge clk)if(reset_n && write_enable)begin
        bitmap[write_address]=write_pixel;writes++;
        if(dut.state==1)clears++;else draws++;
    end
    task tick(input integer n);repeat(n)@(negedge clk);endtask
    task send_point(input[16:0]p);
        integer n;
        begin
            n=0;while(!point_ready)begin tick(1);n++;if(n>258)$fatal(1,"segment exceeded 256 raster pixels");end
            if(n>max_wait)max_wait=n;
            x=p[7:0];y=p[15:8];point_nonzero=p[16];point_valid=1;tick(1);point_valid=0;point_count++;
        end
    endtask
    integer offset=0,n;reg snapshot_before_reset;
    initial begin
        $readmemh("meta.mem",meta);$readmemh("points.mem",points);$readmemh("expected.mem",expected);
        for(integer a=0;a<65536;a++)bitmap[a]=(a%3)==1;
        tick(3);reset_n=1;tick(2);
        for(integer f=0;f<FRAMES;f++)begin
            if(meta[f][19])begin
                // Interrupt an actual drawing operation, then start a fresh
                // same-gain context. Prior RAM contents remain physically
                // present and must be rejected by the owner's valid lifetime.
                gain=meta[f][18:16];frame_start=1;tick(1);frame_start=0;
                wait(frame_ready);tick(1);send_point({1'b1,8'd4,8'd5});send_point({1'b1,8'd250,8'd245});
                tick(4);reset_n=0;tick(3);reset_n=1;tick(2);
            end
            gain=meta[f][18:16];frame_start=1;tick(1);frame_start=0;n=0;
            while(!frame_ready)begin tick(1);n++;if(n>131074)$fatal(1,"clear exceeded two cycles per pixel");end
            for(integer p=0;p<int'(meta[f][15:0]);p++)send_point(points[offset+p]);
            offset+=int'(meta[f][15:0]);n=0;
            while(!idle)begin tick(1);n++;if(n>258)$fatal(1,"last segment exceeded bound");end
            tick(2);
            for(integer a=0;a<65536;a++)begin
                if(bitmap[a]!==expected[f*65536+a])$fatal(1,"XY trace bitmap mismatch frame=%0d x=%0d y=%0d actual=%b expected=%b",f,a%256,a/256,bitmap[a],expected[f*65536+a]);
                compared++;
            end
        end
        if(offset!=POINTS || clears<FRAMES*65536 || draws==0)$fatal(1,"fixture omitted inputs/clear/draw");
        $display("PASS xy_trace frames=%0d accepted_points=%0d compared_pixels=%0d actual_writes=%0d raw_clear_writes=%0d line_pixel_writes=%0d maximum_segment_wait=%0d",FRAMES,point_count,compared,writes,clears,draws,max_wait);
        $finish;
    end
    initial begin #100000000;$fatal(1,"XY trace watchdog");end
endmodule
