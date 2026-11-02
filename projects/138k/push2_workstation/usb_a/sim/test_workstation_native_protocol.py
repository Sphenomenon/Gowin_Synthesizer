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
    audit_headless_display_absence, audit_native_protocol, protocol_netlist, validate_native_protocol_sdc, RAM_SCOPE, RAM_STEM, TOP,
    APB, DELAY, DMA, audit_demo_held_boundaries,
)
from tools.workstation_runtime_pcm_cdc import Graph
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
                audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping, connected_xy=os.environ.get('GW138K_CONNECTED_XY') == '1', stereo_xy=os.environ.get('GW138K_STEREO_XY') == '1', profile_revision=4 if os.environ.get('GW138K_STEREO_XY') == '1' else None, xy_axes_policy='ordinary_mid_side_vector_direct_v1' if os.environ.get('GW138K_STEREO_XY') == '1' else None)
        self.mutations.append(dict(case=name, rejected=True, error=str(error.exception)))

class ActualNativeProtocol(ActualNativeFixture):
    def display_only(self):
        if self.profile == 'w-demo-audio':
            audit_headless_display_absence(self.n)
            self.skipTest('explicit W-audio retires display/RAM and display-loss monitor; actual absence verified')

    def test_actual_mailboxes_exact_payload_and_no_false_acceptance(self):
        result = audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping, connected_xy=os.environ.get('GW138K_CONNECTED_XY') == '1', stereo_xy=os.environ.get('GW138K_STEREO_XY') == '1', profile_revision=4 if os.environ.get('GW138K_STEREO_XY') == '1' else None, xy_axes_policy='ordinary_mid_side_vector_direct_v1' if os.environ.get('GW138K_STEREO_XY') == '1' else None)
        if self.profile == 'w-demo-audio':
            self.assertEqual(result['mailbox_count'], 2)
            self.assertEqual({row['scope'] for row in result['mailboxes']},
                             {'u_managed/pc_bytes', 'u_managed/health_snapshot'})
            self.assertTrue(result['display_absence']['video_hierarchy_absent'])
            self.assertFalse(result['physical_cdc_accepted'])
            return
        self.assertEqual(result['mailbox_count'], 5 if result.get('hmi_inventory_reviewed') else 4)
        display = next(x for x in result['mailboxes'] if x['scope'] == 'u_managed/display')
        self.assertEqual(display['registered_ram_bits'], 98)
        expected_display = (75 if self.profile == 'w-demo-d' else 132) if result.get('hmi_inventory_reviewed') else (41 if self.profile == 'w-demo-d' else 73)
        if os.environ.get('GW138K_CONNECTED_XY') == '1' and self.profile == 'm-demo-core':
            expected_display += 10  # exact existing connected-XY PANIC payload inventory
        self.assertEqual(display['held_ff_bits'], expected_display)
        self.assertFalse(result['physical_cdc_accepted'])
        pins = {p + '/' + port for p, c in self.n.cells.items()
                if p.startswith((RAM_SCOPE, 'u_managed/display/')) for port in c['ports']}
        for line in protocol_constraints().splitlines():
            if RAM_SCOPE in line:
                bodies = re.findall(r'\[get_pins \{([^}]+)\}\]', line)
                self.assertEqual([sum(fnmatch.fnmatchcase(pin, s) for pin in pins) for s in bodies[0].split()],
                                 [3 if self.mapping == 'synthesis' else 6])
                self.assertEqual([sum(fnmatch.fnmatchcase(pin, s) for pin in pins) for s in bodies[1].split()], [1] * 98)

    def test_headless_display_cannot_return_in_cells_hierarchy_or_sdc(self):
        if self.profile != 'w-demo-audio':
            self.skipTest('explicit W-audio retirement only')
        import copy
        for scope in ('u_video', 'u_managed/display', 'u_managed/display_observation_health'):
            path = scope + '/forbidden_retired_owner'
            source = 'u_managed/pc_bytes/ack_meta_s0'
            self.n.cells[path] = copy.deepcopy(self.n.cells[source])
            self.n.cells[path]['ports']['Q'] = 'forbidden_retired_output'
            self.n.scopes[path] = self.n.scopes[source]
            try:
                with self.assertRaisesRegex(ValueError, 'headless profile retained display/video') as error:
                    audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping, connected_xy=os.environ.get('GW138K_CONNECTED_XY') == '1', stereo_xy=os.environ.get('GW138K_STEREO_XY') == '1', profile_revision=4 if os.environ.get('GW138K_STEREO_XY') == '1' else None, xy_axes_policy='ordinary_mid_side_vector_direct_v1' if os.environ.get('GW138K_STEREO_XY') == '1' else None)
                self.mutations.append(dict(case='headless cell returned ' + scope, rejected=True, error=str(error.exception)))
            finally:
                del self.n.cells[path]
                del self.n.scopes[path]
            self.n.frames[scope] = self.n.frames['']
            try:
                with self.assertRaisesRegex(ValueError, 'headless profile retained display/video') as error:
                    audit_headless_display_absence(self.n)
                self.mutations.append(dict(case='headless hierarchy returned ' + scope, rejected=True, error=str(error.exception)))
            finally:
                del self.n.frames[scope]
            from tools.workstation_worker_audio_only import constraints
            sdc, unused = constraints(protocol_constraints())
            result = audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping, connected_xy=os.environ.get('GW138K_CONNECTED_XY') == '1', stereo_xy=os.environ.get('GW138K_STEREO_XY') == '1', profile_revision=4 if os.environ.get('GW138K_STEREO_XY') == '1' else None, xy_axes_policy='ordinary_mid_side_vector_direct_v1' if os.environ.get('GW138K_STEREO_XY') == '1' else None)
            for command in ('set_false_path', 'set_max_delay 2.000'):
                changed = sdc + command + ' -to [get_pins {' + path + '/D}]\n'
                with self.assertRaisesRegex(ValueError, 'retired display timing selector') as error:
                    validate_native_protocol_sdc(changed, self.n, result)
                self.mutations.append(dict(case='headless selector returned ' + command + ' ' + scope,
                                          rejected=True, error=str(error.exception)))

    def test_m22_new_hmi_mailbox_negative_controls(self):
        if self.profile != 'm-demo-core' or 'u_video/u_applied_parameters_cdc' not in self.n.frames:
            self.skipTest('M22 actual new HMI mailbox only')
        result=audit_native_protocol(self.n,profile=self.profile,mapping=self.mapping,connected_xy=os.environ.get('GW138K_CONNECTED_XY') == '1', stereo_xy=os.environ.get('GW138K_STEREO_XY') == '1', profile_revision=4 if os.environ.get('GW138K_STEREO_XY') == '1' else None, xy_axes_policy='ordinary_mid_side_vector_direct_v1' if os.environ.get('GW138K_STEREO_XY') == '1' else None)
        display=next(x for x in result['mailboxes'] if x['scope']=='u_managed/display')
        hmi=next(x for x in result['mailboxes'] if x['scope']=='u_video/u_applied_parameters_cdc')
        expected=(142,98,240) if os.environ.get('GW138K_CONNECTED_XY') == '1' else (132,98,230)
        self.assertEqual((display['held_ff_bits'],display['registered_ram_bits'],display['payload_bits']),expected)
        self.assertEqual((hmi['held_ff_bits'],hmi['registered_ram_bits'],hmi['payload_bits']),(60,0,60))
        g=Graph(self.n);scope='u_video/u_applied_parameters_cdc'
        held=g.register(scope,'held_data',3);destination=g.register(scope,'destination_data',3)
        reqmeta=g.register(scope,'req_meta');reqsync=g.register(scope,'req_sync')
        request=g.register(scope,'request_toggle');ack=g.register(scope,'acknowledge_toggle')
        for name,path,pin,value in [
            ('HMI held payload alias',destination,'D',self.n.cells[g.register(scope,'held_data',4)]['ports']['Q']),
            ('HMI destination wrong clock',destination,'CLK',"1'b0"),
            ('HMI source ignores busy',held,'CE',"1'b1"),
            ('HMI capture ignores settled request',destination,'CE',"1'b1"),
            ('HMI first meta functional fanout',held,'D',self.n.cells[reqmeta]['ports']['Q']),
            ('HMI second request stage bypass',reqsync,'D',self.n.cells[request]['ports']['Q']),
            ('HMI request does not toggle',request,'D',"1'b0"),
            ('HMI ACK ignores settled request',ack,'D',"1'b0"),
        ]:
            self.reject(name,path,'ports',pin,value,'.')

    def test_installed_sdc_keeps_later_stages_and_exact_local_bounds(self):
        result = audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping, connected_xy=os.environ.get('GW138K_CONNECTED_XY') == '1', stereo_xy=os.environ.get('GW138K_STEREO_XY') == '1', profile_revision=4 if os.environ.get('GW138K_STEREO_XY') == '1' else None, xy_axes_policy='ordinary_mid_side_vector_direct_v1' if os.environ.get('GW138K_STEREO_XY') == '1' else None)
        sdc = protocol_constraints()
        headless = self.profile == 'w-demo-audio'
        if headless:
            from tools.workstation_worker_audio_only import constraints
            sdc, unused = constraints(sdc)
        checked = validate_native_protocol_sdc(sdc, self.n, result)
        self.assertEqual(len(checked['exact_98_registered_ram_capture_pins']), 0 if headless else 98)
        self.assertEqual(len(checked['registered_ram_source_pins']), 0 if headless else 3 if self.mapping == 'synthesis' else 6)
        for line in sdc.splitlines():
            if RAM_SCOPE in line or 'display_observation_health/loss_meta_0' in line:
                with self.subTest(missing=line), self.assertRaisesRegex(ValueError, 'missing, duplicated or changed'):
                    validate_native_protocol_sdc(sdc.replace(line + '\n', '', 1), self.n, result)
        for stem in (() if headless else ('req_sync', 'req_settled', 'ack_sync')):
            for kind in ('', ' -hold'):
                changed = sdc + f'set_false_path{kind} -to [get_pins {{u_managed/display/{stem}_s*/D}}]\n'
                with self.subTest(cut=stem, kind=kind), self.assertRaisesRegex(ValueError, 'later synchronizer/settled'):
                    validate_native_protocol_sdc(changed, self.n, result)
        changed = sdc + 'set_false_path -to [get_regs {u_managed/display_observation_health/loss_sync_0_s*}]\n'
        if not headless:
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
        self.display_only()
        self.reject('RAM overwrite while busy', RAM_SCOPE + RAM_STEM + '0_s', 'ports', 'CEB', "1'b1", 'RAM read register')

    def test_ram_read_clock_cannot_be_selected_mclk(self):
        self.display_only()
        self.reject('RAM read wrong clock', RAM_SCOPE + RAM_STEM + '0_s', 'ports', 'CLKB', "1'b0", 'RAM read register')

    def test_ram_output_mode_must_be_reviewed(self):
        self.display_only()
        self.reject('RAM extra output stage', RAM_SCOPE + RAM_STEM + '0_s', 'parameters', 'READ_MODE', "1'b1", 'RAM read register')

    def test_ram_bit_mapping_is_exact(self):
        self.display_only()
        path = 'u_managed/display/destination_data_105_s0'
        self.reject('RAM bit alias', path, 'ports', 'D', self.n.cells['u_managed/display/destination_data_106_s0']['ports']['D'],
                    'RAM payload destination fanout')

    def test_ack_first_stage_cannot_drive_functional_payload(self):
        self.display_only()
        path = 'u_managed/display/held_data_0_s0'
        # This stays entirely inside the actual hierarchy; it adds a consumer
        # of meta.Q before its second synchronizer stage.
        self.reject('first meta extra consumer', path, 'ports', 'D',
                    self.n.cells['u_managed/display/ack_meta_s0']['ports']['Q'], 'first-stage fanout')

    def test_ack_first_stage_has_exact_clock(self):
        self.reject('first meta wrong clock', 'u_managed/pc_bytes/ack_meta_s0', 'ports', 'CLK', "1'b0", 'clock changed')

    def test_request_third_stage_cannot_bypass_second(self):
        self.display_only()
        self.reject('settled bypass', 'u_managed/display/req_settled_s0', 'ports', 'D', 'request_toggle', 'third request stage')

    def test_request_must_toggle_with_actual_acceptance(self):
        self.display_only()
        request=Graph(self.n).register('u_managed/display','request_toggle')
        self.reject('request toggles without capture',request,'ports','D',"1'b0",'request must toggle')

    def test_acceptance_cannot_overwrite_busy_payload(self):
        self.display_only()
        g=Graph(self.n);held=g.register('u_managed/display','held_data',0)
        drivers=g.drivers[self.n.pin(held,'CE')]
        self.assertEqual(len(drivers),1);gate,output=drivers[0]
        self.assertEqual(output,'F');kind=self.n.cells[gate]['kind']
        self.assertIn(kind,('LUT3','LUT4'))
        value="16'hFFFF" if kind=='LUT4' else "8'hFF"
        self.reject('capture ignores ACK',gate,'parameters','INIT',value,'overwrite while request')

    def test_loss_bypass_cannot_be_removed(self):
        self.display_only()
        path = 'u_managed/display_observation_health/loss_meta_0_s0'
        self.reject('lost final-drop bypass', path, 'ports', 'D',
                    self.n.cells['u_managed/display_observation_health/source_sticky_0_s0']['ports']['Q'],
                    'sticky OR all nonzero')

    def test_loss_counter_must_be_in_compute_domain(self):
        self.reject('loss source wrong clock', 'u_managed/observation/drops/sync_value_13_s0', 'ports', 'CLK', "1'b0", 'clock changed')

    def test_ram_payload_cannot_feed_an_extra_register(self):
        self.display_only()
        self.reject('RAM payload extra consumer', 'u_managed/display/held_data_0_s0', 'ports', 'D',
                    self.n.cells['u_managed/display/destination_data_105_s0']['ports']['D'],
                    'RAM payload destination fanout')

    def test_routed_added_ram_fragment_must_use_the_same_acceptance(self):
        self.display_only()
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

    def tf_lut_driver(self, net, kind):
        # Bind the mutation to its actual register consumer, never a generated
        # optimizer name. Ambiguous drivers and changed gate shapes fail closed.
        drivers = Graph(self.n).drivers.get(net, [])
        self.assertEqual(len(drivers), 1)
        path, port = drivers[0]
        self.assertEqual(port, 'F')
        self.assertEqual(self.n.cells[path]['kind'], kind)
        return path

    def tf_lut_init(self, path, function):
        width = int(self.n.cells[path]['kind'][3:])
        value = sum(int(function(tuple((row >> bit) & 1 for bit in range(width)))) << row
                    for row in range(1 << width))
        return str(1 << width) + "'h" + format(value, '0' + str((1 << width) // 4) + 'X')

    def test_tf_payload_bit_swap_rejected(self):
        self.tf()
        self.reject('TF payload bit swapped', 'u_tf_audio/compute_control_0_s0', 'ports', 'D',
                    self.n.cells['u_tf_audio/compute_control_1_s0']['ports']['D'], 'TF held payload bit mapping')

    def test_tf_source_busy_gate_rejected(self):
        self.tf()
        g = Graph(self.n)
        held = g.group('u_tf_audio', 'held_control', 36)
        enables = {self.n.pin(path, 'CE') for path in held}
        self.assertEqual(len(enables), 1)
        gate = self.tf_lut_driver(next(iter(enables)), 'LUT3')
        self.reject('TF busy overwrite', gate, 'parameters', 'INIT', "8'hFF", 'TF acceptance must require')

    def test_tf_compare_must_cover_same_desired_bits(self):
        self.tf()
        self.reject('TF desired comparison bit mismatch', 'u_tf_audio/held_control_0_s0', 'ports', 'D',
                    self.n.cells['u_tf_audio/held_control_1_s0']['ports']['D'], 'comparison must include every exact')

    def test_tf_request_must_toggle_on_capture(self):
        self.tf()
        request = Graph(self.n).register('u_tf_audio', 'control_request')
        gate = self.tf_lut_driver(self.n.pin(request, 'D'), 'LUT4')
        request_q = self.n.pin(request, 'Q')
        request_inputs = [bit for bit in range(4) if self.n.pin(gate, 'I' + str(bit)) == request_q]
        self.assertEqual(len(request_inputs), 2)
        hold_q = self.tf_lut_init(gate, lambda values: values[request_inputs[0]])
        self.reject('TF request no longer follows capture', gate, 'parameters', 'INIT', hold_q, 'TF request must toggle')

    def test_tf_capture_needs_registered_settling(self):
        self.tf()
        g = Graph(self.n)
        capture = g.register('u_tf_audio', 'control_capture')
        gate = self.tf_lut_driver(self.n.pin(capture, 'D'), 'LUT3')
        request_q = self.n.pin(g.register('u_tf_audio', 'request_sync', 1), 'Q')
        ack_q = self.n.pin(g.register('u_tf_audio', 'control_ack'), 'Q')
        leaves = [self.n.pin(gate, 'I' + str(bit)) for bit in range(3)]
        self.assertEqual(set(leaves), {request_q, ack_q, self.n.pin(capture, 'Q')})
        bypass_settling = self.tf_lut_init(gate, lambda values: values[leaves.index(request_q)] != values[leaves.index(ack_q)])
        self.reject('TF capture bypasses its settled state', gate, 'parameters', 'INIT', bypass_settling, 'TF capture must register')

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


class ActualTimingBoundaries(ActualNativeFixture):
    def reg(self, scope, stem):
        rows = [p for p, c in self.n.cells.items() if c['kind'].startswith('DFF') and
                re.fullmatch(re.escape(scope + '/' + stem) + r'_s\d+', p)]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def bind(self, target, source):
        net = self.n.pin(source, 'Q')
        scope = self.n.scopes[target]
        if scope:
            self.assertTrue(net.startswith(scope + '/'))
            return net[len(scope) + 1:]
        return self.n.cells[source]['ports']['Q']

    def test_delay_heartbeat_source_must_be_registered_unconditionally(self):
        self.reject('heartbeat conditional publisher', self.reg(DELAY, 'heartbeat_counter_4'),
                    'ports', 'CE', "1'b0", 'timing-boundary register')

    def test_delay_meta_cannot_have_a_functional_consumer(self):
        target = self.reg(DMA, 'peer_last')
        self.reject('delay meta functional fanout', target, 'ports', 'D',
                    self.bind(target, self.reg(DMA, 'peer_meta')), 'first-stage has another consumer')

    def test_delay_first_stage_cannot_cross_to_a_different_bit(self):
        target = self.reg(DMA, 'peer_meta')
        self.reject('delay heartbeat bit swap', target, 'ports', 'D',
                    self.bind(target, self.reg(DMA, 'heartbeat_counter_3')), 'synchronizer bypass/reset')

    def test_apb_held_response_mapping_is_exact(self):
        self.reject('APB response bit alias', self.reg(APB, 'response_local_0'), 'ports', 'D',
                    self.n.cells[self.reg(APB, 'response_local_1')]['ports']['D'], 'payload bit mapping')

    def test_apb_ack_cannot_precede_payload(self):
        self.reject('APB ACK before response capture', self.reg(APB, 'acknowledge_toggle'),
                    'ports', 'CE', "1'b1", 'ACK and response publication')

    def test_apb_response_cannot_have_an_extra_consumer(self):
        target = self.reg(APB, 'request_decoded')
        self.reject('APB response extra consumer', target, 'ports', 'D',
                    self.bind(target, self.reg(APB, 'response_held_0')), 'exact consumer closure')

    def test_apb_command_valid_must_suppress_repeat_publication(self):
        g = Graph(self.n)
        enable = self.n.pin(self.reg(APB, 'acknowledge_toggle'), 'CE')
        gate = g.drivers[enable][0][0]
        width = int(self.n.cells[gate]['kind'][3:])
        self.reject('APB ACK gating removed', gate, 'parameters', 'INIT',
                    str(1 << width) + "'h" + 'F' * ((1 << width) // 4), 'command-valid may publish')

    def test_apb_payload_cannot_capture_before_third_ack(self):
        target = self.reg(APB, 'ack_settled')
        self.reject('APB third ACK bypass', target, 'ports', 'D',
                    self.bind(target, self.reg(APB, 'ack_meta')), 'first-stage has another consumer')

    def test_apb_state_cannot_relaunch_while_waiting(self):
        g = Graph(self.n)
        target = self.reg(APB, 'request_toggle')
        gate = g.drivers[self.n.pin(target, 'D')][0][0]
        if self.n.cells[gate]['kind'] in ('INV', 'LUT1'):
            gate = g.drivers[self.n.pin(target, 'CE')][0][0]
            self.reject('APB CE relaunch while waiting', gate, 'parameters', 'INIT',
                        "16'hFFFF", 'request payload can launch outside IDLE')
        else:
            self.reject('APB relaunch while waiting', gate, 'parameters', 'INIT',
                        "16'h5555", 'request can launch outside IDLE')

    def test_apb_ce_toggle_feedback_must_invert_its_own_q(self):
        g = Graph(self.n)
        target = self.reg(APB, 'request_toggle')
        gate = g.drivers[self.n.pin(target, 'D')][0][0]
        if self.n.cells[gate]['kind'] not in ('INV', 'LUT1'):
            self.skipTest('reviewed CE-factored request mapping not present')
        pin = 'I' if self.n.cells[gate]['kind'] == 'INV' else 'I0'
        self.reject('APB wrong inverse feedback', gate, 'ports', pin,
                    self.bind(gate, self.reg(APB, 'ack_settled')), 'toggle feedback must invert Q')

    def test_apb_routed_inverse_lut_truth_table_is_exact(self):
        g = Graph(self.n)
        target = self.reg(APB, 'request_toggle')
        gate = g.drivers[self.n.pin(target, 'D')][0][0]
        if self.n.cells[gate]['kind'] != 'LUT1':
            self.skipTest('reviewed routed LUT1 inverse mapping not present')
        self.reject('APB routed inverse LUT truth changed', gate, 'parameters', 'INIT',
                    "2'h2", 'toggle feedback must invert Q')

    def test_apb_split_launch_combined_and_is_exact(self):
        g = Graph(self.n)
        target = self.reg(APB, 'request_toggle')
        toggle = g.drivers[self.n.pin(target, 'D')][0][0]
        held = self.reg(APB, 'request_held_0')
        capture = g.drivers[self.n.pin(held, 'CE')][0][0]
        if self.n.cells[toggle]['kind'] != 'LUT4' or self.n.cells[capture]['kind'] != 'LUT4':
            self.skipTest('reviewed split launch AND mapping not present')
        state = {self.n.pin(self.reg(APB, stem), 'Q') for stem in ('state_0', 'state_1', 'request_toggle')}
        combined = next(self.n.pin(toggle, 'I' + str(i)) for i in range(4)
                        if self.n.pin(toggle, 'I' + str(i)) not in state)
        gate = g.drivers[combined][0][0]
        self.reject('APB split launch AND truth changed', gate, 'parameters', 'INIT',
                    "4'hE", 'split launch AND function changed')

    def test_apb_all_request_payload_bits_share_capture_ce(self):
        self.reject('APB one request bit bypasses capture', self.reg(APB, 'request_held_48'),
                    'ports', 'CE', "1'b1", 'request payload capture CE/clock/reset differs')

    def test_apb_request_payload_source_clock_is_exact(self):
        self.reject('APB one held request bit changes clock', self.reg(APB, 'request_held_48'),
                    'ports', 'CLK', "1'b0", 'request payload capture CE/clock/reset differs')

    def test_apb_request_payload_source_reset_is_exact(self):
        self.reject('APB one held request bit changes reset', self.reg(APB, 'request_held_48'),
                    'ports', 'CLEAR', "1'b0", 'request payload capture CE/clock/reset differs')

    def test_apb_request_local_payload_clock_is_exact(self):
        self.reject('APB one local request bit changes clock', self.reg(APB, 'request_local_48'),
                    'ports', 'CLK', "1'b0", 'request local payload capture CE/clock/reset differs')

    def test_apb_request_local_payload_reset_is_exact(self):
        self.reject('APB one local request bit changes reset', self.reg(APB, 'request_local_48'),
                    'ports', 'CLEAR', "1'b0", 'request local payload capture CE/clock/reset differs')

    def test_apb_request_payload_mapping_cannot_alias_bits(self):
        target = self.reg(APB, 'request_local_0')
        self.reject('APB held request bit aliases another', target, 'ports', 'D',
                    self.bind(target, self.reg(APB, 'request_held_1')), 'held/local payload bit mapping changed')

    def test_apb_request_payload_cannot_have_an_extra_consumer(self):
        target = self.reg(APB, 'state_0')
        self.reject('APB held request has extra state consumer', target, 'ports', 'D',
                    self.bind(target, self.reg(APB, 'request_held_0')), 'request payload exact consumer closure changed')

    def test_apb_request_local_payload_cannot_capture_before_third_stage(self):
        g = Graph(self.n)
        target = self.reg(APB, 'request_local_0')
        gate = g.drivers[self.n.pin(target, 'CE')][0][0]
        width = int(self.n.cells[gate]['kind'][3:])
        self.reject('APB request local capture loses third-stage gate', gate, 'parameters', 'INIT',
                    str(1 << width) + "'h" + 'F' * ((1 << width) // 4), 'local capture must wait for third request stage')

    def test_apb_ce_toggle_cannot_bypass_payload_capture(self):
        g = Graph(self.n)
        target = self.reg(APB, 'request_toggle')
        gate = g.drivers[self.n.pin(target, 'D')][0][0]
        if self.n.cells[gate]['kind'] not in ('INV', 'LUT1'):
            self.skipTest('reviewed CE-factored request mapping not present')
        self.reject('APB toggle CE bypasses payload', target, 'ports', 'CE',
                    "1'b1", 'toggle CE differs from payload capture')

    def test_apb_toggle_cannot_drive_an_unreviewed_payload_input(self):
        target = self.reg(APB, 'request_held_0')
        self.reject('APB toggle extra payload consumer', target, 'ports', 'D',
                    self.bind(target, self.reg(APB, 'request_toggle')), 'toggle has an unreviewed consumer')

    def test_apb_capture_gate_must_use_wait_state_and_settled_ack(self):
        g = Graph(self.n)
        gate = g.drivers[self.n.pin(self.reg(APB, 'response_local_0'), 'CE')][0][0]
        self.reject('APB response premature capture', gate, 'parameters', 'INIT', "16'hFFFF", 'capture must wait')

    def test_tf_quiesce_cannot_bypass_registered_source(self):
        if self.profile != 'm-demo-base':
            self.skipTest('W retires TF')
        self.reject('TF quiesce unregistered source', self.reg('u_tf_audio/frames', 'quiesce_sync_0'),
                    'ports', 'D', "1'b1", 'synchronizer bypass/reset')

    def test_tf_quiesce_first_stage_cannot_reach_functional_state(self):
        if self.profile != 'm-demo-base':
            self.skipTest('W retires TF')
        target = self.reg('u_tf_audio/frames', 'quiet_published')
        self.reject('TF quiesce meta functional fanout', target, 'ports', 'D',
                    self.bind(target, self.reg('u_tf_audio/frames', 'quiesce_sync_0')), 'first-stage has another consumer')

    def test_sdc_protects_payload_setup_and_all_later_stages(self):
        result = audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping, connected_xy=os.environ.get('GW138K_CONNECTED_XY') == '1', stereo_xy=os.environ.get('GW138K_STEREO_XY') == '1', profile_revision=4 if os.environ.get('GW138K_STEREO_XY') == '1' else None, xy_axes_policy='ordinary_mid_side_vector_direct_v1' if os.environ.get('GW138K_STEREO_XY') == '1' else None)
        timing = result['timing_boundaries']
        sdc = protocol_constraints()
        headless = self.profile == 'w-demo-audio'
        if headless:
            from tools.workstation_worker_audio_only import constraints
            sdc, unused = constraints(sdc)
        checked = validate_native_protocol_sdc(sdc, self.n, result)
        self.assertEqual(checked['apb_response_payload_pins_verified'], 33)
        lines = [line for line in sdc.splitlines() if APB + '/response_held_' in line or DELAY + '/' in line or
                 self.profile == 'm-demo-base' and 'u_tf_audio/frames/quiesce_sync_' in line]
        for line in lines:
            with self.subTest(missing=line), self.assertRaisesRegex(ValueError, 'missing, duplicated or changed'):
                validate_native_protocol_sdc(sdc.replace(line + '\n', '', 1), self.n, result)
        cuts = [row['second'] for row in timing['delay_heartbeats']]
        cuts += [row[key] for row in timing['apb_response']['chains'] for key in ('second', 'third')]
        cuts += timing['apb_response']['capture_pins'][:1]
        if timing['tf_quiesce']:
            cuts.append(timing['tf_quiesce']['second'])
        for pin in cuts:
            for option in ('', ' -hold'):
                with self.subTest(cut=pin, option=option), self.assertRaisesRegex(ValueError, 'later synchronizer/settled'):
                    validate_native_protocol_sdc(sdc + f'set_false_path{option} -to [get_pins {{{pin}}}]\n', self.n, result)


class ActualDemoHeldHandshakes(ActualNativeFixture):
    def audited(self):
        result = audit_native_protocol(self.n, profile=self.profile, mapping=self.mapping, connected_xy=os.environ.get('GW138K_CONNECTED_XY') == '1', stereo_xy=os.environ.get('GW138K_STEREO_XY') == '1', profile_revision=4 if os.environ.get('GW138K_STEREO_XY') == '1' else None, xy_axes_policy='ordinary_mid_side_vector_direct_v1' if os.environ.get('GW138K_STEREO_XY') == '1' else None)
        result['demo_held_handshakes'] = audit_demo_held_boundaries(self.n, result)
        return result

    def test_actual_pc_power_up_and_apb_local_release_are_separate(self):
        result = self.audited()['demo_held_handshakes']
        self.assertEqual(len(result['pc_source_pins']), 8)
        self.assertEqual(len(result['apb_request_source_pins']), 49)
        self.assertEqual(result['pc_actual_reset']['mode'], 'custom_top_power_up_only')
        self.assertFalse(result['pc_actual_reset']['runtime_reset_supported'])
        self.assertFalse(result['pc_actual_reset']['reusable_reset_simulation'])
        self.assertEqual(result['apb_resets']['common_assertion_proof']['exhaustive_assignments'], 2)

    def test_actual_graph_mutants(self):
        g = Graph(self.n); scope = 'u_managed/pc_bytes'
        reg = lambda s, t: g.register(s, t)
        for label, target, port, source, value in (
                ('PC payload alias', reg(scope,'destination_data_7'),'D',reg(scope,'destination_data_6'),None),
                ('PC held extra consumer',reg(scope,'drop_count_0'),'D',reg(scope,'held_data_0'),None),
                ('PC first bypass',reg(scope,'req_sync'),'D',reg(scope,'request_toggle'),None),
                ('PC meta functional consumer',reg(scope,'destination_data_0'),'CE',reg(scope,'req_meta'),None),
                ('PC active reset',reg(scope,'destination_data_7'),'RESET',None,"1'b1"),
                ('PC wrong clock',reg(scope,'held_data_7'),'CLK',None,"1'b0"),
                ('APB payload reset',reg(APB,'request_held_48'),'CLEAR',None,"1'b0"),
                ('APB release bypass',reg(APB,'a_release_2'),'D',reg(APB,'a_release_0'),None)):
            if source is not None:
                value = self.n.cells[source]['ports']['D' if label == 'PC payload alias' else 'Q']
            # The reviewed PC mapping may use either synchronous RESET or
            # asynchronous CLEAR when the constant-inactive control is folded.
            if label == 'PC active reset' and port not in self.n.cells[target]['ports']:
                port = 'CLEAR'
            with self.change(target,'ports',port,value):
                with self.assertRaises(ValueError) as error:
                    self.audited()
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))

    def test_selected_sdc_and_negative_controls(self):
        from tools.workstation_performance_reset import demo_held_handshake_constraints
        result = self.audited(); addition = demo_held_handshake_constraints()
        baseline = protocol_constraints()
        if self.profile == 'w-demo-audio':
            from tools.workstation_worker_audio_only import constraints
            baseline, unused = constraints(baseline)
        sdc = baseline + addition
        def check(text, selected=addition):
            return validate_native_protocol_sdc(text,self.n,result,demo_held_handshakes=selected)
        self.assertEqual(len(check(sdc)['demo_held_handshake_constraints']),10)
        lines = addition.splitlines(); scope = 'u_managed/pc_bytes'
        mutants = {
            'missing payload bit': addition.replace(scope+'/held_data_*_s*/Q',
                ' '.join(scope+'/held_data_'+str(i)+'_s*/Q' for i in range(7))),
            'missing APB bit': addition.replace(APB+'/request_held_*_s*/Q',
                ' '.join(APB+'/request_held_'+str(i)+'_s*/Q' for i in range(48))),
            'wrong payload destination': addition.replace(scope+'/destination_data_*_s*/D',scope+'/drop_count_*_s*/D'),
            'payload setup false path': addition.replace(lines[1],lines[1].replace(' -hold','')),
            'later stage cut': addition.replace(lines[4],lines[4].replace('/req_meta_','/req_sync_')),
            'weaker setup budget': addition.replace('13.020','20.000'),
            'wrong ACK publisher': addition.replace(lines[8],lines[8].replace('/acknowledge_toggle_','/request_toggle_')),
            'wider source also reaches another mailbox': addition.replace(scope+'/held_data_*_s*/Q','u_managed/*/held_data_*_s*/Q'),
        }
        for label,bad in mutants.items():
            with self.subTest(case=label),self.assertRaises(ValueError) as error:
                check(baseline+bad,bad)
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))

        for label,bad in (
                ('missing line',sdc.replace(lines[0]+'\n','')),
                ('duplicate line',sdc+lines[0]+'\n'),
                ('override finite payload bound',sdc+lines[0].replace('13.020','20.000')+'\n'),
                ('override second-stage bound',sdc+lines[5].replace('2.000','3.000')+'\n'),
                ('whole clock cut',sdc+'set_false_path -from [get_clocks {clk_50m}] -to [get_clocks {audio_76m8}]\n'),
                ('remove old PC ACK',sdc.replace(next(x for x in baseline.splitlines() if scope+'/ack_meta_' in x)+'\n','')),
                ('remove old APB response',sdc.replace(next(x for x in baseline.splitlines() if APB+'/response_held_' in x)+'\n',''))):
            with self.subTest(case=label),self.assertRaises(ValueError) as error:
                check(bad)
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))

    def test_shared_selected_entry_checks_actual_source_slice(self):
        from tools.workstation_performance_reset import (
            DEMO_TIMING_TOOL, select_demo_timing, audit_demo_held_handshakes)
        path = Path(os.environ['GW138K_NATIVE_PROTOCOL_VG'])
        physical = next((p for p in path.parents if (p/'physical_inputs.json').is_file()),None)
        candidate = (Path(json.loads((physical/'physical_inputs.json').read_text())['parent_candidate'])
                     if physical else next((p for p in path.parents if (p/'integration_inputs.json').is_file()),None))
        if candidate is None:
            self.skipTest('actual sealed candidate required for entry source slice')
        source = candidate/'workstation/Prj1'
        role = 'W' if self.profile in ('w-demo-d', 'w-demo-audio') else 'M'
        with tempfile.TemporaryDirectory(prefix='selected-demo-held-entry-') as directory:
            fixture = Path(directory)/'candidate'
            stage = fixture/'workstation/Prj1'
            for relative in (DEMO_TIMING_TOOL,'rtl/workstation/gw138k_push_workstation_top.v',
                             'rtl/workstation/workstation_runtime_controlled.sv',
                             'rtl/workstation/workstation_profile_' + ('m' if role == 'M' else 'w') + '_demo.sv'):
                target = stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(((ROOT if relative == DEMO_TIMING_TOOL else source)/relative).read_bytes())
            if os.environ.get('GW138K_STEREO_XY') == '1':
                (fixture/'workstation_profile.json').write_bytes((candidate/'workstation_profile.json').read_bytes())
            baseline = protocol_constraints()
            if self.profile == 'w-demo-audio':
                from tools.workstation_worker_audio_only import constraints
                baseline, unused = constraints(baseline)
            sdc,evidence = select_demo_timing(stage,baseline,role)
            def gate(text=sdc):
                return audit_demo_held_handshakes(stage,text,role,evidence,self.n,mapping=self.mapping)
            checked = gate()
            self.assertTrue(checked['gate_applied'])
            self.assertEqual(checked['actual_pc_reset_scope'],'power_up_only')
            self.assertFalse(checked['reusable_module_reset_simulation'])
            with self.assertRaisesRegex(ValueError,'absent or duplicated'):
                gate(sdc.replace(evidence['added_lines'][-1]+'\n',''))
            controlled=stage/'rtl/workstation/workstation_runtime_controlled.sv'
            changed,count=re.subn(r'(\bpc_bytes\s*\(\s*\.reset_n\()common_reset_n',
                r'\g<1>rst_ni',controlled.read_text(),count=1)
            self.assertEqual(count,1)
            controlled.write_text(changed)
            with self.assertRaisesRegex(ValueError,'source common-reset selection changed'):
                gate()
            self.mutations.extend((dict(case='selected entry missing SDC line',rejected=True),
                                   dict(case='selected entry actual PC source reset binding',rejected=True)))


