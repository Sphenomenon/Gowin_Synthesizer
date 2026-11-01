#!/usr/bin/env python3
"""Actual task3 root-state next-Q and destructive controls; no EDA launch."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools.workstation_task3_root_reset_audit import (
    audit_root_startup, source_binding, RootDiagram, ROOT_SOURCE, PROVIDER, TOP_SOURCE)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class RootPrimitiveReference(unittest.TestCase):
    def test_official_add_and_reset_before_enable(self):
        selected = os.environ.get('GW138K_GW5A_PRIM_SIM')
        if not selected:
            self.skipTest('explicit official GW5A prim_sim required')
        model = Path(selected).read_text()
        modules = []
        for name in ('GSR', 'ALU', 'DFFCE', 'DFFRE'):
            rows = re.findall(r'^module\s+' + name + r'\s*\(.*?^endmodule\b[^\n]*', model, re.M | re.S)
            self.assertEqual(len(rows), 1)
            modules.append(rows[0])
        fixture = r'''`timescale 1ns/1ps
module tb_root_primitive;
reg [2:0] inputs=0;
wire sum,carry,async_q,sync_q;
reg d=0,ce=0,reset=0,clk=0;
integer i;
GSR GSR(.GSRI(1'b1));
ALU #(.ALU_MODE(0)) add(.SUM(sum),.COUT(carry),.I0(inputs[0]),.I1(inputs[1]),.I3(1'b0),.CIN(inputs[2]));
DFFCE #(.INIT(1'b0)) a(.Q(async_q),.D(d),.CLK(clk),.CE(ce),.CLEAR(reset));
DFFRE #(.INIT(1'b0)) s(.Q(sync_q),.D(d),.CLK(clk),.CE(ce),.RESET(reset));
initial begin
 #5;
 for(i=0;i<8;i=i+1)begin inputs=i;#1;$display("ADD %0d %0d %0d",i,sum,carry);end
 d=1;ce=1;#1;clk=1;#1;clk=0;#1;
 if(async_q!==1 || sync_q!==1)$fatal(1,"initial enabled capture failed");
 ce=0;reset=1;#1;
 if(async_q!==0 || sync_q!==1)$fatal(1,"async/sync reset timing wrong");
 clk=1;#1;clk=0;#1;
 if(async_q!==0 || sync_q!==0)$fatal(1,"reset must precede disabled CE");
 reset=0;d=1;#1;clk=1;#1;clk=0;#1;
 if(async_q!==0 || sync_q!==0)$fatal(1,"disabled FF did not hold");
 ce=1;#1;clk=1;#1;clk=0;#1;
 if(async_q!==1 || sync_q!==1)$fatal(1,"FF did not resume after reset");
 $display("PASS official reset-before-CE");$finish;
end
endmodule
'''
        with tempfile.TemporaryDirectory(prefix='task3-root-primitive-') as directory:
            source, exe = Path(directory) / 'tb.sv', Path(directory) / 'run'
            source.write_text('\n'.join(modules) + '\n' + fixture)
            build = subprocess.run(['iverilog', '-g2012', '-s', 'tb_root_primitive',
                                    '-o', str(exe), str(source)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run(['vvp', str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        ports = {'I0':'a', 'I1':'b', 'CIN':'c', 'I3':"1'b0", 'SUM':'sum', 'COUT':'cout'}
        n = SimpleNamespace(cells={'alu':{'kind':'ALU','parameters':{'ALU_MODE':'0'}}},
                            pin=lambda path, pin: ports[pin])
        graph = SimpleNamespace(n=n, high={"1'b1"}, low={"1'b0"}, regs={},
                                drivers={'sum':[('alu','SUM')], 'cout':[('alu','COUT')]})
        bd = RootDiagram(['a','b','c'])
        roots = [bd.net(graph, name) for name in ('sum','cout')]
        def evaluate(node, value):
            while node > 1:
                variable, low, high = bd.nodes[node]
                node = high if (value >> variable) & 1 else low
            return node
        rows = re.findall(r'^ADD (\d+) ([01]) ([01])$', run.stdout, re.M)
        self.assertEqual(len(rows), 8)
        for value, expected_sum, expected_carry in rows:
            self.assertEqual([evaluate(node,int(value)) for node in roots],
                             [int(expected_sum),int(expected_carry)])
        print('PASS official GW5A ADD 8 vectors and DFFCE/DFFRE reset-before-CE; sha256=' + sha(selected))


class ActualTask3Root(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        selected = os.environ.get('GW138K_TASK3_ROOT_VG')
        stage = os.environ.get('GW138K_TASK3_ROOT_STAGE')
        if not selected or not stage:
            raise unittest.SkipTest('explicit actual VG and sealed stage required; no cache fallback')
        cls.path, cls.stage = Path(selected), Path(stage)
        cls.mapping = os.environ.get('GW138K_TASK3_ROOT_MAPPING', 'synthesis')
        cls.n = protocol_netlist(cls.path.read_text(), mapping=cls.mapping)
        cls.mutations, cls.positive = [], None
        cls.before = {str(path):sha(path) for path in (cls.path, cls.stage/'Prj1.gprj',
                      cls.stage/ROOT_SOURCE, cls.stage/PROVIDER, cls.stage/TOP_SOURCE)}

    @classmethod
    def tearDownClass(cls):
        assert cls.before == {path:sha(path) for path in cls.before}, 'actual source/netlist inputs drifted'
        selected = os.environ.get('GW138K_TASK3_ROOT_EVIDENCE')
        if selected:
            Path(selected).write_text(json.dumps(dict(status='PASS', mapping=cls.mapping,
                actual_input_sha256=cls.before, actual_root=cls.positive,
                mutations=cls.mutations, mutation_count=len(cls.mutations),
                hardware_tested=False), indent=2)+'\n')

    def test_actual_all_35_reset_inclusive_state_updates(self):
        result = audit_root_startup(self.n, stage=self.stage)
        self.assertEqual(result['actual_state_bits'], 35)
        self.assertEqual(result['state_assignment_count'], 1 << 35)
        self.assertEqual(result['hold_compare_exact_value'], 1023)
        self.assertEqual(result['first_root_rise_clock_edge_from_zero_init'], 1026)
        self.assertTrue(result['all_state_assignments_proven'])
        self.__class__.positive = result

    @contextmanager
    def changed(self, path, part, key, value):
        old = self.n.cells[path][part][key]
        self.n.cells[path][part][key] = value
        try:
            yield
        finally:
            self.n.cells[path][part][key] = old

    def test_actual_state_and_arithmetic_mutants(self):
        g = Graph(self.n)
        started = g.register('u_reset','started')
        sync = g.group('u_reset','sync_ff',2)
        count = g.group('u_reset','startup_count',32)
        alu = next(path for path, cell in self.n.cells.items()
                   if path.startswith('u_reset/') and cell['kind']=='ALU')
        comparator = next(path for path, cell in self.n.cells.items()
                          if path.startswith('u_reset/') and cell['kind']=='LUT4'
                          and cell['parameters'].get('INIT')=="16'h1000")
        cases = [
            ('root INIT',started,'parameters','INIT',"1'b1"),
            ('root clock',started,'ports','CLK',"1'b0"),
            ('root premature CE',started,'ports','CE',"1'b1"),
            ('root reset removed',started,'ports','RESET',"1'b0"),
            ('sync1 bypass',sync[1],'ports','D',"1'b1"),
            ('sync0 assertion',sync[0],'ports','CLEAR',"1'b1"),
            ('counter high INIT',count[31],'parameters','INIT',"1'b1"),
            ('counter LSB D',count[0],'ports','D',"1'b0"),
            ('counter high CE',count[31],'ports','CE',"1'b0"),
            ('counter reset removed',count[23],'ports','RESET',"1'b0"),
            ('compare threshold changed',comparator,'parameters','INIT',"16'h2000"),
            ('unreviewed ALU mode',alu,'parameters','ALU_MODE','1'),
            ('ALU I3 ungrounded',alu,'ports','I3',"1'b1"),
            ('ALU carry seed changed',alu,'ports','CIN',"1'b1"),
        ]
        for label,path,part,key,value in cases:
            with self.subTest(case=label), self.changed(path,part,key,value):
                with self.assertRaises(ValueError) as error:
                    audit_root_startup(self.n,stage=self.stage)
            self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))

    def test_selected_source_negative_controls(self):
        with tempfile.TemporaryDirectory(prefix='task3-root-source-') as directory:
            stage=Path(directory)
            for relative in ('Prj1.gprj',ROOT_SOURCE,PROVIDER,TOP_SOURCE,
                    'rtl/workstation/workstation_task3_tf_storage_top_reference.json',
                    'rtl/workstation/workstation_task3_w_media_top_reference.json'):
                path=stage/relative;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes((self.stage/relative).read_bytes())
            source_binding(stage)
            cases = [
                ('root source HOLD changed',ROOT_SOURCE,'HOLD_CYCLES = 1024','HOLD_CYCLES = 1023'),
                ('provider DIRECT disabled',PROVIDER,'`define WORKSTATION_TF_DIRECT_NATIVE','// no DIRECT'),
                ('top common replaced by one',TOP_SOURCE,'wire runtime_common_reset_n=reset_n;',"wire runtime_common_reset_n=1'b1;"),
                ('top root clock disconnected',TOP_SOURCE,'reset_release u_reset(.clk(clk_50m)','reset_release u_reset(.clk(audio_clk)'),
                ('provider compilation unselected','Prj1.gprj','path="'+PROVIDER+'" type="file.verilog" enable="1"','path="'+PROVIDER+'" type="file.verilog" enable="0"'),
            ]
            for label,relative,before,after in cases:
                path=stage/relative;original=path.read_text()
                self.assertEqual(original.count(before),1,label)
                path.write_text(original.replace(before,after))
                try:
                    with self.subTest(case=label),self.assertRaises(ValueError) as error:
                        source_binding(stage)
                finally:
                    path.write_text(original)
                self.mutations.append(dict(case=label,rejected=True,error=str(error.exception)))


if __name__ == '__main__':
    unittest.main()
