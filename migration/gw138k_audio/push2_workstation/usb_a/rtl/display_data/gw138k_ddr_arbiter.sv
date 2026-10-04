// Native DDR command arbitration. Read responses are in issue order and arrive
// no earlier than the cycle after acceptance. Display reloads start only after
// the BIST has completed, so they reuse the original BIST owner code without
// widening the existing arbitration tag path.
module gw138k_ddr_arbiter #(
    parameter TAG_BITS=8
)(
    input wire clk,reset_n,bist_done,
    input wire bist_valid,bist_write,
    input wire [28:0] bist_address,
    input wire [255:0] bist_data,
    output wire bist_ready,bist_response,
    input wire scan_valid,
    input wire [28:0] scan_address,
    output wire scan_ready,scan_response,
    input wire display_valid,
    input wire [28:0] display_address,
    output wire display_ready,display_response,
    input wire audio_valid,audio_write,
    input wire [28:0] audio_address,
    input wire [255:0] audio_data,
    output wire audio_ready,audio_response,
    input wire music_valid,music_write,
    input wire [28:0] music_address,
    input wire [255:0] music_data,
    input wire [31:0] music_mask,
    output wire music_ready,music_response,
    input wire writer_valid,
    input wire [28:0] writer_address,
    input wire [255:0] writer_data,
    output wire writer_ready,
    input wire cpu_valid,cpu_write,
    input wire [28:0] cpu_address,
    input wire [255:0] cpu_data,
    input wire [31:0] cpu_mask,
    output wire cpu_ready,cpu_response,
    output reg [2:0] app_cmd,
    output wire app_en,app_wren,app_wend,
    output reg [28:0] app_address,
    output reg [255:0] app_data,
    output reg [31:0] app_mask,
    input wire app_ready,app_write_ready,app_response,
    output reg response_fault
);
    localparam DEPTH=1<<TAG_BITS;
    reg [2:0] tags[0:DEPTH-1];
    reg [TAG_BITS-1:0] read_pointer,write_pointer;
    reg [TAG_BITS:0] count;
    reg prefer_cpu,prefer_music,music_turn,cpu_read_pending;
    wire cpu_available=cpu_valid && !cpu_read_pending;
    reg [2:0] owner;
    reg valid,is_write;
    always @* begin
        owner=0;valid=0;is_write=0;app_address=0;app_data=0;app_mask=0;
        if(!bist_done) begin
            valid=bist_valid;is_write=bist_write;app_address=bist_address;app_data=bist_data;
        end else if(scan_valid) begin
            owner=1;valid=1;app_address=scan_address;
        end else if(music_turn) begin
            // Give a waiting model upload/analysis request one full DDR slot
            // after audio.  A stalled music request retains the turn.
            owner=5;valid=music_valid;is_write=music_write;
            app_address=music_address;app_data=music_data;app_mask=music_mask;
        end else if(audio_valid) begin
            // Scanout keeps first priority; the streaming audio client is
            // next so a full TF ring cannot be blocked by UI/CPU traffic.
            owner=4;valid=1;is_write=audio_write;
            app_address=audio_address;app_data=audio_data;
        end else if(display_valid) begin
            // Owner 0 is free after BIST; response routing below uses bist_done
            // to distinguish this post-BIST read epoch.
            owner=0;valid=1;app_address=display_address;
        end else if(music_valid && (!prefer_music || (!cpu_available && !writer_valid))) begin
            owner=5;valid=1;is_write=music_write;
            app_address=music_address;app_data=music_data;app_mask=music_mask;
        end else if(cpu_available && (!writer_valid || prefer_cpu)) begin
            owner=2;valid=1;is_write=cpu_write;app_address=cpu_address;app_data=cpu_data;app_mask=cpu_mask;
        end else begin
            owner=3;valid=writer_valid;is_write=1;app_address=writer_address;app_data=writer_data;
        end
        app_cmd=is_write?3'b000:3'b001;
    end
    assign app_en=reset_n && valid && app_ready && (!is_write || app_write_ready) && (is_write || count<DEPTH);
    assign app_wren=app_en && is_write;
    assign app_wend=app_wren;
    assign bist_ready=app_en && owner==0 && !bist_done;
    assign scan_ready=app_en && owner==1;
    assign display_ready=app_en && owner==0 && bist_done;
    // Audio handshake has no dependency on lower-priority music/CPU/writer
    // selects.  This also keeps the TF DMA counter path within one UI cycle.
    assign audio_ready=reset_n && bist_done && !scan_valid && !music_turn && audio_valid &&
        app_ready && (!audio_write || app_write_ready) &&
        (audio_write || count<DEPTH);
    assign music_ready=app_en && owner==5;
    assign cpu_ready=app_en && owner==2;
    assign writer_ready=app_en && owner==3;
    wire push=app_en && !is_write;
    wire pop=app_response && count!=0;
    assign bist_response=pop && tags[read_pointer]==0 && !bist_done;
    assign display_response=pop && tags[read_pointer]==0 && bist_done;
    assign scan_response=pop && tags[read_pointer]==1;
    assign cpu_response=pop && tags[read_pointer]==2;
    assign audio_response=pop && tags[read_pointer]==4;
    assign music_response=pop && tags[read_pointer]==5;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin read_pointer<=0;write_pointer<=0;count<=0;prefer_cpu<=0;prefer_music<=0;music_turn<=0;cpu_read_pending<=0;response_fault<=0;end
        else begin
            if(app_en && (owner==2 || owner==3)) prefer_cpu<=owner==3;
            if(app_en && owner==5) prefer_music<=1;
            else if(app_en && (owner==2 || owner==3)) prefer_music<=0;
            if(bist_done && !scan_valid) begin
                if(music_turn) begin
                    if(!music_valid || music_ready) music_turn<=0;
                end else if((audio_ready || display_ready) && music_valid) music_turn<=1;
            end
            if(cpu_response) cpu_read_pending<=0;
            if(push && owner==2) cpu_read_pending<=1;
            if(push) begin tags[write_pointer]<=owner;write_pointer<=write_pointer+1'b1;end
            if(pop) read_pointer<=read_pointer+1'b1;
            case({push,pop})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:begin end
            endcase
            if(app_response && count==0) response_fault<=1;
        end
    end
endmodule