class ActualStereoXYPolicy(ActualNativeFixture):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('GW138K_STEREO_XY') != '1':
            raise unittest.SkipTest('explicit stereo candidate required for qualification controls')
        super().setUpClass()

    def test_stereo_inventory_requires_explicit_role_revision_and_axes_policy(self):
        selected = dict(profile=self.profile, mapping=self.mapping, connected_xy=True,
                        stereo_xy=True, profile_revision=4,
                        xy_axes_policy='ordinary_mid_side_vector_direct_v1')
        for label, change in (
                ('stereo W role', dict(profile='w-demo-audio')),
                ('stereo legacy M base', dict(profile='m-demo-base')),
                ('stereo revision3', dict(profile_revision=3)),
                ('stereo unspecified revision', dict(profile_revision=None)),
                ('stereo unspecified axes', dict(xy_axes_policy=None)),
                ('stereo wrong axes', dict(xy_axes_policy='direct_xy')),
                ('stereo without connected trace', dict(connected_xy=False)),
                ('new inventory without stereo selection', dict(stereo_xy=False))):
            with self.subTest(case=label), self.assertRaises(ValueError) as error:
                audit_native_protocol(self.n, **dict(selected, **change))
            self.mutations.append(dict(case=label, rejected=True, error=str(error.exception)))

    def test_actual_entry_rejects_missing_or_disagreeing_stereo_qualification(self):
        from tools.workstation_performance_reset import DEMO_TIMING_TOOL, audit_demo_held_handshakes
        path = Path(os.environ['GW138K_NATIVE_PROTOCOL_VG'])
        candidate = next((p for p in path.parents if (p/'integration_inputs.json').is_file()),None)
        if candidate is None:
            self.skipTest('sealed source candidate required for provider qualification')
        source = candidate/'workstation/Prj1'
        metadata = json.loads((candidate/'integration_inputs.json').read_text())
        profile = json.loads((candidate/'workstation_profile.json').read_text())
        sdc = (source/'constraints/custom_138k.sdc').read_text()
        with tempfile.TemporaryDirectory(prefix='stereo-entry-qualification-') as directory:
            fixture = Path(directory)/'candidate'
            stage = fixture/'workstation/Prj1'
            for relative in (DEMO_TIMING_TOOL,'rtl/workstation/gw138k_push_workstation_top.v',
                             'rtl/workstation/workstation_runtime_controlled.sv',
                             'rtl/workstation/workstation_profile_m_demo.sv'):
                target = stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((source/relative).read_bytes())
            artifact = fixture/'workstation_profile.json'
            provider = stage/'rtl/workstation/workstation_profile_m_demo.sv'
            original = provider.read_text()
            self.assertEqual(original.splitlines().count('`define WORKSTATION_XY_STEREO'),1)
            def gate():
                return audit_demo_held_handshakes(stage,sdc,'M',metadata['demo_runtime_timing'],
                    self.n,mapping=self.mapping,netlist_text=path.read_text())
            def reject(label, message):
                with self.assertRaisesRegex(ValueError,message) as error:
                    gate()
                self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))
            reject('stereo provider missing artifact','profile artifact missing')
            artifact.write_text(json.dumps(profile))
            provider.write_text(original.replace('`define WORKSTATION_XY_STEREO','// stereo marker removed'))
            reject('stereo policy without provider marker','profile/provider disagreement')
            provider.write_text(original)
            changed=json.loads(json.dumps(profile));changed['configuration'].pop('xy_axes_policy')
            artifact.write_text(json.dumps(changed))
            reject('stereo provider without axes policy','profile/provider disagreement')
            changed=json.loads(json.dumps(profile));changed['revision']=3
            artifact.write_text(json.dumps(changed))
            reject('stereo provider revision3','revision4 axes policy')
            changed=json.loads(json.dumps(profile));changed['configuration']['demo_role']='W'
            artifact.write_text(json.dumps(changed))
            reject('stereo artifact wrong role','sealed M role')

if __name__ == '__main__':
    unittest.main()
