`timescale 1ns/1ps
module tb_video_dashboard;
    reg [9:0] x=0,y=0;
    reg de=1;
    reg [31:0] level=32'h40000000, voices=5, status=3;
    wire [23:0] rgb;
    video_dashboard dut(x,y,de,level,voices,status,rgb);
    string output_path;
    integer image_file,row,col;
    task check_color(input integer px,input integer py,input [23:0] expected);
        begin
            x=px; y=py; #1;
            if(rgb!==expected) $fatal(1,"dashboard pixel (%d,%d) got %h expected %h",px,py,rgb,expected);
        end
    endtask
    initial begin
        check_color(100,160,24'h3cdbab);
        check_color(500,160,24'h273b50);
        check_color(80,300,24'h157d70);
        check_color(208,300,24'h263a4f);
        check_color(336,300,24'h157d70);
        check_color(464,300,24'h263a4f);
        level=0; check_color(100,160,24'h273b50);
        level=32'h80000000; check_color(560,160,24'hef6572);
        de=0; check_color(100,160,0);
        de=1; level=32'h40000000;
        // Optional actual RTL-generated raster for visual review (P6 PPM).
        if($value$plusargs("PPM=%s",output_path)) begin
            image_file=$fopen(output_path,"wb");
            if(image_file==0) $fatal(1,"could not open dashboard render output");
            $fwrite(image_file,"P6\n640 480\n255\n");
            for(row=0;row<480;row=row+1) begin
                for(col=0;col<640;col=col+1) begin
                    x=col; y=row; #1;
                    $fwrite(image_file,"%c%c%c",rgb[23:16],rgb[15:8],rgb[7:0]);
                end
            end
            $fclose(image_file);
        end
        $display("PASS tb_video_dashboard: level scale, four independent voice tiles, blanking");
        $finish;
    end
endmodule
