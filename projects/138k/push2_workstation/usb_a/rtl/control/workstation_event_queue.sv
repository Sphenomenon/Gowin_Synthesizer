// Two complete event words; input ready depends only on occupancy and source
// arbitration. Lifecycle cancellation discards all accepted old-session words.
module workstation_event_queue (
 input wire clk,reset_n,clear,g1_valid,pc_valid,cpu_valid,
 input wire [17:0] g1_data,pc_data,cpu_data,
 output wire g1_ready,pc_ready,cpu_ready,
 output wire event_valid,output wire [17:0] event_data,input wire event_ready
);
 reg [1:0] first,selected,count;
 reg head,tail;reg [17:0] data[0:1];
 wire room=count<2 && !clear;
 wire push=room && (g1_valid || pc_valid || cpu_valid);
 wire pop=event_valid && event_ready;
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
 assign event_valid=count!=0 && !clear;
 assign event_data=data[head];
 always @(posedge clk or negedge reset_n)
  if(!reset_n)begin count<=0;head<=0;tail<=0;first<=0;data[0]<=0;data[1]<=0;end
  else if(clear)begin count<=0;head<=0;tail<=0;end
  else begin
   case({push,pop})2'b10:count<=count+1'b1;2'b01:count<=count-1'b1;default:begin end endcase
   if(pop)head<=!head;
   if(push)begin
    data[tail]<=selected==0?g1_data:selected==1?pc_data:cpu_data;
    tail<=!tail;first<=selected==2?0:selected+1'b1;
   end
  end
endmodule
