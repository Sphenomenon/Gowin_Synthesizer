// Fill one documented 512-byte Push pixel block directly into the existing
// USB TX FIFO.  The CPU remains blocked until all 256 encoded pixels are in
// the FIFO, so token/PID/ACK handling and retry ownership stay unchanged.
module push2_screen_fifo_streamer(
    input wire clk,reset_n,start,
    output wire pixel_read,input wire pixel_ready,input wire [31:0] pixel_data,
    output wire fifo_push,output wire [7:0] fifo_data,
    output wire active,done
);
    localparam IDLE=0,READ_PIXEL=1,PUSH_LOW=2,PUSH_HIGH=3,FINISH=4;
    reg [2:0] state;
    reg [7:0] count;
    reg [15:0] encoded;
    assign active=state!=IDLE;
    assign done=state==FINISH;
    assign pixel_read=state==READ_PIXEL;
    assign fifo_push=state==PUSH_LOW || state==PUSH_HIGH;
    assign fifo_data=state==PUSH_HIGH?encoded[15:8]:encoded[7:0];
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n)begin state<=IDLE;count<=0;encoded<=0;end
        else case(state)
            IDLE:if(start)begin count<=0;state<=READ_PIXEL;end
            READ_PIXEL:if(pixel_ready)begin
                encoded<=pixel_data[15:0]^(count[0]?16'hffe7:16'hf3e7);
                state<=PUSH_LOW;
            end
            PUSH_LOW:state<=PUSH_HIGH;
            PUSH_HIGH:if(count==255)state<=FINISH;
                      else begin count<=count+1'b1;state<=READ_PIXEL;end
            FINISH:state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
