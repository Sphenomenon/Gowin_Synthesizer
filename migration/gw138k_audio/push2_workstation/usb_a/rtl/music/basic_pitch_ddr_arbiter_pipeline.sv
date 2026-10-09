`timescale 1ns/1ps
// Full85 priority/fairness policy with registered native command and return
// boundaries. Two-cycle command initiation, one-cycle return latency; no BSRAM.
module basic_pitch_ddr_arbiter_pipeline #(
    parameter TAG_BITS=5
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
    input wire delay_valid,delay_write,
    input wire [28:0] delay_address,
    input wire [255:0] delay_data,
    output wire delay_ready,delay_response,
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
    input wire [255:0] app_response_data,
    output reg [255:0] response_data,
    output reg response_fault
);
    localparam DEPTH=1<<TAG_BITS;
    initial if(TAG_BITS<2 || TAG_BITS>8)$fatal(1,"DDR tag bits must be2..8");
    reg [2:0] tags[0:DEPTH-1];
    reg [TAG_BITS-1:0] read_pointer,write_pointer;
    reg [TAG_BITS:0] count;
    reg prefer_cpu,prefer_music,music_turn,cpu_read_pending;
    wire cpu_available=cpu_valid && !cpu_read_pending;
    reg [2:0] owner;
    reg valid,is_write;
    reg [7:0] grant;
    reg [28:0] selected_address;
    reg [255:0] selected_data;
    reg [31:0] selected_mask;
    always @* begin
        owner=0;valid=0;is_write=0;grant=0;selected_address=0;selected_data=0;selected_mask=0;
        if(!bist_done) begin
            valid=bist_valid;grant[0]=bist_valid;is_write=bist_write;selected_address=bist_address;selected_data=bist_data;
        end else if(scan_valid) begin
            owner=1;valid=1;grant[1]=1;selected_address=scan_address;
        end else if(music_turn) begin
            // Give a waiting model upload/analysis request one full DDR slot
            // after audio.  A stalled music request retains the turn.
            owner=5;valid=music_valid;grant[5]=music_valid;is_write=music_write;
            selected_address=music_address;selected_data=music_data;selected_mask=music_mask;
        end else if(audio_valid) begin
            // Scanout keeps first priority; the streaming audio client is
            // next so a full TF ring cannot be blocked by UI/CPU traffic.
            owner=4;valid=1;grant[4]=1;is_write=audio_write;
            selected_address=audio_address;selected_data=audio_data;
        end else if(display_valid) begin
            // Distinct tag avoids changing response ownership at BIST completion.
            owner=7;valid=1;grant[7]=1;selected_address=display_address;
        end else if(music_valid && (!prefer_music || (!cpu_available && !writer_valid))) begin
            owner=5;valid=1;grant[5]=1;is_write=music_write;
            selected_address=music_address;selected_data=music_data;selected_mask=music_mask;
        end else if(delay_valid) begin
            // Delay-effect ring streaming (owner 6): below TF audio and the
            // music turn, above CPU/writer.  Worst case ~24k 32B requests/s
            // (<0.1% of slots), so it cannot perturb the existing latency
            // guarantees while its 384 KB/s stays unstarved here.
            owner=6;valid=1;grant[6]=1;is_write=delay_write;
            selected_address=delay_address;selected_data=delay_data;
        end else if(cpu_available && (!writer_valid || prefer_cpu)) begin
            owner=2;valid=1;grant[2]=1;is_write=cpu_write;selected_address=cpu_address;selected_data=cpu_data;selected_mask=cpu_mask;
        end else begin
            owner=3;valid=writer_valid;grant[3]=writer_valid;is_write=1;selected_address=writer_address;selected_data=writer_data;
        end
    end
    reg command_full,command_write;
    reg [2:0] command_owner,response_owner;
    reg response_valid;
    // Client acceptance means a complete command has entered this one-entry
    // buffer. Leave one empty cycle on drain: no PHY-ready feedback into
    // arbitration or the client request/ready logic.
    wire can_buffer=reset_n && !command_full;
    wire read_room=count<DEPTH;
    // One-hot selections bypass binary owner decode and selected-write mux in
    // each client's ready cone. Priority/fairness are still the policy above.
    assign bist_ready=can_buffer && grant[0] && (bist_write || read_room);
    assign scan_ready=can_buffer && grant[1] && read_room;
    assign cpu_ready=can_buffer && grant[2] && (cpu_write || read_room);
    assign writer_ready=can_buffer && grant[3];
    assign audio_ready=can_buffer && grant[4] && (audio_write || read_room);
    assign music_ready=can_buffer && grant[5] && (music_write || read_room);
    assign delay_ready=can_buffer && grant[6] && (delay_write || read_room);
    assign display_ready=can_buffer && grant[7] && read_room;
    wire accept=bist_ready || scan_ready || cpu_ready || writer_ready ||
        audio_ready || music_ready || delay_ready || display_ready;
    assign app_en=reset_n && command_full && app_ready &&
        (!command_write || app_write_ready) && (command_write || read_room);
    assign app_wren=app_en && command_write;
    assign app_wend=app_wren;
    wire push=app_en && !command_write;
    wire pop=app_response && count!=0;
    assign bist_response=response_valid && response_owner==0;
    assign display_response=response_valid && response_owner==7;
    assign scan_response=response_valid && response_owner==1;
    assign cpu_response=response_valid && response_owner==2;
    assign audio_response=response_valid && response_owner==4;
    assign music_response=response_valid && response_owner==5;
    assign delay_response=response_valid && response_owner==6;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            command_full<=0;command_write<=0;command_owner<=0;
            app_cmd<=0;app_address<=0;app_data<=0;app_mask<=0;
        end else begin
            if(app_en)command_full<=0;
            if(accept)begin
                command_full<=1;command_write<=is_write;command_owner<=owner;
            end
            // Wide data/address/mask registers need only local idle enables.
            // Their values are committed by command_full at the acceptance
            // edge and held throughout every native stall.
            if(!command_full)begin
                app_cmd<=is_write?3'b000:3'b001;
                app_address<=selected_address;app_data<=selected_data;app_mask<=selected_mask;
            end
        end
    end
    // Data and ownership advance together. Native data may change every cycle;
    // consumers must use this returned bus with the registered response pulse.
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n)begin response_valid<=0;response_owner<=0;response_data<=0;end
        else begin
            response_valid<=pop;
            response_data<=app_response_data;
            if(pop)response_owner<=tags[read_pointer];
        end
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            read_pointer<=0;write_pointer<=0;count<=0;
            prefer_cpu<=0;prefer_music<=0;music_turn<=0;cpu_read_pending<=0;response_fault<=0;
        end else begin
            if(accept && (owner==2 || owner==3))prefer_cpu<=owner==3;
            if(accept && owner==5)prefer_music<=1;
            else if(accept && (owner==2 || owner==3))prefer_music<=0;
            if(bist_done && !scan_valid)begin
                if(music_turn)begin
                    if(!music_valid || music_ready)music_turn<=0;
                end else if((audio_ready || display_ready) && music_valid)music_turn<=1;
            end
            if(cpu_response)cpu_read_pending<=0;
            if(accept && owner==2 && !is_write)cpu_read_pending<=1;
            if(push)begin tags[write_pointer]<=command_owner;write_pointer<=write_pointer+1'b1;end
            if(pop)read_pointer<=read_pointer+1'b1;
            case({push,pop})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:begin end
            endcase
            if(app_response && count==0)response_fault<=1;
        end
    end
endmodule
