#!/usr/bin/env python3
"""Complete top-output inventories through the actual netlist parser/graph."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_recording_phase1_cdc import complete_closure
from tools.workstation_runtime_pcm_cdc import Graph, TOP
from tools.workstation_synthesis_netlist import SynthesisNetlist
from tools.workstation_task3_peripheral_releases_audit import closure_identity


def netlist(declarations, cells=''):
    return f"""module {TOP} (clk, scalar);
input clk;
output scalar;
{declarations}
DFFCE source_s0 (.Q(scalar), .D(1'b1), .CLK(clk), .CE(1'b1), .CLEAR(1'b0));
{cells}
endmodule
"""


def inventory(text):
    n = SynthesisNetlist(text, TOP)
    g = Graph(n)
    return complete_closure(n, g, ['source_s0'])


class CompleteClosureOutputs(unittest.TestCase):
    def test_scalar_label_is_unchanged(self):
        self.assertEqual(inventory(netlist(''))['top_output_endpoints'], {'scalar': 'scalar'})

    def test_each_reached_vector_bit_is_retained(self):
        text = netlist('output [4:2] observed;', """
LUT1 high_bit (.F(observed[4]), .I0(scalar));
defparam high_bit.INIT = 2'h1;
LUT1 low_bit (.F(observed[2]), .I0(scalar));
defparam low_bit.INIT = 2'h2;
DFFCE unrelated_s0 (.Q(observed[3]), .D(1'b0), .CLK(clk), .CE(1'b1), .CLEAR(1'b0));
""")
        self.assertEqual(inventory(text)['top_output_endpoints'], {
            'observed[2]': 'observed[2]', 'observed[4]': 'observed[4]', 'scalar': 'scalar'})

    def test_output_aliases_and_inout_bits_share_net_without_overwriting(self):
        text = netlist('output [4:2] observed;\noutput mirror;\ninout [0:1] bidirectional;', """
BUFG high_alias (.O(observed[4]), .I(scalar));
BUFG low_alias (.O(observed[2]), .I(scalar));
BUFG scalar_alias (.O(mirror), .I(scalar));
BUFG inout_zero (.O(bidirectional[0]), .I(scalar));
BUFG inout_one (.O(bidirectional[1]), .I(scalar));
""")
        expected = {bit: 'scalar' for bit in (
            'scalar', 'observed[2]', 'observed[4]', 'mirror', 'bidirectional[0]', 'bidirectional[1]')}
        n = SynthesisNetlist(text, TOP)
        g = Graph(n)
        self.assertEqual(complete_closure(n, g, ['source_s0'])['top_output_endpoints'], expected)
        # Reusing the cached map must preserve the complete public inventory.
        self.assertEqual(complete_closure(n, g, ['source_s0', 'source_s0'])['top_output_endpoints'], expected)

    def test_extra_export_changes_existing_inventory_identity(self):
        # Only a net's public direction changes; its cells, arcs and canonical
        # net are identical, so the export itself must invalidate the old seal.
        text = netlist('wire mirror;', 'BUFG alias (.O(mirror), .I(scalar));')
        original = inventory(text)
        changed = inventory(text.replace('wire mirror;', 'output mirror;'))
        self.assertEqual({k: v for k, v in original.items() if k != 'top_output_endpoints'},
                         {k: v for k, v in changed.items() if k != 'top_output_endpoints'})
        self.assertEqual(original['top_output_endpoints'], {'scalar': 'scalar'})
        self.assertEqual(changed['top_output_endpoints'], {'mirror': 'scalar', 'scalar': 'scalar'})
        self.assertNotEqual(closure_identity(original), closure_identity(changed))


if __name__ == '__main__':
    unittest.main()
