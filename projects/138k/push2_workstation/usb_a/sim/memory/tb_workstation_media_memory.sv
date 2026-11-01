`timescale 1ns/1ps
`include "rtl/ddr_address_map.vh"
module tb_workstation_media_memory;
    parameter integer SEED=7;
    parameter integer PHASE=0;
    reg clock50=0,memory_clock=0,memory_run=1;
    always #10 clock50=~clock50;
    initial begin #(PHASE);forever begin #7;if(memory_run)memory_clock=~memory_clock;end end
    reg reset_n=1,memory_reset_n=1,calibrated=1,pll_locked=1;
    wire client_reset_n,client_ready,fault;
    reg [8:0] valid=0,write_kind=0;
    reg [28:0] address[0:8];
    reg [255:0] data[0:8];
    reg [31:0] mask[0:8];
    wire [8:0] ready,response,slot_accept,core_accept,native_accept;
    wire [2:0] app_cmd;
    wire app_en,app_wren,app_wend;
    wire [28:0] app_address;
    wire [255:0] app_data,response_data;
    wire [31:0] app_mask;
    wire [7:0] flags;
    reg app_ready=1,app_write_ready=1,app_response=0;
    reg [255:0] app_response_data=0;
    reg stress=0,pause_returns=0,inject_return=0,corrupt_bist=0;
    integer stall_mode=0;
    workstation_media_memory #(.BIST_BURSTS(4),.TAG_BITS(3)) dut(
        .reset_ni(reset_n),.clk_50m_i(clock50),.memory_clk_i(memory_clock),
        .memory_reset_ni(memory_reset_n),.memory_calibrated_i(calibrated),.memory_pll_locked_i(pll_locked),
        .client_reset_no(client_reset_n),.client_ready_o(client_ready),
        .music_valid_i(valid[5]),.music_write_i(write_kind[5]),.music_address_i(address[5]),
        .music_data_i(data[5]),.music_mask_i(mask[5]),.music_ready_o(ready[5]),.music_response_o(response[5]),
        .delay_valid_i(valid[6]),.delay_write_i(write_kind[6]),.delay_address_i(address[6]),
        .delay_data_i(data[6]),.delay_ready_o(ready[6]),.delay_response_o(response[6]),
        .recording_valid_i(valid[8]),.recording_write_i(write_kind[8]),.recording_address_i(address[8]),
        .recording_data_i(data[8]),.recording_mask_i(mask[8]),.recording_ready_o(ready[8]),.recording_response_o(response[8]),
        .app_cmd_o(app_cmd),.app_en_o(app_en),.app_wren_o(app_wren),.app_wend_o(app_wend),
        .app_address_o(app_address),.app_data_o(app_data),.app_mask_o(app_mask),
        .app_ready_i(app_ready),.app_write_ready_i(app_write_ready),.app_response_i(app_response),
        .app_response_data_i(app_response_data),.response_data_o(response_data),.memory_flags_o(flags),
        .slot_accept_o(slot_accept),.core_accept_o(core_accept),.native_accept_o(native_accept),.transport_fault_o(fault));
    assign ready[4:0]=0;assign ready[7]=0;
    assign response[4:1]=0;assign response[7]=0;assign response[0]=dut.bist_response;

    reg [255:0] memory[0:1535];
    integer slots[0:8],cores[0:8],natives[0:8],returns[0:8],max_wait[0:8];
    integer accepted_at[0:8][0:4095];
    reg queued_write[0:8][0:4095];
    reg [28:0] queued_address[0:8][0:4095];
    reg [255:0] queued_data[0:8][0:4095];
    reg [31:0] queued_mask[0:8][0:4095];
    integer wanted_owner[0:8191],wanted_head=0,wanted_tail=0;
    reg [255:0] wanted_data[0:8191];
    integer native_due[0:8191],native_head=0,native_tail=0;
    reg [255:0] native_rdata[0:8191];
    integer cycle=0,checks=0,phases=0,total_native=0,total_returns=0;
    integer masked_cnn=0,masked_recording=0,command_stalls=0,write_stalls=0;
    integer max_native_queue=0,max_pending_commands=0,saturation_recording=0,saturation_delay=0;
    integer pending,owner,index,word_index,byte_index,wait_cycles;
    reg [31:0] random_state=SEED;
    reg [255:0] returned_value;
    task automatic check(input bit ok,input [767:0] message);
        begin checks=checks+1;if(!ok)$fatal(1,"%0s cycle=%0d seed=%0d",message,cycle,SEED);end
    endtask
    function integer memory_index(input [28:0] a);
        begin
            if(a<29'd32)memory_index=a>>3;
            else if(a>=`PRJ1_DDR_NN_POOL_APP_BASE && a<`PRJ1_DDR_NN_POOL_APP_BASE+29'd1024)
                memory_index=64+((a-`PRJ1_DDR_NN_POOL_APP_BASE)>>3);
            else if(a>=`PRJ1_DDR_DELAY_RING_APP_BASE && a<`PRJ1_DDR_DELAY_RING_APP_BASE+29'd1024)
                memory_index=512+((a-`PRJ1_DDR_DELAY_RING_APP_BASE)>>3);
            else if(a>=`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE && a<`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE+29'd1024)
                memory_index=1024+((a-`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE)>>3);
            else memory_index=-1;
        end
    endfunction
    function [28:0] owner_address(input integer who,input integer offset);
        begin case(who)
            5:owner_address=`PRJ1_DDR_NN_POOL_APP_BASE+29'(offset*8);
            6:owner_address=`PRJ1_DDR_DELAY_RING_APP_BASE+29'(offset*8);
            default:owner_address=`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE+29'(offset*8);
        endcase end
    endfunction
    function [255:0] pattern(input integer who,input integer serial);
        integer k;
        begin for(k=0;k<8;k=k+1)pattern[k*32+:32]=32'hc3519a27^(32'(who)<<24)^32'(serial*101+k*17);end
    endfunction

    // Actual native command acceptance and in-order behavior model. Read data
    // is sampled at the native read edge, then returned after independent delay.
    always @(posedge memory_clock)begin
        cycle=cycle+1;
        if(!client_reset_n)begin
            native_head=0;native_tail=0;wanted_head=0;wanted_tail=0;
            for(integer k=0;k<9;k=k+1)begin slots[k]=0;cores[k]=0;natives[k]=0;returns[k]=0;max_wait[k]=0;end
            check(!(app_en || |ready || |response || |native_accept),"reset isolates client/native response");
        end else begin
            check((slot_accept & 9'b010011110)==0 && (core_accept & 9'b010011110)==0 &&
                (native_accept & 9'b010011110)==0,"retired owners1/2/3/4/7 cannot issue");
            for(integer k=5;k<9;k=k+1)if(k!=7)begin
                check(slot_accept[k]==(valid[k] && ready[k]),"local ready equals actual slot acceptance");
                if(valid[k] && ready[k])begin
                    index=slots[k];check(index<4096,"request scoreboard capacity");
                    queued_write[k][index]=write_kind[k];queued_address[k][index]=address[k];
                    queued_data[k][index]=data[k];queued_mask[k][index]=(k==6)?0:mask[k];
                    accepted_at[k][index]=cycle;slots[k]=slots[k]+1;
                end
                if(core_accept[k])begin cores[k]=cores[k]+1;check(cores[k]<=slots[k],"core acceptance needs prior local slot");end
            end
            check(app_en==(|native_accept),"native trace equals actual command edge");
            check(native_accept==0 || (native_accept & (native_accept-1'b1))==0,"native owner is exclusive");
            if(app_en)begin
                owner=0;for(integer k=0;k<9;k=k+1)if(native_accept[k])owner=k;
                check(app_ready && (!app_wren || app_write_ready),"joint command/write readiness");
                check(app_cmd==(app_wren?3'b000:3'b001) && app_wend==app_wren,"native command encoding");
                check(app_address[2:0]==0,"native BL8 alignment");
                word_index=memory_index(app_address);check(word_index>=0,"native address uses real disjoint map");
                total_native=total_native+1;
                if(owner!=0)begin
                    index=natives[owner];check(index<cores[owner],"native commit needs core acceptance");
                    check(app_wren==queued_write[owner][index] && app_address==queued_address[owner][index] &&
                        app_mask==queued_mask[owner][index] && (!app_wren || app_data==queued_data[owner][index]),
                        "native command/data/mask preserved in owner order");
                    wait_cycles=cycle-accepted_at[owner][index];
                    if(wait_cycles>max_wait[owner])max_wait[owner]=wait_cycles;
                    natives[owner]=natives[owner]+1;
                    if(app_wren && app_mask!=0)begin
                        if(owner==5)masked_cnn=masked_cnn+1;
                        if(owner==8)masked_recording=masked_recording+1;
                    end
                end
                if(app_wren)begin
                    for(byte_index=0;byte_index<32;byte_index=byte_index+1)
                        if(!app_mask[byte_index])memory[word_index][byte_index*8+:8]=app_data[byte_index*8+:8];
                end else begin
                    returned_value=memory[word_index] ^ ((corrupt_bist && owner==0)?256'd1:256'd0);
                    native_rdata[native_tail]=returned_value;native_due[native_tail]=cycle+2+integer'(random_state[3:0]);
                    native_tail=native_tail+1;
                    wanted_owner[wanted_tail]=owner;wanted_data[wanted_tail]=returned_value;wanted_tail=wanted_tail+1;
                end
            end
            if(|response)begin
                check((response & (response-1'b1))==0,"returned owner is exclusive");
                owner=0;for(integer k=0;k<9;k=k+1)if(response[k])owner=k;
                check(wanted_head<wanted_tail,"no fabricated or duplicate return");
                check(owner==wanted_owner[wanted_head] && response_data===wanted_data[wanted_head],
                    "native returned data paired with actual owner");
                wanted_head=wanted_head+1;returns[owner]=returns[owner]+1;total_returns=total_returns+1;
            end
            pending=0;for(integer k=5;k<9;k=k+1)if(k!=7)pending=pending+slots[k]-natives[k];
            check(pending<=4,"three local slots plus one core command bound");
            if(pending>max_pending_commands)max_pending_commands=pending;
            if(native_tail-native_head>max_native_queue)max_native_queue=native_tail-native_head;
            if(!app_ready && dut.u_arbiter.g_recording.u_core.g_recording.command_full)command_stalls=command_stalls+1;
            if(app_ready && !app_write_ready && dut.u_arbiter.g_recording.u_core.g_recording.command_full &&
                dut.u_arbiter.g_recording.u_core.g_recording.command_write)write_stalls=write_stalls+1;
        end
    end
    always @(negedge memory_clock)begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        app_ready=(stall_mode!=1) && (!stress || random_state[2:0]!=0);
        app_write_ready=(stall_mode!=2) && (!stress || random_state[4:2]!=0);
        app_response=0;app_response_data=0;
        if(inject_return)begin app_response=1;app_response_data=256'h123456789abcdef;end
        else if(client_reset_n && !pause_returns && native_head<native_tail && cycle>=native_due[native_head])begin
            app_response=1;app_response_data=native_rdata[native_head];native_head=native_head+1;
        end
    end
    task automatic cycles(input integer n);begin repeat(n)@(posedge memory_clock);#1;end endtask
    task automatic await_ready;
        integer n;begin n=0;while(!client_ready && n<3000)begin cycles(1);n=n+1;end
            check(client_ready && !fault,"actual BIST qualifies clients");end
    endtask
    task automatic await_drain;
        integer n;reg drained;
        begin n=0;drained=0;while(!drained && n<6000)begin
            cycles(1);drained=(wanted_head==wanted_tail);
            for(integer k=5;k<9;k=k+1)if(k!=7)drained=drained && slots[k]==natives[k];
            n=n+1;
        end
        check(drained && !fault,"all local commands reach native and every read returns once");cycles(4);end
    endtask
    task automatic submit(input integer who,input bit wr,input integer offset,input [255:0] value,input [31:0] byte_mask);
        integer n;reg accepted;
        begin @(negedge memory_clock);valid[who]=1;write_kind[who]=wr;address[who]=owner_address(who,offset);
            data[who]=value;mask[who]=byte_mask;n=0;accepted=0;
            while(!accepted && n<3000)begin @(posedge memory_clock);accepted=ready[who];n=n+1;end
            check(accepted,"request admission deadline");@(negedge memory_clock);valid[who]=0;
        end
    endtask
    task automatic traffic(input integer who);
        begin for(integer k=0;k<24;k=k+1)begin
            submit(who,1,k,pattern(who,k),0);
            submit(who,1,k,pattern(who,k+100),(who==6)?0:32'h55aa0ff0);
            submit(who,0,k,0,0);
        end end
    endtask
    task automatic coherent_reset;
        begin @(negedge memory_clock);valid=0;reset_n=0;memory_reset_n=0;calibrated=0;pll_locked=0;
            stress=0;stall_mode=0;pause_returns=0;inject_return=0;corrupt_bist=0;
            #0.1;check(!client_reset_n && !client_ready && !(|ready) && !(|response),"asynchronous root isolation");
            cycles(2);inject_return=1;cycles(1);
            check(!client_ready && !app_en && !(|response),"native return during asserted coherent reset is isolated");
            inject_return=0;cycles(1);@(negedge memory_clock);reset_n=1;memory_reset_n=1;calibrated=1;pll_locked=1;await_ready();
        end
    endtask
    initial begin
        for(integer k=0;k<1536;k=k+1)memory[k]=0;
        for(integer k=0;k<9;k=k+1)begin address[k]=0;data[k]=0;mask[k]=0;end
        #1;reset_n=0;memory_reset_n=0;calibrated=0;pll_locked=0;
        cycles(4);reset_n=1;memory_reset_n=1;pll_locked=1;
        valid=9'b101100000;cycles(10);
        check(!(client_ready || |ready || |slot_accept),"uncalibrated inputs cannot claim admission");
        valid=0;calibrated=1;await_ready();repeat(5)@(posedge clock50);#1;
        check(flags==8'h43,"established status meanings and absent video bits");phases=phases+1;
        stress=1;fork traffic(5);traffic(6);traffic(8);join
        stress=0;await_drain();check(masked_cnn==24 && masked_recording==24,"both masked write owners exercised");
        $display("TRAFFIC owner5_wait=%0d owner6_wait=%0d owner8_wait=%0d",max_wait[5],max_wait[6],max_wait[8]);phases=phases+1;

        // The write-data path can stall independently from command acceptance.
        stall_mode=2;submit(8,1,70,pattern(8,701),32'h80000001);cycles(32);
        check(slots[8]>natives[8] && !app_en,"write ready cannot be replaced by local/core ready");
        stall_mode=0;await_drain();phases=phases+1;
        stall_mode=1;fork submit(5,0,1,0,0);submit(6,0,2,0,0);submit(8,0,3,0,0);join
        cycles(32);check(wanted_head==wanted_tail && !app_en,"command pause retains queued requests");
        pause_returns=1;stall_mode=0;cycles(32);
        check(wanted_tail-wanted_head==3,"native acceptance is distinct from read completion");
        cycles(64);check(wanted_tail-wanted_head==3,"delayed native reads do not fabricate completion");
        pause_returns=0;await_drain();phases=phases+1;

        // Saturate the actual stable-slot composition, preserving its bubbles.
        @(negedge memory_clock);for(integer k=5;k<9;k=k+1)if(k!=7)begin
            valid[k]=1;write_kind[k]=1;address[k]=owner_address(k,80);data[k]=pattern(k,800);mask[k]=0;
        end
        saturation_recording=natives[8];saturation_delay=natives[6];cycles(1024);
        @(negedge memory_clock);valid=0;
        saturation_recording=natives[8]-saturation_recording;saturation_delay=natives[6]-saturation_delay;
        check(saturation_recording>0 && saturation_delay>0,"actual slot bubbles allow recording progress under this tested load");
        await_drain();$display("SATURATION cycles=1024 owner8_native=%0d owner6_native=%0d owner8_max_wait=%0d",saturation_recording,saturation_delay,max_wait[8]);phases=phases+1;

        // Reset with admitted reads pending. The native controller/model is
        // coherently reset too; local reset cannot label arbitrary old returns.
        pause_returns=1;submit(5,0,2,0,0);submit(8,0,2,0,0);cycles(32);
        check(wanted_tail>wanted_head,"reset scenario has actual outstanding native reads");
        coherent_reset();cycles(20);check(!(response[5] || response[6] || response[8]),"coherent reset cancels old return ledger");
        submit(8,1,90,pattern(8,900),0);submit(8,0,90,0,0);await_drain();phases=phases+1;

        // Calibration loss closes asynchronously even when memory clock stops.
        @(negedge memory_clock);#1;memory_run=0;calibrated=0;#0.1;
        check(!client_reset_n && !client_ready && !(|ready),"calibration loss isolates without a memory edge");
        repeat(5)@(posedge clock50);memory_run=1;coherent_reset();phases=phases+1;

        // A response arriving after all tags drained is a transport error,
        // never a media response. It must fence this same native edge.
        stall_mode=1;submit(8,1,91,pattern(8,901),0);cycles(12);
        check(slots[8]>natives[8],"late response scenario has a queued native write");
        @(posedge memory_clock);#1;stall_mode=0;inject_return=1;@(negedge memory_clock);#1;
        check(fault && !client_ready && !app_en && !(response[5] || response[6] || response[8]),"unowned late response fences on the same edge");
        cycles(1);inject_return=0;cycles(5);check(fault && !client_ready,"late response fault is sticky");
        repeat(5)@(posedge clock50);#1;check(flags[4] && !flags[3] && !flags[5] && !flags[7],"fault reaches unchanged public flags");
        coherent_reset();phases=phases+1;

        // A true BIST mismatch never opens any media client.
        @(negedge memory_clock);reset_n=0;memory_reset_n=0;calibrated=0;cycles(4);
        corrupt_bist=1;reset_n=1;memory_reset_n=1;calibrated=1;cycles(600);
        check(dut.bist_done && dut.bist_failed && !client_ready && !(|ready),"actual BIST failure rejects all media");
        check(command_stalls>0 && write_stalls>0 && max_pending_commands>=3,"independent stalls and concurrent queue load exercised");phases=phases+1;
        $display("PASS media_memory seed=%0d phase=%0d phases=%0d checks=%0d native=%0d returned=%0d masked_cnn=%0d masked_recording=%0d command_stalls=%0d write_stalls=%0d max_native_queue=%0d max_pending_commands=%0d",SEED,PHASE,phases,checks,total_native,total_returns,masked_cnn,masked_recording,command_stalls,write_stalls,max_native_queue,max_pending_commands);
        $finish;
    end
    initial begin #10000000;$fatal(1,"media memory watchdog");end
endmodule

// Negative budget probe of the maintained core at its queued-input boundary.
// This intentionally bypasses the mandatory local slots. It proves why their
// bubbles/offered-load constraints cannot be omitted from a deadline argument.
module tb_media_memory_priority_budget;
    reg clk=0,reset_n=0;
    always #7 clk=~clk;
    wire delay_ready,recording_ready,app_en;
    wire [8:0] native_accept;
    integer delay_native=0,recording_native=0;
    workstation_recording_ddr_arbiter_pipeline #(.RECORDING_ENABLE(1),.REGISTER_GRANTS(1)) dut(
        .clk(clk),.reset_n(reset_n),.bist_done(1'b1),
        .bist_valid(1'b0),.bist_write(1'b0),.bist_address(29'd0),.bist_data(256'd0),
        .scan_valid(1'b0),.scan_address(29'd0),.display_valid(1'b0),.display_address(29'd0),
        .audio_valid(1'b0),.audio_write(1'b0),.audio_address(29'd0),.audio_data(256'd0),
        .music_valid(1'b0),.music_write(1'b0),.music_address(29'd0),.music_data(256'd0),.music_mask(32'd0),
        .delay_valid(1'b1),.delay_write(1'b1),.delay_address(`PRJ1_DDR_DELAY_RING_APP_BASE),.delay_data(256'd1),.delay_ready(delay_ready),
        .writer_valid(1'b0),.writer_address(29'd0),.writer_data(256'd0),
        .cpu_valid(1'b0),.cpu_write(1'b0),.cpu_address(29'd0),.cpu_data(256'd0),.cpu_mask(32'd0),
        .recording_valid(1'b1),.recording_write(1'b1),.recording_address(`PRJ1_DDR_TASK3_W_RECORDING_APP_BASE),
        .recording_data(256'd2),.recording_mask(32'd0),.recording_ready(recording_ready),
        .app_en(app_en),.app_ready(1'b1),.app_write_ready(1'b1),.app_response(1'b0),.app_response_data(256'd0),
        .native_accept_o(native_accept));
    always @(posedge clk)if(reset_n)begin
        if(native_accept[6])delay_native=delay_native+1;
        if(native_accept[8])recording_native=recording_native+1;
        if(recording_ready)$fatal(1,"core priority budget no longer matches reviewed negative control");
    end
    initial begin repeat(3)@(negedge clk);reset_n=1;repeat(256)@(negedge clk);
        if(delay_native==0 || recording_native!=0)$fatal(1,"core priority saturation evidence missing");
        $display("PASS priority_budget bypass_local_slots=1 pending_cycles=256 delay_native=%0d recording_native=%0d recording_core_accept=0",delay_native,recording_native);$finish;
    end
endmodule
