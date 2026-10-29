"""Native DDR BIST request-time pattern capture and frozen-reference equivalence."""

from pathlib import Path
from functools import lru_cache
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_baselines import load_baseline
from tools import workstation_custom_board as integration
from tools.workstation_synthesis_netlist import SynthesisNetlist


def synthesized_failure_cone(text):
    design = SynthesisNetlist(text, 'workstation_custom_138k_top')
    prefix = 'u_video/u_bist/'
    cells = {name: cell for name, cell in design.cells.items() if name.startswith(prefix)}
    drivers = {}
    for name, cell in cells.items():
        kind = cell['kind']
        outputs = (('Q',) if kind.startswith('DFF') else ('F',) if kind.startswith('LUT') else
                   ('O',) if kind == 'INV' else ('SUM', 'COUT') if kind == 'ALU' else
                   ('V',) if kind == 'VCC' else ('G',) if kind == 'GND' else ())
        if not outputs:
            raise ValueError('unreviewed BIST primitive: ' + kind)
        for pin in outputs:
            if pin in cell['ports']:
                net = design.pin(name, pin)
                if net in drivers and drivers[net] != (name, pin):
                    raise ValueError('multiple BIST drivers: ' + net)
                drivers[net] = (name, pin)

    @lru_cache(None)
    def cone(net):
        if net not in drivers:
            return frozenset(), 0
        name, output = drivers[net]
        cell = cells[name]
        kind = cell['kind']
        if kind.startswith('DFF'):
            return frozenset((name,)), 0
        if kind in ('VCC', 'GND'):
            return frozenset(), 0
        inputs = (('I',) if kind == 'INV' else
                  tuple('I' + str(index) for index in range(int(kind[3:]))) if kind.startswith('LUT') else
                  tuple(pin for pin in ('I0', 'I1', 'I2', 'I3', 'CIN') if pin in cell['ports']))
        paths = [cone(design.pin(name, pin)) for pin in inputs]
        return (frozenset().union(*(sources for sources, depth in paths)),
                max(depth for sources, depth in paths) + int(kind == 'ALU'))

    failed = [name for name, cell in cells.items() if cell['kind'].startswith('DFF') and
              re.fullmatch(re.escape(prefix) + r'failed_s\d+', name)]
    if len(failed) != 1:
        raise ValueError('BIST failure register inventory changed')
    paths = [cone(design.pin(failed[0], pin)) for pin in ('D', 'CE') if pin in cells[failed[0]]['ports']]
    sources = sorted(frozenset().union(*(entries for entries, depth in paths)))
    return dict(address_sources=[name for name in sources if name.startswith(prefix + 'address_')],
                expected_sources=[name for name in sources if name.startswith(prefix + 'expected_rdata_')],
                maximum_alu_depth=max(depth for entries, depth in paths))


