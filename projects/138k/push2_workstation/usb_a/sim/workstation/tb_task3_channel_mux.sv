`timescale 1ns/1ps
module task3_channel_mux_case #(
    parameter integer CH=8, W=256, D=4,
    parameter integer CB=(CH>1)?$clog2(CH):1,
    parameter integer ID=0
) (output reg done=0);
    reg clk=0;
    always #5 clk=~clk;
    reg reset_n=0,flush=0,link_ready=1,link_down=0,panic=0;
    reg [CH-1:0] iv=0;
    wire [CH-1:0] ir,full,overflow;
    reg [CH*W-1:0] data_in=0;
    wire ov;
    reg ordy=0;
    wire [CB-1:0] och;
    wire [W-1:0] data_out;
    wire [CH*3-1:0] counts;
    workstation_task3_channel_mux #(.CHANNELS(CH),.WIDTH(W),.DEPTH(D),.COUNTER_WIDTH(3)) dut(
        .clk_i(clk),.reset_ni(reset_n),.flush_i(flush),.link_ready_i(link_ready),
        .link_down_i(link_down),.panic_i(panic),.in_valid_i(iv),.in_ready_o(ir),.in_data_i(data_in),
        .out_valid_o(ov),.out_ready_i(ordy),.out_channel_o(och),.out_data_o(data_out),
        .full_o(full),.overflow_o(overflow),.overflow_count_o(counts));
    reg [W-1:0] expected [0:CH-1][0:D-1];
    integer n[0:CH-1],rp[0:CH-1],wp[0:CH-1],blocked[0:CH-1],seq[0:CH-1];
    integer deliveries[0:CH-1];
    integer accepted=0,delivered=0,steps=0,checks=0,saturated=0;
    reg was_stalled=0;
    reg [CB-1:0] stalled_channel;
    reg [W-1:0] stalled_data;
    reg [31:0] rng=32'h13801380+ID;
    integer i,k,j,total,pop_channel;
    reg active,popped,ready_expected;
    reg [CH-1:0] pushes;

    function automatic [W-1:0] payload(input integer ch,input integer number);
        integer b;
        reg [31:0] bits;
        begin
            bits=32'h9e3779b9 ^ (32'(ch)*32'h3c6ef372) ^ 32'(number);
            for(b=0;b<W;b=b+1) begin
                bits={bits[30:0],bits[31]^bits[21]^bits[1]^bits[0]};
                payload[b]=bits[0];
            end
        end
    endfunction

    task automatic require(input reg condition,input string message);
        begin
            checks=checks+1;
            if(!condition)$fatal(1,"mux case%0d CH%0d D%0d step%0d: %s",ID,CH,D,steps,message);
        end
    endtask

    task automatic step(input reg [CH-1:0] mask,input reg ready,
                        input reg f,input reg down,input reg p,input reg connected);
        begin
            @(negedge clk);
            iv=mask;ordy=ready;flush=f;link_down=down;panic=p;link_ready=connected;
            for(j=0;j<CH;j=j+1)data_in[j*W +: W]=payload(j,seq[j]);
            @(posedge clk);
            steps=steps+1;
            active=reset_n&&!f&&!down&&!p&&connected;
            total=0;for(j=0;j<CH;j=j+1)total=total+n[j];
            require(ov==(active&&total!=0),"out valid/empty qualification");
            if(was_stalled&&active)begin
                require(ov,"backpressured output remains valid");
                require(och==stalled_channel&&data_out==stalled_data,"stable stalled payload/channel");
            end
            if(ov)begin
                require(integer'(och)<CH,"valid channel range");
                require(n[och]>0,"no empty channel delivery");
                require(data_out===expected[och][rp[och]],"per-channel ordering/full payload");
            end
            popped=ov&&ready;
            pop_channel=integer'(och);
            pushes=0;
            for(j=0;j<CH;j=j+1)begin
                ready_expected=active&&(n[j]<D||(popped&&pop_channel==j));
                require(ir[j]==ready_expected,"independent capacity/replace ready");
                require(full[j]==(active&&n[j]==D),"full status");
                require(overflow[j]==(active&&mask[j]&&!ready_expected),"full offered-cycle report");
                pushes[j]=mask[j]&&ir[j];
                if(overflow[j]&&blocked[j]<7)blocked[j]=blocked[j]+1;
            end
            was_stalled=ov&&!ready;
            stalled_channel=och;stalled_data=data_out;
            if(!active)begin
                was_stalled=0;
                for(j=0;j<CH;j=j+1)begin n[j]=0;rp[j]=0;wp[j]=0;end
            end else begin
                if(popped)begin
                    rp[pop_channel]=(rp[pop_channel]+1)%D;
                    n[pop_channel]=n[pop_channel]-1;
                    delivered=delivered+1;
                    deliveries[pop_channel]=deliveries[pop_channel]+1;
                end
                for(j=0;j<CH;j=j+1)if(pushes[j])begin
                    expected[j][wp[j]]=data_in[j*W +: W];
                    wp[j]=(wp[j]+1)%D;n[j]=n[j]+1;
                    accepted=accepted+1;
                end
            end
            for(j=0;j<CH;j=j+1)seq[j]=seq[j]+1;
            #1;
            for(j=0;j<CH;j=j+1)require(counts[j*3 +: 3]==3'(blocked[j]),"saturating full-offer diagnostics");
        end
    endtask

    initial begin
        for(i=0;i<CH;i=i+1)begin
            n[i]=0;rp[i]=0;wp[i]=0;blocked[i]=0;seq[i]=0;deliveries[i]=0;
        end
        repeat(3)@(negedge clk);reset_n=1;
        // First offer a late channel, then insert earlier contenders under
        // backpressure: an unlocked combinational priority mux would change it.
        step(CH'(1)<<(CH-1),0,0,0,0,1);
        step(0,0,0,0,0,1);
        step(CH'(1),0,0,0,0,1);
        repeat(D+12)step({CH{1'b1}},0,0,0,0,1);
        for(i=0;i<CH;i=i+1)require(blocked[i]==7,"full pressure counter saturates");
        // Full queues all remain nonempty. Every accepted output must advance
        // to the next channel, including non-power-of-two channel geometries.
        k=CH-1;
        repeat(CH*20)begin
            step({CH{1'b1}},1,0,0,0,1);
            require(integer'(stalled_channel)==k,"round robin bounded fairness");
            k=(k+1)%CH;
        end
        step({CH{1'b1}},1,1,0,0,1);
        step(0,1,0,0,0,1);
        // A fence cancels even the held output immediately; no old item is
        // allowed through on reconnect or after PANIC deassertion.
        for(i=0;i<3;i=i+1)begin
            step({CH{1'b1}},0,0,0,0,1);
            step(0,0,0,0,0,1);
            step({CH{1'b1}},1,0,i==0,i==1,i!=2);
            step(0,1,0,0,0,1);
        end
        for(i=0;i<3000;i=i+1)begin
            rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
            step(CH'(rng),rng[16]||rng[17],i%193==0,i%257==0,i%307==0,i%211!=0);
        end
        repeat(CH*D+3)step(0,1,0,0,0,1);
        require(!ov,"final drain empty");
        $display("PASS task3_channel_mux case=%0d channels=%0d depth=%0d width=%0d steps=%0d checks=%0d accepted=%0d delivered=%0d",ID,CH,D,W,steps,checks,accepted,delivered);
        done=1;
    end
endmodule

module tb_task3_channel_mux;
    wire a,b,c;
    task3_channel_mux_case #(.ID(0)) main_case(a);
    task3_channel_mux_case #(.CH(3),.W(37),.D(3),.ID(1)) nonpower_case(b);
    task3_channel_mux_case #(.CH(1),.W(8),.D(1),.ID(2)) singleton_case(c);
    initial begin wait(a&&b&&c);$display("PASS all task3_channel_mux geometries");$finish;end
    initial begin #1000000;$fatal(1,"task3 mux timeout");end
endmodule
