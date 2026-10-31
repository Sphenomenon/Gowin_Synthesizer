`timescale 1ns/1ps
module tb_native_telemetry_usb_reset;
    reg clk_50m=0,usb_clk=0,cpu_clk=0,audio_clk=0,usb_run=1;
    always #5 clk_50m=!clk_50m;
    always #7 if(usb_run)usb_clk=!usb_clk;
    always #11 cpu_clk=!cpu_clk;
    always #13 audio_clk=!audio_clk;
    reg reset_n=1,usb_reset_n=1,cpu_reset_n=1,audio_reset_n=1,raw_n=1;
    reg [223:0] usb_words=224'h123456789abcdef00123456789abcdef00123456789abcdef00123456;
    wire [447:0] old_feedback,default_feedback,selected_feedback;
    wire old_serial,default_serial,selected_serial;
    integer checks=0,raw_edges=0;
`define TELEMETRY_PORTS \
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n), \
        .audio_locked(1'b1),.sample_valid(1'b1),.memory_flags(8'h96),.audio_status(32'h12345678), \
        .video_diagnostics(128'h0123456789abcdef0123456789abcdef),.cpu_clk(cpu_clk), \
        .cpu_reset_n(cpu_reset_n),.cpu_words(224'h13579),.performance_words(448'h2468a), \
        .usb_clk(usb_clk),.usb_reset_n(usb_reset_n),.usb_words(usb_words),.push_words(224'habc)
    telemetry_reference #(.INTERVAL_CYCLES(100),.CPU_SNAPSHOT_BITS(2)) reference(
        `TELEMETRY_PORTS,.performance_feedback(old_feedback),.serial_out(old_serial));
    gw138k_push_performance_uart #(.INTERVAL_CYCLES(100),.CPU_SNAPSHOT_BITS(2)) default_mode(
        `TELEMETRY_PORTS,.usb_cdc_assert_ni(1'b0),
        .performance_feedback(default_feedback),.serial_out(default_serial));
    gw138k_push_performance_uart #(.INTERVAL_CYCLES(100),.CPU_SNAPSHOT_BITS(2),.USB_CDC_SEPARATE_RESET(1)) selected(
        `TELEMETRY_PORTS,.usb_cdc_assert_ni(raw_n),
        .performance_feedback(selected_feedback),.serial_out(selected_serial));
`undef TELEMETRY_PORTS
    always @(posedge selected.u_usb_cdc.reset_n or negedge selected.u_usb_cdc.reset_n)raw_edges=raw_edges+1;
    always @(posedge clk_50m or posedge usb_clk or posedge cpu_clk or posedge audio_clk)begin
        #0.1;
        if({default_serial,default_feedback,default_mode.usb_divider,default_mode.usb_snapshot,
            default_mode.cpu_snapshot,default_mode.state,default_mode.record_kind,default_mode.sequence_count,
            default_mode.payload,default_mode.crc,default_mode.u_usb_cdc.source_release,
            default_mode.u_usb_cdc.destination_release} !==
           {old_serial,old_feedback,reference.usb_divider,reference.usb_snapshot,
            reference.cpu_snapshot,reference.state,reference.record_kind,reference.sequence_count,
            reference.payload,reference.crc,reference.u_usb_cdc.source_release,
            reference.u_usb_cdc.destination_release})$fatal(1,"default telemetry behavior changed");
        if({selected_feedback,selected.cpu_snapshot,selected.cpu_divider,selected.performance_divider,
            selected.state,selected.record_kind,selected.sequence_count,selected.sample_sync,selected.flags_sync} !==
           {old_feedback,reference.cpu_snapshot,reference.cpu_divider,reference.performance_divider,
            reference.state,reference.record_kind,reference.sequence_count,reference.sample_sync,reference.flags_sync})
            $fatal(1,"USB reset adaptation changed UART/CPU/audio observer lifecycle");
        checks=checks+1;
    end
    integer before_edges;
    initial begin
        #1;reset_n=0;usb_reset_n=0;cpu_reset_n=0;audio_reset_n=0;raw_n=0;
        #2;raw_n=1;#1;reset_n=1;cpu_reset_n=1;audio_reset_n=1;
        repeat(10)@(negedge usb_clk);
        if(selected.g_usb_cdc_reset.usb_ready!==0 || selected.usb_divider!==0 ||
           selected.u_usb_cdc.held_data!==0 || selected.usb_snapshot!==0)
            $fatal(1,"USB observation progressed before local startup grant");
        // Reference-domain grant edges must never reach USB release CLEAR.
        usb_run=0;before_edges=raw_edges;
        #1;reset_n=0;#3;reset_n=1;usb_reset_n=1;#50;
        if(raw_edges!=before_edges || selected.u_usb_cdc.reset_n!==1 ||
           selected.g_usb_cdc_reset.usb_ready!==0 || selected.usb_divider!==0)
            $fatal(1,"stopped USB clock admitted a reference-domain release");
        usb_run=1;
        @(posedge usb_clk);#0.2;
        if(selected.g_usb_cdc_reset.usb_ready!==2'b01 || selected.usb_divider!==0)
            $fatal(1,"first USB readiness stage escaped locally");
        @(posedge usb_clk);#0.2;
        if(selected.g_usb_cdc_reset.usb_ready!==2'b11 || selected.usb_divider!==0)
            $fatal(1,"USB readiness did not require two local edges");
        wait(selected.usb_snapshot===usb_words);
        // A raw assertion clears an in-use mailbox even with no USB edges;
        // UART and the CPU/audio observers retain their independent resets.
        @(negedge usb_clk);usb_run=0;#1;raw_n=0;#0.2;
        if(selected.u_usb_cdc.source_release!==0 || selected.u_usb_cdc.destination_release!==0 ||
           selected.u_usb_cdc.held_data!==0 || selected.usb_snapshot!==0 ||
           selected.g_usb_cdc_reset.usb_ready!==0 || selected.usb_divider!==0)
            $fatal(1,"raw assertion did not flush stopped-clock USB observation");
        raw_n=1;repeat(8)@(negedge clk_50m);
        if(selected.u_usb_cdc.source_release!==0 || selected.g_usb_cdc_reset.usb_ready!==0 ||
           selected.usb_snapshot!==0)$fatal(1,"raw release bypassed stopped USB clock fence");
        usb_words=~usb_words;usb_run=1;
        wait(selected.usb_snapshot===usb_words);
        if(checks<100000)$fatal(1,"insufficient default/observer comparison coverage");
        $display("PASS telemetry USB reset: checks=%0d default_equal=1 local_grant=2 stopped_release=1 raw_flush=1 fresh_restart=1 uart_cpu_audio_preserved=1",checks);
        $finish;
    end
    initial begin #3000000;$fatal(1,"telemetry USB reset watchdog");end
endmodule
