"""Preserve global STA versus explicit DDR/held timing report ownership."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.audit_clk50_timing import TimingTables


class TimingReportContext(unittest.TestCase):
    def test_exception_failure_does_not_become_global_removal(self):
        # Minimal excerpts of the actual M v21 headings and failing path.
        report = '''
<h4>Report Command:report_timing -removal -max_paths 2000 -max_common_paths 1</h4>
<table><tr><td>Slack</td><td>0.278</td></tr></table>
<h4>Report Command:report_exceptions -setup -max_paths 5 -max_common_paths 1</h4>
<h4>Timing Path Constraint[95]: set_max_delay 10.000 -from [get_pins {u_ddr_init/*/Q}] -to [get_pins {u_dqs/HOLD}]</h4>
<table><tr><td>Slack</td><td>-2.006</td></tr></table>
<h4>Report Command:report_exceptions -hold -max_paths 5 -max_common_paths 1</h4>
<h4>Timing Path Constraint[3]: set_min_delay 1.800 -from [get_pins {held/Q}] -to [get_pins {local/D}]</h4>
<table><tr><td>Slack</td><td>-0.231</td></tr></table>
<h4>Report Command:report_timing -setup -max_paths 2000 -max_common_paths 1</h4>
<table><tr><td>Slack</td><td>-4.072</td></tr></table>'''
        parser = TimingTables()
        parser.feed(report)
        self.assertEqual(len(parser.tables), 4)
        self.assertEqual(len(parser.table_contexts), 4)
        self.assertTrue(parser.tables[0][0].startswith('report_timing -removal '))
        self.assertTrue(parser.tables[1][0].startswith('report_exceptions -setup '))
        self.assertTrue(parser.tables[2][0].startswith('report_exceptions -hold '))
        self.assertIn('set_max_delay 10.000', parser.table_contexts[1]['constraint'])
        self.assertIn('set_min_delay 1.800', parser.table_contexts[2]['constraint'])
        self.assertEqual(parser.table_contexts[3]['constraint'], '')
        global_removal = [float(dict(rows)['Slack']) for cmd, rows in parser.tables
                          if cmd.startswith('report_timing -removal ')]
        self.assertEqual(min(global_removal), 0.278)


if __name__ == '__main__':
    unittest.main()
