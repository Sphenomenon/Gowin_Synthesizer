`default_nettype none
// A fresh trigger-aligned trace on every capture. No similarity rejection.
// PCM stays unfiltered; the capture module smooths the trigger reference only.
module feedback_wave_align(
    input wire clk,reset_n,start,
    input wire [31:0] snapshot_revision,snapshot_peak,
    output reg busy,done,
    output wire waveform_held,
    output wire capture_read_enable,
    output wire [8:0] capture_read_addr,
    input wire [31:0] capture_read_data,
    input wire wave_read_enable,
    input wire [8:0] wave_read_addr,
    output reg [31:0] wave_read_data
);
    localparam [1:0] IDLE=0,READ=1,COPY=2;
    reg [1:0] state;
    reg [8:0] index;
    reg [31:0] trace_samples[0:511];
    assign waveform_held=1'b0;
    assign capture_read_enable=state==READ;
    assign capture_read_addr=index;
    always @(posedge clk) begin
        if(state==COPY)trace_samples[index]<=capture_read_data;
        if(wave_read_enable && !busy)wave_read_data<=trace_samples[wave_read_addr];
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n)begin state<=IDLE;index<=0;busy<=0;done<=0;end
        else begin
            done<=0;
            case(state)
                IDLE:if(start)begin index<=0;busy<=1;state<=READ;end
                READ:state<=COPY;
                COPY:if(index==511)begin state<=IDLE;busy<=0;done<=1;end
                     else begin index<=index+1'b1;state<=READ;end
                default:begin state<=IDLE;busy<=0;end
            endcase
        end
    end
endmodule
`default_nettype wire
