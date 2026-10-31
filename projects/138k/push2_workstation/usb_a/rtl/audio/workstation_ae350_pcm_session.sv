`default_nettype none
// Source holds epoch/generation immutable while ready is high. A source-key
// change MUST revoke ready for at least one complete source clock cycle.
module workstation_ae350_pcm_session(
    input wire reset_ni,clk_i,source_ready_i,
    input wire [31:0] source_epoch_i,source_generation_i,
    output reg live_o=0,
    output reg [31:0] epoch_o=0,generation_o=0
);
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [2:0] release_pipe=0;
    // Only this single registered source level crosses asynchronously. Data
    // never controls asynchronous reset, and is captured as one held bundle.
    always @(posedge clk_i or negedge reset_ni or negedge source_ready_i)
        if(!reset_ni || !source_ready_i)release_pipe<=0;
        else release_pipe<={release_pipe[1:0],1'b1};
    always @(posedge clk_i or negedge reset_ni or negedge source_ready_i)
        if(!reset_ni || !source_ready_i)live_o<=0;
        else if(release_pipe[2])live_o<=1;
    always @(posedge clk_i or negedge reset_ni)
        if(!reset_ni)begin epoch_o<=0;generation_o<=0;end
        else if(release_pipe[2] && !live_o)begin
            epoch_o<=source_epoch_i;generation_o<=source_generation_i;
        end
endmodule
`default_nettype wire
