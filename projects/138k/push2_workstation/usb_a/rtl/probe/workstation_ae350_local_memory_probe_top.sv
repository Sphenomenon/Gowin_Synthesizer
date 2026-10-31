`default_nettype none
`include "probe_identity.vh"
module workstation_ae350_local_memory_probe_top(
    input wire clk_50m,
    output wire debug_uart_tx,
    output wire ak_pdn,ak_mclk,ak_bick,ak_lrck,ak_sdata,ak_smute
);
    // Same audited digital audio pins as the B7 muted probe. Never rely on
    // unused-IO defaults to retain a previous image's DAC mute or reset.
    assign ak_pdn=1'b0,ak_mclk=1'b0,ak_bick=1'b0,ak_lrck=1'b0,ak_sdata=1'b0;
    assign ak_smute=1'b1;
    reg [15:0] power_on=0;
    always @(posedge clk_50m)if(!(&power_on))power_on<=power_on+1'b1;
    wire system_reset_n=&power_on;
    wire core_clk,bus_clk,pll_locked;
    gw138k_cpu_pll_cell u_cpu_pll(.clkin(clk_50m),.init_clk(clk_50m),.reset(!system_reset_n),
        .enable0(1'b1),.lock(pll_locked),.clkout0(bus_clk),.clkout1(core_clk));
    reg [16:0] lock_count=0;
    reg lock_qualified=0;
    wire ready_async=system_reset_n && pll_locked;
    always @(posedge clk_50m or negedge ready_async)
        if(!ready_async) begin lock_count<=0;lock_qualified<=0;end
        else if(!lock_qualified) begin
            if(lock_count==17'd100000)lock_qualified<=1;
            else lock_count<=lock_count+1'b1;
        end
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [3:0] core_reset_pipe=0;
    always @(posedge core_clk or negedge lock_qualified)
        if(!lock_qualified)core_reset_pipe<=0;
        else core_reset_pipe<={core_reset_pipe[2:0],1'b1};
    wire cpu_reset_n=core_reset_pipe[3];
    wire rtc_clk;
    workstation_ae350_rtc u_rtc(.clk_50m(clk_50m),.reset_n(system_reset_n),.rtc_clk(rtc_clk));
    wire rom_clk,rom_reset_n,rom_write;
    wire [31:0] rom_address,rom_data,fetch_count,last_fetch;
    wire [1:0] rom_transfer;
    wire ram_clk,ram_reset_n,ram_write;
    wire [31:0] ram_address;
    wire [63:0] ram_read_data,ram_write_data;
    wire [1:0] ram_transfer;
    wire [2:0] ram_size;
    wire local_address=ram_address[31:13]==0 && (ram_size==0 ||
        (ram_size==1 && !ram_address[0]) || (ram_size==2 && ram_address[1:0]==0) ||
        (ram_size==3 && ram_address[2:0]==0));
    reg data_fault=0,error_second=0,unmapped_seen=0;
    wire ram_ready=!data_fault || error_second;
    always @(posedge ram_clk or negedge ram_reset_n)
        if(!ram_reset_n) begin data_fault<=0;error_second<=0;unmapped_seen<=0;end
        else if(data_fault && !error_second)error_second<=1;
        else if(ram_ready) begin
            data_fault<=ram_transfer[1] && !local_address;error_second<=0;
            if(ram_transfer[1] && !local_address)unmapped_seen<=1;
        end
    reg upper_seen=0,rom_seen=0;
    always @(posedge rom_clk or negedge rom_reset_n)
        if(!rom_reset_n)begin upper_seen<=0;rom_seen<=0;end
        else if(rom_transfer[1])begin
            rom_seen<=1;
            if(rom_address[31:16]==16'h8000 && rom_address[15:14]!=0)upper_seen<=1;
        end
    gw138k_boot_memory #(.ROM_BYTES(65536),.ROM_FILE("firmware/boot.mem")) u_boot_memory(
        .rom_clk(rom_clk),.rom_reset_n(rom_reset_n),.rom_address(rom_address),
        .rom_transfer(rom_transfer),.rom_data(rom_data),.fetch_count(fetch_count),.last_fetch(last_fetch),
        .ram_clk(ram_clk),.ram_reset_n(ram_reset_n),.ram_address(ram_address),
        .ram_transfer((ram_ready && local_address)?ram_transfer:2'b00),.ram_size(ram_size),
        .ram_write(ram_write),.ram_write_data(ram_write_data),.ram_read_data(ram_read_data));
    wire pclk,preset_n,psel,penable,pwrite;
    wire [31:0] paddr,pwdata;
    wire [3:0] pstrb;
    wire valid_address=paddr[31:8]==24'hf80000 && paddr[1:0]==0;
    reg [31:0] diagnostic[0:63];integer word_index;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] upper_sync=0,unmapped_sync=0;
    always @(posedge pclk or negedge preset_n)
        if(!preset_n) begin
            for(word_index=0;word_index<64;word_index=word_index+1)diagnostic[word_index]<=0;
            upper_sync<=0;unmapped_sync<=0;
        end else begin
            upper_sync<={upper_sync[0],upper_seen};unmapped_sync<={unmapped_sync[0],unmapped_seen};
            if(psel && penable && pwrite && valid_address && pstrb==4'hf && paddr[7:2]<58)
                diagnostic[paddr[7:2]]<=pwdata;
            diagnostic[58]<={31'd0,upper_sync[1]};diagnostic[59]<={31'd0,unmapped_sync[1]};
        end
    wire [31:0] prdata=valid_address?diagnostic[paddr[7:2]]:32'd0;
    wire pslverr=!valid_address || (pwrite && (pstrb!=4'hf || paddr[7:2]>=58));
    wire [2047:0] source_words;
    genvar w;generate for(w=0;w<64;w=w+1)begin:word_bank
        assign source_words[w*32+:32]=diagnostic[w];
    end endgenerate
    wire [511:0] uart_status_50mhz;
    wire [2079:0] full_snapshot_50mhz;
    wire snapshot_published_50mhz;
    wire [6:0] transport_health_50mhz;
    (* ASYNC_REG="TRUE",syn_preserve=1 *) reg [1:0] rom_health_sync=0,upper_health_sync=0;
    always @(posedge clk_50m or negedge system_reset_n)
        if(!system_reset_n)begin rom_health_sync<=0;upper_health_sync<=0;end
        else begin rom_health_sync<={rom_health_sync[0],rom_seen};upper_health_sync<={upper_health_sync[0],upper_seen};end
    // Preserve real top-level registers for GAO; an unused wire alias is swept.
    // A live digital output-drive observation, not pad/USB-UART reception.
    reg last_tx=1;
    reg [29:0] tx_edges=0;
    always @(posedge clk_50m or negedge system_reset_n)
        if(!system_reset_n) begin last_tx<=1;tx_edges<=0;end
        else begin
            last_tx<=debug_uart_tx;
            if(last_tx!=debug_uart_tx)tx_edges<=tx_edges+1'b1;
        end
    (* syn_keep=1,syn_preserve=1 *) reg [2207:0] status_50mhz;
    always @(posedge clk_50m or negedge system_reset_n)
        if(!system_reset_n)status_50mhz<=0;
        else status_50mhz<={power_on,lock_count[4:0],rom_health_sync[1],upper_health_sync[1],
            lock_qualified,system_reset_n,transport_health_50mhz,
            tx_edges,snapshot_published_50mhz,debug_uart_tx,
            32'ha1386401,`AE350_PROBE_USER_CODE,full_snapshot_50mhz};
    workstation_ae350_probe_uart #(.USER_CODE(`AE350_PROBE_USER_CODE)) u_uart(
        .clk_50m(clk_50m),.reset_n(system_reset_n),.pclk(pclk),.preset_n(preset_n),
        .source_words(source_words),.platform_flags({preset_n,cpu_reset_n,lock_qualified,pll_locked}),
        .full_snapshot_50mhz(full_snapshot_50mhz),.snapshot_published_50mhz(snapshot_published_50mhz),
        .tx(debug_uart_tx),.status_50mhz(uart_status_50mhz),.transport_health_50mhz(transport_health_50mhz));
    RiscV_AE350_SOC_Top u_cpu(
        .ROM_HRDATA(rom_data),.ROM_HREADY(1'b1),.ROM_HRESP(1'b0),.ROM_HADDR(rom_address),
        .ROM_HTRANS(rom_transfer),.ROM_HWRITE(rom_write),.ROM_HCLK(rom_clk),.ROM_HRSTN(rom_reset_n),
        .DDR_HRDATA(data_fault?64'd0:ram_read_data),.DDR_HREADY(ram_ready),.DDR_HRESP(data_fault),
        .DDR_HADDR(ram_address),.DDR_HBURST(),.DDR_HPROT(),.DDR_HSIZE(ram_size),.DDR_HTRANS(ram_transfer),
        .DDR_HWDATA(ram_write_data),.DDR_HWRITE(ram_write),.DDR_HCLK(ram_clk),.DDR_HRSTN(ram_reset_n),
        .APB_PRDATA(prdata),.APB_PREADY(1'b1),.APB_PSLVERR(pslverr),.APB_PADDR(paddr),
        .APB_PENABLE(penable),.APB_PSEL(psel),.APB_PWDATA(pwdata),.APB_PWRITE(pwrite),
        .APB_PPROT(),.APB_PSTRB(pstrb),.APB_PCLK(pclk),.APB_PRSTN(preset_n),
        .TCK_IN(1'b0),.TMS_IN(1'b1),.TRST_IN(1'b1),.TDI_IN(1'b0),.TDO_OUT(),.TDO_OE(),
        .CORE0_WFI_MODE(),.RTC_WAKEUP(),.CORE_CLK(core_clk),.DDR_CLK(bus_clk),
        .AHB_CLK(bus_clk),.APB_CLK(bus_clk),.RTC_CLK(rtc_clk),.POR_RSTN(cpu_reset_n),.HW_RSTN(cpu_reset_n));
endmodule
`default_nettype wire
