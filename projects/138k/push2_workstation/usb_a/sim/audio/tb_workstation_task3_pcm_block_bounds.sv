`timescale 1ns/1ps
module tb_workstation_task3_pcm_block_bounds;
    reg clk=0;always #5 clk=~clk;
    reg reset_n=0,live=1,start=0,cancel=0,flush=0;
    reg [31:0] token=1,first_index=0;
    reg fv=0;wire fr;reg [31:0] fi=0,fp=0;
    reg use_direct=0,iv=0;reg [255:0] ip=0;reg [5:0] il=0;
    wire tv;reg tr=1;wire [255:0] tp;wire [5:0] tl;
    reg sink_ready=1,credit_allow=1;
    wire ofv;wire [31:0] ofi,ofp;
    wire cv;wire [31:0] ct,cl;
    reg inject_credit=0,inject_credit_valid=0;
    reg [31:0] inject_credit_token=0,inject_credit_limit=0;
    wire tx_empty,tx_active,tx_fault,rx_empty,rx_active,rx_fault;
    wire [31:0] sent,accepted,delivered;
    integer checks=0,received=0;reg inspect_pcm=0;
    wire rx_input_valid=use_direct?iv:(tv && tr);
    workstation_task3_pcm_block_tx #(.PARTIAL_TIMEOUT_CYCLES(30)) tx(
        .clk_i(clk),.reset_ni(reset_n),.live_i(live),.start_i(start),.cancel_i(cancel),.flush_i(flush),.token_i(token),.first_index_i(first_index),
        .frame_valid_i(fv),.frame_ready_o(fr),.frame_index_i(fi),.frame_pcm_i(fp),
        .credit_valid_i(inject_credit?inject_credit_valid:(cv && credit_allow)),.credit_token_i(inject_credit?inject_credit_token:ct),.credit_limit_i(inject_credit?inject_credit_limit:cl),
        .block_valid_o(tv),.block_ready_i(tr),.block_payload_o(tp),.block_length_o(tl),.empty_o(tx_empty),.active_o(tx_active),.fault_o(tx_fault),.sent_blocks_o(sent));
    workstation_task3_pcm_block_rx rx(
        .clk_i(clk),.reset_ni(reset_n),.live_i(live),.start_i(start),.cancel_i(cancel),.token_i(token),.first_index_i(first_index),
        .block_valid_i(rx_input_valid),.block_payload_i(use_direct?ip:tp),.block_length_i(use_direct?il:tl),
        .frame_valid_o(ofv),.frame_ready_i(sink_ready),.frame_index_o(ofi),.frame_pcm_o(ofp),
        .credit_valid_o(cv),.credit_ready_i(credit_allow),.credit_token_o(ct),.credit_limit_o(cl),.empty_o(rx_empty),.active_o(rx_active),.fault_o(rx_fault),
        .accepted_blocks_o(accepted),.delivered_frames_o(delivered));
    task tick(input integer n);begin repeat(n)@(negedge clk);end endtask
    task check(input bit ok,input [511:0] message);begin checks=checks+1;if(!ok)$fatal(1,"%s at %0t",message,$time);end endtask
    task context_start;begin
        cancel=1;fv=0;iv=0;inject_credit_valid=0;tick(1);cancel=0;token=token+1;start=1;tick(1);start=0;tick(3);
        check(tx_active && rx_active && !tx_fault && !rx_fault,"fresh context initializes finite media queues");
    end endtask
    task sample(input [31:0] index);integer n;begin
        fi=index;fp=32'h5a000000+index;fv=1;n=0;#1;while(!fr && n<100)begin tick(1);n=n+1;end
        if(!fr)$display("SAMPLE STALL index=%0d active=%b fault=%b count=%0d sealed=%b expected=%0d granted=%0d sent=%0d",index,tx_active,tx_fault,tx.count,tx.sealed,tx.expected_index,tx.granted,sent);
        check(fr,"bounded packer accepts ordered sample");tick(1);fv=0;
    end endtask
    task direct_packet(input [5:0] len,input [31:0] tok,input [31:0] index,input bit padding);begin
        use_direct=1;il=len;ip=0;ip[31:0]=tok;ip[63:32]=index;ip[95:64]=32'h12345678;
        if(padding)ip[255:248]=8'hc3;iv=1;tick(1);iv=0;tick(1);
    end endtask
    task rejected_shape(input [5:0] len,input integer which);begin
        context_start;
        case(which)
            0:direct_packet(len,token,0,0);
            1:direct_packet(len,token+1,0,0);
            2:direct_packet(len,token,1,0);
            3:direct_packet(len,token,0,1);
        endcase
        check(rx_fault && !rx_active && !ofv && rx_empty,"invalid block consumed and stream fails without output");
    end endtask
    always @(posedge clk)if(reset_n && inspect_pcm && ofv && sink_ready)begin
        check(ofi==received,"decoded indices exact");check(ofp==32'h5a000000+received,"decoded PCM exact");received=received+1;
    end
    integer i;reg [31:0] held_limit;reg [255:0] held_payload;
    initial begin
        tick(3);reset_n=1;context_start;inspect_pcm=1;
        for(i=0;i<17;i=i+1)sample(i);
        flush=1;tick(20);flush=0;
        check(received==17 && sent==3 && accepted==3 && rx_empty && tx_empty,"full and partial blocks preserve exact stream");inspect_pcm=0;
        // Credit duplicate/retreat is idempotent.
        context_start;inject_credit=1;inject_credit_token=token;inject_credit_valid=1;inject_credit_limit=8;tick(1);
        inject_credit_limit=4;tick(1);check(tx.granted==8 && !tx_fault,"lower credit cannot revoke or mint grants");
        inject_credit_limit=8;tick(1);check(tx.granted==8 && !tx_fault,"duplicate credit remains idempotent");inject_credit_valid=0;
        // Invalid credit cannot concurrently accept a sample.
        fi=0;fp=1;fv=1;inject_credit_limit=9;inject_credit_valid=1;#1;check(!fr,"bad credit fences concurrent sample acceptance");tick(1);fv=0;inject_credit_valid=0;
        check(tx_fault && !tx_active && tx_empty && sent==0,"bad credit fails with no concurrent sample update");
        inject_credit=0;context_start;tr=0;for(i=0;i<6;i=i+1)sample(i);tick(2);
        check(tv,"complete block waits under backpressure");held_payload=tp;tick(3);check(tp==held_payload,"held block payload stable");
        inject_credit=1;inject_credit_valid=1;inject_credit_token=token;inject_credit_limit=9;tr=1;#1;
        check(!tv,"bad credit fences concurrent block delivery");tick(1);inject_credit_valid=0;inject_credit=0;
        check(sent==0 && tx_fault && tx_empty,"bad credit cannot pop a sealed block");
        context_start;fi=1;fv=1;#1;check(!fr,"noncontiguous index fences current acceptance");tick(1);fv=0;check(tx_fault && tx_empty,"TX index discontinuity fails branch");
        // Exact wire grammar and token/index fencing.
        rejected_shape(0,0);rejected_shape(8,0);rejected_shape(13,0);rejected_shape(36,0);
        rejected_shape(12,1);rejected_shape(12,2);rejected_shape(12,3);
        first_index=32'hfffffffe;context_start;direct_packet(32,token,first_index,0);check(rx_fault,"frame index addition cannot wrap");first_index=0;
        // No receiver reservation is inferred from a pending/unaccepted grant.
        credit_allow=0;context_start;direct_packet(12,token,0,0);check(rx_fault,"sender before credit receipt fails explicitly");credit_allow=1;
        // A malformed input revokes a pending grant on the SAME edge.
        credit_allow=0;context_start;use_direct=1;iv=1;il=13;ip=0;ip[31:0]=token;credit_allow=1;#1;
        check(!cv,"malformed input fences concurrent pending credit handshake");tick(1);iv=0;
        check(rx_fault && rx.published_limit==0,"fault edge cannot publish a new reservation");
        // Wrong-token credits cannot revive or extend this context.
        context_start;inject_credit=1;inject_credit_valid=1;inject_credit_token=token-1;inject_credit_limit=32'hffffffff;tick(1);
        check(!tx_fault && tx.granted==8,"stale credit from retired token ignored");inject_credit_valid=0;inject_credit=0;
        // Slot credits count entire blocks, including one-frame tails.
        sink_ready=0;context_start;
        for(i=0;i<8;i=i+1)direct_packet(12,token,i,0);
        check(accepted==8 && rx.count==8 && !rx_fault,"all eight reserved block slots usable");
        direct_packet(12,token,8,0);check(rx_fault && rx_empty,"ninth block without returned credit fails and releases queue");
        // Duplicate first index is an error even if packet framing is fresh.
        context_start;direct_packet(12,token,0,0);direct_packet(12,token,0,0);check(rx_fault,"duplicate block index cannot replay PCM");
        // A held credit snapshot remains stable while more slots are returned.
        context_start;for(i=0;i<6;i=i+1)direct_packet(12,token,i,0);
        credit_allow=0;sink_ready=1;tick(6);check(cv,"return-credit snapshot becomes pending");held_limit=cl;tick(10);
        check(cv && cl==held_limit,"held credit limit does not drift with further consumption");credit_allow=1;tick(3);
        // Same-cycle malformed input must suppress an otherwise ready old frame.
        sink_ready=0;context_start;direct_packet(12,token,0,0);sink_ready=1;
        use_direct=1;iv=1;il=13;ip=0;ip[31:0]=token;ip[63:32]=1;#1;check(!ofv,"malformed input fences concurrent queue pop");tick(1);iv=0;
        check(rx_fault && delivered==0,"malformed edge cannot deliver queued PCM");
        context_start;cancel=1;direct_packet(12,token,0,0);check(!rx_active && !tx_active && rx_empty && tx_empty,"cancel wins packet/partial handshake and clears grants");cancel=0;
        context_start;live=0;tick(1);check(!rx_active && !tx_active && !cv && !tv,"link loss clears contexts and held grants");
        $display("PASS task3 PCM block bounds checks=%0d exact_frames=%0d",checks,received);$finish;
    end
    initial begin #200000;$fatal(1,"block bounds watchdog");end
endmodule
