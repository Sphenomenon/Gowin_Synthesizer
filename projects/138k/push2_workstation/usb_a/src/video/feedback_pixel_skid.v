`default_nettype none
// Two 64-bit beats isolate the writer's backpressure from raster-wide enables.
// Ready is a register of the exact next occupancy. No BSRAM or clock crossing.
// Completion is released only after every accepted beat reaches the writer.
module feedback_pixel_skid (
    input wire clk,rst_n,
    input wire source_valid,
    output reg source_ready,
    input wire [63:0] source_data,
    input wire source_done,
    output wire sink_valid,
    input wire sink_ready,
    output wire [63:0] sink_data,
    output reg sink_done
);
    reg [63:0] data0,data1;
    reg head,tail;
    reg [1:0] count;
    reg done_pending;
    wire push=source_valid && source_ready;
    wire pop=sink_valid && sink_ready;
    wire empty_after=(count==0 && !push) || (count==1 && pop && !push);
    assign sink_valid=count!=0;
    assign sink_data=head ? data1 : data0;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n)begin
            data0<=0;data1<=0;head<=0;tail<=0;count<=0;
            source_ready<=1;done_pending<=0;sink_done<=0;
        end else begin
            sink_done<=0;
            if(source_done)done_pending<=1;
            if((done_pending || source_done) && empty_after)begin
                sink_done<=1;done_pending<=0;
            end
            if(push)begin
                if(tail)data1<=source_data;else data0<=source_data;
                tail<=!tail;
            end
            if(pop)head<=!head;
            case({push,pop})
                2'b10:begin count<=count+1'b1;source_ready<=count==0;end
                2'b01:begin count<=count-1'b1;source_ready<=1;end
                default:begin end
            endcase
        end
    end
endmodule
`default_nettype wire
