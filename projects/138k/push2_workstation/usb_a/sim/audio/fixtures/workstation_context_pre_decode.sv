    localparam [2:0] CFG_IDLE=0,CFG_SETTLE=1,CFG_DRAIN=2,CFG_ACCEPT=3,CFG_ACK=4;
    reg [2:0] config_state;
    reg pending_rate,compute_rate,compute_context_valid;
    reg [31:0] pending_epoch,compute_epoch;
    // integration_fault is set only in CFG_ACK or an invalid state; neither
    // can return to CFG_ACCEPT. Keep actual service/PCM fault vetoes here
    // without feeding that unreachable integration-fault condition through
    // the service's acceptance/ready path and back into this state register.
    wire config_valid=config_state==CFG_ACCEPT && !service_fault && !pcm_hard_fault;
    always @(posedge compute_clk_i or negedge compute_reset_n)begin
        if(!compute_reset_n)begin
            context_sync<=0;context_ack<=0;config_state<=CFG_IDLE;
            pending_rate<=0;pending_epoch<=0;compute_rate<=0;compute_epoch<=0;
            compute_context_valid<=0;integration_fault<=0;
        end else begin
            context_sync<={context_sync[0],context_toggle};
            case(config_state)
                CFG_IDLE:if(context_sync[1]!=context_ack)config_state<=CFG_SETTLE;
                CFG_SETTLE:begin
                    {pending_rate,pending_epoch}<=context_payload;config_state<=CFG_DRAIN;
                end
                CFG_DRAIN:if(router_quiet && service_quiet && !bridge_busy)config_state<=CFG_ACCEPT;
                CFG_ACCEPT:if(config_ready)config_state<=CFG_ACK;
                CFG_ACK:if(config_applied && !integration_fault)begin
                    if(service_rate!=pending_rate)integration_fault<=1;
                    else begin
                        compute_rate<=pending_rate;compute_epoch<=pending_epoch;compute_context_valid<=1;
                        context_ack<=context_sync[1];config_state<=CFG_IDLE;
                    end
                end
                default:integration_fault<=1;
            endcase
        end
    end

