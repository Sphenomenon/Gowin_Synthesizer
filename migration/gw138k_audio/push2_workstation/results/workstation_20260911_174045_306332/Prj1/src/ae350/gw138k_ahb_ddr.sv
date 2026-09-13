// One outstanding 64-bit AHB transfer -> native 256-bit DDR request.
// CPU 0x10000000..0x107fffff maps to DDR byte 0x01000000..0x017fffff,
// outside the existing 8MiB BIST/display reservation. Native addresses count
// 32-bit DQ words: a 32-byte transfer advances by 8, not by 1 or by 32.
// Both domains share reset assertion. Integration must reset the CPU/bridge
// on DDR loss; the audio clock/reset is independent of this control path.
module gw138k_ahb_ddr (
    input wire reset_n,hclk,memory_clk,
    input wire [31:0] haddr,
    input wire [1:0] htrans,
    input wire [2:0] hsize,
    input wire hwrite,
    input wire [63:0] hwdata,
    output wire [63:0] hrdata,
    output wire hready,hresp,
    output wire req_valid,req_write,
    output wire [28:0] req_address,
    output wire [255:0] req_data,
    output wire [31:0] req_mask,
    input wire req_ready,rsp_valid,
    input wire [255:0] rsp_data
);
    reg [2:0] h_release,m_release;
    always @(posedge hclk or negedge reset_n)
        if(!reset_n) h_release<=0;else h_release<={h_release[1:0],1'b1};
    always @(posedge memory_clk or negedge reset_n)
        if(!reset_n) m_release<=0;else m_release<={m_release[1:0],1'b1};
    wire hreset_n=h_release[2],mreset_n=m_release[2];
    localparam [2:0] IDLE=0,WRITE_DATA=1,ISSUE=2,WAIT_RESPONSE=3,COMPLETE=4,ERROR_FIRST=5,ERROR_LAST=6;
    reg [2:0] state;
    reg [95:0] request_held,request_local;
    reg [63:0] response_held,response_local;
    reg request_toggle,acknowledge_toggle;
    (* ASYNC_REG="TRUE" *) reg req_meta,req_sync,ack_meta,ack_sync;
    reg req_settled,ack_settled;
    reg [7:0] byte_mask;
    reg aligned;
    always @* begin
        aligned=0;byte_mask=0;
        case(hsize)
            0:begin aligned=1;byte_mask=8'h01<<haddr[2:0];end
            1:begin aligned=!haddr[0];byte_mask=8'h03<<haddr[2:0];end
            2:begin aligned=haddr[1:0]==0;byte_mask=8'h0f<<haddr[2:0];end
            3:begin aligned=haddr[2:0]==0;byte_mask=8'hff;end
            default:begin end
        endcase
    end
    assign hready=hreset_n && (state==IDLE || state==COMPLETE || state==ERROR_LAST);
    assign hresp=state==ERROR_FIRST || state==ERROR_LAST;
    assign hrdata=response_local;
    always @(posedge hclk or negedge hreset_n) begin
        if(!hreset_n) begin
            state<=IDLE;request_held<=0;response_local<=0;request_toggle<=0;
            ack_meta<=0;ack_sync<=0;ack_settled<=0;
        end else begin
            ack_meta<=acknowledge_toggle;ack_sync<=ack_meta;ack_settled<=ack_sync;
            case(state)
                IDLE,COMPLETE,ERROR_LAST:begin
                    state<=IDLE;
                    if(htrans[1]) begin
                        if(!aligned || haddr[31:23]!=9'h020) state<=ERROR_FIRST;
                        else begin
                            request_held<={hwrite,haddr[22:0],64'd0,byte_mask};
                            state<=hwrite?WRITE_DATA:ISSUE;
                        end
                    end
                end
                WRITE_DATA:begin request_held[71:8]<=hwdata;state<=ISSUE;end
                ISSUE:begin request_toggle<=!request_toggle;state<=WAIT_RESPONSE;end
                WAIT_RESPONSE:if(ack_settled==request_toggle) begin
                    response_local<=response_held;state<=COMPLETE;
                end
                ERROR_FIRST:state<=ERROR_LAST;
                default:state<=IDLE;
            endcase
        end
    end
    localparam [1:0] M_IDLE=0,M_REQUEST=1,M_RESPONSE=2;
    reg [1:0] memory_state;
    wire [22:0] byte_address=request_local[94:72];
    assign req_valid=mreset_n && memory_state==M_REQUEST;
    assign req_write=request_local[95];
    assign req_address=29'd4194304+{8'd0,byte_address[22:5],3'b000};
    // CPU data already uses the selected byte lanes in its 64-bit word.
    assign req_data={4{request_local[71:8]}};
    assign req_mask=~({24'd0,request_local[7:0]}<<{byte_address[4:3],3'b000});
    always @(posedge memory_clk or negedge mreset_n) begin
        if(!mreset_n) begin
            req_meta<=0;req_sync<=0;req_settled<=0;request_local<=0;
            acknowledge_toggle<=0;response_held<=0;memory_state<=M_IDLE;
        end else begin
            req_meta<=request_toggle;req_sync<=req_meta;req_settled<=req_sync;
            case(memory_state)
                M_IDLE:if(req_settled!=acknowledge_toggle) begin
                    request_local<=request_held;memory_state<=M_REQUEST;
                end
                M_REQUEST:if(req_ready) begin
                    if(req_write) begin
                        response_held<=0;acknowledge_toggle<=req_settled;memory_state<=M_IDLE;
                    end else memory_state<=M_RESPONSE;
                end
                M_RESPONSE:if(rsp_valid) begin
                    case(byte_address[4:3])
                        0:response_held<=rsp_data[63:0];
                        1:response_held<=rsp_data[127:64];
                        2:response_held<=rsp_data[191:128];
                        3:response_held<=rsp_data[255:192];
                    endcase
                    acknowledge_toggle<=req_settled;memory_state<=M_IDLE;
                end
                default:memory_state<=M_IDLE;
            endcase
        end
    end
endmodule
