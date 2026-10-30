`timescale 1ns/1ps
// The real selected top and recording owners run here. Unrelated full-system
// providers and the BLE radio/business endpoint are black boxes. Command and
// raw ports are driven at their existing owning-subsystem interfaces.
module tb_ble_ddr_top_composition;
    parameter integer CASE=0;
    reg control_clk=0,memory_clk=0,source_clk=0,memory_running=1;
    always #10 control_clk=~control_clk;
    always #7 if(memory_running)memory_clk=~memory_clk;else memory_clk=0;
    always #41 source_clk=~source_clk;
    reg root_reset=0,ledger_reset=0,backend_ready=0;
    reg raw_start=0,raw_clear=0,raw_capture=0,raw_close=0,raw_fetch=0;
    reg [31:0] raw_index=0,raw_pcm=0,raw_offset=0,raw_sample=0;
    reg [13:0] raw_length=0;
    reg frame_valid=0;
    reg [31:0] frame_sequence=0,frame_pcm=0;
    reg cpu_command=0,cpu_write=0;
    reg [11:0] cpu_address=0;
    reg [31:0] cpu_data=0;
    workstation_custom_138k_top dut(.clk_50m(control_clk),.clk_12m288(source_clk),.clk_16m9344(source_clk));
    reg native_enable=1,response_enable=1,slot_pending=0,read_pending=0;
    wire native_pulse,response_pulse;
    reg [28:0] model_address=0,read_address=0;
    reg model_write=0;
    reg [255:0] model_data=0,return_data=0;
    reg [31:0] model_mask=0;
    integer delay=0,read_delay=0,writes0=0,writes1=0,reads0=0,reads1=0,checks=0;
    assign native_pulse=root_reset && slot_pending && delay==0 && native_enable;
    assign response_pulse=root_reset && read_pending && read_delay==0 && response_enable;
    reg [255:0] memory0[0:2047],memory1[0:2047];
    wire local_ready=!slot_pending && !read_pending;
    function [31:0] cpu_pattern(input integer n);cpu_pattern=32'hb1694352 ^ (n*32'h1837);endfunction
    function [31:0] ble_pattern(input integer n);ble_pattern=32'h4275dcba ^ (n*32'h12345);endfunction
    task check(input bit okay,input [511:0] message);
        begin checks=checks+1;if(!okay)$fatal(1,"%0s at %0t",message,$time);end
    endtask
    initial begin
        force dut.reset_n=root_reset;force dut.memory_clk=memory_clk;force dut.dac_mclk=source_clk;
        force dut.ddr_client_reset_n=ledger_reset;force dut.ddr_client_ready=backend_ready;
        force dut.recording_ready=local_ready;force dut.recording_native_accept=native_pulse;
        force dut.recording_response=response_pulse;force dut.recording_transport_fault=1'b0;
        force dut.client_rdata=return_data;
        force dut.raw_start_valid=raw_start;force dut.raw_clear_valid=raw_clear;
        force dut.raw_capture_valid=raw_capture;force dut.raw_capture_index=raw_index;force dut.raw_capture_pcm=raw_pcm;
        force dut.raw_close_valid=raw_close;force dut.raw_fetch_valid=raw_fetch;
        force dut.raw_fetch_offset=raw_offset;force dut.raw_fetch_length=raw_length;force dut.raw_sample_addr=raw_sample;
        force dut.physical_frame_valid=frame_valid;force dut.physical_frame_error=1'b0;force dut.physical_frame44=1'b0;
        force dut.physical_frame_epoch=32'd73;force dut.physical_frame_sequence=frame_sequence;force dut.physical_frame_pcm=frame_pcm;
        force dut.u_recording.command_reset=root_reset;force dut.u_recording.command_valid=cpu_command;
        force dut.u_recording.command_write=cpu_write;force dut.u_recording.command_address=cpu_address;
        force dut.u_recording.command_data=cpu_data;force dut.u_recording.command_strobes=4'hf;
        force dut.recording_seal_hold=1'b0;force dut.recording_seal_request=1'b0;
    end
    always @* begin
        return_data=read_address<29'h0c144000 ? memory0[(read_address-29'h0c140000)>>3] : memory1[(read_address-29'h0c144000)>>3];
    end
    always @(posedge memory_clk)begin
        if(!root_reset)begin slot_pending<=0;read_pending<=0;writes0<=0;writes1<=0;reads0<=0;reads1<=0;end
        else begin
            if(dut.recording_req && local_ready)begin
                check(dut.recording_address[2:0]==0 && dut.recording_address>=29'h0c140000 &&
                    dut.recording_address<=29'h0c147ff8,"top native address/window/alignment");
                slot_pending<=1;model_address<=dut.recording_address;model_write<=dut.recording_write;
                model_data<=dut.recording_data;model_mask<=dut.recording_mask;delay<=3;
            end
            if(slot_pending && !native_pulse)begin
                check({dut.recording_write,dut.recording_address,dut.recording_data,dut.recording_mask}===
                    {model_write,model_address,model_data,model_mask},"top published native fields stable");
                if(delay>0)delay<=delay-1;
            end
            if(native_pulse)begin
                slot_pending<=0;
                if(model_write)begin
                    if(model_address<29'h0c144000)begin
                        if(writes0==0)check(model_address==29'h0c140000,"actual CPU first native write base/units");
                        writes0<=writes0+1;
                        for(integer b=0;b<32;b=b+1)if(!model_mask[b])memory0[(model_address-29'h0c140000)>>3][b*8+:8]<=model_data[b*8+:8];
                    end else begin
                        if(writes1==0)check(model_address==29'h0c144000,"actual BLE first native write base/units");
                        writes1<=writes1+1;
                        for(integer b=0;b<32;b=b+1)if(!model_mask[b])memory1[(model_address-29'h0c144000)>>3][b*8+:8]<=model_data[b*8+:8];
                    end
                end else begin
                    read_pending<=1;read_address<=model_address;read_delay<=5;
                    if(model_address<29'h0c144000)reads0<=reads0+1;else reads1<=reads1+1;
                end
            end
            if(read_pending && read_delay>0)read_delay<=read_delay-1;
            if(response_pulse)read_pending<=0;
        end
    end
    task command(input bit wr,input [11:0] address,input [31:0] data,output reg [31:0] result);
        integer budget;
        begin
            @(negedge memory_clk);cpu_command=1;cpu_write=wr;cpu_address=address;cpu_data=data;budget=0;#1;
            while(!dut.u_recording.command_ready && budget<10000)begin @(negedge memory_clk);#1;budget=budget+1;end
            if(!dut.u_recording.command_ready || dut.u_recording.response_error)begin
                $fatal(1,"top CPU command acceptance addr=%h data=%h ready=%b error=%b state=%d reset=%b id=%h limit=%d eligible=%b clear=%b hold=%b fault=%b pcm_loss=%b",address,data,
                    dut.u_recording.command_ready,dut.u_recording.response_error,dut.u_recording.service.object_state_o,dut.u_recording.command_reset,
                    dut.u_recording.service.staged_id,dut.u_recording.service.staged_limit,dut.u_recording.service.create_eligible,
                    dut.u_recording.service.create_ready,dut.u_recording.service.seal_hold_i,dut.recording_mux_fault,dut.u_recording.pcm_loss);
            end
            result=dut.u_recording.response_data;@(negedge memory_clk);cpu_command=0;
        end
    endtask
    reg [31:0] ignored;
    task write_command(input [11:0] address,input [31:0] data);command(1,address,data,ignored);endtask
    task source_frame(input integer n);
        reg [31:0] p;
        begin
            p=cpu_pattern(n);@(negedge source_clk);frame_sequence=n;frame_pcm={p[15:0],p[31:16]};frame_valid=1;
            @(negedge source_clk);frame_valid=0;repeat(6)@(negedge source_clk);
        end
    endtask
    task begin_raw;
        begin wait(dut.raw_start_ready && dut.recording_channel_ready50);@(negedge control_clk);raw_start=1;@(negedge control_clk);raw_start=0;end
    endtask
    integer deadline,n;
    reg [31:0] result;
    initial begin
        for(n=0;n<2048;n=n+1)begin memory0[n]={32{8'ha5}};memory1[n]={32{8'hcd}};end
        repeat(6)@(negedge memory_clk);
        if(CASE==2)begin
            memory_running=0;root_reset=1;repeat(12)@(negedge control_clk);
            check(!dut.recording_memory_reset_n && !dut.recording_ble_store.memory_reset_n &&
                !dut.recording_authority.root_memory_reset_n,"root release while stopped cannot release memory owners");
            check(dut.recording_owner8.state==0 && !dut.recording_req,"stopped root release preserves empty owner transport");
            memory_running=1;@(posedge memory_clk);#1;check(!dut.recording_memory_reset_n,"memory reset requires second local release edge");
            @(posedge memory_clk);#1;check(dut.recording_memory_reset_n,"memory owners release on second local edge only");
            repeat(6)@(negedge memory_clk);ledger_reset=1;backend_ready=1;
            wait(dut.recording_channel_ready && dut.recording_channel_ready50);
            check(dut.recording_authority.boot_seen && !dut.recording_authority_fault,"local root release precedes first usable ledger edge");
        end else begin
        root_reset=1;repeat(8)@(negedge memory_clk);ledger_reset=1;
        if(CASE==1)begin
            repeat(8)@(negedge memory_clk);check(dut.recording_authority.boot_seen,"ledger boot observed before ready");
            ledger_reset=0;#1;check(!dut.recording_channel_ready,"pre-ready ledger loss closes authority");
            repeat(3)@(negedge memory_clk);ledger_reset=1;backend_ready=1;
            repeat(100)@(negedge control_clk);
            check(!dut.recording_channel_ready && dut.recording_authority_fault && !dut.recording_req,"BIST-only old epoch never rearms");
            check(!dut.u_recording.service.backend_ready_i && !dut.recording_channel_ready50,"both business source qualifications reject recovered old epoch");
        end else begin
            backend_ready=1;wait(dut.recording_channel_ready && dut.recording_channel_ready50);
            write_command(12'h010,32'h12345678);write_command(12'h014,32'habcdef01);write_command(12'h018,17);
            fork
                write_command(12'h008,1);
                begin repeat(15)@(negedge source_clk);source_frame(-1);for(integer i=0;i<17;i=i+1)source_frame(i);end
                begin
                    begin_raw;
                    for(integer i=0;i<19;i=i+1)begin
                        @(negedge control_clk);raw_index=i;raw_pcm=ble_pattern(i);raw_capture=1;
                        @(negedge control_clk);raw_capture=0;
                    end
                    @(negedge control_clk);raw_close=1;wait(dut.raw_close_ready);@(negedge control_clk);raw_close=0;
                end
            join
            deadline=0;while((!dut.raw_drained || dut.u_recording.service.object_state_o!=3) && deadline<10000)begin
                @(negedge control_clk);deadline=deadline+1;end
            check(dut.raw_drained && !dut.raw_fault && dut.raw_committed==19,"top BLE real committed drain");
            check(dut.u_recording.service.object_state_o==3 && dut.u_recording.service.committed_frames_o==17,"top CPU real committed drain");
            check(writes0==3 && writes1==3,"both disjoint clients reached actual native acceptance");
            for(n=0;n<19;n=n+1)check(memory1[n/8][(n%8)*32+:32]===ble_pattern(n),"BLE PCM32 order and window preserved");
            for(n=0;n<17;n=n+1)check(memory0[n/8][(n%8)*32+:32]===cpu_pattern(n),"CPU PCM32 order and window preserved");
            check(memory0[2][255:32]=={28{8'ha5}} && memory1[2][255:96]=={20{8'hcd}},"both partial masks retained");
            @(negedge control_clk);raw_offset=3;raw_length=67;raw_fetch=1;@(negedge control_clk);raw_fetch=0;
            wait(dut.raw_fetch_done);check(dut.raw_cache_valid && reads1==3,"top BLE cache publishes after returned owner1 reads");
            for(n=0;n<18;n=n+1)begin @(negedge control_clk);raw_sample=n;@(posedge control_clk);#1;
                check(dut.raw_sample_word===ble_pattern(n),"top BLE one-cycle absolute cache word");end
            write_command(12'h008,5);write_command(12'h040,0);write_command(12'h044,32);write_command(12'h008,7);
            wait(dut.u_recording.service.download_valid);write_command(12'h008,8);
            command(0,12'h04c,0,result);check(result===cpu_pattern(0) && reads0==1,"top CPU returned owner0 snapshot");
            check(!dut.raw_fault,"CPU read response must not reach BLE raw read owner");
            // A live old physical read survives ledger loss. No local object or
            // recovered ready may reinterpret its eventual untagged response.
            response_enable=0;@(negedge control_clk);raw_offset=0;raw_length=32;raw_fetch=1;@(negedge control_clk);raw_fetch=0;
            wait(read_pending);@(negedge memory_clk);ledger_reset=0;#1;
            check(!dut.recording_req && dut.recording_subclient_native==0 && dut.recording_subclient_response==0,"ledger loss closes every owner bypass");
            repeat(5)@(negedge memory_clk);ledger_reset=1;response_enable=1;
            repeat(100)@(negedge control_clk);
            check(dut.recording_authority_fault && !dut.recording_channel_ready && !dut.recording_req &&
                dut.raw_channel_fault && !dut.raw_cache_valid,"late physical response cannot revive raw channel/cache");
            check(dut.u_recording.service.object_state_o==4,"authority loss fails CPU object without resetting it");
        end
        end
        $display("PASS BLE_DDR_TOP_COMPOSITION case=%0d checks=%0d cpu_writes=%0d ble_writes=%0d cpu_reads=%0d ble_reads=%0d",CASE,checks,writes0,writes1,reads0,reads1);$finish;
    end
    initial begin #10000000;$fatal(1,"top composition watchdog");end
endmodule
