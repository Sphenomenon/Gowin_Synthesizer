`timescale 1ns/1ps
module tb_workstation_ddr_scan_window;
    reg busy,writer_valid,writer_ready,cpu_valid,cpu_write,cpu_ready;
    wire default_wvalid,default_wready,default_cvalid,default_cready;
    wire window_wvalid,window_wready,window_cvalid,window_cready;
    workstation_ddr_scan_window default_off (
        .scan_fetch_busy_i(busy),.writer_valid_i(writer_valid),.writer_ready_i(writer_ready),
        .writer_valid_o(default_wvalid),.writer_ready_o(default_wready),
        .cpu_valid_i(cpu_valid),.cpu_write_i(cpu_write),.cpu_ready_i(cpu_ready),
        .cpu_valid_o(default_cvalid),.cpu_ready_o(default_cready));
    workstation_ddr_scan_window #(.ENABLE(1)) enabled (
        .scan_fetch_busy_i(busy),.writer_valid_i(writer_valid),.writer_ready_i(writer_ready),
        .writer_valid_o(window_wvalid),.writer_ready_o(window_wready),
        .cpu_valid_i(cpu_valid),.cpu_write_i(cpu_write),.cpu_ready_i(cpu_ready),
        .cpu_valid_o(window_cvalid),.cpu_ready_o(window_cready));
    integer pattern;
    initial begin
        for(pattern=0;pattern<64;pattern=pattern+1)begin
            {busy,writer_valid,writer_ready,cpu_valid,cpu_write,cpu_ready}=6'(pattern);
            #1;
            if({default_wvalid,default_wready,default_cvalid,default_cready}!==
               {writer_valid,writer_ready,cpu_valid,cpu_ready})$fatal(1,"default pass-through");
            if(window_wvalid!==(writer_valid && !busy) || window_wready!==(writer_ready && !busy))
                $fatal(1,"blocked writer false ACK or lost unblocked transfer");
            if(cpu_write && busy)begin
                if(window_cvalid || window_cready)$fatal(1,"blocked CPU write false ACK");
            end else if({window_cvalid,window_cready}!=={cpu_valid,cpu_ready})
                $fatal(1,"CPU read or unblocked write changed");
        end
        $display("PASS scan-window admission: exhaustive 64 handshake states, default pass-through, writer/CPU write valid and ready masking, CPU read bypass");
        $finish;
    end
endmodule
