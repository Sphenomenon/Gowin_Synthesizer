`timescale 1ns/1ps
module tb_workstation_task3_phone_batch_m;
    reg clk=0,compute_clk=0;
    always #10 clk=~clk;
    always #6.510417 compute_clk=~compute_clk;
    reg reset_n=0,live=0,cancel=0,observer_reset=0,allow_owner=1;
    reg [31:0] token=1,controller=44,generation=55,physical=7;
    reg rate44100=0;
    reg packet_valid=0,reply_ready=0;
    reg [255:0] packet=0;
    reg [5:0] packet_length=30;
    wire packet_ready,reply_valid,busy,fault;
    wire [255:0] reply;
    wire [5:0] reply_length;
    wire bv,bw,br,be;
    wire [11:0] ba;
    wire [31:0] bd,breal;
    wire [3:0] bs;
    reg direct=0,dv=0,dw=0;
    reg [11:0] da=0;
    reg [31:0] dd=0;
    reg [3:0] ds=15;
    wire cv,cw,cr,ce,compute_ready;
    wire [11:0] ca;
    wire [31:0] cd,cresponse;
    wire [3:0] cs;
    wire selected,failed,idle,history,serial_hold,hard_fault;
    wire signed [31:0] left,right;
    wire [21:0] cancel_epoch;
    reg history_enable=0;
    reg [1:0] history_done=0;
    integer phase=0,ticks_audio=0,checks=0,reads=0,writes=0,compared=0;
    wire take=phase==1599;
    always @(posedge compute_clk)begin
        if(!reset_n)begin phase<=0;history_done<=0;end
        else begin
            phase<=take ? 0:phase+1;
            history_done<={history_done[0],owner.history_state==2 && history_enable};
            if(take)ticks_audio<=ticks_audio+1;
        end
    end
    integer inject=0;
    reg [31:0] filtered_response;
    always @*begin
        filtered_response=breal;
        case(inject)
            1:if(ba==12'h000)filtered_response=0;
            2:if(ba==12'h004)filtered_response=0;
            3:if(ba==12'h008)filtered_response=32'h6b;
            4:if(ba==12'h044 && batch.operation==13)filtered_response=breal+1'b1;
            5:if(ba==12'h090)filtered_response=0;
            6:if(ba==12'h144 && batch.operation==15)filtered_response=0;
            7:if(ba==12'h148)filtered_response=1;
            8:if(ba==12'h144 && batch.operation==17)filtered_response=breal+1'b1;
            9:if(ba==12'h044 && batch.operation==3)filtered_response=32'hffffffff;
            10:if(ba==12'h144 && batch.operation==15)filtered_response=1;
            default:begin end
        endcase
    end
    workstation_task3_phone_batch_m #(.TIMEOUT_CYCLES(2500)) batch(
        .clk_i(clk),.reset_ni(reset_n),.live_i(live),.cancel_i(cancel),.token_i(token),
        .packet_valid_i(packet_valid),.packet_ready_o(packet_ready),.packet_payload_i(packet),.packet_length_i(packet_length),
        .reply_valid_o(reply_valid),.reply_ready_i(reply_ready),.reply_payload_o(reply),.reply_length_o(reply_length),
        .command_valid_o(bv),.command_write_o(bw),.command_address_o(ba),.command_data_o(bd),.command_strobes_o(bs),
        .command_ready_i(direct ? 1'b0:br),.command_response_data_i(filtered_response),.command_response_error_i(be),.busy_o(busy),.fault_o(fault));
    gw138k_apb_cdc cdc(
        .reset_n(reset_n && !observer_reset),.pclk(clk),.audio_clk(compute_clk),
        .psel(direct ? dv:bv),.penable(direct ? dv:bv),.pwrite(direct ? dw:bw),
        .paddr(direct ? da:ba),.pwdata(direct ? dd:bd),.pstrb(direct ? ds:bs),
        .pready(br),.pslverr(be),.prdata(breal),.command_reset_n(compute_ready),
        .command_valid(cv),.command_ready(cr),.command_write(cw),.command_address(ca),.command_data(cd),.command_strobes(cs),
        .response_data(cresponse),.response_error(ce));
    workstation_ae350_pcm_owner #(.SNAPSHOT_ENABLE(1)) owner(
        .clk_i(compute_clk),.reset_ni(reset_n),.cpu_ready_i(compute_ready && allow_owner),
        .command_valid_i(cv),.command_ready_o(cr),.command_write_i(cw),.command_address_i(ca),.command_data_i(cd),.command_strobes_i(cs),
        .response_data_o(cresponse),.response_error_o(ce),.session_live_i(live),.controller_epoch_i(controller),.transport_generation_i(generation),
        .context_ready_i(1'b1),.rate_44100_i(rate44100),.physical_epoch_i(physical),.tf_busy_i(1'b0),.switch_busy_i(1'b0),
        .sample_take_i(take),.legacy_left_i(32'h12340000),.legacy_right_i(32'hfedc0000),.pcm_left_o(left),.pcm_right_o(right),
        .history_clear_o(history),.history_ready_i(1'b1),.history_done_i(history_done[1]),.serial_hold_o(serial_hold),
        .cancel_epoch_o(cancel_epoch),.selected_o(selected),.failed_o(failed),.hard_fault_o(hard_fault),.idle_o(idle));
    wire [31:0] disabled_response,reference_response;
    wire disabled_error,reference_error;
    wire [92:0] disabled_outputs,reference_outputs;
    workstation_ae350_pcm_owner disabled(
        .clk_i(compute_clk),.reset_ni(reset_n),.cpu_ready_i(compute_ready && allow_owner),
        .command_valid_i(cv),.command_ready_o(disabled_outputs[88]),.command_write_i(cw),.command_address_i(ca),.command_data_i(cd),.command_strobes_i(cs),
        .response_data_o(disabled_response),.response_error_o(disabled_error),.session_live_i(live),.controller_epoch_i(controller),.transport_generation_i(generation),
        .context_ready_i(1'b1),.rate_44100_i(rate44100),.physical_epoch_i(physical),.tf_busy_i(1'b0),.switch_busy_i(1'b0),
        .sample_take_i(take),.legacy_left_i(32'h12340000),.legacy_right_i(32'hfedc0000),.pcm_left_o(disabled_outputs[31:0]),.pcm_right_o(disabled_outputs[63:32]),
        .history_clear_o(disabled_outputs[64]),.history_ready_i(1'b1),.history_done_i(history_done[1]),.serial_hold_o(disabled_outputs[65]),
        .cancel_epoch_o(disabled_outputs[87:66]),.selected_o(disabled_outputs[89]),.failed_o(disabled_outputs[90]),.hard_fault_o(disabled_outputs[91]),.idle_o(disabled_outputs[92]));
    workstation_ae350_pcm_owner_default_reference reference_owner(
        .clk_i(compute_clk),.reset_ni(reset_n),.cpu_ready_i(compute_ready && allow_owner),
        .command_valid_i(cv),.command_ready_o(reference_outputs[88]),.command_write_i(cw),.command_address_i(ca),.command_data_i(cd),.command_strobes_i(cs),
        .response_data_o(reference_response),.response_error_o(reference_error),.session_live_i(live),.controller_epoch_i(controller),.transport_generation_i(generation),
        .context_ready_i(1'b1),.rate_44100_i(rate44100),.physical_epoch_i(physical),.tf_busy_i(1'b0),.switch_busy_i(1'b0),
        .sample_take_i(take),.legacy_left_i(32'h12340000),.legacy_right_i(32'hfedc0000),.pcm_left_o(reference_outputs[31:0]),.pcm_right_o(reference_outputs[63:32]),
        .history_clear_o(reference_outputs[64]),.history_ready_i(1'b1),.history_done_i(history_done[1]),.serial_hold_o(reference_outputs[65]),
        .cancel_epoch_o(reference_outputs[87:66]),.selected_o(reference_outputs[89]),.failed_o(reference_outputs[90]),.hard_fault_o(reference_outputs[91]),.idle_o(reference_outputs[92]));
    integer k;
    always @(negedge compute_clk)if(reset_n)begin
        compared=compared+1;
        if({disabled_response,disabled_error,disabled_outputs}!=={reference_response,reference_error,reference_outputs})
            $fatal(1,"disabled feature changed original cycle behavior");
        if({owner.owned,owner.queued,owner.expected_sequence,owner.command_id,owner.applied_id,left,right,cancel_epoch,history,serial_hold,selected,failed,hard_fault,idle} !==
           {disabled.owned,disabled.queued,disabled.expected_sequence,disabled.command_id,disabled.applied_id,disabled_outputs[31:0],disabled_outputs[63:32],disabled_outputs[87:66],disabled_outputs[64],disabled_outputs[65],disabled_outputs[89],disabled_outputs[90],disabled_outputs[91],disabled_outputs[92]})
            $fatal(1,"read-only snapshot changed owner behavior");
        for(k=0;k<4;k=k+1)if(owner.written[k]!==disabled.written[k])$fatal(1,"snapshot changed bitmap");
    end
    always @(posedge compute_clk)if(reset_n && cv && cr)begin
        if(cw)writes=writes+1;else reads=reads+1;
    end
    task check(input bit ok,input [511:0] message);begin checks=checks+1;if(!ok)$fatal(1,"%s at %0t",message,$time);end endtask
    task tick(input integer n);begin repeat(n)@(negedge clk);end endtask
    task restart;begin
        reset_n=0;live=0;cancel=0;observer_reset=0;direct=0;dv=0;allow_owner=1;inject=0;
        token=1;controller=44;generation=55;physical=7;rate44100=0;packet_valid=0;reply_ready=0;history_enable=0;
        tick(5);reset_n=1;tick(10);live=1;tick(10);
    end endtask
    function automatic [255:0] request(input [31:0] seq,input [2:0] op,input [1:0] sl,input [7:0] count,input [31:0] blockseq);
        request={18'd0,count,sl,1'b0,op,blockseq,32'd7,32'd1,32'd55,32'd44,seq,32'd1};
    endfunction
    reg [255:0] answer;
    task start(input [255:0] payload,input [5:0] length);integer timeout;begin
        timeout=0;while(!packet_ready && timeout<1000)begin tick(1);timeout=timeout+1;end
        check(packet_ready,"batch accepts one request");
        packet=payload;packet_length=length;packet_valid=1;tick(1);packet_valid=0;
    end endtask
    task finish(input bit error_expected);integer timeout;reg [255:0] held;begin
        timeout=0;while(!reply_valid && timeout<6000)begin tick(1);timeout=timeout+1;end
        check(reply_valid,"batch returns bounded real completion");
        check(reply_length==32 && reply[31:0]==1,"reply shape and token");
        check(reply[252]==error_expected,"owner/protocol error is explicit");
        check(reply[253]==!error_expected,"snapshot validity distinguishes errors");
        held=reply;tick(5);check(reply===held && !packet_ready,"one reply held atomically under backpressure");
        answer=reply;reply_ready=1;tick(1);reply_ready=0;tick(3);
    end endtask
    task transact(input [31:0] seq,input [2:0] op,input [1:0] sl,input [7:0] count,input [31:0] blockseq,input bit err);begin
        start(request(seq,op,sl,count,blockseq),30);finish(err);
        check(answer[63:32]==seq,"exact request sequence returned");
    end endtask
    reg [31:0] direct_result;
    task bus(input bit write,input [11:0] address,input [31:0] data,input bit error_expected);integer timeout;begin
        check(!busy,"direct fixture access cannot overlap executor");
        direct=1;dw=write;da=address;dd=data;ds=15;tick(1);dv=1;
        timeout=0;while(!br && timeout<500)begin tick(1);timeout=timeout+1;end
        check(br && be==error_expected,"real asynchronous APB completion");
        direct_result=breal;tick(1);dv=0;tick(5);direct=0;tick(2);
    end endtask
    task fill(input integer slotno);integer i;begin
        for(i=0;i<128;i=i+1)bus(1,12'('h800+slotno*512+i*4),32'he8901f40,0);
    end endtask
    integer before_writes,before_reads,n,prior_ticks;
    reg [31:0] old_id,frozen[0:19];
    reg [255:0] malformed;
    initial begin
        restart();before_reads=reads;
        transact(0,0,0,0,0,0);
        check(reads-before_reads==26 && !answer[255],"SNAP probes real ID/version/CAPS; production sustained false");
        check(answer[250] && !answer[251] && answer[191:160]!=0,"atomic live match and nonzero capture");
        before_writes=writes;transact(1,1,0,0,0,0);
        check(writes-before_writes==6 && answer[95:64]==1 && answer[251] && answer[224],"ARM replays full key and real accepted ID");
        fill(0);before_writes=writes;transact(2,2,0,128,0,0);
        check(writes-before_writes==9 && answer[95:64]==2 && answer[159:128]==1,"COMMIT uses original nine writes and real next block sequence");
        check(answer[245:236]==128 && answer[235:232]==14,"published queue/free reflect real slot ownership");
        fill(1);transact(3,2,1,128,1,0);
        transact(4,3,0,0,0,0);
        check(answer[95:64]==4 && answer[127:96]==0 && answer[228],"accepted SELECT stays distinct from history-applied ID");
        history_enable=1;n=0;while(owner.applied_id!=4 && n<2000)begin tick(1);n=n+1;end
        check(owner.applied_id==4 && selected,"source applies at actual renderer sample");
        transact(5,0,0,0,0,0);check(answer[127:96]==4 && answer[225],"snapshot reports true applied source");
        transact(6,4,0,0,0,0);n=0;while(owner.applied_id!=5 && n<2000)begin tick(1);n=n+1;end
        check(owner.applied_id==5 && !selected,"STOP reaches real history/sample boundary");
        bus(0,12'h090,0,0);bus(0,12'h144,0,0);old_id=direct_result;
        for(n=0;n<20;n=n+1)begin bus(0,12'('h100+n*4),0,0);frozen[n]=direct_result;end
        controller=77;generation=88;physical=9;rate44100=1;tick(5);
        for(n=0;n<20;n=n+1)begin bus(0,12'('h100+n*4),0,0);check(direct_result===frozen[n],"frozen 20-word capture does not tear after context changes");end
        bus(0,12'h090,0,0);bus(0,12'h100,0,0);check(direct_result==77,"new capture observes new live context");
        observer_reset=1;tick(5);observer_reset=0;tick(10);
        bus(0,12'h144,0,1);bus(0,12'h090,0,0);bus(0,12'h144,0,0);
        check(direct_result==old_id+2,"CPU observer reset invalidates snapshot without reusing capture identity");
        force owner.g_snapshot.capture_id=32'hffffffff;
        bus(0,12'h090,0,1);bus(0,12'h100,0,1);release owner.g_snapshot.capture_id;
        for(n=0;n<8;n=n+1)begin
            restart();malformed=request(0,0,0,0,0);
            case(n)
                0:malformed[31:0]=2;
                1:malformed[63:32]=1;
                2:malformed[238]=1;
                3:malformed[226:224]=6;
                4:malformed[237:230]=1;
                5:begin malformed[226:224]=2;malformed[237:230]=0;end
                6:begin malformed[226:224]=2;malformed[237:230]=129;end
                default:begin end
            endcase
            before_reads=reads;start(malformed,n==7 ? 29:30);finish(1);
            check(fault && reads==before_reads && owner.command_id==0,"malformed requests never reach owner");
        end
        restart();transact(0,0,0,0,0,0);before_reads=reads;transact(0,0,0,0,0,1);
        check(fault && reads==before_reads,"duplicate transaction rejected before owner");
        restart();transact(0,1,0,0,0,0);bus(1,12'h800,32'h12345678,0);
        transact(1,2,0,2,0,1);check(owner.failure==5 && owner.expected_sequence==0,"original missing-frame bitmap terminates matching COMMIT");
        restart();transact(0,1,0,0,0,0);bus(1,12'h800,32'h12345678,0);
        transact(1,2,0,1,1,1);check(owner.failure==6 && owner.expected_sequence==0,"original block sequence check still terminates matching bad COMMIT");
        restart();transact(0,1,0,0,0,0);malformed=request(1,2,0,1,0);malformed[159:128]=2;
        start(malformed,30);finish(1);check(owner.armed && !owner.failed && owner.command_id==1,"stale full key cannot publish or cancel another stream");
        restart();transact(0,1,0,0,0,0);transact(1,5,0,0,0,0);
        check(!owner.armed && owner.applied_id==2 && answer[95:64]==2,"full-key idle CANCEL reports actual accepted/applied IDs");
        for(n=1;n<=8;n=n+1)begin
            restart();inject=n;
            transact(0,n==4 ? 3'd1:3'd0,0,0,0,1);
            check(fault,"ID/version/CAPS/progression/capture corruption fails closed");
        end
        restart();inject=9;before_writes=writes;transact(0,1,0,0,0,1);
        check(writes==before_writes,"exhausted real command ID prevents any key/control replay");
        restart();transact(0,0,0,0,0,0);inject=10;transact(1,0,0,0,0,1);
        check(fault,"reused capture identity is rejected");
        restart();force batch.next_sequence=32'hffffffff;
        malformed=request(32'hffffffff,0,0,0,0);before_reads=reads;start(malformed,30);finish(1);
        check(reads==before_reads,"transaction identity cannot wrap");release batch.next_sequence;
        restart();allow_owner=0;prior_ticks=ticks_audio;start(request(0,0,0,0,0),30);finish(1);
        check(fault && ticks_audio>prior_ticks,"owner timeout never stalls physical sample ticks");
        restart();allow_owner=0;start(request(0,0,0,0,0),30);tick(10);cancel=1;tick(1);
        check(!bv,"cancel immediately suppresses command issuance");cancel=0;finish(1);check(fault,"cancel is terminal without replay");
        restart();allow_owner=0;start(request(0,0,0,0,0),30);tick(10);live=0;tick(2);
        check(!bv && !reply_valid && !busy,"link revoke drops old request and reply");
        allow_owner=1;tick(30);check(br,"revoked pending APB can retain COMPLETE until drained/reset");
        live=1;tick(3);before_reads=reads;transact(0,0,0,0,0,1);
        check(fault && reads==before_reads,"old APB completion cannot become a new lease completion");
        live=0;observer_reset=1;tick(5);observer_reset=0;tick(10);live=1;tick(3);
        transact(0,0,0,0,0,0);check(!fault,"new lease starts at sequence zero after observer CDC drain/reset");
        token=2;tick(1);check(fault && !packet_ready && !bv,"token change while live is sticky failure");
        tick(10);check(fault,"token fault cannot reopen before live revoke");
        check(compared>10000,"default owner and read-only snapshot compared across substantial actual cycles");
        $display("PASS phone batch M checks=%0d compared_cycles=%0d owner_reads=%0d owner_writes=%0d audio_ticks=%0d",checks,compared,reads,writes,ticks_audio);
        $finish;
    end
    initial begin #100000000;$fatal(1,"global test timeout");end
endmodule
