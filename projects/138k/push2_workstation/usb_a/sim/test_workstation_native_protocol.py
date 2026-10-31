#!/usr/bin/env python3
"""Real native mailbox inventories and destructive CDC controls; no EDA."""
from contextlib import contextmanager
from pathlib import Path
import fnmatch
import hashlib
import json
import os
import re
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import (
    audit_native_protocol, protocol_netlist, validate_native_protocol_sdc, RAM_SCOPE, RAM_STEM, TOP,
)
from tools.workstation_runtime_profile import protocol_constraints


class NativeProtocolPolicy(unittest.TestCase):
    def test_vendor_registered_read_holds_in_18_and_36_bit_mappings(self):
        vendor = os.environ.get('GW138K_GW5A_PRIM_SIM')
        if not vendor:
            self.skipTest('explicit GW5A vendor model required in GW138K_GW5A_PRIM_SIM')
        model = Path(vendor).read_text()
        selected = []
        for name in ('GSR', 'SDPX9B'):
            modules = re.findall(r'^module\s+' + name + r'\s*\(.*?^endmodule\b[^\n]*', model, re.M | re.S)
            self.assertEqual(len(modules), 1)
            selected.append(modules[0])
        fixture = r'''`timescale 1ns/1ps
module tb_registered_display_ram;
reg clka=0,clkb=0,ceb=0;
reg [35:0] di=0;
wire [35:0] do36,do18;
integer index;
GSR GSR(.GSRI(1'b1));
SDPX9B #(.READ_MODE(0),.BIT_WIDTH_0(36),.BIT_WIDTH_1(36)) ram36(
 .DO(do36),.DI(di),.BLKSELA(3'd0),.BLKSELB(3'd0),.ADA(14'b1111),.ADB(14'd0),
 .CLKA(clka),.CLKB(clkb),.CEA(1'b1),.CEB(ceb),.OCE(1'b0),.RESET(1'b0));
SDPX9B #(.READ_MODE(0),.BIT_WIDTH_0(18),.BIT_WIDTH_1(18)) ram18(
 .DO(do18),.DI(di),.BLKSELA(3'd0),.BLKSELB(3'd0),.ADA(14'b11),.ADB(14'd0),
 .CLKA(clka),.CLKB(clkb),.CEA(1'b1),.CEB(ceb),.OCE(1'b0),.RESET(1'b0));
task write_word(input [35:0] value);begin di=value;#1;clka=1;#1;clka=0;#1;end endtask
task read_edge;begin #1;clkb=1;#1;clkb=0;#1;end endtask
initial begin
 #2;write_word(36'h123456789);ceb=1;read_edge();ceb=0;
 if(do36!==36'h123456789 || do18[17:0]!==18'h16789)$fatal(1,"registered capture mismatch");
 for(index=0;index<1024;index=index+1)begin
  write_word(36'(index));
  if(index<512)read_edge(); // then stop the RAM read/source clock as well
  if(do36!==36'h123456789 || do18[17:0]!==18'h16789)$fatal(1,"busy/stopped source RAM output changed");
 end
 ceb=1;read_edge();ceb=0;
 if(do36!==36'd1023 || do18[17:0]!==18'd1023)$fatal(1,"next accepted read did not update");
 $display("PASS display RAM registered hold: 18/36bit 1024 busy writes 512 stopped read clocks");$finish;
end
endmodule
'''
        with tempfile.TemporaryDirectory(prefix='native-protocol-ram-') as directory:
            stage = Path(directory)
            source, executable = stage / 'model.sv', stage / 'simulation'
            source.write_text('\n'.join(selected) + '\n' + fixture)
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'tb_registered_display_ram',
                '-o', str(executable), str(source)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            simulation = subprocess.run(['vvp', str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(simulation.returncode, 0, simulation.stdout + simulation.stderr)
            self.assertIn('PASS display RAM registered hold', simulation.stdout)
            print(simulation.stdout.strip() + ' vendor_sha256=' + hashlib.sha256(Path(vendor).read_bytes()).hexdigest())

    def test_registered_ram_constraint_selects_only_98_payload_destinations(self):
        sdc = protocol_constraints()
        selected = [line for line in sdc.splitlines() if RAM_SCOPE in line]
        self.assertEqual(len(selected), 2)
        source = RAM_SCOPE + '*' + RAM_STEM + '*_s/DO*'
        targets = ' '.join(f'u_managed/display/destination_data_{i}_s*/D' for i in range(105, 203))
        path = f'-from [get_pins {{{source}}}] -to [get_pins {{{targets}}}]'
        self.assertEqual(selected, ['set_max_delay 20.000 ' + path, 'set_false_path -hold ' + path])
        self.assertNotIn('get_clocks', '\n'.join(selected))
        for bit in (0, 1):
            first, second = (f'u_managed/display_observation_health/{stem}_{bit}_s*' for stem in ('loss_meta', 'loss_sync'))
            self.assertEqual(sdc.splitlines().count(f'set_false_path -to [get_pins {{{first}/D}}]'), 1)
            self.assertIn(f'set_max_delay 2.000 -from [get_pins {{{first}/Q}}] -to [get_pins {{{second}/D}}]', sdc)


class ActualNativeFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_NATIVE_PROTOCOL_VG')
        if not selected:
            raise unittest.SkipTest('explicit actual VG required in GW138K_NATIVE_PROTOCOL_VG; no cache fallback')
        cls.mapping = os.environ.get('GW138K_NATIVE_PROTOCOL_MAPPING', 'synthesis')
        cls.n = protocol_netlist(Path(selected).read_text(), mapping=cls.mapping)
        cls.profile = os.environ.get('GW138K_NATIVE_PROTOCOL_PROFILE', 'm-demo-base')
        cls.mutations = []

    @classmethod
    def tearDownClass(cls):
        evidence = os.environ.get('GW138K_NATIVE_PROTOCOL_EVIDENCE')
        if evidence:
            path = Path(evidence)
            earlier = json.loads(path.read_text()) if path.is_file() else {}
            if earlier:
                assert earlier['profile'] == cls.profile and earlier['mapping'] == cls.mapping
            mutations = [row for row in earlier.get('mutations', []) if row.get('test_class') != cls.__name__]
            mutations.extend(dict(**row, test_class=cls.__name__) for row in cls.mutations)
            path.write_text(json.dumps(dict(profile=cls.profile, mapping=cls.mapping, mutations=mutations,
                mutation_count=len(mutations), physical_cdc_accepted=False), indent=2) + '\n')

    @contextmanager
    def change(self, path, part, key, value):
        binding = self.n.cells[path][part]
        original = binding[key]
        binding[key] = value
        try:
            yield
        finally:
            binding[key] = original

    def reject(self, name, path, part, key, value, message):
        with self.change(path, part, key, value):
            with self.assertRaisesRegex(ValueError, message) as error:
                audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping)
        self.mutations.append(dict(case=name, rejected=True, error=str(error.exception)))

class ActualNativeProtocol(ActualNativeFixture):
    def test_actual_mailboxes_exact_payload_and_no_false_acceptance(self):
        result = audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping)
        self.assertEqual(result['mailbox_count'], 4)
        display = next(x for x in result['mailboxes'] if x['scope'] == 'u_managed/display')
        self.assertEqual(display['registered_ram_bits'], 98)
        self.assertEqual(display['held_ff_bits'], 73 if self.profile == 'm-demo-base' else 41)
        self.assertFalse(result['physical_cdc_accepted'])
        pins = {p + '/' + port for p, c in self.n.cells.items()
                if p.startswith((RAM_SCOPE, 'u_managed/display/')) for port in c['ports']}
        for line in protocol_constraints().splitlines():
            if RAM_SCOPE in line:
                bodies = re.findall(r'\[get_pins \{([^}]+)\}\]', line)
                self.assertEqual([sum(fnmatch.fnmatchcase(pin, s) for pin in pins) for s in bodies[0].split()],
                                 [3 if self.mapping == 'synthesis' else 6])
                self.assertEqual([sum(fnmatch.fnmatchcase(pin, s) for pin in pins) for s in bodies[1].split()], [1] * 98)

    def test_installed_sdc_keeps_later_stages_and_exact_local_bounds(self):
        result = audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping)
        sdc = protocol_constraints()
        checked = validate_native_protocol_sdc(sdc, self.n, result)
        self.assertEqual(len(checked['exact_98_registered_ram_capture_pins']), 98)
        self.assertEqual(len(checked['registered_ram_source_pins']), 3 if self.mapping == 'synthesis' else 6)
        for line in sdc.splitlines():
            if RAM_SCOPE in line or 'display_observation_health/loss_meta_0' in line:
                with self.subTest(missing=line), self.assertRaisesRegex(ValueError, 'missing, duplicated or changed'):
                    validate_native_protocol_sdc(sdc.replace(line + '\n', '', 1), self.n, result)
        for stem in ('req_sync', 'req_settled', 'ack_sync'):
            for kind in ('', ' -hold'):
                changed = sdc + f'set_false_path{kind} -to [get_pins {{u_managed/display/{stem}_s*/D}}]\n'
                with self.subTest(cut=stem, kind=kind), self.assertRaisesRegex(ValueError, 'later synchronizer/settled'):
                    validate_native_protocol_sdc(changed, self.n, result)
        changed = sdc + 'set_false_path -to [get_regs {u_managed/display_observation_health/loss_sync_0_s*}]\n'
        with self.assertRaisesRegex(ValueError, 'later synchronizer/settled'):
            validate_native_protocol_sdc(changed, self.n, result)
        for stem in ('pc_health_sync_0', 'pc_health_sync_1'):
            with self.subTest(cut=stem), self.assertRaisesRegex(ValueError, 'later synchronizer/settled'):
                validate_native_protocol_sdc(sdc + f'set_false_path -hold -to [get_pins {{u_managed/{stem}_s*/D}}]\n', self.n, result)
        control_lines = [line for line in sdc.splitlines() if 'u_managed/pc_health_meta_' in line or
                         self.profile == 'm-demo-base' and 'u_tf_audio/held_control_' in line]
        for line in control_lines:
            with self.subTest(missing_control=line), self.assertRaisesRegex(ValueError, 'missing, duplicated or changed'):
                validate_native_protocol_sdc(sdc.replace(line + '\n', '', 1), self.n, result)
        if self.profile == 'm-demo-base':
            for stem in ('request_sync_1', 'ack_sync_1', 'control_capture'):
                with self.subTest(cut_tf=stem), self.assertRaisesRegex(ValueError, 'later synchronizer/settled'):
                    validate_native_protocol_sdc(sdc + f'set_false_path -hold -to [get_pins {{u_tf_audio/{stem}_s*/D}}]\n', self.n, result)

    def test_ram_enable_cannot_ignore_mailbox_busy(self):
        self.reject('RAM overwrite while busy', RAM_SCOPE + RAM_STEM + '0_s', 'ports', 'CEB', "1'b1", 'RAM read register')

    def test_ram_read_clock_cannot_be_selected_mclk(self):
        self.reject('RAM read wrong clock', RAM_SCOPE + RAM_STEM + '0_s', 'ports', 'CLKB', "1'b0", 'RAM read register')

    def test_ram_output_mode_must_be_reviewed(self):
        self.reject('RAM extra output stage', RAM_SCOPE + RAM_STEM + '0_s', 'parameters', 'READ_MODE', "1'b1", 'RAM read register')

    def test_ram_bit_mapping_is_exact(self):
        path = 'u_managed/display/destination_data_105_s0'
        self.reject('RAM bit alias', path, 'ports', 'D', self.n.cells['u_managed/display/destination_data_106_s0']['ports']['D'],
                    'RAM payload destination fanout')

    def test_ack_first_stage_cannot_drive_functional_payload(self):
        path = 'u_managed/display/held_data_0_s0'
        # This stays entirely inside the actual hierarchy; it adds a consumer
        # of meta.Q before its second synchronizer stage.
        self.reject('first meta extra consumer', path, 'ports', 'D',
                    self.n.cells['u_managed/display/ack_meta_s0']['ports']['Q'], 'first-stage fanout')

    def test_ack_first_stage_has_exact_clock(self):
        self.reject('first meta wrong clock', 'u_managed/pc_bytes/ack_meta_s0', 'ports', 'CLK', "1'b0", 'clock changed')

    def test_request_third_stage_cannot_bypass_second(self):
        self.reject('settled bypass', 'u_managed/display/req_settled_s0', 'ports', 'D', 'request_toggle', 'third request stage')

    def test_request_must_toggle_with_actual_acceptance(self):
        self.reject('request toggles without capture', 'u_managed/display/n496_s5', 'parameters', 'INIT', "16'hAAAA", 'request must toggle')

    def test_acceptance_cannot_overwrite_busy_payload(self):
        self.reject('capture ignores ACK', 'u_managed/display/n1637_s4', 'parameters', 'INIT', "16'hFFFF", 'overwrite while request')

    def test_loss_bypass_cannot_be_removed(self):
        path = 'u_managed/display_observation_health/loss_meta_0_s0'
        self.reject('lost final-drop bypass', path, 'ports', 'D',
                    self.n.cells['u_managed/display_observation_health/source_sticky_0_s0']['ports']['Q'],
                    'sticky OR all nonzero')

    def test_loss_counter_must_be_in_compute_domain(self):
        self.reject('loss source wrong clock', 'u_managed/observation/drops/sync_value_13_s0', 'ports', 'CLK', "1'b0", 'clock changed')

    def test_ram_payload_cannot_feed_an_extra_register(self):
        self.reject('RAM payload extra consumer', 'u_managed/display/held_data_0_s0', 'ports', 'D',
                    self.n.cells['u_managed/display/destination_data_105_s0']['ports']['D'],
                    'RAM payload destination fanout')

    def test_routed_added_ram_fragment_must_use_the_same_acceptance(self):
        if self.mapping != 'routed':
            self.skipTest('routed 18-bit split only')
        self.reject('routed added half ignores busy', RAM_SCOPE + 'gowin_add_SDPX9B_' + RAM_STEM + '0_s',
                    'ports', 'CEB', "1'b1", 'RAM read register')


