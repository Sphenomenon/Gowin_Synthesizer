// Native BLE logical fragmentation/reassembly, derived from versioned 25K bridge.
// Sole physical credits, handle generations and event validation are external.
// HCI ACL fragmentation boundary. GATT sees complete L2CAP packets; H5 sees
// controller-sized ACL packets. Events may interleave an incomplete RX PDU.
// All three payload memories have a single synchronous read/write port.
module workstation_hci_ble_bridge #(
    parameter CLK_HZ=50000000,
    parameter ACL_BYTES=27,
    parameter MAX_PACKET=264,
    parameter REASSEMBLY_MS=2000
)(
    input wire clk, resetn, enable, connected,
    input wire [11:0] connection_handle,
    input wire [15:0] acl_data_limit_i,
    input wire app_tx_start,
    input wire [3:0] app_tx_type,
    input wire [8:0] app_tx_length,
    output wire [8:0] app_tx_addr,
    input wire [7:0] app_tx_data,
    output wire app_tx_ready,
    output reg app_tx_done, app_tx_error,
    output reg app_rx_valid,
    output reg [3:0] app_rx_type,
    output reg [8:0] app_rx_length,
    input wire [8:0] app_rx_addr,
    output wire [7:0] app_rx_data,
    input wire app_rx_consume,
    output reg h5_tx_start,
    output wire [3:0] h5_tx_type,
    output wire [8:0] h5_tx_length,
    input wire [8:0] h5_tx_addr,
    output wire [7:0] h5_tx_data,
    input wire h5_tx_ready, h5_tx_done, h5_tx_error,
    input wire h5_rx_valid,
    input wire [3:0] h5_rx_type,
    input wire [8:0] h5_rx_length,
    output reg [8:0] h5_rx_addr,
    input wire [7:0] h5_rx_data,
    output reg h5_rx_consume,
    output reg [31:0] errors
);
    localparam T_IDLE=0,T_COPY=1,T_PREP=2,T_SEND=3,T_WAIT=4;
    localparam R_IDLE=0,R_HEAD=1,R_L2=2,R_PREFIX=3,R_COPY=4,R_EVENT=5,R_DROP=6;
    localparam TIMEOUT=(CLK_HZ/1000)*REASSEMBLY_MS;
    reg [2:0] t_state, r_state;
    (* ram_style="block" *) reg [7:0] tx_ram[0:MAX_PACKET-1];
    (* ram_style="block" *) reg [7:0] acl_ram[0:MAX_PACKET-1];
    (* ram_style="block" *) reg [7:0] event_ram[0:MAX_PACKET-1];
    reg [7:0] tx_read, acl_read, event_read;
    reg [8:0] t_index,t_length,t_offset,t_chunk;
    reg [3:0] t_type,r_type;
    reg [7:0] t_head[0:3], r_head[0:7];
    reg t_wait,r_wait;
    reg [8:0] r_index,r_length,r_position,r_total;
    reg partial;
    reg [11:0] partial_handle;
    reg [31:0] partial_timer;
    // Logical BLE PDU copy/fragmentation only. Physical controller credits
    // belong exclusively to workstation_hci_flow_owner in the native router.
    wire [8:0] fragment_limit=acl_data_limit_i<ACL_BYTES ? acl_data_limit_i[8:0] : 9'(ACL_BYTES);
    wire issue=t_state==T_SEND && h5_tx_ready;
    wire [8:0] tx_read_addr=t_type==2 ? t_offset+h5_tx_addr : h5_tx_addr;
    assign app_tx_addr=t_index;
    assign app_tx_ready=enable && t_state==T_IDLE;
    assign h5_tx_type=t_type;
    assign h5_tx_length=t_type==2 ? t_chunk+9'd4 : t_length;
    assign h5_tx_data=t_type!=2 || h5_tx_addr>=4 ? tx_read :
        h5_tx_addr==0 ? t_head[0] :
        h5_tx_addr==1 ? {(t_offset==0 ? 4'b0000 : 4'b0001),t_head[1][3:0]} :
        h5_tx_addr==2 ? t_chunk[7:0] : 8'd0;
    assign app_rx_data=app_rx_type==2 ? acl_read : event_read;
    wire tx_we=enable && t_state==T_COPY && !t_wait;
    wire acl_we=enable && (r_state==R_PREFIX || (r_state==R_COPY && !r_wait));
    wire [8:0] acl_write_addr=r_state==R_PREFIX ? r_index : r_position;
    wire [8:0] normalized_length=r_total-9'd4;
    wire [7:0] acl_write_data=r_state!=R_PREFIX ? h5_rx_data :
        r_index==1 ? {4'd0,r_head[1][3:0]} :
        r_index==2 ? normalized_length[7:0] :
        r_index==3 ? {7'd0,normalized_length[8]} : r_head[r_index[2:0]];
    wire event_we=enable && r_state==R_EVENT && !r_wait;
    always @(posedge clk) begin
        if(tx_we) tx_ram[t_index]<=app_tx_data;
        tx_read<=tx_ram[tx_read_addr];
        if(acl_we) acl_ram[acl_write_addr]<=acl_write_data;
        acl_read<=acl_ram[app_rx_addr];
        if(event_we) event_ram[r_index]<=h5_rx_data;
        event_read<=event_ram[app_rx_addr];
    end
    always @(posedge clk) begin
        app_tx_done<=0;app_tx_error<=0;h5_tx_start<=0;
        if(!resetn || !enable) begin
            t_state<=T_IDLE;t_index<=0;t_length<=0;t_type<=0;
            t_offset<=0;t_chunk<=0;t_wait<=1;
        end else if(t_state!=T_IDLE && t_type==2 && !connected) begin
            // Disconnect aborts a pending ACL PDU without failing the HCI link.
            t_state<=T_IDLE;app_tx_done<=1;
        end else case(t_state)
            T_IDLE: if(app_tx_start) begin
                if(app_tx_length==0 || app_tx_length>MAX_PACKET) app_tx_error<=1;
                else begin
                    t_type<=app_tx_type;t_length<=app_tx_length;
                    t_index<=0;t_wait<=1;t_state<=T_COPY;
                end
            end
            T_COPY: if(t_wait)t_wait<=0;else begin
                t_wait<=1;
                if(t_index<4)t_head[t_index[1:0]]<=app_tx_data;
                if(t_index+1==t_length)t_state<=T_PREP;
                else t_index<=t_index+1'b1;
            end
            T_PREP: begin
                if(t_type==2 && (t_length<8 || {t_head[3],t_head[2]}!=t_length-4 ||
                    t_head[1][7:6]!=0 || (t_head[1][5:4]!=0 && t_head[1][5:4]!=2))) begin
                    app_tx_error<=1;t_state<=T_IDLE;
                end else begin
                    t_offset<=0;t_chunk<=t_length-4>fragment_limit ? fragment_limit : t_length-4;
                    t_state<=T_SEND;
                end
            end
            T_SEND: if(issue)begin h5_tx_start<=1;t_state<=T_WAIT;end
            T_WAIT: if(h5_tx_error)begin app_tx_error<=1;t_state<=T_IDLE;end
                else if(h5_tx_done) begin
                    if(t_type==2 && t_offset+t_chunk<t_length-4)begin
                        t_offset<=t_offset+t_chunk;
                        t_chunk<=t_length-4-t_offset-t_chunk>fragment_limit ? fragment_limit : t_length-4-t_offset-t_chunk;
                        t_state<=T_SEND;
                    end else begin app_tx_done<=1;t_state<=T_IDLE;end
                end
            default:t_state<=T_IDLE;
        endcase
    end
    task drop_rx;
        begin errors<=errors+1'b1;h5_rx_consume<=1;r_state<=R_DROP;end
    endtask
    task finish_acl;
        begin
            if(r_position+1==r_total)begin
                app_rx_valid<=1;app_rx_type<=2;app_rx_length<=r_total;partial<=0;
            end else begin partial<=1;partial_timer<=0;end
            h5_rx_consume<=1;r_state<=R_DROP;
        end
    endtask
    always @(posedge clk) begin
        h5_rx_consume<=0;
        if(!resetn || !enable)begin
            r_state<=R_IDLE;r_type<=0;r_length<=0;r_index<=0;
            r_position<=0;r_total<=0;partial<=0;partial_handle<=0;partial_timer<=0;
            r_wait<=1;h5_rx_addr<=0;app_rx_valid<=0;app_rx_type<=0;app_rx_length<=0;
            errors<=0;
        end else begin
            if(app_rx_consume)app_rx_valid<=0;
            if(!connected)partial<=0;
            else if(partial)begin
                if(partial_timer>=TIMEOUT-1)begin partial<=0;errors<=errors+1'b1;end
                else partial_timer<=partial_timer+1'b1;
            end
            case(r_state)
                R_IDLE: if(h5_rx_valid && (!app_rx_valid || app_rx_consume))begin
                    if(h5_rx_length==0 || h5_rx_length>MAX_PACKET)drop_rx();
                    else begin
                        r_type<=h5_rx_type;r_length<=h5_rx_length;r_index<=0;
                        h5_rx_addr<=0;r_wait<=1;
                        if(h5_rx_type==2)begin
                            if(h5_rx_length<4)drop_rx();else r_state<=R_HEAD;
                        end else begin r_state<=R_EVENT;end
                    end
                end
                R_HEAD: if(r_wait)r_wait<=0;else begin
                    r_wait<=1;r_head[r_index[2:0]]<=h5_rx_data;
                    if(r_index==3)begin
                        if({h5_rx_data,r_head[2]}!=r_length-4 || r_head[1][7:6]!=0 ||
                            !connected || {r_head[1][3:0],r_head[0]}!=connection_handle)drop_rx();
                        else if(r_head[1][5:4]==1)begin
                            if(!partial || {r_head[1][3:0],r_head[0]}!=partial_handle ||
                                r_length==4 || r_position+r_length-4>r_total)begin partial<=0;drop_rx();end
                            else begin
                                r_index<=4;h5_rx_addr<=4;r_state<=R_COPY;partial_timer<=0;
                            end
                        end else if(r_head[1][5:4]==0 || r_head[1][5:4]==2)begin
                            partial<=0;
                            if(r_length<8)drop_rx();
                            else begin r_index<=4;h5_rx_addr<=4;r_state<=R_L2;end
                        end else drop_rx();
                    end else begin r_index<=r_index+1'b1;h5_rx_addr<=h5_rx_addr+1'b1;end
                end
                R_L2: if(r_wait)r_wait<=0;else begin
                    r_wait<=1;r_head[r_index[2:0]]<=h5_rx_data;
                    if(r_index==7)begin
                        if({r_head[5],r_head[4]}>MAX_PACKET-8 ||
                            r_length>{r_head[5],r_head[4]}+8)drop_rx();
                        else begin
                            r_total<={r_head[5],r_head[4]}+8;
                            partial_handle<={r_head[1][3:0],r_head[0]};
                            r_position<=8;r_index<=0;r_state<=R_PREFIX;
                        end
                    end else begin r_index<=r_index+1'b1;h5_rx_addr<=h5_rx_addr+1'b1;end
                end
                R_PREFIX: if(r_index==7)begin
                    if(r_length==8)begin
                        if(r_total==8)begin app_rx_valid<=1;app_rx_type<=2;app_rx_length<=8;partial<=0;end
                        else begin partial<=1;partial_timer<=0;end
                        h5_rx_consume<=1;r_state<=R_DROP;
                    end else begin r_index<=8;h5_rx_addr<=8;r_wait<=1;r_state<=R_COPY;end
                end else r_index<=r_index+1'b1;
                R_COPY: if(r_wait)r_wait<=0;else begin
                    r_wait<=1;r_position<=r_position+1'b1;
                    if(r_index+1==r_length)finish_acl();
                    else begin r_index<=r_index+1'b1;h5_rx_addr<=h5_rx_addr+1'b1;end
                end
                R_EVENT: if(r_wait)r_wait<=0;else begin
                    r_wait<=1;
                    if(r_index+1==r_length)begin
                        app_rx_valid<=1;app_rx_type<=r_type;app_rx_length<=r_length;
                        h5_rx_consume<=1;r_state<=R_DROP;
                    end else begin r_index<=r_index+1'b1;h5_rx_addr<=h5_rx_addr+1'b1;end
                end
                R_DROP: if(!h5_rx_valid)r_state<=R_IDLE;
                default:r_state<=R_IDLE;
            endcase
        end
    end
endmodule
