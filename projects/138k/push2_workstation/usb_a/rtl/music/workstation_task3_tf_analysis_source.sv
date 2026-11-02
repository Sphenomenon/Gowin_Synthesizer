`timescale 1ns/1ps
// Logical M-side producer for a dedicated, backpressurable TF decode pass.
// No port here gates the DAC sample schedule. SOURCE_NONBLOCKING is only for
// observing an already accepted playback tap; congestion then fails analysis.
// A full file is split into bounded clips, with its decoder/file cursor held
// between clips. A clip boundary is never represented as physical file EOF.
module workstation_task3_tf_analysis_source #(
    parameter integer QUEUE_FRAMES=256,
    parameter bit SOURCE_NONBLOCKING=1'b0,
    parameter [31:0] WAIT_TIMEOUT_CYCLES=32'd4000000000
)(
    input wire clk_i,reset_ni,link_ready_i,transport_fault_i,cancel_i,panic_i,
    input wire start_valid_i,
    output wire start_ready_o,
    input wire [31:0] start_boot_i,start_session_i,start_task_id_i,start_generation_i,
    input wire [31:0] clip_frames_i,
    input wire pcm_valid_i,
    output wire pcm_ready_o,
    input wire [31:0] pcm_pair_i,
    input wire pcm_last_i,
    // Identity is {M boot, session, task, generation}, high to low.
    output wire desc_valid_o,
    input wire desc_ready_i,
    output wire [199:0] desc_o,
    output wire frame_valid_o,
    input wire frame_ready_i,
    output wire [191:0] frame_o,
    output wire seal_valid_o,
    input wire seal_ready_i,
    output wire [191:0] seal_o,
    output wire cancel_valid_o,
    input wire cancel_ready_i,
    output wire [127:0] cancel_o,
    // Local arm and the outgoing descriptor are one atomic handshake.
    output wire arm_valid_o,
    input wire arm_ready_i,
    output wire [127:0] arm_identity_o,
    output wire arm_append_o,
    output reg chunk_file_last_o,
    // From the M result collector after count/identity validation.
    input wire completion_valid_i,
    input wire [163:0] completion_i,
    output wire busy_o,
    output reg done_o,failed_o,
    output reg [3:0] failure_code_o,
    output reg [31:0] total_frames_o,completed_clips_o
);
    localparam integer AW=$clog2(QUEUE_FRAMES);
    localparam [2:0] IDLE=0,DESC=1,STREAM=2,SEAL=3,WAIT_RESULT=4,CANCEL=5;
    reg [2:0] state;
    reg [127:0] identity;
    reg [31:0] budget,accepted,sent,crc,crc_word,elapsed;
    reg [1:0] crc_phase;
    reg crc_busy,clip_closed,append;
    (* ram_style="block",syn_ramstyle="block_ram" *) reg [31:0] queue[0:QUEUE_FRAMES-1];
    reg [AW-1:0] wr,rd;
    reg [AW:0] count;
    reg held_valid;
    reg [31:0] held;
    wire live=reset_ni && link_ready_i && !transport_fault_i && !cancel_i && !panic_i;
    assign busy_o=state!=IDLE;
    assign start_ready_o=live && state==IDLE && arm_ready_i;
    assign desc_valid_o=live && state==DESC && arm_ready_i;
    assign arm_valid_o=live && state==DESC && desc_ready_i;
    assign desc_o={identity,budget,32'd0,8'd1};
    assign arm_identity_o=identity;
    assign arm_append_o=append;
    assign pcm_ready_o=live && state==STREAM && !clip_closed && !crc_busy &&
        (32'(count)+32'(held_valid))<QUEUE_FRAMES;
    assign frame_valid_o=live && (state==STREAM || state==SEAL) && held_valid;
    assign frame_o={identity,sent,held};
    assign seal_valid_o=live && state==SEAL && !held_valid && count==0 && !crc_busy;
    assign seal_o={identity,accepted,~crc};
    assign cancel_valid_o=reset_ni && link_ready_i && state==CANCEL;
    assign cancel_o=identity;
    wire pcm_fire=pcm_valid_i && pcm_ready_o;
    wire frame_fire=frame_valid_o && frame_ready_i;
    wire prefetch=(state==STREAM || state==SEAL) && (!held_valid || frame_fire) && count!=0;
    wire complete_match=completion_valid_i && completion_i[163:36]==identity;
    function automatic [31:0] crc_byte(input [31:0] old_crc,input [7:0] data);
        reg [31:0] c;integer k;
        begin c=old_crc^{24'd0,data};for(k=0;k<8;k=k+1)c=c[0]?((c>>1)^32'hedb88320):(c>>1);crc_byte=c;end
    endfunction
    task automatic fail(input [3:0] code);
        begin state<=link_ready_i?CANCEL:IDLE;failed_o<=1;failure_code_o<=code;
            held_valid<=0;count<=0;crc_busy<=0;done_o<=1;end
    endtask
    initial if(QUEUE_FRAMES<4 || (1<<AW)!=QUEUE_FRAMES || WAIT_TIMEOUT_CYCLES<16)
        $fatal(1,"invalid TF analysis source budget");
    always @(posedge clk_i or negedge reset_ni)begin
        if(!reset_ni)begin
            state<=IDLE;identity<=0;budget<=0;accepted<=0;sent<=0;crc<=32'hffffffff;
            crc_word<=0;crc_phase<=0;crc_busy<=0;clip_closed<=0;append<=0;elapsed<=0;
            wr<=0;rd<=0;count<=0;held_valid<=0;held<=0;chunk_file_last_o<=0;
            done_o<=0;failed_o<=0;failure_code_o<=0;total_frames_o<=0;completed_clips_o<=0;
        end else begin
            done_o<=0;
            if(state!=IDLE && state!=CANCEL && elapsed!=WAIT_TIMEOUT_CYCLES)elapsed<=elapsed+1'b1;
            if(crc_busy)begin
                crc<=crc_byte(crc,crc_word[crc_phase*8+:8]);crc_phase<=crc_phase+1'b1;
                if(crc_phase==3)crc_busy<=0;
            end
            if(pcm_fire)begin
                queue[wr]<=pcm_pair_i;wr<=wr+1'b1;accepted<=accepted+1'b1;
                total_frames_o<=total_frames_o+1'b1;crc_word<=pcm_pair_i;crc_phase<=0;crc_busy<=1;
                if(pcm_last_i || accepted+1'b1==budget)begin
                    clip_closed<=1;chunk_file_last_o<=pcm_last_i;state<=SEAL;
                end
            end
            if(prefetch)begin held<=queue[rd];rd<=rd+1'b1;held_valid<=1;end
            else if(frame_fire)held_valid<=0;
            if(frame_fire)sent<=sent+1'b1;
            case({pcm_fire,prefetch})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:begin end
            endcase
            if(state!=IDLE && state!=CANCEL && (!live || elapsed==WAIT_TIMEOUT_CYCLES ||
                (SOURCE_NONBLOCKING && state==STREAM && pcm_valid_i && !pcm_ready_o)))begin
                fail(!link_ready_i?4'd1:panic_i?4'd2:cancel_i?4'd3:
                    transport_fault_i?4'd4:elapsed==WAIT_TIMEOUT_CYCLES?4'd5:4'd6);
            end else case(state)
                IDLE:if(start_valid_i && start_ready_o)begin
                    if(start_boot_i==0 || start_session_i==0 || start_task_id_i==0 || start_generation_i==0 ||
                        clip_frames_i==0 || clip_frames_i>96000)begin
                        failed_o<=1;failure_code_o<=7;done_o<=1;
                    end else begin
                        identity<={start_boot_i,start_session_i,start_task_id_i,start_generation_i};
                        budget<=clip_frames_i;accepted<=0;sent<=0;crc<=32'hffffffff;crc_busy<=0;
                        wr<=0;rd<=0;count<=0;held_valid<=0;clip_closed<=0;append<=0;elapsed<=0;
                        chunk_file_last_o<=0;failed_o<=0;failure_code_o<=0;total_frames_o<=0;completed_clips_o<=0;state<=DESC;
                    end
                end
                DESC:if(desc_valid_o && desc_ready_i)begin state<=STREAM;elapsed<=0;end
                SEAL:if(seal_valid_o && seal_ready_i)begin state<=WAIT_RESULT;elapsed<=0;end
                WAIT_RESULT:if(complete_match)begin
                    if(completion_i[3:0]!=0)fail(8);
                    else begin
                        completed_clips_o<=completed_clips_o+1'b1;
                        if(chunk_file_last_o)begin state<=IDLE;done_o<=1;end
                        else if(SOURCE_NONBLOCKING)fail(10);
                        else if(identity[63:32]==32'hffffffff || identity[31:0]==32'hffffffff)fail(9);
                        else begin
                            identity[63:32]<=identity[63:32]+1'b1;identity[31:0]<=identity[31:0]+1'b1;
                            accepted<=0;sent<=0;crc<=32'hffffffff;crc_busy<=0;clip_closed<=0;
                            wr<=0;rd<=0;count<=0;held_valid<=0;append<=1;elapsed<=0;state<=DESC;
                        end
                    end
                end
                CANCEL:if(!link_ready_i || (cancel_valid_o && cancel_ready_i))state<=IDLE;
                default:begin end
            endcase
        end
    end
endmodule