class ActualControlBoundaries(ActualNativeFixture):
    def bind(self, target, source, port='Q'):
        net = self.n.pin(source, port)
        scope = self.n.scopes[target]
        if scope:
            self.assertTrue(net.startswith(scope + '/'))
            return net[len(scope) + 1:]
        return self.n.cells[source]['ports'][port]

    def tf(self):
        if self.profile != 'm-demo-base':
            self.skipTest('W explicitly retires the TF owner')

    def test_tf_payload_bit_swap_rejected(self):
        self.tf()
        self.reject('TF payload bit swapped', 'u_tf_audio/compute_control_0_s0', 'ports', 'D',
                    self.n.cells['u_tf_audio/compute_control_1_s0']['ports']['D'], 'TF held payload bit mapping')

    def test_tf_source_busy_gate_rejected(self):
        self.tf()
        self.reject('TF busy overwrite', 'u_tf_audio/n2708_s1', 'parameters', 'INIT', "8'hFF", 'TF acceptance must require')

    def test_tf_compare_must_cover_same_desired_bits(self):
        self.tf()
        self.reject('TF desired comparison bit mismatch', 'u_tf_audio/held_control_0_s0', 'ports', 'D',
                    self.n.cells['u_tf_audio/held_control_1_s0']['ports']['D'], 'comparison must include every exact')

    def test_tf_request_must_toggle_on_capture(self):
        self.tf()
        self.reject('TF request no longer follows capture', 'u_tf_audio/n2746_s5', 'parameters', 'INIT', "16'hAAAA", 'TF request must toggle')

    def test_tf_capture_needs_registered_settling(self):
        self.tf()
        self.reject('TF capture bypasses its settled state', 'u_tf_audio/n2827_s1', 'parameters', 'INIT', "8'h3C", 'TF capture must register')

    def test_tf_ack_must_wait_for_payload_capture(self):
        self.tf()
        self.reject('TF ACK before payload', 'u_tf_audio/control_ack_s0', 'ports', 'CE', "1'b1", 'TF ACK and payload')

    def test_tf_request_second_cannot_bypass_first(self):
        self.tf()
        target = 'u_tf_audio/request_sync_1_s0'
        self.reject('TF request synchronizer bypass', target, 'ports', 'D',
                    self.bind(target, 'u_tf_audio/control_request_s2'), 'control synchronizer direct')

    def test_tf_request_meta_extra_consumer_rejected(self):
        self.tf()
        target = 'u_tf_audio/launched_epoch_0_s0'
        self.reject('TF request meta extra consumer', target, 'ports', 'D',
                    self.bind(target, 'u_tf_audio/request_sync_0_s0'), 'first-stage fanout changed')

    def test_pc_source_bits_cannot_swap(self):
        target = 'u_managed/pc_health_meta_0_s0'
        self.reject('PC health source bit swapped', target, 'ports', 'D',
                    self.bind(target, 'u_managed/pc_drop_seen_50_s0'), 'control synchronizer direct')

    def test_pc_meta_must_be_unconditional(self):
        self.reject('PC health conditional meta', 'u_managed/pc_health_meta_0_s0', 'ports', 'CE', "1'b0", 'control synchronizer clock/primitive/CE')

    def test_pc_drop_reduction_must_include_all_bits(self):
        target = 'u_managed/pc_drop_seen_50_s0'
        source = next(p for p in self.n.cells if re.fullmatch(r'u_managed/pc_bytes/drop_count_0_s\d+', p))
        self.reject('PC unregistered/wrong drop reduction', target, 'ports', 'D',
                    self.bind(target, source), 'drop reduction must be registered')


if __name__ == '__main__':
    unittest.main()
