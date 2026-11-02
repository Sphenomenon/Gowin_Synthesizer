`timescale 1ns/1ps
// M owns publication. Partial/failed W scores never become Push guidance.
// Notes from bounded clips accumulate in one bounded song image. Only the
// actual file-final clip's successful terminal starts publication to Push.
module workstation_task3_score_commit_m #(
    parameter integer MAX_NOTES=2048
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
    output reg [31:0] note_count_o
);
    localparam integer AW=$clog2(MAX_NOTES);
    localparam [1:0] IDLE=0,COLLECT=1,PUBLISH=2,DONE=3;
    reg [1:0] state;
    reg [127:0] identity;
    reg [31:0] clip_notes,cursor;
    reg poisoned;
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [6:0] notes[0:MAX_NOTES-1];
    assign arm_ready_o=reset_ni && link_ready_i && (state==IDLE || state==DONE);
    // Stale identities are consumed and discarded, never allowed to fill a
    // transport queue indefinitely after local cancel or a session restart.
    assign score_ready_o=reset_ni;
    assign terminal_ready_o=reset_ni;
    wire score_match=score_valid_i && state==COLLECT && score_i[166:39]==identity;
    wire score_good=score_match && score_i[38:7]==clip_notes && note_count_o<MAX_NOTES;
    wire terminal_match=terminal_valid_i && state==COLLECT && terminal_i[163:36]==identity;
    assign push_score_valid_o=reset_ni && link_ready_i && !cancel_i && !panic_i && state==PUBLISH && cursor<note_count_o;
    assign push_score_note_o=notes[cursor[AW-1:0]];
    initial if(MAX_NOTES<4 || (1<<AW)!=MAX_NOTES)$fatal(1,"invalid bounded score capacity");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;identity<=0;clip_notes<=0;cursor<=0;poisoned<=0;
            completion_valid_o<=0;completion_o<=0;analysis_done_o<=0;failed_o<=0;failure_code_o<=0;note_count_o<=0;
        end else begin
            completion_valid_o<=0;
            if(!link_ready_i || cancel_i || panic_i)begin
                state<=IDLE;clip_notes<=0;cursor<=0;poisoned<=0;note_count_o<=0;analysis_done_o<=0;
                if(state!=IDLE)begin failed_o<=1;failure_code_o<=1;end
            end else begin
                if(arm_valid_i && arm_ready_o)begin
                    identity<=arm_identity_i;clip_notes<=0;poisoned<=0;cursor<=0;state<=COLLECT;analysis_done_o<=0;
                    if(!arm_append_i)begin note_count_o<=0;failed_o<=0;failure_code_o<=0;end
                end
                if(score_match)begin
                    if(!score_good)begin poisoned<=1;failed_o<=1;failure_code_o<=2;end
                    else begin notes[note_count_o[AW-1:0]]<=score_i[6:0];note_count_o<=note_count_o+1'b1;clip_notes<=clip_notes+1'b1;end
                end
                if(terminal_match)begin
                    completion_valid_o<=1;
                    if(terminal_i[3:0]!=0 || poisoned || (score_match && !score_good) ||
                        terminal_i[35:4]!=(clip_notes+32'(score_good)))begin
                        completion_o<={identity,clip_notes,4'd14};state<=IDLE;note_count_o<=0;
                        failed_o<=1;failure_code_o<=3;analysis_done_o<=0;
                    end else begin
                        completion_o<=terminal_i;
                        if(chunk_file_last_i)begin
                            cursor<=0;
                            if(note_count_o+32'(score_good)==0)begin state<=DONE;analysis_done_o<=1;end
                            else state<=PUBLISH;
                        end else state<=IDLE;
                    end
                end
                if(push_score_valid_o && push_score_ready_i)begin
                    cursor<=cursor+1'b1;
                    if(cursor+1'b1==note_count_o)begin state<=DONE;analysis_done_o<=1;end
                end
            end
        end
    end
endmodule
