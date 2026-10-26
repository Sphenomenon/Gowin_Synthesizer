from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline


MEMORY_MODEL = r'''
`timescale 1ns/1ps
module ddr3_platform #(parameter ENABLE_CALIBRATION=1) (
    input wire clk_50m, rst_n,
    output reg ui_clk=0,
    output wire ui_rst_n, calib_done, pll_locked,
    input wire [2:0] app_cmd,
    input wire app_en,
    input wire [28:0] app_addr,
    output wire app_rdy,
    input wire [255:0] app_wdata,
    input wire [31:0] app_wmask,
    input wire app_wren, app_wend,
    output wire app_wrdy,
    output reg [255:0] app_rdata=0,
    output reg app_rvalid=0,
    output wire app_rend,
    output wire [14:0] ddr_addr,
    output wire [2:0] ddr_bank,
    output wire ddr_cs, ddr_ras, ddr_cas, ddr_we,
    output wire ddr_ck, ddr_ck_n, ddr_cke, ddr_odt, ddr_reset_n,
    output wire [3:0] ddr_dm,
    inout wire [31:0] ddr_dq,
    inout wire [3:0] ddr_dqs, ddr_dqs_n
);
    always #5 ui_clk=~ui_clk;
    reg [7:0] cycles=0;
    reg [255:0] memory [0:15];
    assign pll_locked=rst_n && cycles>=4;
    assign calib_done=rst_n && ENABLE_CALIBRATION && cycles>=100;
    assign ui_rst_n=calib_done;
    assign app_rdy=ui_rst_n && cycles[1:0]!=1;
    assign app_wrdy=ui_rst_n && cycles[2:0]!=2;
    assign app_rend=app_rvalid;
    always @(posedge ui_clk) begin
        if (!rst_n) cycles<=0;
        else if (cycles!=255) cycles<=cycles+1'b1;
        app_rvalid<=0;
        if (app_en && (!ui_rst_n || !app_rdy)) $fatal(1,"unaccepted command");
        if (app_wren && (!app_en || app_cmd!=0 || !app_wrdy || !app_wend))
            $fatal(1,"write data/command handshake separated");
        if (app_en) begin
            if (app_addr[2:0]!=0 || app_addr>=128) $fatal(1,"native address units");
            if (app_cmd==0) begin
                if (!app_wren || app_wmask!=0) $fatal(1,"write payload missing");
                memory[app_addr>>3]<=app_wdata;
            end else if (app_cmd==1) begin
                if (app_wren) $fatal(1,"write enabled during read");
                app_rdata<=memory[app_addr>>3];
                app_rvalid<=1;
            end else $fatal(1,"unsupported command");
        end
    end
endmodule
'''


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required')
class DdrDiagnostic(unittest.TestCase):
    def simulate(self, calibration):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        with tempfile.TemporaryDirectory(prefix='ddr-diagnostic-') as directory:
            output = Path(directory)
            for relative in ('src/memory/ddr3_bist.v', 'src/memory/ddr_address_map.vh',
                             'src/platform/reset_release.v'):
                destination = output / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(baseline.read_bytes(relative))
            (output / 'memory_model.sv').write_text(MEMORY_MODEL)
            success = r'''
                wait(dut.bist_done);
                repeat(12) @(negedge clk_50m);
                if (dut.bist_failed || dut.error_count!=0 ||
                    (dut.status_sync & 8'h3f)!=8'h1f) $fatal(1,"BIST failed");
            '''
            blocked = r'''
                wait(dut.reset_n);
                repeat(20) @(negedge clk_50m);
                previous_gray=dut.ui_gray_sync;
                repeat(30) begin
                    @(negedge clk_50m);
                    if (dut.ui_gray_sync!=previous_gray) transitions=transitions+1;
                    previous_gray=dut.ui_gray_sync;
                end
                if ((dut.status_sync & 8'h3f)!=8'h03 || dut.bist_done ||
                    dut.request_valid || transitions==0)
                    $fatal(1,"uncalibrated clock/status not independently observable");
            '''
            body = success if calibration else blocked
            (output / 'testbench.sv').write_text(r'''
                `timescale 1ns/1ps
                module testbench;
                    reg clk_50m=0;
                    always #10 clk_50m=~clk_50m;
                    wire flash_clk, flash_cs_n, flash_mosi, flash_wp_n, flash_hold_n;
                    reg [7:0] previous_gray;
                    integer transitions=0;
                    ddr_calibration_diagnostic dut(
                        .clk_50m(clk_50m), .flash_clk(flash_clk), .flash_cs_n(flash_cs_n),
                        .flash_mosi(flash_mosi), .flash_wp_n(flash_wp_n),
                        .flash_hold_n(flash_hold_n));
                    defparam dut.u_reset.HOLD_CYCLES=4;
                    defparam dut.u_bist.BURSTS=16;
                    defparam dut.u_bist.TIMEOUT_CYCLES=100;
                    defparam dut.u_memory.ENABLE_CALIBRATION=''' + str(int(calibration)) + r''';
                    initial begin
                        ''' + body + r'''
                        if ({flash_clk,flash_cs_n,flash_mosi,flash_wp_n,flash_hold_n}
                            !==5'b01011) $fatal(1,"Flash pins not idle");
                        $display("PASS DDR diagnostic calibration/handshake contract");
                        $finish;
                    end
                    initial begin #20000; $fatal(1,"simulation timeout"); end
                endmodule
            ''')
            sources = [ROOT / 'reports/hdmi_usb3_20261025/ddr_calibration_diagnostic.sv',
                       output / 'src/platform/reset_release.v', output / 'src/memory/ddr3_bist.v',
                       output / 'memory_model.sv', output / 'testbench.sv']
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'testbench',
                                       '-I', str(output), '-o', str(output / 'simulation'),
                                       *map(str, sources)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(['vvp', str(output / 'simulation')], capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS DDR diagnostic', result.stdout)

    def test_bist_commands_survive_independent_ready_stalls(self):
        self.simulate(True)

    def test_ui_clock_remains_observable_without_calibration(self):
        self.simulate(False)


if __name__ == '__main__':
    unittest.main()
