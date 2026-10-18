`timescale 1ns/1ps
// Transparent pixel overlay: snapshot only on existing P26 frame_start.
module sampler_grid(
  input logic clk,rst_n,frame_start,
  input logic [63:0] grid,input logic [3:0] pattern,step,input logic [1:0] group_select,
  input logic running,input logic [10:0] x,input logic [7:0] y,
  output logic dirty,ink,output logic [23:0] rgb
);
  logic [63:0] snap_grid;logic [3:0] snap_pattern,snap_step;
  logic [1:0] snap_group;logic snap_running;integer t,s;
  assign dirty=grid!=snap_grid || pattern!=snap_pattern || step!=snap_step ||
    group_select!=snap_group || running!=snap_running;
  always_ff @(posedge clk or negedge rst_n) begin
    if(!rst_n) begin snap_grid<=0;snap_pattern<=0;snap_step<=0;snap_group<=0;snap_running<=0;end
    else if(frame_start) begin snap_grid<=grid;snap_pattern<=pattern;snap_step<=step;snap_group<=group_select;snap_running<=running;end
  end
  always_comb begin
    ink=0;rgb=0;t=0;s=0;
    if(x>=32 && x<800 && y>=32 && y<128) begin
      t=(int'(y)-32)/24;s=(int'(x)-32)/48;
      if((x-32)%48<44 && (y-32)%24<20) begin
        ink=1;rgb=snap_grid[t*16+s] ? 24'h20a080 : 24'h182028;
        if(snap_running && s==int'(snap_step)) rgb=snap_grid[t*16+s] ? 24'hf0c040 : 24'h605020;
        if(t==int'(snap_group) && (y-32)%24<2) rgb=24'h80b0e0;
      end
    end
    if(y>=136 && y<144 && x>=32 && x<800 && (x-32)/48==snap_pattern) begin ink=1;rgb=24'h40a0f0;end
  end
endmodule
