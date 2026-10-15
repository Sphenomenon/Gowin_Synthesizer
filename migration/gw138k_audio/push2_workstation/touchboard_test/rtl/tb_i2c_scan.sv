// Address-only writes, including 0x00; no device registers are modified.
// Schematic confirms PCA9685 U3, address 0x40 with A0..A5 grounded.
module tb_i2c_scan #(parameter integer CLK_HZ=50000000, I2C_HZ=100000)(
    input wire clk,rst_n, inout wire scl,sda,
    output reg [127:0] acknowledgements,
    output reg [3:0] last_error
);
    reg [31:0] timer;
    reg [6:0] address;
    reg start,pending;
    wire busy,done;
    wire [3:0] error;
    tb_i2c_master #(.CLK_HZ(CLK_HZ),.I2C_HZ(I2C_HZ)) bus(
      .clk(clk),.rst_n(rst_n),.start(start),.address(address),.read_mode(1'b0),
      .length(7'd0),.tx_data(512'd0),.rx_data(),.busy(busy),.done(done),.error(error),.scl(scl),.sda(sda),.pad_scl(1'b1),.pad_sda(1'b1),.drive_scl_low(),.drive_sda_low(),.peak_stretch());
    always @(posedge clk or negedge rst_n) begin
      if(!rst_n) begin timer<=CLK_HZ-1; address<=0; start<=0; pending<=0; acknowledgements<=0; last_error<=0; end
      else begin
        start<=0;
        if(timer!=0) timer<=timer-1'b1;
        else if(!pending && !busy) begin start<=1; pending<=1; end
        else if(pending && done) begin
          pending<=0; acknowledgements[address]<=(error==0);
          if(error>=3) last_error<=error;
          else if(error==0) last_error<=0;
          if(address==7'h77) begin address<=0; timer<=CLK_HZ-1; end
          else if(address==0) address<=8;
          else address<=address+1'b1;
        end
      end
    end
endmodule
