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
    def test_envelope_lane_preserves_all_states_and_unsigned_boundaries(self):
        original = self.original_sources()['legacy/rtl/audio/unified_oscillator_engine.sv'].decode()
        adapted = timing.envelope_arithmetic(original)
        inputs = ['level', 'attack', 'decay', 'sustain', 'release']
        modules = []
        for name, source in [('reference', original), ('adapted', adapted)]:
            declarations = '\n'.join('input [23:0] envelope_update_'+stem+'_q24;' for stem in inputs)
            arithmetic = source[source.index('  function automatic [24:0] envelope_add24;'):
                                source.index('  assign updated_slot_phase')] if name == 'adapted' else source[
                                    source.index('  assign envelope_update_attack_sum ='):
                                    source.index('  assign updated_slot_phase')]
            combinational = re.search(r'  always @\* begin\n    envelope_next_level_q24.*?\n  end', source, re.S)[0]
            constants = '\n'.join(line for line in source.splitlines() if 'localparam logic' in line and
                                  ('ENVELOPE_' in line or 'MAXIMUM_LEVEL_Q24' in line))
            modules.append('module '+name+'(envelope_update_state,'+
                           ','.join('envelope_update_'+s+'_q24' for s in inputs)+
                           ',envelope_next_state,envelope_next_level_q24,envelope_next_level_q18);\n'+
                           'input [2:0] envelope_update_state;\n'+declarations+'\n'+
                           'output reg [2:0] envelope_next_state;\noutput reg [23:0] envelope_next_level_q24;\n'+
                           'output reg [17:0] envelope_next_level_q18;\nwire [24:0] envelope_update_attack_sum;\n'+
                           constants+'\n'+arithmetic+'\n'+combinational+'\nendmodule\n')
        bench = '''module tb_envelope;
reg [2:0] state;
reg [23:0] level,attack,decay,sustain,release_step;
reg [31:0] rng=32'h138a2901;
wire [44:0] expected,actual;
reference r(state,level,attack,decay,sustain,release_step,expected[44:42],expected[41:18],expected[17:0]);
adapted a(state,level,attack,decay,sustain,release_step,actual[44:42],actual[41:18],actual[17:0]);
integer i,j,k;
task randomize_value;
begin rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]}; end
endtask
task verify;
begin #1;if(actual!==expected) $fatal(1,"ADSR mismatch state=%d level=%h attack=%h decay=%h sustain=%h release=%h actual=%h expected=%h",state,level,attack,decay,sustain,release_step,actual,expected);end
endtask
initial begin
 for(i=0;i<200000;i=i+1)begin
  randomize_value();state=rng[2:0];level=rng[31:8];
  randomize_value();attack=rng[31:8];randomize_value();decay=rng[31:8];
  randomize_value();sustain=rng[31:8];randomize_value();release_step=rng[31:8];verify();
 end
 for(k=0;k<8;k=k+1)for(i=0;i<128;i=i+1)for(j=0;j<8;j=j+1)begin
  state=3'(k);level=24'hffff80+24'(i);sustain=level-24'(j);
  attack=24'(j);decay=24'(j);release_step=level-24'(j);verify();
  level=24'(i);sustain=level+24'(j);attack=24'hffffff-24'(j);release_step=0;verify();
 end
 $display("PASS ADSR lane: 216384 state/boundary vectors, unchanged combinational interface");$finish;
end
endmodule
'''
        with tempfile.TemporaryDirectory(prefix='native-envelope-') as directory:
            source, executable = Path(directory)/'test.sv', Path(directory)/'simulation'
            source.write_text('\n'.join(modules)+bench)
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_envelope', '-o', str(executable),
                                          str(source)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stderr)
            simulation = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=60)
            self.assertEqual(simulation.returncode, 0, simulation.stdout+simulation.stderr)
            print(simulation.stdout.strip())

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

    def test_exceptions_only_terminate_at_audited_receiver_entries(self):
        constraints = timing.constraints()
        exceptions = [line for line in constraints.splitlines() if line.startswith('set_false_path')]
        self.assertEqual(len(exceptions), len(timing.RESET_CHAINS) + len(timing.THREE_STAGE_RESET_CHAINS) + len(timing.LEVEL_CHAINS))
        for line in exceptions:
            self.assertRegex(line, r'^set_false_path -to \[get_pins \{u_native_usb/')
            self.assertTrue(line.endswith('/CLEAR}]') or line.endswith('/D}]'))
        self.assertNotIn('set_clock_groups', constraints)
        self.assertNotIn('get_clocks', constraints)
        self.assertIn('set_min_delay 0.800 -from [get_pins', constraints)

    def test_ring_increment_matches_power_of_two_and_general_wrap(self):
        original = self.original_sources()['src/storage/tf_audio_ddr_dma.v'].decode()
        adapted = timing.byte_increment(original)
        functions = '\n'.join(re.search(r'    function \[31:0\] '+name+r';.*?    endfunction',
                                        adapted, re.S)[0] for name in ('add_byte_count', 'advance_ring'))
        reference = re.search(r'    function \[31:0\] advance_ring;.*?    endfunction', original, re.S)[0]
        reference = reference.replace('advance_ring', 'reference_ring')
        bench = '''module ring_check #(parameter [31:0] AUDIO_TOTAL_BYTES=128);
FUNCTIONS
REFERENCE
reg [31:0] rng=32'h138a2801,offset;
integer i;
task verify;
begin
    if(advance_ring(offset)!==reference_ring(offset))
        $fatal(1,"ring advance changed capacity=%h offset=%h",AUDIO_TOTAL_BYTES,offset);
end
endtask
initial begin
    // Exercise every beat near both bank/ring boundaries, unaligned inputs,
    // and 32-bit addition overflow as well as actual aligned DMA pointers.
    for(i=0;i<256;i=i+1)begin
        offset=AUDIO_TOTAL_BYTES-32'(i);verify();
        offset=(AUDIO_TOTAL_BYTES>>1)-32'(i);verify();
        offset=32'hffffffff-32'(i);verify();
    end
    for(i=0;i<100000;i=i+1)begin
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};offset=rng;verify();
        offset=rng & 32'hffffffe0;verify();
    end
end
endmodule
module tb_ring;
ring_check #(128) small_power();
ring_check #(192) general_wrap();
ring_check #(32'h08000000) hardware_capacity();
ring_check #(0) zero_capacity();
initial begin #1;$display("PASS ring increment: 803072 exact boundary/random/aligned vectors, four capacities");$finish;end
endmodule
'''.replace('FUNCTIONS', functions).replace('REFERENCE', reference)
        with tempfile.TemporaryDirectory(prefix='native-ring-increment-') as directory:
            source = Path(directory)/'test.sv'
            executable = Path(directory)/'simulation'
            source.write_text(bench)
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'tb_ring', '-o', str(executable), str(source)],
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            simulation = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=90)
            self.assertEqual(simulation.returncode, 0, simulation.stdout+simulation.stderr)
            self.assertIn('PASS ring increment', simulation.stdout)
            print(simulation.stdout.strip())

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
