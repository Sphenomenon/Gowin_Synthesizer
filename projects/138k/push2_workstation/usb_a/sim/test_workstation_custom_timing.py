"""Pinned native adaptations and cycle-free arithmetic equivalence."""

from pathlib import Path
import hashlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_custom_timing as timing
from tools import workstation_custom_flash as flash
from tools.workstation_baselines import load_baseline
from tools.workstation_resource_timing import tf_dma, voice_count


class NativeTiming(unittest.TestCase):
    def test_vector_velocity_mapping_matches_every_midi_value(self):
        text = (ROOT / 'rtl/audio/scope_vec/scope_vec_engine.sv').read_text()
        expression = re.search(r'velocity\[j\]<=([^;]*event_velocity_i[^;]*);', text)[1]
        testbench = '''module tb_native_vector_velocity;
reg [6:0] event_velocity_i;
wire [15:0] actual=EXPRESSION;
integer velocity_index;
initial begin
    for(velocity_index=0;velocity_index<128;velocity_index=velocity_index+1) begin
        event_velocity_i=7'(velocity_index);#1;
        if(actual!==(velocity_index==127 ? 16'd32767 : 16'(velocity_index*258+(velocity_index>=64))))
            $fatal(1,"vector velocity mapping changed");
    end
    $display("PASS native vector velocity: all 128 MIDI values, no added latency");
    $finish;
end
endmodule
'''.replace('EXPRESSION', expression)
        with tempfile.TemporaryDirectory(prefix='native-vector-velocity-') as directory:
            source = Path(directory) / 'test.sv'
            executable = Path(directory) / 'simulation'
            source.write_text(testbench)
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_native_vector_velocity', '-o', str(executable),
                                          str(source)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            simulation = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(simulation.returncode, 0, simulation.stdout + simulation.stderr)
            print(simulation.stdout.strip())

    def original_sources(self):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        sources = {name: baseline.read_bytes(name) for name in timing.INPUTS}
        name = 'src/storage/tf_audio_ddr_dma.v'
        sources[name] = tf_dma(sources[name].decode()).encode()
        name = 'legacy/rtl/audio/unified_oscillator_engine.sv'
        sources[name] = voice_count(sources[name].decode()).encode()
        return sources

    def test_exact_parent_identities_and_fail_closed_drift(self):
        sources = self.original_sources()
        with tempfile.TemporaryDirectory(prefix='native-timing-adaptations-') as directory:
            stage = Path(directory)
            for name, original in sources.items():
                self.assertEqual(hashlib.sha256(original).hexdigest(), timing.INPUTS[name])
                source = stage / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(original)
            evidence = timing.apply(stage)
            self.assertEqual(set(evidence), set(timing.INPUTS))
            for name, record in evidence.items():
                self.assertEqual(hashlib.sha256((stage / name).read_bytes()).hexdigest(), record['after'])
                self.assertEqual(record['before'], timing.INPUTS[name])
            with self.assertRaisesRegex(ValueError, 'input identity drifted'):
                timing.apply(stage)
        for name, original in sources.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                timing.TRANSFORMS[name](original.decode().replace('wire [2:0] pll_lpfres;', 'wire [2:0] changed;')
                                        if 'audio_clock' in name else '')

    def test_parallel_increment_matches_full_width_addition(self):
        sources = self.original_sources()
        adapted = timing.byte_increment(sources['src/storage/tf_audio_ddr_dma.v'].decode())
        function = re.search(r'    function \[31:0\] add_byte_count;.*?    endfunction', adapted, re.S)[0]
        sine = timing.sine_address(sources['legacy/rtl/audio/sine_interp.sv'].decode())
        expression = re.search(r'next_address_s0 <= (\{.*?\});', sine)[1]
        testbench = '''module tb_native_parallel_increment;
reg [31:0] value, phase_i;
reg [5:0] increment;
reg [31:0] expected;
reg [31:0] random_q = 32'hc1102521;
wire [10:0] next_address = EXPRESSION;
integer vector_index, increment_index;
FUNCTION
task verify;
begin
    expected = value + {26'd0,increment};
    if(add_byte_count(value,increment)!==expected) $fatal(1,"byte increment mismatch");
end
endtask
initial begin
    for(vector_index=0;vector_index<2048;vector_index=vector_index+1) begin
        phase_i={11'(vector_index),21'd0}; #1;
        if(next_address!==11'(vector_index+1)) $fatal(1,"sine address mismatch");
    end
    for(increment_index=0;increment_index<64;increment_index=increment_index+1) begin
        increment=6'(increment_index);
        value=32'hffffffff; verify();
        value=32'h000000ff; verify();
        value=32'h0000ffff; verify();
        value=32'h00ffffff; verify();
        value=32'h7fffffff; verify();
        for(vector_index=0;vector_index<4096;vector_index=vector_index+1) begin
            random_q={random_q[30:0],random_q[31]^random_q[21]^random_q[1]^random_q[0]};
            value=random_q; verify();
        end
    end
    $display("PASS native parallel increments: 262464 byte vectors and all 2048 sine addresses");
    $finish;
end
endmodule
'''.replace('EXPRESSION', expression).replace('FUNCTION', function)
        with tempfile.TemporaryDirectory(prefix='native-parallel-increments-') as directory:
            source = Path(directory) / 'test.sv'
            executable = Path(directory) / 'simulation'
            source.write_text(testbench)
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_native_parallel_increment', '-o', str(executable),
                                          str(source)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            simulation = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(simulation.returncode, 0, simulation.stdout + simulation.stderr)
            self.assertIn('PASS native parallel increments', simulation.stdout)
            print(simulation.stdout.strip())

    def test_telemetry_usb_reset_keeps_default_and_other_observers(self):
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        original = self.original_sources()['src/push2/gw138k_push_performance_uart.sv'].decode()
        adapted = timing.telemetry_usb_reset(original)
        with self.assertRaisesRegex(ValueError, 'anchor drifted'):
            timing.telemetry_usb_reset(original.replace('.source_valid(&usb_divider)', '.source_valid(1\'b0)'))
        with tempfile.TemporaryDirectory(prefix='native-telemetry-usb-reset-') as directory:
            stage = Path(directory)
            reference, candidate = stage / 'reference.sv', stage / 'candidate.sv'
            reference.write_text(original.replace('module gw138k_push_performance_uart #(', 'module telemetry_reference #('))
            candidate.write_text(adapted)
            support = []
            for name in ('src/migration/gw138k_stream_cdc.sv', 'src/control/uart_tx.v'):
                path = stage / Path(name).name
                path.write_bytes(baseline.read_bytes(name))
                support.append(path)
            fixture = ROOT / 'sim/cdc/tb_native_telemetry_usb_reset.sv'
            executable = stage / 'simulation'
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_native_telemetry_usb_reset',
                '-o', str(executable), *map(str, [reference, candidate, *support, fixture])],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            simulation = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=60)
            self.assertEqual(simulation.returncode, 0, simulation.stdout + simulation.stderr)
            self.assertIn('default_equal=1 local_grant=2 stopped_release=1 raw_flush=1 fresh_restart=1 uart_cpu_audio_preserved=1', simulation.stdout)
            print(simulation.stdout.strip())

    def test_exceptions_only_terminate_at_audited_receiver_entries(self):
        constraints = timing.constraints()
        exceptions = [line for line in constraints.splitlines() if line.startswith('set_false_path')]
        self.assertEqual(len(exceptions), len(timing.RESET_CHAINS) + len(timing.THREE_STAGE_RESET_CHAINS) + len(timing.LEVEL_CHAINS))
        for line in exceptions:
            self.assertRegex(line, r'^set_false_path -to \[get_pins \{u_native_usb/')
            self.assertTrue(line.endswith('/CLEAR}]') or line.endswith('/D}]'))
        self.assertNotIn('set_clock_groups', constraints)
        exceptions = '\n'.join(line for line in constraints.splitlines() if line.startswith('set_'))
        self.assertNotIn('get_clocks', exceptions)
        self.assertEqual(sum('-from_clock [get_clocks {cpu_core100}]' in line
                             for line in constraints.splitlines() if line.startswith('report_timing ')), 2)
        self.assertIn('set_min_delay 1.800 -from [get_pins', constraints)
        runtime = timing.constraints(runtime_reset=True)
        added = set(runtime.splitlines()) - set(constraints.splitlines())
        asynchronous = {
            'u_managed/startup_compute',
            'u_managed/runtime/startup_compute', 'u_managed/runtime/startup_memory',
            'u_managed/runtime/startup_serial',
            'u_managed/runtime/clocks/reference_48_monitor/startup_source',
            'u_managed/runtime/clocks/reference_44_monitor/startup_source',
            'u_managed/runtime/clocks/selected_monitor/startup_source',
            'u_tf_audio/startup_compute', 'u_tf_audio/startup_memory',
            'u_tf_audio/frames/startup_compute', 'output_safe_sync',
            'u_runtime/g_usb_cdc_reset.usb_ready',
        }
        synchronous = {
            'u_managed/startup_control', 'u_managed/runtime/startup_control',
            'u_managed/runtime/clocks/startup_control', 'u_tf_audio/startup_source',
            'u_tf_audio/frames/startup_source',
        }
        self.assertEqual({stem for stem, _, _ in timing.RUNTIME_GRANT_CHAINS}, asynchronous | synchronous)
        self.assertEqual({stem for stem, source, destination in timing.RUNTIME_GRANT_CHAINS
                          if source != destination}, asynchronous)
        expected = {f'set_false_path -to [get_pins {{{stem}_0_s*/D}}]' for stem in asynchronous}
        expected.update(f'set_max_delay 2.000 -from [get_pins {{{stem}_0_s*/Q}}] '
                        f'-to [get_pins {{{stem}_1_s*/D}}]' for stem in asynchronous | synchronous)
        self.assertEqual(added, expected)
        self.assertEqual(len(added), 29)
        # Existing raw assertion/CLEAR policy is unchanged. No functional,
        # second-stage, clock-wide or broad prefix exception is added.
        self.assertEqual([line for line in runtime.splitlines() if '/CLEAR' in line],
                         [line for line in constraints.splitlines() if '/CLEAR' in line])
        self.assertTrue(set(constraints.splitlines()).issubset(runtime.splitlines()))
        with self.assertRaisesRegex(ValueError, 'selection must be boolean'):
            timing.constraints(runtime_reset=1)

    def test_parallel_voice_control_preserves_allocation_and_gain_cycles(self):
        original = self.original_sources()['legacy/rtl/audio/unified_oscillator_engine.sv'].decode()
        adapted = timing.voice_controls(original)
        control = re.search(r'  wire \[31:0\] allocation_candidates.*?  assign allocation_index\[4\]=[^\n]*;', adapted, re.S)[0]
        allocation = re.search(r'      if \(!allocation_found.*?      end\n', original, re.S)[0]
        expression = re.search(r'        expression_gain_q8\[allocation_index\] <=.*?\n      end else begin',
                               original, re.S)[0].removesuffix('\n      end else begin')
        expression = expression.replace('expression_gain_q8', 'expected_gain').replace('allocation_index', 'expected_index')
        testbench = '''module tb_native_voice_controls;
reg clk_i=0,rst_ni=0,accepted_event=0,event_note_on_i=0,accepted_expression=0;
reg [31:0] allocated_mask_o=0,expression_select=0;
reg [4:0] maximum_voice_index=0;
reg [6:0] expression_value_i=0;
reg [7:0] expression_gain_q8[0:31],expected_gain[0:31];
wire [4:0] allocation_index;
wire allocation_found;
reg [4:0] expected_index;
reg expected_found;
reg [31:0] random_q=32'hc1102523;
integer vector_index,voice_index;
CONTROL
always #5 clk_i=~clk_i;
always @* begin
    expected_found=0;expected_index=0;
    for(integer index=0;index<32;index=index+1) begin
        ALLOCATION
    end
end
always @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
        for(integer voice=0;voice<32;voice=voice+1) expected_gain[voice]<=8'd128;
    end else if(accepted_event && event_note_on_i) begin
        EXPRESSION
    end
end
initial begin
    for(vector_index=0;vector_index<50000;vector_index=vector_index+1) begin
        @(negedge clk_i);
        random_q={random_q[30:0],random_q[31]^random_q[21]^random_q[1]^random_q[0]};
        rst_ni=vector_index>1 && vector_index%503!=0;
        maximum_voice_index=5'(vector_index);
        allocated_mask_o=random_q;
        if(vector_index<1024) allocated_mask_o=~(32'b1 << (vector_index%32));
        if(vector_index%67==0) allocated_mask_o=32'hffffffff;
        if(vector_index%71==0) allocated_mask_o=0;
        expression_select={random_q[15:0],random_q[31:16]};
        expression_value_i=7'(vector_index);
        {accepted_event,event_note_on_i,accepted_expression}=3'(vector_index>>2);
        #1;
        if(allocation_found!==expected_found || allocation_index!==expected_index)
            $fatal(1,"allocation priority changed");
        if(!rst_ni) begin
            for(voice_index=0;voice_index<32;voice_index=voice_index+1)
                if(expression_gain_q8[voice_index]!==8'd128) $fatal(1,"gain asynchronous reset changed");
        end
        @(posedge clk_i);#1;
        for(voice_index=0;voice_index<32;voice_index=voice_index+1)
            if(expression_gain_q8[voice_index]!==expected_gain[voice_index]) $fatal(1,"gain write cycle changed");
    end
    $display("PASS native voice controls: 50000 allocation/priority/reset/write-cycle vectors, all 32 voices");
    $finish;
end
endmodule
'''.replace('CONTROL', control).replace('ALLOCATION', allocation.replace('allocation_found', 'expected_found').replace('allocation_index', 'expected_index')).replace('EXPRESSION', expression)
        with tempfile.TemporaryDirectory(prefix='native-voice-controls-') as directory:
            source = Path(directory) / 'test.sv'
            executable = Path(directory) / 'simulation'
            source.write_text(testbench)
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_native_voice_controls', '-o', str(executable),
                                          str(source)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            simulation = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=90)
            self.assertEqual(simulation.returncode, 0, simulation.stdout + simulation.stderr)
            self.assertIn('PASS native voice controls', simulation.stdout)
            print(simulation.stdout.strip())

    def test_pll_control_tuple_is_atomic_and_asserts_reset_asynchronously(self):
        original = self.original_sources()['src/migration/gw138k_audio_clock.v'].decode()
        adapted = timing.audio_pll(original)
        control = re.search(r'\(\* syn_preserve=1 \*\) reg \[9:0\] pll_control=.*?assign \{pll_reset,pll_icpsel,pll_lpfres\}=pll_control;', adapted, re.S)[0]
        testbench = '''module tb_native_pll_tuple;
reg init_clk=0, reset=0, helper_reset=0;
reg [5:0] helper_icpsel=0;
reg [2:0] helper_lpfres=0;
wire pll_reset;
wire [5:0] pll_icpsel;
wire [2:0] pll_lpfres;
reg [9:0] expected;
reg [31:0] random_q=32'hc1102521;
integer tuple_index;
always #10 init_clk=~init_clk;
CONTROL
always @(posedge init_clk) begin
    expected=reset ? 10'b1000000000 : {helper_reset,helper_icpsel,helper_lpfres};
    #1;
    if({pll_reset,pll_icpsel,pll_lpfres}!==expected) $fatal(1,"PLL tuple latency/coherence mismatch");
end
initial begin
    #3; reset=1; #1;
    if({pll_reset,pll_icpsel,pll_lpfres}!==10'b1000000000) $fatal(1,"PLL asynchronous reset mismatch");
    reset=0;
    for(tuple_index=0;tuple_index<2048;tuple_index=tuple_index+1) begin
        @(negedge init_clk);
        random_q={random_q[30:0],random_q[31]^random_q[21]^random_q[1]^random_q[0]};
        {helper_reset,helper_icpsel,helper_lpfres}=random_q[9:0];
        if(tuple_index%17==0) begin
            #2; reset=1; #1;
            if({pll_reset,pll_icpsel,pll_lpfres}!==10'b1000000000) $fatal(1,"PLL midcycle reset mismatch");
            #2; reset=0;
        end
    end
    @(negedge init_clk);
    $display("PASS native PLL tuple: 2048 atomic words and asynchronous midcycle resets");
    $finish;
end
endmodule
'''.replace('CONTROL', control)
        with tempfile.TemporaryDirectory(prefix='native-pll-tuple-') as directory:
            source = Path(directory) / 'test.sv'
            executable = Path(directory) / 'simulation'
            source.write_text(testbench)
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_native_pll_tuple', '-o', str(executable), str(source)],
                                         capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            simulation = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(simulation.returncode, 0, simulation.stdout + simulation.stderr)
            self.assertIn('PASS native PLL tuple', simulation.stdout)
            print(simulation.stdout.strip())

    def test_model_flash_uses_existing_validated_shared_pad_contract(self):
        selected = flash.reviewed_cst(ROOT)
        self.assertEqual(len(re.findall('IO_LOC ', selected)), 6)
        self.assertIn('set_input_delay 15.000', flash.SDC)


if __name__ == '__main__':
    unittest.main()
