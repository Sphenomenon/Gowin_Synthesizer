"""Mapped W comparison capture: reject changed data, clocks and admission."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_native_protocol_audit import protocol_netlist
from tools.workstation_runtime_pcm_cdc import Graph
from tools import workstation_w_generation_match as match


class GenerationMatch(unittest.TestCase):
    def test_actual_mapping_and_negative_controls(self):
        selected = os.environ.get('GW138K_GENERATION_MATCH_W_STAGE')
        if not selected:
            self.skipTest('explicit complete W synthesis stage required')
        path = Path(selected) / 'impl/gwsynthesis/custom_138k_integration.vg'
        before = path.read_bytes()
        n = protocol_netlist(before.decode(), mapping='synthesis')
        g = Graph(n)
        scope = 'u_task3_media/raw_store'
        proof = match.audit(n)
        self.assertEqual(proof['conditional_comparison_stability_induction'], 'unsat')
        targets = [g.register(scope, 'g_command_capture.' + stem)
                   for stem in ('next_generation_match', 'current_generation_match')]
        cases = [(p, 'ports', 'D', "1'b0") for p in targets]
        cases += [(targets[0], part, pin, value) for part, pin, value in (
            ('ports', 'CE', "1'b1"), ('ports', 'CLEAR', "1'b0"),
            ('ports', 'CLK', 'audio_clk'), ('parameters', 'INIT', "1'b1"))]
        # Preserve the common bank, then deliberately allow a write while no
        # command starts. The stability proof must reject this real hazard.
        bank = g.group(scope, 'memory_generation', 32)
        for p, part, pin, value in cases:
            saved = deepcopy(n.cells[p])
            n.cells[p][part][pin] = value
            try:
                with self.subTest(register=p, pin=pin), self.assertRaises(ValueError):
                    match.audit(n)
            finally:
                n.cells[p] = saved
        saved = {p:deepcopy(n.cells[p]) for p in bank}
        for p in bank:
            n.cells[p]['ports']['CE'] = "1'b1"
        try:
            with self.assertRaises(ValueError):
                match.audit(n)
        finally:
            n.cells.update(saved)
        self.assertEqual(path.read_bytes(), before)
        print('W mapped32-bit comparisons, conditional stability and seven mutants PASS',
              hashlib.sha256(before).hexdigest())


if __name__ == '__main__':
    unittest.main()
