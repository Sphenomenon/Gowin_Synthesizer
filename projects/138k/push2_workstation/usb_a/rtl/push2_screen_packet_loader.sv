// One blocking CPU command loads 256 pixels into the existing USB TX FIFO.
// Uses the existing pixel-read and USB-register handshakes, all at 48 MHz.
module push2_screen_packet_loader(
    input wire clk,reset_n,start,
    output wire pixel_read,input wire pixel_ready,input wire [31:0] pixel_data,
    output wire usb_write,output wire [7:0] usb_data,input wire usb_ack,
    output wire active,done
);
    localparam IDLE=0,READ_PIXEL=1,WRITE_LOW=2,LOW_GAP=3,
               WRITE_HIGH=4,HIGH_GAP=5,FINISH=6;
    reg [2:0] state;
    reg [7:0] count;
    reg [15:0] encoded;
    assign active=state!=IDLE;
    assign done=state==FINISH;
    assign pixel_read=state==READ_PIXEL;
    assign usb_write=state==WRITE_LOW || state==WRITE_HIGH;
    assign usb_data=(state==WRITE_HIGH || state==HIGH_GAP)?encoded[15:8]:encoded[7:0];
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n)begin state<=IDLE;count<=0;encoded<=0;end
        else case(state)
            IDLE:if(start)begin count<=0;state<=READ_PIXEL;end
            READ_PIXEL:if(pixel_ready)begin
                encoded<=pixel_data[15:0]^(count[0]?16'hffe7:16'hf3e7);
                state<=WRITE_LOW;
            end
            WRITE_LOW:if(usb_ack)state<=LOW_GAP;
            LOW_GAP:state<=WRITE_HIGH;
            WRITE_HIGH:if(usb_ack)state<=HIGH_GAP;
            HIGH_GAP:if(count==255)state<=FINISH;
                     else begin count<=count+1'b1;state<=READ_PIXEL;end
            FINISH:state<=IDLE;
            default:state<=IDLE;
        endcase
    end
endmodule
