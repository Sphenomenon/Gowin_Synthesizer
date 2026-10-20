"""Insert the selected physical MMIO pipeline into existing transaction fixtures."""
def attach(text):
    anchor='    push2_usb_a_control dut('
    connection='.select(sel),.write(wr),.address(addr),.wdata(wd),.ready(ready),.rdata(rd)'
    if text.count(anchor)!=1 or text.count(connection)!=1:
        raise ValueError('unexpected MMIO fixture connection')
    declarations='''    wire control_sel,control_wr,control_ready;
    wire [7:0] control_addr;wire [31:0] control_wd,control_rd;
    gw138k_mmio_pipeline mmio_pipeline(
        .clk(clk),.reset_n(rn),.select_i(sel),.write_i(wr),.address_i(addr),.wdata_i(wd),
        .ready_o(ready),.rdata_o(rd),.select_o(control_sel),.write_o(control_wr),
        .address_o(control_addr),.wdata_o(control_wd),.ready_i(control_ready),.rdata_i(control_rd));
'''
    return text.replace(anchor,declarations+anchor,1).replace(connection,
        '.select(control_sel),.write(control_wr),.address(control_addr),.wdata(control_wd),.ready(control_ready),.rdata(control_rd)',1)


def pixel(text):
    text=text.replace('module tb_push_pixel_mmio;','module tb_push_pixel_mmio_bridge;',1)
    text=text.replace('PASS push_pixel_mmio:', 'PASS push_pixel_mmio_bridge:',1)
    anchor='  push2_usb_a_control dut('
    connection='.select(select),.write(write_bus),.address(address),.wdata(wdata),.ready(ready),.rdata(rdata)'
    if text.count(anchor)!=1 or text.count(connection)!=1:
        raise ValueError('unexpected pixel MMIO fixture')
    declarations='''  wire control_sel,control_wr,control_ready;
  wire [7:0] control_addr;wire [31:0] control_wd,control_rd;
  gw138k_mmio_pipeline mmio_pipeline(
      .clk(clk),.reset_n(reset_n),.select_i(select),.write_i(write_bus),.address_i(address),.wdata_i(wdata),
      .ready_o(ready),.rdata_o(rdata),.select_o(control_sel),.write_o(control_wr),
      .address_o(control_addr),.wdata_o(control_wd),.ready_i(control_ready),.rdata_i(control_rd));
  reg [17:0] committed_index;reg [15:0] committed_pixel;
  always @(posedge clk)if(reset_n && control_sel && control_ready && !control_wr && control_addr==8'h2c)begin
      committed_index<=dut.pixel_index;
      committed_pixel<=dut.pixel_index[9:0]<960 ? expected : 16'd0;
  end
'''
    text=text.replace(anchor,declarations+anchor,1).replace(connection,
        '.select(control_sel),.write(control_wr),.address(control_addr),.wdata(control_wd),.ready(control_ready),.rdata(control_rd)',1)
    return text.replace('old_index=dut.pixel_index;want=old_index[9:0]<960 ? expected : 16\'d0;',
        'old_index=committed_index;want=committed_pixel;',1)