TESTBENCH = r'''
module tb_workstation_ddr_bist;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst_n = 0;
    reg req_ready = 0;
    reg rsp_valid = 0;
    reg [255:0] rsp_data = 0;
    wire req_valid, req_write, done, failed;
    wire [28:0] req_addr, first_error_addr;
    wire [255:0] req_wdata;
    wire [31:0] error_count;
    wire reference_req_valid, reference_req_write, reference_done, reference_failed;
    wire [28:0] reference_req_addr, reference_first_error_addr;
    wire [255:0] reference_req_wdata;
    wire [31:0] reference_error_count;
    ddr3_bist #(.BURSTS(8), .TIMEOUT_CYCLES(31)) candidate (.*);
    ddr3_bist_reference #(.BURSTS(8), .TIMEOUT_CYCLES(31)) reference (
        .clk(clk), .rst_n(rst_n), .req_ready(req_ready),
        .rsp_valid(rsp_valid), .rsp_data(rsp_data),
        .req_valid(reference_req_valid), .req_write(reference_req_write),
        .req_addr(reference_req_addr), .req_wdata(reference_req_wdata),
        .done(reference_done), .failed(reference_failed),
        .error_count(reference_error_count), .first_error_addr(reference_first_error_addr)
    );
    reg [255:0] memory [0:7];
    reg pending;
    reg [255:0] pending_data, captured_expected;
    integer pending_delay, cycle_count, read_count, write_count;
    integer scenario, lane, check_count = 0, capture_count = 0;
    reg capture_expected, reset_injected;

    function [255:0] independent_pattern;
        input [28:0] word_address;
        input inverted;
        integer lane_index;
        reg [31:0] base_word;
        begin
            base_word = 32'ha0000000 | {3'b0, word_address};
            for (lane_index = 0; lane_index < 8; lane_index = lane_index + 1)
                independent_pattern[lane_index*32 +: 32] =
                    (base_word ^ (32'h9e3779b9 * (lane_index + 1))) ^
                    (inverted ? 32'hffffffff : 32'd0);
        end
    endfunction

    task check_outputs;
        begin
            if ({req_valid, req_write, req_addr, req_wdata, done,
                 failed, error_count, first_error_addr} !==
                {reference_req_valid, reference_req_write, reference_req_addr,
                 reference_req_wdata, reference_done, reference_failed,
                 reference_error_count, reference_first_error_addr})
                $fatal(1, "BIST cycle equivalence failed: scenario=%0d cycle=%0d",
                       scenario, cycle_count);
            check_count = check_count + 1;
        end
    endtask

    task reset_design;
        begin
            @(negedge clk);
            rst_n = 0;
            req_ready = 0;
            rsp_valid = 0;
            pending = 0;
            pending_delay = 0;
            read_count = 0;
            write_count = 0;
            cycle_count = 0;
            for (lane = 0; lane < 8; lane = lane + 1)
                memory[lane] = 0;
            repeat (2) begin
                @(posedge clk); #1;
                check_outputs();
            end
            @(negedge clk);
            rst_n = 1;
        end
    endtask

    initial begin
        for (scenario = 0; scenario < 6; scenario = scenario + 1) begin
            reset_injected = 0;
            reset_design();
            while (!done && cycle_count < 2000) begin
                @(negedge clk);
                req_ready = scenario != 3 && (cycle_count % 7 != 0) &&
                            (cycle_count % 7 != 2);
                rsp_valid = pending && pending_delay == 0 && scenario != 4;
                rsp_data = pending_data;
                if (scenario == 2 && rsp_valid && read_count == 1) begin
                    candidate.error_count = 32'hfffffffe;
                    reference.error_count = 32'hfffffffe;
                end
                @(posedge clk);
                capture_expected = req_valid && req_ready && !req_write;
                if (capture_expected) captured_expected = req_wdata;
                if (rsp_valid) pending = 0;
                if (req_valid && req_ready) begin
                    if (req_wdata !== independent_pattern(req_addr, read_count >= 8))
                        $fatal(1, "BIST pattern changed");
                    if (req_write) begin
                        memory[req_addr >> 3] = req_wdata;
                        write_count = write_count + 1;
                    end else begin
                        if (pending) $fatal(1, "BIST multiple outstanding reads");
                        pending = 1;
                        pending_delay = 2 + read_count % 5;
                        pending_data = memory[req_addr >> 3];
                        if (scenario == 1 || scenario == 2)
                            pending_data[(read_count % 8)*32 + read_count % 32] =
                                ~pending_data[(read_count % 8)*32 + read_count % 32];
                        read_count = read_count + 1;
                    end
                end
                if (pending_delay > 0) pending_delay = pending_delay - 1;
                #1;
                check_outputs();
                if (capture_expected) begin
                    if (candidate.expected_rdata !== captured_expected)
                        $fatal(1, "BIST request-time expected pattern capture changed");
                    capture_count = capture_count + 1;
                end
                cycle_count = cycle_count + 1;
                if (scenario == 5 && !reset_injected && read_count == 3 && pending) begin
                    reset_design();
                    reset_injected = 1;
                end
            end
            if (!done) $fatal(1, "BIST failed to terminate");
            if ((scenario == 0 || scenario == 5) && (failed || error_count != 0))
                $fatal(1, "BIST clean or reset recovery failed");
            if ((scenario == 0 || scenario == 1 || scenario == 2 || scenario == 5) &&
                (write_count != 16 || read_count != 16))
                $fatal(1, "BIST did not complete both patterns");
            if (scenario == 1 && (!failed || error_count != 16 || first_error_addr != 0))
                $fatal(1, "BIST lane corruption reporting changed");
            if (scenario == 2 && (!failed || error_count != 32'hffffffff))
                $fatal(1, "BIST error counter saturation changed");
            if ((scenario == 3 || scenario == 4) &&
                (!failed || error_count != 1 || first_error_addr != 0))
                $fatal(1, "BIST command or response watchdog changed");
            repeat (4) begin
                @(negedge clk); req_ready = 1; rsp_valid = 1; rsp_data = 0;
                @(posedge clk); #1; check_outputs();
                if (!done || req_valid) $fatal(1, "BIST terminal state changed");
            end
        end
        $display("PASS native DDR BIST: %0d cycle comparisons, %0d request captures; six scenarios",
                 check_count, capture_count);
        $finish;
    end
endmodule
'''


