// CPU owns only the unpublished UI page. PRESENT freezes its base/mode until
// the video frame boundary; software polls pending/current before reusing the
// old page. The analysis renderer owns separate DDR pages and keeps running.
module gw138k_ui_services (
    input wire clk,reset_n,command_valid,command_write,
    input wire [11:0] command_address,
    input wire [31:0] command_data,
    input wire [3:0] command_strobes,
    output wire command_ready,
    output reg [31:0] response_data,
    output reg response_error,
    input wire frame_commit,
    input wire input_attached,input_valid,input_down,
    input wire [15:0] input_x,input_y,
    output reg pending,visible,
    output wire [28:0] front_base,next_base,
    output reg next_visible
);
    reg [31:0] staged_address,front_address,commits;
    reg presented,touch_down;
    reg [31:0] touch_xy,touch_sequence;
    assign command_ready=1;
    assign front_base=front_address[22]?29'h0500000:29'h0400000;
    assign next_base=staged_address[22]?29'h0500000:29'h0400000;
    always @* begin
        response_data=0;response_error=0;
        if(command_address[1:0]!=0 || (command_write && command_strobes!=15)) response_error=1;
        else if(command_write) case(command_address)
            12'h010:response_error=pending || (command_data!=32'h10000000 && command_data!=32'h10400000);
            12'h014:response_error=pending || command_data!=1;
            12'h018:response_error=pending || command_data>1;
            default:response_error=1;
        endcase
        else case(command_address)
            12'h000:response_data=32'h55493338; // UI38
            12'h004:response_data={29'd0,presented,visible,pending};
            12'h008:response_data=front_address;
            12'h00c:response_data=commits;
            12'h010:response_data=staged_address;
            12'h018:response_data={31'd0,next_visible};
            12'h020:response_data={30'd0,touch_down,input_attached};
            12'h024:response_data=touch_xy;
            12'h028:response_data=touch_sequence;
            default:response_error=1;
        endcase
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            staged_address<=32'h10000000;front_address<=32'h10000000;
            pending<=0;visible<=0;next_visible<=0;presented<=0;commits<=0;
            touch_down<=0;touch_xy<=0;touch_sequence<=0;
        end else begin
            if(input_valid) begin
                touch_down<=input_down;touch_xy<={input_y,input_x};touch_sequence<=touch_sequence+1'b1;
            end
            if(command_valid && command_write && !response_error) case(command_address)
                12'h010:staged_address<=command_data;
                12'h014:pending<=1;
                12'h018:next_visible<=command_data[0];
                default:begin end
            endcase
            if(frame_commit && pending) begin
                front_address<=staged_address;visible<=next_visible;pending<=0;
                presented<=1;commits<=commits+1'b1;
            end
        end
    end
endmodule
