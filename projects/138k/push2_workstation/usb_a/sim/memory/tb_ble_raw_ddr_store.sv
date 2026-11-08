`timescale 1ns/1ps
module tb_ble_raw_ddr_store #(parameter integer FIFO_BITS=8,MEM_HALF=7,CAPTURE_COMMAND=0);
    reg clk=0,memory_clk=0,rst_n=0,memory_run=1;
    always #10 clk=~clk;
    always #(MEM_HALF) if(memory_run)memory_clk=~memory_clk;else memory_clk=0;
    localparam [28:0] BASE=29'h0040000;
    reg start=0,clear=0,capture=0,close_req=0,fetch=0;
    reg [31:0] capture_index=0,capture_pcm=0,offset=0,sample_addr=0;
    reg [13:0] length=0;
    wire start_ready,start_done,clear_ready,clear_done,capture_ready,close_ready,drained,fault,object_fault,channel_fault;
    wire [3:0] failure;
    wire [31:0] accepted,committed,sample_word;
    wire fetch_ready,fetch_done,fetch_fault,cache_valid;
    wire slot_valid,slot_ready,native_accept,ddr_write;
    wire [28:0] address;
    wire [255:0] write_data;
    wire [31:0] mask;
    reg read_response=0;
    reg [255:0] read_data=0;
    reg transport_fault=0;
    workstation_ble_raw_ddr_store #(.CAPTURE_COMMAND(CAPTURE_COMMAND),.BASE_APP(BASE),.FIFO_ADDRESS_BITS(FIFO_BITS),.COMMAND_TIMEOUT_CYCLES(2048),.READ_TIMEOUT_CYCLES(2048)) dut(
        .clk_i(clk),.memory_clk_i(memory_clk),.rst_ni(rst_n),
        .start_valid_i(start),.start_ready_o(start_ready),.start_done_o(start_done),
        .clear_valid_i(clear),.clear_ready_o(clear_ready),.clear_done_o(clear_done),
        .capture_valid_i(capture),.capture_index_i(capture_index),.capture_pcm_i(capture_pcm),.capture_ready_o(capture_ready),
        .close_valid_i(close_req),.close_ready_o(close_ready),.drained_o(drained),.fault_o(fault),
        .object_fault_o(object_fault),.channel_fault_o(channel_fault),.failure_code_o(failure),
        .accepted_frames_o(accepted),.committed_frames_o(committed),
        .fetch_valid_i(fetch),.fetch_ready_o(fetch_ready),.fetch_offset_i(offset),.fetch_length_i(length),
        .fetch_done_o(fetch_done),.fetch_fault_o(fetch_fault),.cache_valid_o(cache_valid),
        .sample_addr_i(sample_addr),.sample_word_o(sample_word),
        .slot_valid_o(slot_valid),.slot_ready_i(slot_ready),.native_accept_i(native_accept),
        .ddr_write_o(ddr_write),.ddr_address_o(address),.ddr_data_o(write_data),.ddr_mask_o(mask),
        .read_response_i(read_response),.read_data_i(read_data),.transport_fault_i(transport_fault));

    reg slot_enable=1,native_enable=1,response_enable=1,force_native=0,force_response=0,same_edge_response=0;
    reg model_slot=0,model_read=0,model_write=0;
    reg [28:0] model_address=0,model_read_address=0;
    reg [255:0] model_data=0;
    reg [31:0] model_mask=0;
    integer model_delay=0,read_delay=0,native_latency=2,response_latency=3;
    reg native_pulse=0;
    assign slot_ready=slot_enable && !model_slot && !model_read;
    assign native_accept=native_pulse || force_native;
    reg [255:0] memory[0:2047];
    integer writes=0,reads=0,slots=0,checks=0,start_completions=0,clear_completions=0,fetch_completions=0,fetch_failures=0;
    integer n,b;
    function [31:0] pattern(input integer at);
        pattern=32'h9e370b5a ^ (at*32'h0010203);
    endfunction
    task check(input bit condition,input [511:0] message);
        begin checks=checks+1;if(!condition)$fatal(1,"%0s t=%0t code=%0d a=%0d c=%0d",message,$time,failure,accepted,committed);end
    endtask
    always @(negedge memory_clk)begin
        native_pulse=rst_n && model_slot && model_delay==0 && native_enable;
        read_response=rst_n && ((model_read && read_delay==0 && response_enable) ||
            (same_edge_response && native_pulse && !model_write && response_enable) || force_response);
        if(model_read)read_data=memory[(model_read_address-BASE)>>3];
        else if(same_edge_response && native_pulse && !model_write)read_data=memory[(model_address-BASE)>>3];
        else read_data=256'd0;
    end
    always @(posedge memory_clk or negedge rst_n)begin
        if(!rst_n)begin model_slot<=0;model_read<=0;model_delay<=0;read_delay<=0;writes<=0;reads<=0;slots<=0;end
        else begin
            if(slot_valid && slot_ready)begin
                check(address[2:0]==0 && address>=BASE && address<BASE+16384,"native address authority/alignment");
                model_slot<=1;model_address<=address;model_write<=ddr_write;model_data<=write_data;model_mask<=mask;
                model_delay<=native_latency;slots<=slots+1;
            end
            if(model_slot && !native_accept)begin
                check({ddr_write,address,write_data,mask}==={model_write,model_address,model_data,model_mask},"published fields changed before native acceptance");
                if(model_delay>0)model_delay<=model_delay-1;
            end
            if(native_pulse)begin
`ifdef BLE_STORE_NATIVE_TRACE
                $display("BLE_STORE_NATIVE write=%0d address=%h mask=%h data=%h",model_write,model_address,model_mask,model_data);
