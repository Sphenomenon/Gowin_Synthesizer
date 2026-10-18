`timescale 1ns/1ps
module tb_screen_packet_loader;
    reg clk=0,reset_n=0,start=0;
    always #10 clk=~clk;
    wire read_pixel,write_usb,active,done,ack;
    wire [7:0] byte_data;
    integer pixel_index=0,cycles=0,start_cycle,loads=0;
    reg stall_pixels=0;
    wire pixel_ready=!stall_pixels || cycles%5!=0;
    function [15:0] source_pixel(input integer index);
        // Include the 64 padding pixels at the right of each line.
        source_pixel=(index%1024>=960)?16'd0:16'(index*73+16'h1234);
    endfunction
    wire [31:0] pixel_data={16'd0,source_pixel(pixel_index)};
    push2_screen_packet_loader dut(.clk(clk),.reset_n(reset_n),.start(start),
        .pixel_read(read_pixel),.pixel_ready(pixel_ready),.pixel_data(pixel_data),
        .usb_write(write_usb),.usb_data(byte_data),.usb_ack(ack),.active(active),.done(done));
    usbh_core usb(.clk_i(clk),.rstn_i(reset_n),
        .reg_cs(write_usb),.reg_wr(write_usb),.reg_addr(6'h20),
        .reg_wdata({24'd0,byte_data}),.reg_be(4'hf),.reg_rdata(),.reg_ack(ack),
        .utmi_data_in_i(8'd0),.utmi_txready_i(1'b1),.utmi_rxvalid_i(1'b0),
        .utmi_rxactive_i(1'b0),.utmi_rxerror_i(1'b0),.utmi_linestate_i(2'b01));
    always @(posedge clk) begin
        cycles<=cycles+1;
        if(reset_n && read_pixel && pixel_ready)pixel_index<=pixel_index+1;
    end
    task load(input integer first,input bit stalled);
        reg [15:0] expected;
        begin
            @(negedge clk);reset_n=0;start=0;stall_pixels=stalled;
            repeat(3)@(negedge clk);
            pixel_index=first;reset_n=1;
            @(negedge clk);start=1;start_cycle=cycles;
            wait(done);@(negedge clk);start=0;
            if(usb.u_fifo_tx.count!=512 || pixel_index!=first+256)
                $fatal(1,"length/index mismatch count=%0d pixel=%0d",usb.u_fifo_tx.count,pixel_index);
            for(integer i=0;i<256;i++)begin
                expected=source_pixel(first+i)^(i%2?16'hffe7:16'hf3e7);
                if(usb.u_fifo_tx.ram[2*i]!==expected[7:0] ||
                   usb.u_fifo_tx.ram[2*i+1]!==expected[15:8])
                    $fatal(1,"wire byte mismatch packet=%0d pixel=%0d",first/256,i);
            end
            if(!stalled && cycles-start_cycle>1800)$fatal(1,"unexpected packet load cost");
            $display("packet=%0d pixel_stalls=%0d load_cycles=%0d",first/256,stalled,cycles-start_cycle);
            loads++;
        end
    endtask
    initial begin
        load(0,0);load(768,0);load(768,1);load(639*256,1);
        $display("PASS screen packet loader: %0d packets through real USB register pipeline/FIFO; byte order, XOR, padding, replay, backpressure",loads);
        $finish;
    end
    initial begin #1000000;$fatal(1,"timeout");end
endmodule
