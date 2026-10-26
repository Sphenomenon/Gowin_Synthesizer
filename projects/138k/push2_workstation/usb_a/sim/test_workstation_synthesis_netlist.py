"""Scalar and bit-select topology used by clock and native reset audits."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_synthesis_netlist import SynthesisNetlist


SOURCE = '''module leaf (ready, payload, clk);
input [1:1] ready;
input [0:3] payload;
input clk;
endmodule
module top (clk, released, data);
input clk;
input [1:0] released;
input [11:8] data;
wire buffered;
  IBUF clock_buffer (
    .I(clk), .O(buffered)
);
  leaf sliced (
    .ready(released[1]), .payload(data[11:8]), .clk(buffered)
);
  leaf whole (
    .ready(released[0]), .payload(data), .clk(buffered)
);
endmodule
'''


class SourceNetlist(unittest.TestCase):
    def test_escaped_instance_parameters_allow_the_required_separator_space(self):
        source = r'''module top (clk);
input clk;
  CLKDIV \memory/clock/divider  (
    .HCLKIN(clk), .CLKOUT(divided)
);
defparam \memory/clock/divider .DIV_MODE="4";
endmodule
'''
        netlist = SynthesisNetlist(source, 'top')
        self.assertEqual(netlist.cells['memory/clock/divider']['parameters']['DIV_MODE'], '"4"')
        self.assertEqual(netlist.pin('memory/clock/divider', 'HCLKIN'), 'clk')
        with self.assertRaisesRegex(ValueError, 'duplicate netlist parameter'):
            SynthesisNetlist(source.replace('endmodule', 'defparam \\memory/clock/divider .DIV_MODE="5";\nendmodule'), 'top')

    def test_flattened_labels_use_their_declared_scope_not_slash_prefixes(self):
        source = r'''module leaf (clk, data);
input clk;
input [1:1] data;
  DFFCE \engine/path/register  (
    .CLK(clk), .D(data[1]), .Q(held)
);
endmodule
module top (clk, source);
input clk;
input [1:0] source;
  IBUF clock_buffer (
    .I(clk), .O(buffered)
);
  leaf \flattened/path  (
    .clk(buffered), .data(source[1])
);
endmodule
'''
        netlist = SynthesisNetlist(source, 'top')
        self.assertEqual(netlist.pin('flattened/path/engine/path/register', 'CLK'), 'clk')
        self.assertEqual(netlist.pin('flattened/path/engine/path/register', 'D'), 'source[1]')
        self.assertEqual(netlist.scopes['flattened/path'], '')
        self.assertEqual(netlist.directions['leaf'], dict(clk='input', data='input'))

    def test_flattened_and_hierarchical_instance_collision_is_rejected(self):
        source = SOURCE.replace('input clk;\nendmodule', 'input clk;\n  DFFCE register (\n    .CLK(clk)\n);\nendmodule')
        source = source.replace('  leaf whole (', '  DFFCE \\sliced/register  (\n    .CLK(clk)\n);\n  leaf whole (')
        with self.assertRaisesRegex(ValueError, 'ambiguous flattened/hierarchical instance'):
            SynthesisNetlist(source, 'top')

    def test_port_directions_include_scalar_and_escaped_bus_names(self):
        source = SOURCE.replace('wire buffered;', 'wire buffered;\noutput reg result;\ninout [3:0] \\lane/name ;')
        netlist = SynthesisNetlist(source, 'top')
        self.assertEqual(netlist.directions['top']['result'], 'output')
        self.assertEqual(netlist.directions['top']['lane/name'], 'inout')

    def test_scalar_buffers_and_nonzero_single_bit_ports(self):
        netlist = SynthesisNetlist(SOURCE, 'top')
        self.assertEqual(netlist.canonical('sliced', 'clk'), 'clk')
        self.assertEqual(netlist.canonical('sliced', 'ready[1]'), 'released[1]')
        self.assertEqual(netlist.canonical('whole', 'ready[1]'), 'released[0]')

    def test_reversed_formal_range_and_selected_or_whole_actual_bus(self):
        netlist = SynthesisNetlist(SOURCE, 'top')
        for scope in ('sliced', 'whole'):
            for index in range(4):
                self.assertEqual(netlist.canonical(scope, 'payload[' + str(index) + ']'),
                                 'data[' + str(11 - index) + ']')

    def test_unsupported_or_invalid_vector_projection_is_not_guessed(self):
        netlist = SynthesisNetlist(SOURCE.replace('.payload(data[11:8])', '.payload({data[9:8],data[11:10]})'), 'top')
        with self.assertRaisesRegex(ValueError, 'unsupported vector port binding'):
            netlist.canonical('sliced', 'payload[0]')
        with self.assertRaisesRegex(ValueError, 'invalid vector port bit'):
            netlist.canonical('sliced', 'ready[0]')

    def test_duplicate_modules_parameters_and_recursive_hierarchy_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate netlist module'):
            SynthesisNetlist(SOURCE + SOURCE, 'top')
        duplicate = SOURCE.replace('  leaf sliced (',
                                   'defparam clock_buffer.INIT=1;\ndefparam clock_buffer.INIT=0;\n  leaf sliced (')
        with self.assertRaisesRegex(ValueError, 'duplicate netlist parameter'):
            SynthesisNetlist(duplicate, 'top')
        with self.assertRaisesRegex(ValueError, 'recursive netlist hierarchy'):
            SynthesisNetlist(SOURCE.replace('  leaf whole (', '  top whole ('), 'top')


if __name__ == '__main__':
    unittest.main()
