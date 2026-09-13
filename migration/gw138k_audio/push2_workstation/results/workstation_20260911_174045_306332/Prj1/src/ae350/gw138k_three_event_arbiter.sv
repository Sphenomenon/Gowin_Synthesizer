// One registered stage, with independent G1, PC and CPU event parsers.
module gw138k_three_event_arbiter (
 input wire clk,reset_n,g1_valid,pc_valid,cpu_valid,
 input wire [17:0] g1_data,pc_data,cpu_data,
 output wire g1_ready,pc_ready,cpu_ready,
 output reg event_valid,output reg [17:0] event_data,input wire event_ready
);
 reg [1:0] first,selected;
 wire room=!event_valid || event_ready;
 always @* begin
  selected=0;
  case(first)
   0:if(g1_valid)selected=0;else if(pc_valid)selected=1;else selected=2;
   1:if(pc_valid)selected=1;else if(cpu_valid)selected=2;else selected=0;
   default:if(cpu_valid)selected=2;else if(g1_valid)selected=0;else selected=1;
  endcase
 end
 assign g1_ready=room && selected==0;
 assign pc_ready=room && selected==1;
 assign cpu_ready=room && selected==2;
 always @(posedge clk or negedge reset_n)
  if(!reset_n)begin first<=0;event_valid<=0;event_data<=0;end
  else if(room)begin
   event_valid<=g1_valid || pc_valid || cpu_valid;
   if(g1_valid || pc_valid || cpu_valid)begin
    event_data<=selected==0?g1_data:selected==1?pc_data:cpu_data;
    first<=selected==2?0:selected+1'b1;
   end
  end
endmodule
