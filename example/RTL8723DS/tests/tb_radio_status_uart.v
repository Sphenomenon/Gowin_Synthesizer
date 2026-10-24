`timescale 1ns/1ps
module tb_radio_status_uart;
    reg clk=0; always #5 clk=~clk;
    reg resetn=0;
    reg [1023:0] debug=0;
    wire serial_out;
    radio_status_uart #(.CLK_HZ(1152000),.REPORT_MS(1)) dut(
        .clk(clk),.resetn(resetn),.debug(debug),.serial_out(serial_out));
    integer i,j,k,word_index,nibble;
    reg [7:0] value,expected;
    reg [31:0] word_value;
    task clocks;
        input integer n;
        integer x;
        begin for(x=0;x<n;x=x+1) @(posedge clk); #1; end
    endtask
    task receive;
        output [7:0] data;
        integer b;
        begin
            @(negedge serial_out); clocks(5);
            if(serial_out!==0) $fatal(1,"invalid UART start");
            for(b=0;b<8;b=b+1) begin clocks(10); data[b]=serial_out; end
            clocks(10); if(serial_out!==1) $fatal(1,"invalid UART stop");
        end
    endtask
    initial begin
        for(i=0;i<32;i=i+1) debug[i*32+:32]=32'h1000+i;
        clocks(10); resetn=1;
        for(j=0;j<2;j=j+1) begin
            for(k=0;k<262;k=k+1) begin
                receive(value);
                case(k)
                    0: expected="R"; 1: expected="F"; 2: expected="1"; 3: expected="3"; 4: expected=" ";
                    261: expected=10;
                    default: begin
                        word_index=(k-5)/8;
                        word_value=(j==0 ? 32'h1000 : 32'h2000)+word_index;
                        nibble=(word_value>>((7-(k-5)%8)*4))&15;
                        expected=nibble<10 ? 48+nibble : 65+nibble-10;
                    end
                endcase
                if(value!==expected) $fatal(1,"UART frame %d byte %d expected %h got %h",j,k,expected,value);
                if(j==0 && k==10) for(i=0;i<32;i=i+1) debug[i*32+:32]=32'h2000+i;
            end
        end
        $display("PASS: 262-byte UART frames, all 32 words, coherent snapshots"); $finish;
    end
    initial begin #10000000; $fatal(1,"UART watchdog"); end
endmodule
