`timescale 1ns/1ps
// M owns publication. Partial/failed W scores never become Push guidance.
// Notes from bounded clips accumulate in one bounded song image. Only the
// actual file-final clip's successful terminal starts publication to Push.
module workstation_task3_score_commit_m #(
    parameter integer MAX_NOTES=2048,
    parameter bit SYNC_READ_STORAGE=1'b0,
    parameter bit PIPELINED_TERMINAL=1'b0
)(
    input wire clk_i,reset_ni,link_ready_i,cancel_i,panic_i,
    input wire arm_valid_i,
    output wire arm_ready_o,
    input wire [127:0] arm_identity_i,
    input wire arm_append_i,chunk_file_last_i,
    input wire score_valid_i,
    output wire score_ready_o,
    input wire [166:0] score_i,
    input wire terminal_valid_i,
    output wire terminal_ready_o,
    input wire [163:0] terminal_i,
    output reg completion_valid_o,
    output reg [163:0] completion_o,
    output wire push_score_valid_o,
    input wire push_score_ready_i,
    output wire [6:0] push_score_note_o,
    output reg analysis_done_o,failed_o,
    output reg [3:0] failure_code_o,
    output wire [31:0] note_count_o
);
    localparam integer AW=$clog2(MAX_NOTES);
    // The explicit memory candidate bounds local counters to the physical
    // capacity. Protocol lengths and completion payloads remain 32 bits.
    localparam integer CW=SYNC_READ_STORAGE ? AW+1:32;
    localparam [1:0] IDLE=0,COLLECT=1,PUBLISH=2,DONE=3;
    reg [1:0] state;
    reg [127:0] identity;
    reg [CW-1:0] clip_notes,cursor,note_count;
    assign note_count_o=32'(note_count);
    reg poisoned;
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [6:0] notes[0:MAX_NOTES-1];
    assign arm_ready_o=reset_ni && link_ready_i && (state==IDLE || state==DONE);
    // Stale identities are consumed and discarded, never allowed to fill a
    // transport queue indefinitely after local cancel or a session restart.
    wire seal_pending;
    assign score_ready_o=reset_ni && !seal_pending;
    assign terminal_ready_o=reset_ni && !seal_pending;
    wire score_match=score_valid_i && score_ready_o && state==COLLECT && score_i[166:39]==identity;
    wire score_good=score_match && score_i[38:7]==32'(clip_notes) && note_count<MAX_NOTES;
    wire [CW-1:0] clip_notes_after=clip_notes+CW'(score_good);
    wire [CW-1:0] note_count_after=note_count+CW'(score_good);
    wire terminal_match=terminal_valid_i && terminal_ready_o && state==COLLECT && terminal_i[163:36]==identity;
    wire seal_apply,seal_bad,seal_file_last,seal_empty;
    wire [163:0] seal_completion,seal_failure;
    generate if(PIPELINED_TERMINAL)begin:g_terminal_pipeline
        reg pending;
        reg [31:0] held_count;
        reg [CW-1:0] prior_clip_notes;
        reg held_bad,held_file_last;
        // The slot owns only a background result. Accept the final note and
        // terminal together, then compare with the committed count next cycle.
        // Payload is reset-free; validity is fenced asynchronously and on every
        // cancellation, PANIC or link loss. No old result may survive rearm.
        always @(posedge clk_i)
            if(terminal_match && link_ready_i && !cancel_i && !panic_i)begin
                held_count<=terminal_i[35:4];
                prior_clip_notes<=clip_notes;
                held_bad<=terminal_i[3:0]!=0 || poisoned || (score_match && !score_good);
                held_file_last<=chunk_file_last_i;
            end
        always @(posedge clk_i or negedge reset_ni)
            if(!reset_ni)pending<=0;
            else if(!link_ready_i || cancel_i || panic_i)pending<=0;
            else pending<=terminal_match;
        assign seal_pending=pending;
        assign seal_apply=pending;
        assign seal_bad=held_bad || held_count!=32'(clip_notes);
        assign seal_file_last=held_file_last;
        assign seal_empty=note_count==0;
        // Identity cannot change in COLLECT while this slot blocks ingress.
        // Successful status is zero; failures use the prior-count descriptor.
        // Avoid a second resettable or reset-free 128-bit identity copy.
        assign seal_completion={identity,held_count,4'd0};
        assign seal_failure={identity,32'(prior_clip_notes),4'd14};
    end else begin:g_terminal_direct
        assign seal_pending=1'b0;
        assign seal_apply=terminal_match;
        assign seal_bad=terminal_i[3:0]!=0 || poisoned || (score_match && !score_good) ||
                        terminal_i[35:4]!=32'(clip_notes_after);
        assign seal_file_last=chunk_file_last_i;
        assign seal_empty=note_count_after==0;
        assign seal_completion=terminal_i;
        assign seal_failure={identity,32'(clip_notes),4'd14};
    end endgenerate
    wire note_ready;
    wire publish=reset_ni && link_ready_i && !cancel_i && !panic_i && state==PUBLISH && cursor<note_count;
    wire publish_fire=push_score_valid_o && push_score_ready_i;
    wire store_write=reset_ni && link_ready_i && !cancel_i && !panic_i && score_good;
    // Keep the memory ports reset-free. Only publication validity is reset;
    // cancelled/failed notes remain unreachable until a new successful seal.
    always @(posedge clk_i)
        if(store_write)notes[note_count[AW-1:0]]<=score_i[6:0];
    generate if(SYNC_READ_STORAGE)begin:g_sync_notes
        reg [6:0] head;
        reg head_valid;
        wire [CW-1:0] next_cursor=cursor+CW'(publish_fire);
        wire fetch=publish && (!head_valid || publish_fire) && next_cursor<note_count;
        always @(posedge clk_i)
            if(fetch)head<=notes[next_cursor[AW-1:0]];
        always @(posedge clk_i or negedge reset_ni)
            if(!reset_ni)head_valid<=0;
            else if(!publish)head_valid<=0;
            else if(fetch)head_valid<=1;
            else if(publish_fire)head_valid<=0;
        assign note_ready=head_valid;
        assign push_score_note_o=head;
    end else begin:g_async_notes
        assign note_ready=1'b1;
        assign push_score_note_o=notes[cursor[AW-1:0]];
    end endgenerate
    assign push_score_valid_o=publish && note_ready;
    initial if(MAX_NOTES<4 || (1<<AW)!=MAX_NOTES)$fatal(1,"invalid bounded score capacity");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;identity<=0;clip_notes<=0;cursor<=0;poisoned<=0;
            completion_valid_o<=0;completion_o<=0;analysis_done_o<=0;failed_o<=0;failure_code_o<=0;note_count<=0;
        end else begin
            completion_valid_o<=0;
            if(!link_ready_i || cancel_i || panic_i)begin
                state<=IDLE;clip_notes<=0;cursor<=0;poisoned<=0;note_count<=0;analysis_done_o<=0;
                if(state!=IDLE)begin failed_o<=1;failure_code_o<=1;end
            end else begin
                if(arm_valid_i && arm_ready_o)begin
                    identity<=arm_identity_i;clip_notes<=0;poisoned<=0;cursor<=0;state<=COLLECT;analysis_done_o<=0;
                    if(!arm_append_i)begin note_count<=0;failed_o<=0;failure_code_o<=0;end
                end
                if(score_match)begin
                    if(!score_good)begin poisoned<=1;failed_o<=1;failure_code_o<=2;end
                    else begin note_count<=note_count+1'b1;clip_notes<=clip_notes+1'b1;end
                end
                if(seal_apply)begin
                    completion_valid_o<=1;
                    if(seal_bad)begin
                        completion_o<=seal_failure;state<=IDLE;note_count<=0;
                        failed_o<=1;failure_code_o<=3;analysis_done_o<=0;
                    end else begin
                        completion_o<=seal_completion;
                        if(seal_file_last)begin
                            cursor<=0;
                            if(seal_empty)begin state<=DONE;analysis_done_o<=1;end
                            else state<=PUBLISH;
                        end else state<=IDLE;
                    end
                end
                if(push_score_valid_o && push_score_ready_i)begin
                    cursor<=cursor+1'b1;
                    if(cursor+1'b1==note_count)begin state<=DONE;analysis_done_o<=1;end
                end
            end
        end
    end
endmodule
