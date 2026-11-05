`timescale 1ns/1ps
// M final SERIALIZER-completion observer. This is a local-clock logical
// transport endpoint, not an LCD pin/CDC implementation. The sample source is
// pulse-only and has no ready output: transport congestion fails the recording
// branch and never changes the physical audio schedule.
module workstation_task3_final_tap_export #(
    parameter integer FIFO_ADDRESS_BITS=8,
    parameter bit SYNC_READ_STORAGE=1'b0
) (
    input wire clk_i,reset_ni,link_ready_i,panic_i,
    input wire arm_valid_i,
    output wire arm_ready_o,
    input wire [31:0] arm_boot_i,arm_session_i,arm_generation_i,
    input wire [31:0] arm_physical_epoch_i,arm_first_sequence_i,
    output reg arm_accepted_o,arm_rejected_o,
    output wire arm_tx_valid_o,
    input wire arm_tx_ready_i,arm_result_accepted_i,arm_result_rejected_i,
    output reg [31:0] boot_o,session_o,generation_o,physical_epoch_o,first_sequence_o,
    input wire cancel_valid_i,
    input wire [31:0] cancel_session_i,cancel_generation_i,
    input wire frame_valid_i,frame_44k1_i,frame_error_i,
    input wire [31:0] frame_epoch_i,frame_sequence_i,frame_pcm_i,
    output wire frame_tx_valid_o,
    input wire frame_tx_ready_i,
    output wire [31:0] frame_tx_epoch_o,frame_tx_sequence_o,frame_tx_pcm_o,
    output wire frame_tx_44k1_o,frame_tx_error_o,
    output wire cancel_tx_valid_o,
    input wire cancel_tx_ready_i,
    output reg armed_o,fault_o,
    output reg [3:0] failure_code_o,
    output wire [FIFO_ADDRESS_BITS:0] queued_frames_o,
    output reg [31:0] captured_frames_o,exported_frames_o
);
    localparam integer DEPTH=1<<FIFO_ADDRESS_BITS;
    // 1 overflow, 2 epoch/sequence/format/sample error, 3 link loss,
    // 5 PANIC, 6 matching cancellation. Format1 is stereo16/48k only.
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [97:0] frames[0:DEPTH-1];
    reg [FIFO_ADDRESS_BITS-1:0] wr,rd;
    reg [FIFO_ADDRESS_BITS:0] count;
    reg [31:0] retired_generation,expected_sequence;
    reg arm_pending,arm_sent,cancel_pending;
    wire cancel_match=cancel_valid_i && cancel_session_i==session_o && cancel_generation_i==generation_o;
    wire bad_frame=frame_valid_i && (frame_44k1_i || frame_error_i ||
        frame_epoch_i!=physical_epoch_o || frame_sequence_i!=expected_sequence);
    wire overflow=frame_valid_i && count==(FIFO_ADDRESS_BITS+1)'(DEPTH);
    wire fenced=!link_ready_i || panic_i || cancel_match || bad_frame || overflow || arm_result_rejected_i;
    wire usable=reset_ni && armed_o && !fault_o && !fenced;
    assign arm_ready_o=reset_ni && link_ready_i && !panic_i && !armed_o &&
        !arm_pending && !cancel_pending && retired_generation!=32'hffffffff;
    assign arm_tx_valid_o=usable && arm_pending && !arm_sent;
    wire head_valid;
    wire [97:0] head;
    wire [97:0] incoming={frame_44k1_i,frame_error_i,frame_epoch_i,frame_sequence_i,frame_pcm_i};
    assign frame_tx_valid_o=usable && !arm_pending && count!=0 && head_valid;
    assign {frame_tx_44k1_o,frame_tx_error_o,frame_tx_epoch_o,frame_tx_sequence_o,frame_tx_pcm_o}=head;
    // A cancel remains visible after link loss. The hub may retain it locally
    // or retire it on a new physical boot; it must never replay queued PCM.
    assign cancel_tx_valid_o=reset_ni && cancel_pending;
    assign queued_frames_o=count;
    wire push=usable && frame_valid_i;
    wire pop=frame_tx_valid_o && frame_tx_ready_i;
    // A pulse-only source never waits on the read port or remote transport.
    // Data ports have no reset; occupancy and validity revoke stale contents.
    always @(posedge clk_i)
        if(push)frames[wr]<=incoming;
    generate if(SYNC_READ_STORAGE)begin:g_sync_frames
        reg [97:0] ram_head,bypass_head;
        reg valid,bypass;
        wire [FIFO_ADDRESS_BITS-1:0] next_rd=rd+FIFO_ADDRESS_BITS'(pop);
        wire fetch=usable && ((!valid && count!=0) || (pop && count>1));
        // Write forwarding handles empty and last-pop/new-push collisions;
        // RAM read-during-write behavior is never used as a data authority.
        wire forward=push && (count==0 || (pop && count==1));
        always @(posedge clk_i)begin
            if(fetch)ram_head<=frames[next_rd];
            if(forward)bypass_head<=incoming;
        end
        always @(posedge clk_i or negedge reset_ni)
            if(!reset_ni)begin valid<=0;bypass<=0;end
            else if(!usable)begin valid<=0;bypass<=0;end
            else if(forward)begin valid<=1;bypass<=1;end
            else if(fetch)begin valid<=1;bypass<=0;end
            else if(pop)valid<=0;
        assign head_valid=valid;
        assign head=bypass ? bypass_head:ram_head;
    end else begin:g_async_frames
        assign head_valid=1'b1;
        assign head=frames[rd];
    end endgenerate
    initial if(FIFO_ADDRESS_BITS<2 || FIFO_ADDRESS_BITS>8)
        $fatal(1,"invalid final tap queue geometry");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            wr<=0;rd<=0;count<=0;retired_generation<=0;expected_sequence<=0;
            arm_pending<=0;arm_sent<=0;cancel_pending<=0;armed_o<=0;fault_o<=0;failure_code_o<=0;
            boot_o<=0;session_o<=0;generation_o<=0;physical_epoch_o<=0;first_sequence_o<=0;
            arm_accepted_o<=0;arm_rejected_o<=0;captured_frames_o<=0;exported_frames_o<=0;
        end else begin
            arm_accepted_o<=0;arm_rejected_o<=0;
            if(cancel_tx_valid_o && cancel_tx_ready_i)cancel_pending<=0;
            if(arm_valid_i)begin
                if(!arm_ready_o || arm_boot_i==0 || arm_session_i==0 || arm_generation_i==0 ||
                   arm_generation_i<=retired_generation || arm_physical_epoch_i==0)
                    arm_rejected_o<=1;
                else begin
                    boot_o<=arm_boot_i;session_o<=arm_session_i;generation_o<=arm_generation_i;
                    physical_epoch_o<=arm_physical_epoch_i;first_sequence_o<=arm_first_sequence_i;
                    expected_sequence<=arm_first_sequence_i;retired_generation<=arm_generation_i;
                    wr<=0;rd<=0;count<=0;armed_o<=1;fault_o<=0;failure_code_o<=0;
                    arm_pending<=1;arm_sent<=0;arm_accepted_o<=1;captured_frames_o<=0;exported_frames_o<=0;
                end
            end
            if(armed_o)begin
                if(fenced)begin
                    armed_o<=0;fault_o<=1;count<=0;arm_pending<=0;cancel_pending<=1;
                    failure_code_o<=panic_i?4'd5:cancel_match?4'd6:!link_ready_i?4'd3:overflow?4'd1:4'd2;
                end else begin
                    if(arm_tx_valid_o && arm_tx_ready_i)arm_sent<=1;
                    if(arm_pending && arm_sent && arm_result_accepted_i)arm_pending<=0;
                    if(push)begin
                        wr<=wr+1'b1;expected_sequence<=expected_sequence+1'b1;
                        captured_frames_o<=captured_frames_o+1'b1;
                    end
                    if(pop)begin rd<=rd+1'b1;exported_frames_o<=exported_frames_o+1'b1;end
                    case({push,pop})
                        2'b10:count<=count+1'b1;
                        2'b01:count<=count-1'b1;
                        default:begin end
                    endcase
                end
            end
        end
    end
endmodule