`endif
                model_slot<=0;
                if(model_write)begin
                    for(b=0;b<32;b=b+1)if(!model_mask[b])memory[(model_address-BASE)>>3][b*8+:8]<=model_data[b*8+:8];
                    writes<=writes+1;
                end else begin
                    check(!model_read,"at most one read owner");
                    model_read<=1;model_read_address<=model_address;read_delay<=response_latency;reads<=reads+1;
                end
            end
            if(model_read && read_delay>0)read_delay<=read_delay-1;
            if(read_response)model_read<=0;
        end
    end
    always @(posedge clk)if(rst_n)begin
        if(start_done)start_completions=start_completions+1;
        if(clear_done)clear_completions=clear_completions+1;
        if(fetch_done)fetch_completions=fetch_completions+1;
        if(fetch_fault)fetch_failures=fetch_failures+1;
        check(!(cache_valid && (dut.clear_pending || dut.fetch_active || fault)),"cache published during cancel/fetch/fault");
    end

    task reset_all;
        begin
            @(negedge clk);rst_n=0;start=0;clear=0;capture=0;close_req=0;fetch=0;
            slot_enable=1;native_enable=1;response_enable=1;transport_fault=0;force_native=0;force_response=0;memory_run=1;same_edge_response=0;
            repeat(5)@(negedge clk);rst_n=1;
            repeat(20)@(negedge clk);
            check(start_ready && drained && !fault,"common reset/release establishes empty transport");
        end
    endtask
    task begin_capture;
        integer timeout;
        begin
            timeout=0;while(!start_ready && timeout<10000)begin @(negedge clk);timeout=timeout+1;end
            check(start_ready,"start admission");@(negedge clk);start=1;@(negedge clk);start=0;
            check(capture_ready,"start accepts capture before command roundtrip");
        end
    endtask
    task send_frame(input integer at);
        begin @(negedge clk);capture_index=at;capture_pcm=pattern(at);capture=1;@(negedge clk);capture=0;end
    endtask
    task end_capture;
        integer timeout;
        begin
            @(negedge clk);close_req=1;timeout=0;
            while(!close_ready && timeout<10000)begin @(negedge clk);timeout=timeout+1;end
            check(close_ready,"ordered close admission");@(negedge clk);close_req=0;
        end
    endtask
    task wait_drained;
        integer timeout;
        begin timeout=0;while(!drained && !channel_fault && timeout<200000)begin @(negedge clk);timeout=timeout+1;end
            check(drained && !channel_fault,"real transport drain");end
    endtask
    task clear_store;
        integer before_done,timeout;
        begin
            before_done=clear_completions;@(negedge clk);clear=1;check(clear_ready,"clear admission");@(negedge clk);
            timeout=0;while(clear_completions==before_done && timeout<200000)begin @(negedge clk);timeout=timeout+1;end
            check(clear_completions==before_done+1,"clear completes after physical drain");
            repeat(8)@(negedge clk);check(clear_completions==before_done+1,"held clear does not repeat");clear=0;
            @(negedge clk);check(start_ready && !fault && !cache_valid && accepted==0 && committed==0,"clear rearms raw empty only");
        end
    endtask
    task fill_cache(input integer at,input integer bytes_count);
        integer before_done,before_reads,timeout;
        begin
            before_done=fetch_completions;before_reads=reads;@(negedge clk);offset=at;length=bytes_count;fetch=1;
            check(fetch_ready,"fetch admission");@(negedge clk);timeout=0;
            while(fetch_completions==before_done && !fault && timeout<200000)begin @(negedge clk);timeout=timeout+1;end
            check(fetch_completions==before_done+1 && cache_valid && !fault,"complete fetch publishes cache");
            repeat(10)@(negedge clk);check(fetch_completions==before_done+1,"held fetch does not repeat");fetch=0;
            check(reads-before_reads==((at%32+bytes_count+31)/32),"fetch exact complete-beat span");@(negedge clk);
        end
    endtask
    task read_sample(input integer at,input [31:0] expected);
        begin @(negedge clk);sample_addr=at;@(posedge clk);#1;check(sample_word===expected,"cache full-precision one-cycle absolute sample read");end
    endtask
    task request_fetch(input integer at,input integer bytes_count);
        begin @(negedge clk);offset=at;length=bytes_count;fetch=1;check(fetch_ready,"fetch descriptor pulse admission");@(negedge clk);fetch=0;end
    endtask
    task wait_channel_fault;
        integer timeout;
        begin timeout=0;while(!channel_fault && timeout<10000)begin @(negedge clk);timeout=timeout+1;end
            check(channel_fault && fault && !start_ready && !clear_ready && !drained && !cache_valid,"channel quarantine");end
    endtask

    integer saved,saved_reads,tail_len,at;
    initial begin
        for(n=0;n<2048;n=n+1)memory[n]={32{8'hcd}};
        $display("rawstore phase partial/mask/one-cycle cache");
        reset_all;
        saved=start_completions;start=1;repeat(12)@(negedge clk);
        check(start_completions==saved+1 && dut.generation==1,"held start has one generation");start=0;
        for(n=0;n<19;n=n+1)send_frame(n);
        end_capture;wait_drained;check(accepted==19 && committed==19 && writes==3,"native committed prefix including partial");
        for(n=0;n<19;n=n+1)check(memory[n/8][(n%8)*32+:32]===pattern(n),"DDR PCM word order/precision");
        check(memory[2][255:96]=={20{8'hcd}},"last partial byte mask preserves unused data");
        fill_cache(3,67);for(n=0;n<18;n=n+1)read_sample(n,pattern(n));read_sample(18,0);
        clear_store;

        $display("rawstore phase simultaneous START descriptor/new FIFO visibility");
        @(negedge memory_clk);memory_run=0;begin_capture;
        for(n=0;n<3;n=n+1)send_frame(n);
        end_capture;check(accepted==3 && !fault,"capture accepted while memory clock paused after start");
        memory_run=1;wait_drained;check(committed==3 && !fault,"new epoch FIFO may precede START decode");
        $display("rawstore phase native read acceptance/response on same edge");
        same_edge_response=1;fill_cache(0,12);read_sample(0,pattern(0));read_sample(2,pattern(2));
        same_edge_response=0;clear_store;

        // Slot acceptance alone must not publish committed/drained state.
        $display("rawstore phase native acceptance and clear drain");
        begin_capture;native_enable=0;
        for(n=0;n<11;n=n+1)send_frame(n);
        end_capture;repeat(15)@(negedge clk);
        check(model_slot && accepted==11 && committed==0 && !drained,"local slot is not native acceptance");
        saved=clear_completions;clear=1;@(negedge clk);repeat(15)@(negedge clk);
        check(clear_completions==saved && !start_ready && !cache_valid,"clear cannot forget published write");
        native_enable=1;while(clear_completions==saved)@(negedge clk);clear=0;repeat(3)@(negedge clk);
        check(!fault && start_ready,"late write retirement permits real clear");

        $display("rawstore phase all partial masks and burst boundary");
        for(tail_len=1;tail_len<=15;tail_len=tail_len+1)begin
            reset_all;memory[0]={32{8'hcd}};memory[1]={32{8'hcd}};begin_capture;
            for(at=0;at<tail_len;at=at+1)send_frame(at);
            end_capture;wait_drained;
            check(writes==(tail_len+7)/8 && committed==tail_len,"all tail lengths native count");
            for(at=0;at<tail_len;at=at+1)check(memory[at/8][(at%8)*32+:32]===pattern(at),"all tail lengths payload");
            for(at=tail_len;at<((tail_len+7)/8)*8;at=at+1)
                check(memory[at/8][(at%8)*32+:32]===32'hcdcdcdcd,"all tail lengths inactive byte preservation");
        end

        $display("rawstore phase full capacity and max unaligned fetch");
        reset_all;begin_capture;
        for(n=0;n<16384;n=n+1)send_frame(n);
        end_capture;wait_drained;
        check(accepted==16384 && committed==16384 && writes==2048,"full 64KiB capacity");
        fill_cache(31,8112);
        for(n=7;n<2036;n=n+1)read_sample(n,pattern(n));
        read_sample(6,0);read_sample(2036,0);

        // A clear cancels a fetch but retains the outstanding read owner.
        $display("rawstore phase fetch cancellation and late response");
        saved=clear_completions;saved_reads=reads;response_enable=0;request_fetch(0,32);
        while(reads==saved_reads)@(negedge clk);
        clear=1;@(negedge clk);repeat(20)@(negedge clk);
        check(clear_completions==saved && !cache_valid && !start_ready,"cancel fetch retains read until late response");
        response_enable=1;while(clear_completions==saved)@(negedge clk);clear=0;repeat(4)@(negedge clk);
        check(!cache_valid && !fault && start_ready,"old fetch cannot publish cache after clear");
        begin_capture;for(n=0;n<3;n=n+1)send_frame(n);end_capture;wait_drained;fill_cache(0,12);read_sample(2,pattern(2));read_sample(3,0);
        saved=fetch_failures;request_fetch(32'hffffffff,4);repeat(5)@(negedge clk);
        check(fetch_failures==saved+1 && object_fault && !channel_fault && !cache_valid,"descriptor addition/range fault");
        clear_store;

        $display("rawstore phase FIFO overflow and index fault");
        reset_all;begin_capture;native_enable=0;
        for(n=0;n<300;n=n+1)send_frame(n);
        check(object_fault && !channel_fault && failure==1 && accepted<300,"bounded FIFO overflow is observable without backpressure");
        native_enable=1;wait_drained;check(accepted==committed,"overflow drains accepted prefix");clear_store;
        begin_capture;send_frame(0);send_frame(2);wait_drained;
        check(object_fault && !channel_fault && failure==2 && accepted==1 && committed==1,"index gap closes accepted prefix");clear_store;

        $display("rawstore phase capacity overflow never overwrites allocation");
        reset_all;begin_capture;
        for(n=0;n<16384;n=n+1)send_frame(n);
        send_frame(16384);wait_drained;
        check(object_fault && !channel_fault && failure==3 && accepted==16384 && committed==16384 && writes==2048,"capacity overrun closes exact accepted prefix");

        $display("rawstore phase command/read timeout quarantine");
        reset_all;begin_capture;native_enable=0;slot_enable=0;
        for(n=0;n<8;n=n+1)send_frame(n);
        wait_channel_fault;check(failure==5 && dut.published_valid,"command timeout preserves published command");
        native_enable=1;slot_enable=1;repeat(50)@(negedge clk);
        check(channel_fault && !clear_ready && !start_ready,"late native acceptance cannot rearm timed-out channel");

        reset_all;begin_capture;for(n=0;n<8;n=n+1)send_frame(n);end_capture;wait_drained;
        response_enable=0;request_fetch(0,32);
        wait_channel_fault;check(failure==6 && dut.read_outstanding,"read timeout preserves read owner");
        response_enable=1;repeat(60)@(negedge clk);check(channel_fault && !cache_valid && !clear_ready,"late read cannot publish cache/rearm");

        reset_all;transport_fault=1;wait_channel_fault;transport_fault=0;repeat(10)@(negedge clk);
        check(channel_fault,"transport fault sticky after source deassertion");
        reset_all;force_native=1;repeat(3)@(negedge clk);force_native=0;wait_channel_fault;
        reset_all;force_response=1;repeat(3)@(negedge clk);force_response=0;wait_channel_fault;
        $display("rawstore phase held valid on final legal generation");
        // Reach the last generation through real START/CLEAR handshakes. A
        // held request still represents one operation after the counter moves.
        reset_all;force dut.generation=32'hfffffffd;force dut.memory_generation=32'hfffffffd;#1;
        release dut.generation;release dut.memory_generation;
        begin_capture;send_frame(0);end_capture;wait_drained;
        check(dut.generation==32'hfffffffe && dut.memory_generation==32'hfffffffe,
            "penultimate generation completes START");
        saved=clear_completions;@(negedge clk);clear=1;
        while(clear_completions==saved)@(negedge clk);
        repeat(8)@(negedge clk);
        check(clear_completions==saved+1 && dut.generation==32'hffffffff &&
              dut.memory_generation==32'hffffffff && !fault && !start_ready && !clear_ready,
            "held CLEAR at final generation completes once");
        clear=0;repeat(3)@(negedge clk);clear=1;repeat(3)@(negedge clk);
        check(channel_fault && failure==9 && dut.generation==32'hffffffff,
            "new CLEAR after last generation quarantines without wrap");
        reset_all;force dut.generation=32'hfffffffe;force dut.memory_generation=32'hfffffffe;#1;
        release dut.generation;release dut.memory_generation;
        saved=start_completions;start=1;repeat(16)@(negedge clk);
        check(start_completions==saved+1 && dut.generation==32'hffffffff &&
              dut.memory_generation==32'hffffffff && !fault,
            "held START at final generation completes once");
        send_frame(0);end_capture;wait_drained;
        check(accepted==1 && committed==1 && !fault,"last legal START retains its complete capture");
        start=0;repeat(3)@(negedge clk);start=1;repeat(3)@(negedge clk);
        check(channel_fault && failure==9 && dut.generation==32'hffffffff,
            "new START after last generation quarantines without wrap");
        reset_all;force dut.generation=32'hffffffff;start=1;repeat(3)@(negedge clk);
        check(channel_fault && failure==9 && !start_ready && dut.generation==32'hffffffff,"generation exhaustion never wraps");
        release dut.generation;start=0;
        $display("rawstore phase common reset with paused memory clock");
        reset_all;@(negedge memory_clk);memory_run=0;@(negedge clk);rst_n=0;
        repeat(5)@(negedge clk);rst_n=1;repeat(12)@(negedge clk);
        check(!start_ready && !cache_valid,"memory clock must release before start admission");
        memory_run=1;repeat(25)@(negedge clk);check(start_ready && drained && !fault,"common reset releases both domains independently");
        $display("PASS BLE_RAW_DDR_STORE checks=%0d full_frames=16384 max_fetch_bytes=8112",checks);$finish;
    end
    initial begin #100000000;$fatal(1,"raw store watchdog");end
endmodule
