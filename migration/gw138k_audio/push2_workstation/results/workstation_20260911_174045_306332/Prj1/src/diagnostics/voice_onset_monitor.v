// Independent last-NOTE_ON records for all 32 slots. Event timestamps are
// captured before the shared RAM scanner runs, so observation work adds no
// measured latency. Only the same slot's next NOTE_ON replaces a record.
module voice_onset_monitor #(
    parameter integer CLOCK_HZ = 50000000,
    parameter integer EVENT_DEPTH = 4
) (
    input wire clk, input wire rst_n, input wire [31:0] time_cycles,
    input wire command_commit, input wire [31:0] command_header,
    input wire [23:0] command_revision, input wire [31:0] command_active_voices,
    input wire sample_event, input wire [23:0] sample_revision,
    input wire [31:0] nonzero_voices,
    input wire dac_done, input wire [23:0] dac_revision,
    input wire [31:0] dac_nonzero_voices, input wire dac_muted,
    input wire query_request, input wire [4:0] query_voice,
    output reg query_done, output reg [255:0] query_data
);
    localparam integer PTR_BITS = EVENT_DEPTH > 1 ? $clog2(EVENT_DEPTH) : 1;
    localparam integer COUNT_BITS = $clog2(EVENT_DEPTH+1);
    localparam [2:0] COMMAND=0, SAMPLE=1, DAC=2, QUERY=3, AGE=4;
    localparam [2:0] INITIALIZE=0, IDLE=1, FETCH=2, DRAIN=3, APPLY=4, WRITE=5, FINISH=6;
    localparam [31:0] CLOCK_RATE = CLOCK_HZ;
    reg [2:0] state;
    reg observer_overflow;

    // Independent bounded queues accept all three event sources on the same
    // edge. Their heads are merged by modular time, with SAMPLE before DAC
    // before COMMAND on ties. Thus a same-edge sample beats NOTE_OFF/PANIC.
    reg [88:0] command_fifo [0:EVENT_DEPTH-1];
    reg [87:0] sample_fifo [0:EVENT_DEPTH-1];
    reg [88:0] dac_fifo [0:EVENT_DEPTH-1];
    reg [PTR_BITS-1:0] command_read, command_write, sample_read, sample_write, dac_read, dac_write;
    reg [COUNT_BITS-1:0] command_count, sample_count, dac_count;
    wire [88:0] command_head = command_fifo[command_read];
    wire [87:0] sample_head = sample_fifo[sample_read];
    wire [88:0] dac_head = dac_fifo[dac_read];
    wire relevant_command = command_commit && (command_header[23:16] == 1 ||
        command_header[23:16] == 2 || command_header[23:16] == 10);
    reg query_pending;
    reg [4:0] pending_query_voice;
    reg [31:0] query_time;
    reg selection_valid;
    reg [2:0] selected_kind;
    reg [31:0] selected_time;
    function earlier_equal;
        input [31:0] a,b;
        reg [31:0] delta;
        begin delta=a-b; earlier_equal=(a==b) || delta[31]; end
    endfunction
    function [PTR_BITS-1:0] advance_pointer;
        input [PTR_BITS-1:0] value;
        begin advance_pointer=value == EVENT_DEPTH-1 ? 0 : value+1'b1; end
    endfunction
    always @* begin
        selection_valid=query_pending; selected_kind=QUERY; selected_time=query_time;
        if(command_count != 0 && (!selection_valid || earlier_equal(command_head[88:57],selected_time))) begin
            selection_valid=1; selected_kind=COMMAND; selected_time=command_head[88:57];
        end
        if(dac_count != 0 && (!selection_valid || earlier_equal(dac_head[88:57],selected_time))) begin
            selection_valid=1; selected_kind=DAC; selected_time=dac_head[88:57];
        end
        if(sample_count != 0 && (!selection_valid || earlier_equal(sample_head[87:56],selected_time))) begin
            selection_valid=1; selected_kind=SAMPLE; selected_time=sample_head[87:56];
        end
    end
    wire pop_command = state==IDLE && selection_valid && selected_kind==COMMAND;
    wire pop_sample = state==IDLE && selection_valid && selected_kind==SAMPLE;
    wire pop_dac = state==IDLE && selection_valid && selected_kind==DAC;
    wire overflow_now = !observer_overflow &&
        ((relevant_command && command_count==EVENT_DEPTH && !pop_command) ||
         (sample_event && sample_count==EVENT_DEPTH && !pop_sample) ||
         (dac_done && dac_count==EVENT_DEPTH && !pop_dac));
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            command_read<=0; command_write<=0; command_count<=0;
            sample_read<=0; sample_write<=0; sample_count<=0;
            dac_read<=0; dac_write<=0; dac_count<=0; observer_overflow<=0;
        end else if(observer_overflow || overflow_now) begin
            // A lost event invalidates future endpoint observations. Freeze
            // records, discard queued work and keep queries available with
            // the sticky fault bit; never silently fabricate later results.
            observer_overflow<=1;
            command_read<=0; command_write<=0; command_count<=0;
            sample_read<=0; sample_write<=0; sample_count<=0;
            dac_read<=0; dac_write<=0; dac_count<=0;
        end else begin
            if(relevant_command) begin
                command_fifo[command_write]<={time_cycles,command_header,command_revision,
                    command_active_voices[command_header[12:8]]};
                command_write<=advance_pointer(command_write);
            end
            if(pop_command) command_read<=advance_pointer(command_read);
            case({relevant_command,pop_command})
                2'b10: command_count<=command_count+1'b1;
                2'b01: command_count<=command_count-1'b1;
                default: begin end
            endcase
            if(sample_event) begin
                sample_fifo[sample_write]<={time_cycles,sample_revision,nonzero_voices};
                sample_write<=advance_pointer(sample_write);
            end
            if(pop_sample) sample_read<=advance_pointer(sample_read);
            case({sample_event,pop_sample})
                2'b10: sample_count<=sample_count+1'b1;
                2'b01: sample_count<=sample_count-1'b1;
                default: begin end
            endcase
            if(dac_done) begin
                dac_fifo[dac_write]<={time_cycles,dac_revision,dac_nonzero_voices,dac_muted};
                dac_write<=advance_pointer(dac_write);
            end
            if(pop_dac) dac_read<=advance_pointer(dac_read);
            case({dac_done,pop_dac})
                2'b10: dac_count<=dac_count+1'b1;
                2'b01: dac_count<=dac_count-1'b1;
                default: begin end
            endcase
        end
    end

    // Eight 32-bit words per voice. Internal word 2 stores trigger time;
    // queries replace it with CLOCK_HZ. A word-wide RAM avoids paying for
    // a separate wide physical RAM slice for every field.
    (* syn_ramstyle = "block_ram" *) reg [31:0] records [0:255];
    reg [7:0] initialize_address;
    reg [31:0] ram_read_data;
    reg [255:0] record_buffer;
    reg [4:0] scan_voice, age_voice;
    reg [2:0] action_kind;
    reg [7:0] action_opcode, action_sequence;
    reg [31:0] action_time, action_mask;
    reg [23:0] action_revision;
    reg action_was_active, action_muted;
    reg [2:0] fetch_index, write_index;
    reg [7:0] write_mask;
    wire full_record = action_kind==QUERY || (action_kind==COMMAND && action_opcode==1);
    wire scan_all = action_kind==SAMPLE || action_kind==DAC || (action_kind==COMMAND && action_opcode==10);
    function [2:0] read_field;
        input full; input [2:0] index;
        begin read_field=full ? index : index==0 ? 3'd0 : index==1 ? 3'd2 : 3'd6; end
    endfunction
    function [3:0] next_write_field;
        input [7:0] mask; input [3:0] first;
        integer i;
        begin
            next_write_field=8;
            for(i=0;i<8;i=i+1)
                if(i>=first && mask[i] && next_write_field==8) next_write_field=i;
        end
    endfunction
    always @(posedge clk) begin
        if(state==INITIALIZE) records[initialize_address]<=0;
        else if(state==WRITE && !observer_overflow && !overflow_now)
            records[{scan_voice,write_index}]<=record_buffer[write_index*32 +: 32];
        if(state==FETCH) ram_read_data<=records[{scan_voice,read_field(full_record,fetch_index)}];
    end

    wire [7:0] record_flags = record_buffer[7:0];
    wire terminal_record = record_flags[2] || record_flags[4] || record_flags[5];
    wire [31:0] record_age = action_time-record_buffer[95:64];
    wire [23:0] revision_delta = action_revision-record_buffer[215:192];
    wire eligible_revision = !revision_delta[23];
    reg [255:0] updated_record;
    reg [7:0] updated_write_mask;
    always @* begin
        updated_record=record_buffer; updated_write_mask=0;
        if(!observer_overflow && !overflow_now) begin
            if(action_kind==COMMAND && action_opcode==1) begin
                updated_record=0;
                updated_record[7:0]=action_was_active ? 8'h09 : 8'h01;
                updated_record[15:8]=action_sequence;
                updated_record[63:32]=record_buffer[63:32]+1'b1;
                updated_record[95:64]=action_time;
                updated_record[215:192]=action_revision;
                updated_write_mask=8'hff;
            end else if(record_flags[0] && !terminal_record) begin
                if(record_age[31]) begin
                    updated_record[5]=1;
                    updated_record[191:160]=32'h80000000;
                    updated_write_mask=8'h21;
                end else if(action_kind==SAMPLE && !record_flags[1] &&
                            action_mask[scan_voice] && eligible_revision) begin
                    updated_record[1]=1; updated_record[127:96]=record_age;
                    updated_write_mask=8'h09;
                end else if(action_kind==DAC && record_flags[1] &&
                            action_mask[scan_voice] && eligible_revision) begin
                    updated_record[2]=1; updated_record[6]=action_muted;
                    updated_record[159:128]=record_age; updated_record[191:160]=record_age;
                    updated_write_mask=8'h31;
                end else if(action_kind==COMMAND && (action_opcode==2 || action_opcode==10) && !record_flags[1]) begin
                    updated_record[4]=1; updated_record[255:224]=record_age;
                    updated_record[191:160]=record_age; updated_write_mask=8'ha1;
                end
            end
        end
    end
    wire [3:0] first_write = next_write_field(updated_write_mask,0);
    wire [3:0] following_write = next_write_field(write_mask,{1'b0,write_index}+1'b1);
    wire [31:0] query_elapsed = !record_buffer[0] ? 32'd0 :
        (record_buffer[2] || record_buffer[4] || record_buffer[5]) ? record_buffer[191:160] : record_age;

    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=INITIALIZE; initialize_address<=0;
            query_pending<=0; pending_query_voice<=0; query_time<=0; query_done<=0; query_data<=0;
            scan_voice<=0; age_voice<=0; action_kind<=AGE; action_opcode<=0; action_sequence<=0;
            action_time<=0; action_mask<=0; action_revision<=0; action_was_active<=0; action_muted<=0;
            fetch_index<=0; write_index<=0; write_mask<=0;
        end else begin
            query_done<=0;
            if(query_request) begin
                query_pending<=1; pending_query_voice<=query_voice; query_time<=time_cycles;
            end
            case(state)
                INITIALIZE: if(initialize_address==255) state<=IDLE;
                            else initialize_address<=initialize_address+1'b1;
                IDLE: begin
                    fetch_index<=0; action_opcode<=0; action_mask<=0;
                    action_revision<=0; action_was_active<=0; action_muted<=0;
                    if(selection_valid) begin
                        action_kind<=selected_kind; action_time<=selected_time;
                        case(selected_kind)
                            COMMAND: begin
                                action_opcode<=command_head[48:41]; action_sequence<=command_head[56:49];
                                scan_voice<=command_head[48:41]==10 ? 5'd0 : command_head[37:33];
                                action_revision<=command_head[24:1]; action_was_active<=command_head[0];
                            end
                            SAMPLE: begin scan_voice<=0; action_revision<=sample_head[55:32]; action_mask<=sample_head[31:0]; end
                            DAC: begin
                                scan_voice<=0; action_revision<=dac_head[56:33]; action_mask<=dac_head[32:1]; action_muted<=dac_head[0];
                            end
                            default: begin scan_voice<=pending_query_voice; query_pending<=0; end
                        endcase
                    end else begin
                        // Idle-time maintenance guarantees sticky expiry even
                        // if audio events stop; no full-array reset/comparators.
                        action_kind<=AGE; action_time<=time_cycles; scan_voice<=age_voice;
                        age_voice<=age_voice+1'b1;
                    end
                    state<=FETCH;
                end
                FETCH: begin
                    if(fetch_index!=0) record_buffer[read_field(full_record,fetch_index-1'b1)*32 +: 32]<=ram_read_data;
                    if(fetch_index==(full_record ? 7 : 2)) state<=DRAIN;
                    else fetch_index<=fetch_index+1'b1;
                end
                DRAIN: begin
                    record_buffer[read_field(full_record,fetch_index)*32 +: 32]<=ram_read_data;
                    state<=APPLY;
                end
                APPLY: begin
                    record_buffer<=updated_record; write_mask<=updated_write_mask;
                    if(first_write==8) state<=FINISH;
                    else begin write_index<=first_write[2:0]; state<=WRITE; end
                end
                WRITE: if(following_write==8) state<=FINISH;
                       else write_index<=following_write[2:0];
                FINISH: begin
                    if(action_kind==QUERY) begin
                        query_data<={record_buffer[255:224],8'd0,record_buffer[215:192],
                            query_elapsed,record_buffer[159:128],record_buffer[127:96],CLOCK_RATE,
                            record_buffer[63:32],(record_flags | (observer_overflow ? 8'h80 : 8'h00)),
                            record_buffer[15:8],3'd0,scan_voice,8'd1};
                        query_done<=1; state<=IDLE;
                    end else if(scan_all && scan_voice!=31) begin
                        scan_voice<=scan_voice+1'b1; fetch_index<=0; state<=FETCH;
                    end else state<=IDLE;
                end
                default: begin state<=INITIALIZE; initialize_address<=0; end
            endcase
        end
    end
endmodule
