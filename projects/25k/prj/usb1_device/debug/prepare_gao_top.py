"""Create an optional observation copy, leaving the normal USB top unchanged."""
from pathlib import Path


def prepare():
    project = Path(__file__).resolve().parents[1]
    source = project / 'rtl/usb1_device_top.v'
    text = source.read_text()
    required = ('module usb1_device_top', 'wire [63:0] status', 'endmodule')
    if any(text.count(token) != 1 for token in required):
        raise ValueError('USB top changed: review the GAO adapter before generating it')
    added = '''
    // Added only to the optional generated GAO copy. The normal top is intact.
    wire [63:0] status_50mhz_raw;
    reg [63:0] status_50mhz /* synthesis syn_preserve=1 syn_keep=1 */;
    always @(posedge clk_50mhz) status_50mhz <= status_50mhz_raw;
    usb1_status_50mhz u_status_observer (
        .clk_50mhz(clk_50mhz), .usb_dp(usb1_dp), .usb_dm(usb1_dm),
        .stable_flags_async({status[15:12], status[9], status[6], status[5]}),
        .status_50mhz(status_50mhz_raw)
    );
'''
    destination = project / 'generated/usb1_device_gao_top.v'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(text.replace('endmodule', added + 'endmodule'))
    # Gowin enables only one SDC file. Keep board/PLL and GAO TCK clocks in
    # that same file; adding two SDCs silently disables the earlier one.
    sdc = project / 'generated/usb1_gao.sdc'
    sdc.write_text((project/'clock/usb1_clock.sdc').read_text() + '\n' +
                   (project/'debug/usb1_gao.sdc').read_text())
    # Post-synthesis GAO inserts the analyzer during PnR, after the standalone
    # synthesis process has finished. Keep the identical XML capture identity.
    (project/'debug/usb1_status.gao').write_bytes(
        (project/'debug/usb1_status.rao').read_bytes())
    print(destination)
    print(sdc)
    return destination


if __name__ == '__main__':
    prepare()