class NativeDdrBist(unittest.TestCase):
    def test_native_profile_selects_only_versioned_bist(self):
        native = 'rtl/memory/workstation_ddr_bist.v'
        self.assertIn(native, integration.NATIVE_SOURCES)
        self.assertEqual(integration.REPLACED_INPUTS['src/memory/ddr3_bist.v'], native)

    def reference_inputs(self, stage):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        original = baseline.read_bytes('src/memory/ddr3_bist.v').decode()
        anchor = 'module ddr3_bist #('
        self.assertEqual(original.count(anchor), 1)
        header = stage / 'src/memory/ddr_address_map.vh'
        header.parent.mkdir(parents=True)
        header.write_bytes(baseline.read_bytes('src/memory/ddr_address_map.vh'))
        reference = stage / 'reference.v'
        reference.write_text(original.replace(anchor, 'module ddr3_bist_reference #(', 1))
        return reference

    def test_all_cycles_match_frozen_reference_with_faults_and_backpressure(self):
        with tempfile.TemporaryDirectory(prefix='native-ddr-bist-') as directory:
            stage = Path(directory)
            reference = self.reference_inputs(stage)
            bench = stage / 'bench.sv'
            bench.write_text(TESTBENCH)
            executable = stage / 'simulation'
            compilation = subprocess.run([
                'iverilog', '-g2012', '-I', str(stage), '-s', 'tb_workstation_ddr_bist',
                '-o', str(executable), str(ROOT / 'rtl/memory/workstation_ddr_bist.v'),
                str(reference), str(bench),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            simulation = subprocess.run(['vvp', str(executable)], capture_output=True,
                                        text=True, timeout=30)
            self.assertEqual(simulation.returncode, 0, simulation.stdout + simulation.stderr)
            self.assertIn('PASS native DDR BIST:', simulation.stdout)
            print(simulation.stdout.strip())

    @unittest.skipUnless(shutil.which('yosys'), 'Yosys is required for sequential equivalence')
    def test_inductive_output_equivalence_and_expected_pattern_invariant(self):
        original = (ROOT / 'rtl/memory/workstation_ddr_bist.v').read_text()
        self.assertEqual(original.count('endmodule'), 1)
        invariant = ('    always @* assert (state != READ_RESPONSE || '
                     'expected_rdata == test_pattern(address, inverted));\n')
        cases = [('single', 1, 1, False), ('two', 2, 2, False),
                 ('eight', 8, 31, False), ('production', None, None, False),
                 ('corrupted_capture', 8, 31, True)]
        for name, bursts, timeout, corrupted in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix='native-bist-formal-') as directory:
                stage = Path(directory)
                reference = self.reference_inputs(stage)
                candidate_text = original.replace('endmodule', invariant + 'endmodule', 1)
                if corrupted:
                    anchor = 'expected_rdata <= test_pattern(address, inverted);'
                    self.assertEqual(candidate_text.count(anchor), 1)
                    candidate_text = candidate_text.replace(
                        anchor, "expected_rdata <= test_pattern(address, inverted) ^ 256'd1;", 1)
                candidate = stage / 'candidate.v'
                candidate.write_text(candidate_text)
                blacklist = stage / 'blacklist.txt'
                blacklist.write_text('mismatch\n')
                commands = [f'read_verilog -formal -sv -I{stage} {reference} {candidate}']
                if bursts is not None:
                    commands.extend(f'chparam -set BURSTS {bursts} -set TIMEOUT_CYCLES {timeout} {module}'
                                    for module in ('ddr3_bist_reference', 'ddr3_bist'))
                commands.extend([
                    'proc', 'opt_clean',
                    f'equiv_make -make_assert -blacklist {blacklist} '
                    'ddr3_bist_reference ddr3_bist equivalent',
                    'prep -top equivalent', 'async2sync', 'dffunmap',
                    'sat -prove-asserts -set-init-zero -seq 4 -tempinduct -verify',
                ])
                script = stage / 'proof.ys'
                script.write_text('\n'.join(commands) + '\n')
                proof = subprocess.run(['yosys', '-Q', '-T', '-s', str(script)],
                                       capture_output=True, text=True, timeout=120)
                if corrupted:
                    self.assertNotEqual(proof.returncode, 0, 'corrupted expected pattern was accepted')
                else:
                    self.assertEqual(proof.returncode, 0, proof.stdout[-3000:] + proof.stderr)
                    self.assertIn('Induction step proven: SUCCESS!', proof.stdout)
                print(f'PASS native DDR BIST induction: {name}; mutant rejected={corrupted}')


if __name__ == '__main__':
    unittest.main()
