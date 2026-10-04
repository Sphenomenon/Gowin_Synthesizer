`timescale 1ns/1ps
module tb_playlist_bridge;
    reg clk50=0,usbclk=0,rst_n=0,scan_done=0;
    wire [7:0] addr;
    reg [7:0] data;
    wire valid;
    wire [15:0] word;
    integer got=0;
    reg [7:0] name_base=8'd65;
    always #10 clk50=~clk50;
    always #11 usbclk=~usbclk;
    always @(posedge clk50) data<=name_base+addr;
    tf_playlist_bridge dut(.clk_50m(clk50),.reset_n(rst_n),
        .usb_clk(usbclk),.usb_reset_n(rst_n),.scan_done(scan_done),
        .track_count(5'd2),.name_addr(addr),.name_data(data),
        .playlist_valid(valid),.playlist_ready(1'b1),.playlist_word(word));
    always @(posedge usbclk) if(rst_n && valid) begin
        if(got==0 || got==26) begin
            if(word!==16'hff02)$fatal(1,"count header %h",word);
        end else if(got==25) begin
            if(word!==16'hff00)$fatal(1,"stale playlist not cleared %h",word);
        end else if(got<25 && (word[15:8]!==got-1 || word[7:0]!==8'd65+got-1))
            $fatal(1,"name byte %0d: %h",got,word);
        else if(got>26 && (word[15:8]!==got-27 || word[7:0]!==8'd97+got-27))
            $fatal(1,"name byte %0d: %h",got,word);
        got=got+1;
    end
    initial begin
        repeat(5)@(negedge clk50);rst_n=1;
        repeat(3)@(negedge clk50);scan_done=1;
        repeat(150)@(negedge clk50);
        if(got!=25)$fatal(1,"playlist bytes %0d",got);
        scan_done=0;name_base=8'd97;
        repeat(20)@(negedge clk50);
        if(got!=26)$fatal(1,"missing invalidation %0d",got);
        scan_done=1;
        repeat(150)@(negedge clk50);
        if(got!=51)$fatal(1,"playlist reload bytes %0d",got);
        $display("PASS playlist invalidation and reload through CDC");$finish;
    end
endmodule
