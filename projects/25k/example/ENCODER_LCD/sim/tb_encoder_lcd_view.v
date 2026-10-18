`timescale 1ns/1ps
module tb_encoder_lcd_view;
    reg clk=0;
    always #10 clk=!clk;
    reg reset=1, snapshot=0;
    reg signed [15:0] position1=0, position2=0;
    reg [15:0] press_count1=0, press_count2=0, invalid_count1=0, invalid_count2=0;
    reg [1:0] ab1=0, ab2=0;
    reg key1=0, key2=0;
    reg signed [1:0] direction1=0, direction2=0;
    reg [15:0] pixel_x=0,pixel_y=0;
    wire [15:0] pixel_color;
    encoder_lcd_view dut (
        .clk(clk),.reset(reset),.snapshot(snapshot),
        .position1(position1),.position2(position2),
        .press_count1(press_count1),.press_count2(press_count2),
        .invalid_count1(invalid_count1),.invalid_count2(invalid_count2),
        .ab1(ab1),.ab2(ab2),.key1(key1),.key2(key2),
        .direction1(direction1),.direction2(direction2),
        .pixel_x(pixel_x),.pixel_y(pixel_y),.pixel_color(pixel_color)
    );
    reg start_bcd=0;
    reg [15:0] bcd_value=0;
    wire [19:0] converted_bcd;
    encoder_lcd_bcd16 conversion_test (
        .clk(clk),.reset(reset),.start(start_bcd),.value(bcd_value),.bcd(converted_bcd)
    );
    function [19:0] expected_bcd;
        input integer value;
        integer remaining;
        begin
            remaining=value;
            expected_bcd[3:0]=remaining%10; remaining=remaining/10;
            expected_bcd[7:4]=remaining%10; remaining=remaining/10;
            expected_bcd[11:8]=remaining%10; remaining=remaining/10;
            expected_bcd[15:12]=remaining%10; remaining=remaining/10;
            expected_bcd[19:16]=remaining%10;
        end
    endfunction
    task check_conversion;
        input [15:0] value;
        begin
            @(negedge clk); bcd_value=value; start_bcd=1;
            @(negedge clk); start_bcd=0; bcd_value=16'hdead;
            repeat(16) @(negedge clk);
            if(converted_bcd !== expected_bcd(value))
                $fatal(1,"BCD %0d got %h expected %h",value,converted_bcd,expected_bcd(value));
        end
    endtask
    task capture;
        begin
            @(negedge clk); snapshot=1;
            @(negedge clk); snapshot=0;
            repeat(32) @(negedge clk);
        end
    endtask
    // Independent sign glyph checks prove the sign and scaling on both cards.
    function sign_ink;
        input integer gx,gy;
        input negative;
        begin
            sign_ink=(gy==3 && gx<5) || (!negative && gx==2 && gy>=1 && gy<=5);
        end
    endfunction
    task check_sign;
        input integer origin_y;
        input negative;
        input [15:0] ink;
        integer x,y;
        reg [15:0] expected;
        begin
            for(y=0;y<21;y=y+1) begin
                for(x=0;x<18;x=x+1) begin
                    pixel_x=16+x; pixel_y=origin_y+y; #1;
                    expected=sign_ink(x/3,y/3,negative) ? ink : 16'h0000;
                    if(pixel_color !== expected)
                        $fatal(1,"position sign at %0d,%0d got %h expected %h",pixel_x,pixel_y,pixel_color,expected);
                end
            end
        end
    endtask
    reg [15:0] reference_frame [0:60775];
    integer x,y,index,changed,upper_ink,lower_ink;
    integer fp;
    reg [8*1024-1:0] out_path;
    integer red,green,blue;
    initial begin
        repeat(3) @(negedge clk); reset=0;
        check_conversion(0); check_conversion(1); check_conversion(9);
        check_conversion(10); check_conversion(99); check_conversion(100);
        check_conversion(999); check_conversion(1000); check_conversion(9999);
        check_conversion(10000); check_conversion(32767); check_conversion(32768);
        check_conversion(65535);

        position1=-16'sd32767; position2=16'sd32767;
        press_count1=65535; press_count2=10000;
        invalid_count1=9999; invalid_count2=1;
        ab1=2'b10; ab2=2'b01; key1=1; key2=0;
        direction1=-2'sd1; direction2=2'sd1;
        capture;
        if(dut.bcd_position1!==20'h32767 || dut.bcd_position2!==20'h32767 ||
           dut.bcd_press1!==20'h65535 || dut.bcd_press2!==20'h10000 ||
           dut.bcd_invalid1!==20'h09999 || dut.bcd_invalid2!==20'h00001)
            $fatal(1,"six captured BCD results differ from decimal reference");
        check_sign(76,1,16'h07ff);
        check_sign(260,0,16'hffe0);
        upper_ink=0; lower_ink=0;
        for(y=0;y<428;y=y+1) begin
            for(x=0;x<142;x=x+1) begin
                pixel_x=x; pixel_y=y; #1;
                if((^pixel_color) === 1'bx) $fatal(1,"unknown pixel at %0d,%0d",x,y);
                reference_frame[y*142+x]=pixel_color;
                if(y>=72 && y<=169 && pixel_color==16'h07ff) upper_ink=upper_ink+1;
                if(y>=256 && y<=353 && pixel_color==16'hffe0) lower_ink=lower_ink+1;
            end
        end
        if(upper_ink<1000 || lower_ink<1000) $fatal(1,"encoder cards have too few visible pixels");

        // Live input changes cannot alter any pixel until the next snapshot.
        position1=16'sd123; position2=-16'sd456;
        press_count1=42; press_count2=17; invalid_count1=0; invalid_count2=65535;
        ab1=2'b01; ab2=2'b10; key1=0; key2=1;
        direction1=2'sd1; direction2=0;
        repeat(40) @(negedge clk);
        for(y=0;y<428;y=y+1) begin
            for(x=0;x<142;x=x+1) begin
                pixel_x=x; pixel_y=y; #1;
                if(pixel_color !== reference_frame[y*142+x])
                    $fatal(1,"live input leaked into snapshot at %0d,%0d",x,y);
            end
        end
        capture;
        if(dut.bcd_position1!==20'h00123 || dut.bcd_position2!==20'h00456 ||
           dut.bcd_press1!==20'h00042 || dut.bcd_press2!==20'h00017 ||
           dut.bcd_invalid1!==20'h00000 || dut.bcd_invalid2!==20'h65535)
            $fatal(1,"second snapshot values incorrect");
        check_sign(76,0,16'h07ff);
        check_sign(260,1,16'hffe0);
        if(!$value$plusargs("OUT=%s",out_path)) out_path="/private/tmp/encoder_lcd_preview.ppm";
        fp=$fopen(out_path,"w");
        if(!fp) $fatal(1,"cannot open preview %0s",out_path);
        $fwrite(fp,"P3\n142 428\n255\n");
        changed=0;
        for(y=0;y<428;y=y+1) begin
            for(x=0;x<142;x=x+1) begin
                pixel_x=x; pixel_y=y; #1;
                if((^pixel_color) === 1'bx) $fatal(1,"unknown second-snapshot pixel");
                if(pixel_color !== reference_frame[y*142+x]) begin
                    changed=changed+1;
                    if(!(x>=8 && x<=133 && ((y>=72 && y<=169)||(y>=256 && y<=353))))
                        $fatal(1,"changing pixel outside partial refresh windows at %0d,%0d",x,y);
                end
                red=pixel_color[15:11]*255/31;
                green=pixel_color[10:5]*255/63;
                blue=pixel_color[4:0]*255/31;
                $fwrite(fp,"%0d %0d %0d\n",red,green,blue);
            end
        end
        $fclose(fp);
        if(changed<500) $fatal(1,"second snapshot did not change enough pixels");
        $display("PASS: BCD boundaries through 65535 in 16 clocks; six values; signed positions; snapshot isolation; 60776 finite pixels; %0d changed pixels confined to partial windows; preview %0s",changed,out_path);
        $finish;
    end
endmodule
