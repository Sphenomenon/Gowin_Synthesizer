// Minimal BLE peripheral host. H5 framing/retries and HCI initialization are
// outside this module. No processor or firmware executes this ATT database.
// Two response slots keep ACL reception independent of controller TX credit.
module bt_gatt #(
    parameter integer CLK_HZ = 50000000,
    parameter integer NOTIFY_MS = 500
) (
    input wire clk, input wire resetn, input wire enable,
    input wire rx_valid, input wire [3:0] rx_type,
    input wire [8:0] rx_length,
    output reg [8:0] rx_payload_addr,
    input wire [7:0] rx_payload_data,
    output reg rx_consume,
    output reg tx_start, output wire [3:0] tx_type,
    output reg [8:0] tx_length,
    input wire tx_ready, input wire tx_done, input wire tx_error,
    input wire [8:0] tx_payload_addr,
    output wire [7:0] tx_payload_data,
    output reg connected, output reg subscribed,
    output reg [11:0] connection_handle,
    output reg [31:0] notification_count, output reg [31:0] acl_rx_count,
    output reg [31:0] att_request_count,
    output reg [31:0] completed_packets,
    output wire [7:0] debug_state, output reg [31:0] error_count,
    output reg [31:0] elapsed_ms
);
    localparam integer MS_CYCLES = CLK_HZ / 1000;
    localparam [2:0] IDLE=0, CAPTURE=1, PARSE=2, WAIT_DROP=3, COMPLETIONS=4;
    reg [2:0] state;
    reg [3:0] captured_type;
    reg [8:0] captured_length;
    reg [7:0] packet [0:263];
    reg [7:0] response [0:159];
    reg [8:0] response_length [0:1];
    reg [7:0] active_tx [0:79];
    reg [1:0] queued;
    reg read_slot, write_slot, tx_busy, tx_credit;
    reg [31:0] ms_divider, notify_deadline;
    reg [5:0] completion_index;
    reg [31:0] completion_sum;
    integer i, used, start_handle, end_handle, attribute_type;
    integer response_base, matching_completed;
    reg [15:0] work_crc;
    reg [7:0] work_byte;

    assign tx_type = 4'd2;
    assign tx_payload_data = tx_payload_addr < 80 ?
                             active_tx[tx_payload_addr] : 8'h00;
    assign debug_state = {tx_busy, tx_credit, queued, 1'b0, state};

    function [15:0] word_at;
        input integer address;
        begin word_at = {packet[address+1], packet[address]}; end
    endfunction
    function [15:0] attribute_uuid;
        input integer handle;
        begin
            case(handle)
                1,4,5: attribute_uuid=16'h2800;
                2,6: attribute_uuid=16'h2803;
                3: attribute_uuid=16'h2a00;
                7: attribute_uuid=16'hfff1;
                8: attribute_uuid=16'h2902;
                default: attribute_uuid=0;
            endcase
        end
    endfunction
    function [7:0] name_byte;
        input integer index;
        begin
            case(index)
                0:name_byte="R"; 1:name_byte="T"; 2:name_byte="L";
                3:name_byte="8"; 4:name_byte="7"; 5:name_byte="2";
                6:name_byte="3"; 7:name_byte="-"; 8:name_byte="B";
                9:name_byte="L"; 10:name_byte="E";
                default:name_byte=0;
            endcase
        end
    endfunction
    function [7:0] sample_byte;
        input integer index;
        input [31:0] sequence_number;
        input [31:0] milliseconds;
        begin
            case(index)
                0:sample_byte="B"; 1:sample_byte="T";
                2:sample_byte="S"; 3:sample_byte="T";
                4:sample_byte=sequence_number[7:0];
                5:sample_byte=sequence_number[15:8];
                6:sample_byte=sequence_number[23:16];
                7:sample_byte=sequence_number[31:24];
                8:sample_byte=milliseconds[7:0];
                9:sample_byte=milliseconds[15:8];
                10:sample_byte=milliseconds[23:16];
                11:sample_byte=milliseconds[31:24];
                default:sample_byte=index-12;
            endcase
        end
    endfunction
    function [15:0] crc_byte;
        input [15:0] previous;
        input [7:0] data;
        reg [15:0] c;
        integer bit_index;
        begin
            c=previous ^ {data,8'h00};
            for(bit_index=0;bit_index<8;bit_index=bit_index+1)
                c = c[15] ? (c << 1) ^ 16'h1021 : (c << 1);
            crc_byte=c;
        end
    endfunction
    task response_word;
        input integer address;
        input [15:0] data;
        begin
            response[response_base+address]=data[7:0];
            response[response_base+address+1]=data[15:8];
        end
    endtask
    task response_begin;
        input [15:0] cid;
        input integer length;
        begin
            // PB=00: host-to-controller LE first, non-flushable fragment.
            response_word(0,{4'b0000,connection_handle});
            response_word(2,length+4);
            response_word(4,length);
            response_word(6,cid);
            response_length[write_slot] <= length+8;
            write_slot <= ~write_slot;
            queued <= queued+1'b1;
        end
    endtask
    task att_error_response;
        input [7:0] opcode;
        input [15:0] handle;
        input [7:0] code;
        begin
            response_begin(4,5);
            response[response_base+8]=8'h01;
            response[response_base+9]=opcode;
            response_word(10,handle);
            response[response_base+12]=code;
        end
    endtask
    task response_value;
        input integer address;
        integer n;
        begin
            work_crc=16'hffff;
            for(n=0;n<18;n=n+1) begin
                work_byte=sample_byte(n,notification_count,elapsed_ms);
                response[response_base+address+n]=work_byte;
                work_crc=crc_byte(work_crc,work_byte);
            end
            response_word(address+18,work_crc);
        end
    endtask

    // Fixed ATT MTU 23, handles 1..8, matching the verified C peripheral:
    // GAP/device-name, GATT, FFF0 service, read+notify FFF1 and CCCD.
    task process_att;
        begin
            start_handle=word_at(9); end_handle=word_at(11);
            attribute_type=word_at(13);
            case(packet[8])
                8'h02: begin
                    if(captured_length!=11) att_error_response(2,0,8'h04);
                    else begin
                        response_begin(4,3); response[response_base+8]=3;
                        response_word(9,23);
                    end
                end
                8'h06: begin
                    if(captured_length!=17) att_error_response(6,0,8'h04);
                    else if(start_handle==0 || start_handle>end_handle)
                        att_error_response(6,start_handle,1);
                    else begin
                        response[response_base+8]=7; used=1;
                        for(i=1;i<=5;i=i+1) begin
                            if(i>=start_handle && i<=end_handle &&
                               attribute_type==16'h2800 &&
                               ((i==1 && word_at(15)==16'h1800) ||
                                (i==4 && word_at(15)==16'h1801) ||
                                (i==5 && word_at(15)==16'hfff0))) begin
                                response_word(8+used,i);
                                response_word(10+used,i==1 ? 3 : i==4 ? 4 : 8);
                                used=used+4;
                            end
                        end
                        if(used==1) att_error_response(6,start_handle,8'h0a);
                        else response_begin(4,used);
                    end
                end
                8'h10: begin
                    if(captured_length!=15) att_error_response(8'h10,0,8'h04);
                    else if(start_handle==0 || start_handle>end_handle)
                        att_error_response(8'h10,start_handle,1);
                    else if(attribute_type!=16'h2800)
                        att_error_response(8'h10,start_handle,8'h10);
                    else begin
                        response[response_base+8]=8'h11;
                        response[response_base+9]=6; used=2;
                        for(i=1;i<=5;i=i+1) begin
                            if((i==1 || i==4 || i==5) &&
                               i>=start_handle && i<=end_handle) begin
                                response_word(8+used,i);
                                response_word(10+used,i==1 ? 3 : i==4 ? 4 : 8);
                                response_word(12+used,i==1 ? 16'h1800 :
                                                         i==4 ? 16'h1801 : 16'hfff0);
                                used=used+6;
                            end
                        end
                        if(used==2) att_error_response(8'h10,start_handle,8'h0a);
                        else response_begin(4,used);
                    end
                end
                8'h08: begin
                    if(captured_length!=15) att_error_response(8,0,8'h04);
                    else if(start_handle==0 || start_handle>end_handle)
                        att_error_response(8,start_handle,1);
                    else begin
                        response[response_base+8]=9; used=2;
                        if(attribute_type==16'h2803) begin
                            response[response_base+9]=7;
                            for(i=2;i<=6;i=i+4) begin
                                if(i>=start_handle && i<=end_handle) begin
                                    response_word(8+used,i);
                                    response[response_base+10+used]=i==2 ? 2 : 8'h12;
                                    response_word(11+used,i==2 ? 3 : 7);
                                    response_word(13+used,i==2 ? 16'h2a00 : 16'hfff1);
                                    used=used+7;
                                end
                            end
                        end else if(attribute_type==16'h2a00 &&
                                    start_handle<=3 && end_handle>=3) begin
                            response[response_base+9]=13; response_word(10,3);
                            for(i=0;i<11;i=i+1)
                                response[response_base+12+i]=name_byte(i);
                            used=15;
                        end
                        if(used==2) att_error_response(8,start_handle,8'h0a);
                        else response_begin(4,used);
                    end
                end
                8'h04: begin
                    if(captured_length!=13) att_error_response(4,0,8'h04);
                    else if(start_handle==0 || start_handle>end_handle)
                        att_error_response(4,start_handle,1);
                    else begin
                        response[response_base+8]=5;
                        response[response_base+9]=1; used=2;
                        // Five entries fit MTU 23. A static loop is synthesizable.
                        for(i=1;i<=8;i=i+1) begin
                            if(i>=start_handle && i<=end_handle && used+4<=23) begin
                                response_word(8+used,i);
                                response_word(10+used,attribute_uuid(i)); used=used+4;
                            end
                        end
                        if(used==2) att_error_response(4,start_handle,8'h0a);
                        else response_begin(4,used);
                    end
                end
                8'h0a: begin
                    if(captured_length!=11) att_error_response(8'h0a,0,8'h04);
                    else if(start_handle==3) begin
                        response_begin(4,12); response[response_base+8]=8'h0b;
                        for(i=0;i<11;i=i+1) response[response_base+9+i]=name_byte(i);
                    end else if(start_handle==7) begin
                        response_begin(4,21); response[response_base+8]=8'h0b;
                        response_value(9);
                    end else if(start_handle==8) begin
                        response_begin(4,3); response[response_base+8]=8'h0b;
                        response_word(9,{15'b0,subscribed});
                    end else att_error_response(8'h0a,start_handle,
                                        start_handle==0 || start_handle>8 ? 1 : 2);
                end
                8'h12,8'h52: begin
                    if(captured_length<11) begin
                        if(packet[8]==8'h12) att_error_response(8'h12,0,8'h04);
                    end else if(start_handle==8 &&
                       captured_length==13 && word_at(11)<=1) begin
                        subscribed <= packet[11][0];
                        notify_deadline <= elapsed_ms+NOTIFY_MS;
                        if(packet[8]==8'h12) begin
                            response_begin(4,1); response[response_base+8]=8'h13;
                        end
                    end else if(packet[8]==8'h12)
                        att_error_response(8'h12,start_handle,
                                           start_handle==8 ? 8'h0d : 3);
                end
                8'h1e: begin end // Confirmation has no ATT response.
                default: att_error_response(packet[8],
                            captured_length>=11 ? start_handle : 0,6);
            endcase
        end
    endtask

    always @(posedge clk) begin
        if(!resetn || !enable) begin
            state<=IDLE; captured_type<=0; captured_length<=0;
            rx_payload_addr<=0; rx_consume<=0; tx_start<=0; tx_length<=0;
            connected<=0; subscribed<=0; connection_handle<=0;
            notification_count<=0; acl_rx_count<=0; att_request_count<=0;
            completed_packets<=0; error_count<=0; elapsed_ms<=0;
            ms_divider<=0; notify_deadline<=NOTIFY_MS;
            completion_index<=0; completion_sum<=0;
            queued<=0; read_slot<=0; write_slot<=0; tx_busy<=0; tx_credit<=1;
        end else begin
            rx_consume<=0; tx_start<=0;
            if(ms_divider>=MS_CYCLES-1) begin
                ms_divider<=0; elapsed_ms<=elapsed_ms+1'b1;
            end else ms_divider<=ms_divider+1'b1;
            if(tx_busy && (tx_done || tx_error)) begin
                tx_busy<=0;
                if(tx_error) error_count<=error_count+1'b1;
            end
            case(state)
                IDLE: begin
                    if(rx_valid) begin
                        if(rx_length==0 || rx_length>264) begin
                            rx_consume<=1; error_count<=error_count+1'b1;
                            state<=WAIT_DROP;
                        end else begin
                            captured_type<=rx_type; captured_length<=rx_length;
                            rx_payload_addr<=0; state<=CAPTURE;
                        end
                    end else if(!tx_busy && tx_ready && tx_credit && queued!=0) begin
                        for(i=0;i<80;i=i+1) begin
                            if(read_slot) active_tx[i]<=response[80+i];
                            else active_tx[i]<=response[i];
                        end
                        tx_length<=response_length[read_slot]; tx_start<=1;
                        read_slot<=~read_slot; queued<=queued-1'b1;
                        tx_busy<=1; tx_credit<=0;
                    end else if(!tx_busy && tx_ready && tx_credit && queued==0 &&
                                connected && subscribed &&
                                $signed(elapsed_ms-notify_deadline)>=0) begin
                        active_tx[0]<=connection_handle[7:0];
                        active_tx[1]<={4'b0000,connection_handle[11:8]};
                        active_tx[2]<=27; active_tx[3]<=0;
                        active_tx[4]<=23; active_tx[5]<=0;
                        active_tx[6]<=4; active_tx[7]<=0;
                        active_tx[8]<=8'h1b; active_tx[9]<=7; active_tx[10]<=0;
                        work_crc=16'hffff;
                        for(i=0;i<18;i=i+1) begin
                            work_byte=sample_byte(i,notification_count,elapsed_ms);
                            active_tx[11+i]<=work_byte;
                            work_crc=crc_byte(work_crc,work_byte);
                        end
                        active_tx[29]<=work_crc[7:0]; active_tx[30]<=work_crc[15:8];
                        tx_length<=31; tx_start<=1; tx_busy<=1; tx_credit<=0;
                        notification_count<=notification_count+1'b1;
                        notify_deadline<=elapsed_ms+NOTIFY_MS;
                    end
                end
                CAPTURE: begin
                    packet[rx_payload_addr]<=rx_payload_data;
                    if(rx_payload_addr+1'b1==captured_length) begin
                        rx_consume<=1; state<=PARSE;
                    end else rx_payload_addr<=rx_payload_addr+1'b1;
                end
                PARSE: begin
                    state<=IDLE;
                    response_base=write_slot ? 80 : 0;
                    if(captured_type==4 && captured_length>=2 &&
                       captured_length==packet[1]+2) begin
                        if(packet[0]==8'h3e && captured_length>=21 &&
                           (packet[2]==1 || packet[2]==8'h0a) && packet[3]==0) begin
                            connected<=1; subscribed<=0;
                            connection_handle<=word_at(4)&16'h0fff;
                            tx_credit<=1; queued<=0; read_slot<=0; write_slot<=0;
                            notify_deadline<=elapsed_ms+NOTIFY_MS;
                        end else if(packet[0]==5 && captured_length==6 &&
                                    packet[2]==0 &&
                                    (word_at(3)&16'h0fff)==connection_handle) begin
                            connected<=0; subscribed<=0;
                            queued<=0; read_slot<=0; write_slot<=0;
                        end else if(packet[0]==8'h13 && captured_length>=7 &&
                                    captured_length==3+packet[2]*4) begin
                            // One handle per clock avoids a long combinational
                            // chain when an event contains many connections.
                            completion_index<=0; completion_sum<=0;
                            state<=COMPLETIONS;
                        end
                    end else if(captured_type==2) begin
                        // Continuations are explicitly rejected: this fixed MTU
                        // peripheral supports only complete LE L2CAP packets.
                        if(captured_length<8 || !connected ||
                           (word_at(0)&16'h0fff)!=connection_handle ||
                           (packet[1][5:4]!=0 && packet[1][5:4]!=2) ||
                           packet[1][7:6]!=0 ||
                           word_at(2)!=captured_length-4 ||
                           word_at(4)!=captured_length-8) begin
                            error_count<=error_count+1'b1;
                        end else begin
                            acl_rx_count<=acl_rx_count+1'b1;
                            if(word_at(6)==4 && captured_length>8) begin
                                att_request_count<=att_request_count+1'b1;
                                if(queued==2) error_count<=error_count+1'b1;
                                else process_att();
                            end else if(word_at(6)==5 && captured_length>=12) begin
                                if(queued==2) error_count<=error_count+1'b1;
                                else begin
                                    response_begin(5,6);
                                    response[response_base+8]=1;
                                    response[response_base+9]=packet[9];
                                    response_word(10,2); response_word(12,0);
                                end
                            end
                        end
                    end
                end
                COMPLETIONS: begin
                    matching_completed=0;
                    if(connected &&
                       (word_at(3+4*completion_index)&16'h0fff)==connection_handle)
                        matching_completed=word_at(5+4*completion_index);
                    completion_sum<=completion_sum+matching_completed;
                    if(completion_index+1'b1==packet[2]) begin
                        if(completion_sum+matching_completed!=0) begin
                            completed_packets<=completed_packets+completion_sum+matching_completed;
                            tx_credit<=1;
                        end
                        state<=IDLE;
                    end else completion_index<=completion_index+1'b1;
                end
                WAIT_DROP: if(!rx_valid) state<=IDLE;
                default: state<=IDLE;
            endcase
        end
    end
endmodule
