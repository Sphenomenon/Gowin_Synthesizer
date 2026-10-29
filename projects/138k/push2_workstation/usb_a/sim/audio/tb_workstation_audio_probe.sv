`timescale 1ns/1ps
module tb_workstation_audio_probe;
    reg reference=0,raw48=0,raw44=0,restart_n=0,run48=1;
    always #10 reference=~reference;
    initial begin #3.7;forever begin #40.690104;if(run48)raw48=~raw48;end end
    initial begin #17.2;forever #29.525699 raw44=~raw44;end
    wire pdn,mclk,bck,lrck,data,smute;
    workstation_audio_probe_top #(
        .HOLD_REFERENCE_CYCLES(5000),.SNAPSHOT_REFERENCE_CYCLES(100),
        .MONITOR_WINDOW_CYCLES(500),.MONITOR_STABLE_WINDOWS(3),.SERIAL_STARTUP_FRAMES(12)
    ) dut (.clk_50mhz(reference),.clk_12m288(raw48),.clk_16m9344(raw44),.restart_n(restart_n),
        .ak_pdn(pdn),.ak_mclk(mclk),.ak_bick(bck),.ak_lrck(lrck),.ak_sdata(data),.ak_smute(smute));
    reg configured=0,expected44=0;
    integer selected_edges=0,last_bck=0,last_lrck=0,position=0,frames=0,snapshots=0;
    reg [2:0] observed_epochs=0;
    reg [31:0] previous_snapshot=0;
    always @(posedge mclk or negedge dut.audio_reset_n)
        if(!dut.audio_reset_n)begin configured=0;expected44=0;selected_edges=0;end
        else begin
            selected_edges=selected_edges+1;
            if(!configured)begin configured=1;expected44=dut.staged44;end
            #0.2;
            if(dut.frame_valid)begin
                if(dut.frame_error || dut.frame_pcm!=0)$fatal(1,"nonzero/error probe frame");
                frames=frames+1;
            end
        end
    always @(posedge bck or negedge dut.audio_reset_n)
        if(!dut.audio_reset_n)begin last_bck=0;position=0;end
        else begin
            #0.1;
            if(data!==0 || smute!==1 || lrck!==(position>=32))$fatal(1,"probe physical mute/zero/I2S slot");
            if(last_bck!=0 && selected_edges-last_bck!=(expected44 ? 6 : 4))$fatal(1,"probe BCK divider");
            last_bck=selected_edges;position=(position+1)%64;
        end
    always @(posedge lrck or negedge dut.audio_reset_n)
        if(!dut.audio_reset_n)last_lrck=0;
        else begin
            #0.1;
            if(last_lrck!=0 && selected_edges-last_lrck!=(expected44 ? 384 : 256))$fatal(1,"probe LRCK divider");
            last_lrck=selected_edges;
        end
    reg [31:0] count_value,sequence_value,epoch_value,flags;
    always @(negedge reference)begin
        if(smute!==1)$fatal(1,"physical SMUTE must always be high including reset");
        if(dut.reset_n && !dut.flush && dut.snapshot_valid && dut.snapshots_completed!=previous_snapshot)begin
            previous_snapshot=dut.snapshots_completed;snapshots=snapshots+1;
            count_value=dut.snapshot_value[31:0];sequence_value=dut.snapshot_value[63:32];
            epoch_value=dut.snapshot_value[95:64];flags=dut.snapshot_value[191:160];
            if(dut.snapshot_value[159:96]!=0 || flags[4])$fatal(1,"snapshot reports diagnostic frame failure");
            if(count_value!=0)begin
                if(sequence_value!=count_value-1 || epoch_value>2 || flags[3]!=(epoch_value==1))
                    $fatal(1,"torn completed-frame snapshot count=%0d seq=%0d epoch=%0d flags=%0h",count_value,sequence_value,epoch_value,flags);
                observed_epochs[epoch_value]=1;
            end
        end
    end
    task tick;begin @(posedge reference);#1;end endtask
    integer n=0;
    initial begin
        repeat(5)tick();restart_n=1;
        while(dut.probe_state!=8 && dut.probe_state!=15)tick();
        if(dut.probe_state!=8 || dut.epoch!=2 || dut.active44 || dut.completed_cycles!=1 ||
            dut.accepted_count!=2 || dut.applied_count!=2 || dut.rejected_count || dut.failed_count ||
            observed_epochs!=7 || snapshots<20 || frames<12 || dut.boot48_frames<3 || dut.rate44_frames<3 ||
            dut.final48_frames<3 || dut.selected48_history<120 || dut.selected44_history<167)
            $fatal(1,"probe sequence/snapshot coverage state=%0d epochs=%0b snapshots=%0d frames=%0d",dut.probe_state,observed_epochs,snapshots,frames);
        $display("PROBE normal complete epoch=%0d accepts=%0d applies=%0d atomic_snapshots=%0d physical_frames=%0d epochs=%0b",dut.epoch,dut.accepted_count,dut.applied_count,snapshots,frames,observed_epochs);
        wait(raw48===1'b1);run48=0;
        while(dut.probe_state!=15 && n<600)begin tick();n=n+1;end
        if(dut.probe_state!=15 || !dut.fault || dut.fault_code!=6 || dut.audio_reset_n || !smute)
            $fatal(1,"probe fault did not latch safely");
        $display("PASS standalone muted audio probe: automatic48->44.1->48, atomic frame snapshots, zero physical PCM, permanent SMUTE, stopped-high fault6; loss_cycles=%0d",n);
        $finish;
    end
    initial begin #10000000;$fatal(1,"probe watchdog");end
endmodule
