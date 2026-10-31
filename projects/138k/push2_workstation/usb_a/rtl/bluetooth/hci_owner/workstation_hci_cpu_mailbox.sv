// Private bounded CPU copies. No controller credit, H5 or BLE authority.
// Payload RAMs have a single synchronous write port and registered read port.
module workstation_hci_cpu_mailbox (
    input wire clk_i, reset_ni, observer_reset_ni,
    input wire ready_i, controller_fault_i, classic_fenced_i, admission_i,
    input wire [31:0] epoch_i, time_ms_i,
    input wire [15:0] br_limit_i, le_limit_i, br_available_i, le_available_i,
    output reg observer_lost_o, queue_fault_o, fence_o,
    input wire command_valid_i, command_write_i,
    input wire [11:0] command_address_i,
    input wire [31:0] command_data_i,
    input wire [3:0] command_strobes_i,
    output wire command_ready_o,
    output reg response_error_o,
    output reg [31:0] response_data_o,

    output wire tx_valid_o,
    output wire [31:0] tx_epoch_o, tx_generation_o, tx_token_o,
    output wire [3:0] tx_type_o,
    output wire [8:0] tx_length_o,
    input wire [8:0] tx_address_i,
    output reg [7:0] tx_data_o,
    input wire tx_accept_i, tx_reject_i, tx_transport_done_i,
    input wire tx_response_i, tx_uncertain_i,
    input wire [7:0] tx_reject_reason_i,

    // Complete immutable outer staging packet, held through copy_done.
    input wire rx_offer_i,
    output wire rx_ready_o,
    input wire [3:0] rx_type_i,
    input wire [8:0] rx_length_i,
    input wire [31:0] rx_generation_i, rx_command_token_i,
    input wire [11:0] rx_handle_i,
    input wire [1:0] rx_owner_i,
    input wire rx_response_i,
    output wire [8:0] rx_address_o,
    input wire [7:0] rx_data_i,
    output reg rx_copy_done_o,
    input wire rx_drop_i,
    input wire disconnect_i,
    input wire [31:0] disconnect_generation_i
);
    localparam [3:0] EMPTY=0, STAGING=1, PENDING=2, ACCEPTED=3,
        TRANSPORT_DONE=4, REJECTED=5, UNCERTAIN=6;
    localparam [7:0] R_CONTEXT=1,R_FENCED=2,R_TOKEN=3;
    (* ram_style="block" *) reg [7:0] tx_ram [0:279];
    (* ram_style="block" *) reg [7:0] rx_ram [0:2047];
    reg [3:0] tx_state;
    reg [31:0] staged_epoch, staged_generation, staged_token, last_token;
    reg [31:0] staged_meta, release_epoch;
    reg [8:0] staged_bytes, cpu_index;
    reg accepted, transport_done, response_done;
    reg [7:0] reject_reason;
    reg [1:0] head, tail;
    reg [2:0] count;
    reg [31:0] tickets [0:3], epochs [0:3], generations [0:3], command_tokens [0:3];
    reg [8:0] lengths [0:3];
    reg [3:0] types [0:3];
    reg [11:0] handles [0:3];
    reg [1:0] owners [0:3];
    reg [3:0] responses, retired;
    reg [31:0] last_ticket, dropped, rejected;
    reg copying, copy_wait, previous_observer_reset;
    reg [8:0] copy_index;
    reg [1:0] read_settle;
    reg [7:0] cpu_data;
    wire observer_edge=previous_observer_reset && !observer_reset_ni;
    wire cpu_available=observer_reset_ni && ready_i && epoch_i!=0 &&
        !controller_fault_i && !classic_fenced_i && !queue_fault_o;
    wire data_read=command_valid_i && !command_write_i && command_address_i==12'h260;
    assign command_ready_o=!data_read || read_settle==0;
    wire bus_write=command_valid_i && command_ready_o && command_write_i && !response_error_o;
    wire release_head=bus_write && command_address_i==12'h264;
    wire publish=copying && !copy_wait && copy_index+1'b1==lengths[tail] &&
        observer_reset_ni && !observer_edge;
    assign rx_ready_o=cpu_available && !copying && count<4 && last_ticket!=32'hffffffff;
    assign rx_address_o=copy_index;
    assign tx_valid_o=tx_state==PENDING && cpu_available;
    assign tx_epoch_o=staged_epoch, tx_generation_o=staged_generation,
        tx_token_o=staged_token, tx_type_o=staged_meta[3:0], tx_length_o=staged_meta[24:16];
    function automatic [31:0] sat(input [31:0] value);
        sat=&value ? value : value+1'b1;
    endfunction
    always @(posedge clk_i) begin
        tx_data_o<=tx_ram[tx_address_i];
        cpu_data<=rx_ram[{head,cpu_index}];
        if(reset_ni && bus_write && command_address_i==12'h228)
            tx_ram[staged_bytes]<=command_data_i[7:0];
        if(reset_ni && copying && !copy_wait && observer_reset_ni && !observer_edge)
            rx_ram[{tail,copy_index}]<=rx_data_i;
    end
    always @* begin
        response_error_o=0;response_data_o=0;
        if(command_address_i[1:0]!=0)response_error_o=1;
        else if(command_write_i)begin
            if(command_strobes_i!=4'hf || !observer_reset_ni)response_error_o=1;
            else case(command_address_i)
                12'h210,12'h214,12'h218,12'h21c:
                    response_error_o=tx_state!=STAGING;
                12'h220:response_error_o=tx_state!=EMPTY || command_data_i!=1;
                12'h224:response_error_o=tx_state!=STAGING || command_data_i!=1 ||
                    staged_meta[31:25]!=0 || staged_meta[15:4]!=0 ||
                    (staged_meta[3:0]!=1 && staged_meta[3:0]!=2) ||
                    staged_meta[24:16]<3 || staged_meta[24:16]>280 ||
                    staged_bytes!=staged_meta[24:16];
                12'h228:response_error_o=tx_state!=STAGING || staged_bytes>=280 || command_data_i[31:8]!=0;
                12'h230:response_error_o=command_data_i!=staged_token ||
                    !((tx_state==TRANSPORT_DONE && response_done) || tx_state==REJECTED || tx_state==UNCERTAIN);
                12'h23c:begin end
                12'h27c:response_error_o=command_data_i==0 || command_data_i!=epoch_i;
                12'h25c:response_error_o=count==0 || command_data_i>=lengths[head];
                12'h264:response_error_o=count==0 || command_data_i!=tickets[head] ||
                    release_epoch!=epoch_i || release_epoch!=epochs[head] || read_settle!=0;
                default:response_error_o=1;
            endcase
        end else case(command_address_i)
            12'h200:response_data_o=32'h48434931;
            12'h204:response_data_o={8'd1,8'd4,16'd276};
            12'h208:response_data_o={27'd0,admission_i,copying,(classic_fenced_i||queue_fault_o),controller_fault_i,ready_i};
            12'h20c:response_data_o=epoch_i;
            12'h210:response_data_o=staged_epoch;
            12'h214:response_data_o=staged_generation;
            12'h218:response_data_o=staged_token;
            12'h21c:response_data_o=staged_meta;
            12'h22c:response_data_o={21'd0,transport_done,accepted,response_done,4'd0,tx_state};
            12'h234:response_data_o={24'd0,reject_reason};
            12'h238:response_data_o={23'd0,staged_bytes};
            12'h23c:response_data_o=release_epoch;
            12'h240:response_data_o={22'd0,copying,(count!=0),5'd0,count};
            12'h244:response_data_o=count!=0 ? epochs[head] : 0;
            12'h248:response_data_o=count!=0 ? generations[head] : 0;
            12'h24c:response_data_o=count!=0 ? tickets[head] : 0;
            12'h250:response_data_o=count!=0 ? {7'd0,lengths[head],5'd0,responses[head],owners[head],4'd0,types[head]} : 0;
            12'h254:response_data_o=count!=0 ? {15'd0,retired[head],4'd0,handles[head]} : 0;
            12'h258:response_data_o=count!=0 ? command_tokens[head] : 0;
            12'h25c:response_data_o={23'd0,cpu_index};
            12'h260:begin response_data_o={24'd0,cpu_data};response_error_o=count==0 || cpu_index>=lengths[head];end
            12'h268:response_data_o=dropped;
            12'h26c:response_data_o=rejected;
            12'h270:response_data_o={le_limit_i,br_limit_i};
            12'h274:response_data_o={le_available_i,br_available_i};
            12'h278:response_data_o=time_ms_i;
            default:response_error_o=1;
        endcase
    end
    integer at;
    always @(posedge clk_i)begin
        observer_lost_o<=0;rx_copy_done_o<=0;fence_o<=0;
        if(!reset_ni)begin
            tx_state<=EMPTY;staged_epoch<=0;staged_generation<=0;staged_token<=0;
            staged_meta<=0;staged_bytes<=0;last_token<=0;release_epoch<=0;
            accepted<=0;transport_done<=0;response_done<=0;reject_reason<=0;
            head<=0;tail<=0;count<=0;copying<=0;copy_wait<=1;copy_index<=0;
            last_ticket<=0;dropped<=0;rejected<=0;responses<=0;retired<=0;
            previous_observer_reset<=0;queue_fault_o<=0;cpu_index<=0;read_settle<=2;
            for(at=0;at<4;at=at+1)begin
                tickets[at]<=0;epochs[at]<=0;generations[at]<=0;command_tokens[at]<=0;
                lengths[at]<=0;types[at]<=0;handles[at]<=0;owners[at]<=0;
            end
        end else begin
            previous_observer_reset<=observer_reset_ni;
            if(read_settle!=0)read_settle<=read_settle-1'b1;
            if(command_valid_i && command_ready_o && response_error_o)rejected<=sat(rejected);
            if(rx_drop_i)begin dropped<=sat(dropped);queue_fault_o<=1;end
            if(last_ticket==32'hffffffff)queue_fault_o<=1;
            if(disconnect_i)begin
                for(at=0;at<4;at=at+1)
                    if(generations[at]==disconnect_generation_i && generations[at]!=0)retired[at]<=1;
            end
            // A reset invalidates CPU references only. The outer private TX
            // slot and controller ledgers must remain alive through retirement.
            if(observer_edge)begin
                observer_lost_o<=ready_i;
                count<=0;head<=0;tail<=0;cpu_index<=0;read_settle<=2;
                if(copying)rx_copy_done_o<=1;
                copying<=0;copy_wait<=1;
                if(tx_state==PENDING || tx_state==STAGING)begin tx_state<=REJECTED;reject_reason<=R_FENCED;end
                else if(tx_state==ACCEPTED || tx_state==TRANSPORT_DONE)begin tx_state<=UNCERTAIN;reject_reason<=R_FENCED;end
            end else begin
                if(rx_offer_i && rx_ready_o)begin
                    copying<=1;copy_index<=0;copy_wait<=1;
                    lengths[tail]<=rx_length_i;types[tail]<=rx_type_i;generations[tail]<=rx_generation_i;
                    command_tokens[tail]<=rx_command_token_i;handles[tail]<=rx_handle_i;
                    owners[tail]<=rx_owner_i;responses[tail]<=rx_response_i;retired[tail]<=0;
                    epochs[tail]<=epoch_i;tickets[tail]<=last_ticket+1'b1;last_ticket<=last_ticket+1'b1;
                end
                if(copying)begin
                    if(copy_wait)copy_wait<=0;
                    else begin
                        copy_wait<=1;
                        if(copy_index+1'b1==lengths[tail])begin
                            copying<=0;tail<=tail+1'b1;rx_copy_done_o<=1;
                        end else copy_index<=copy_index+1'b1;
                    end
                end
                case({publish,release_head})
                    2'b10:count<=count+1'b1;
                    2'b01:count<=count-1'b1;
                    default:begin end
                endcase
                if(release_head)begin head<=head+1'b1;cpu_index<=0;read_settle<=2;end
                if(bus_write)case(command_address_i)
                    12'h210:staged_epoch<=command_data_i;
                    12'h214:staged_generation<=command_data_i;
                    12'h218:staged_token<=command_data_i;
                    12'h21c:staged_meta<=command_data_i;
                    12'h220:begin
                        tx_state<=STAGING;staged_epoch<=0;staged_generation<=0;staged_token<=0;
                        staged_meta<=0;staged_bytes<=0;accepted<=0;transport_done<=0;response_done<=0;reject_reason<=0;
                    end
                    12'h224:begin
                        if(!cpu_available)begin tx_state<=REJECTED;reject_reason<=R_FENCED;end
                        else if(staged_epoch!=epoch_i)begin tx_state<=REJECTED;reject_reason<=R_CONTEXT;end
                        else if(staged_token==0 || staged_token<=last_token)begin tx_state<=REJECTED;reject_reason<=R_TOKEN;end
                        else begin tx_state<=PENDING;last_token<=staged_token;end
                    end
                    12'h228:staged_bytes<=staged_bytes+1'b1;
                    12'h230:begin tx_state<=EMPTY;accepted<=0;transport_done<=0;response_done<=0;end
                    12'h23c:release_epoch<=command_data_i;
                    12'h27c:fence_o<=1;
                    12'h25c:begin cpu_index<=command_data_i[8:0];read_settle<=2;end
                    default:begin end
                endcase
                if((classic_fenced_i || queue_fault_o || controller_fault_i) && tx_state==PENDING)begin
                    tx_state<=REJECTED;reject_reason<=R_FENCED;
                end
                if(tx_accept_i)begin tx_state<=ACCEPTED;accepted<=1;end
                if(tx_reject_i)begin tx_state<=REJECTED;reject_reason<=tx_reject_reason_i;end
                if(tx_response_i)response_done<=1;
                if(tx_transport_done_i)begin
                    if(tx_state!=UNCERTAIN)tx_state<=TRANSPORT_DONE;transport_done<=1;
                    if(staged_meta[3:0]==2)response_done<=1;
                end
                if((tx_uncertain_i || controller_fault_i) && accepted && !(transport_done && response_done))begin
                    tx_state<=UNCERTAIN;reject_reason<=R_CONTEXT;
                end
            end
        end
    end
endmodule
