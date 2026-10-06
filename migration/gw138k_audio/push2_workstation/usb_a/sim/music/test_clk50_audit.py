"""Release gate checks: missing reports/hold failures/relaxed clocks cannot pass."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_clk50_timing import audit


def table(rows):
    return '<table>' + ''.join('<tr>' + ''.join('<td>' + str(v) + '</td>' for v in r) + '</tr>'
                              for r in rows) + '</table>'


def report(period=20, setup=1, hold=0.1, include_hold=True, recovery=0.2, removal=0.2, include_reset=True):
    # Reproduce Gowin's frequency-column omission: Rise immediately follows Period.
    text = table([['NO.', 'Clock Name', 'Type', 'Period', 'Frequency(MHz)', 'Rise', 'Fall',
                   'Source', 'Master', 'Objects'],
                  [1, 'clk_50m', 'Base', period, 0, 10, '', '', 'clk_50m']])
    text += table([['NO.', 'Clock Name', 'Constraint', 'Actual Fmax', 'Logic Level', 'Entity'],
                   [1, 'clk_50m', '50.000(MHz)', '55.000(MHz)', 12, 'TOP']])
    text += table([['Clock Name', 'Analysis Type', 'Endpoints TNS', 'Number of Endpoints'],
                   ['clk_50m', 'Setup', min(0, setup), int(setup < 0)],
                   ['clk_50m', 'Hold', min(0, hold), int(hold < 0)]])
    for kind, slack in [('setup', setup)] + ([('hold', hold)] if include_hold else []):
        text += '<h4>Report Command:report_timing -' + kind + ' -from_clock [get_clocks {clk_50m}] -to_clock [get_clocks {clk_50m}] -max_paths 100</h4>'
        text += table([['Path Number', 'Path Slack', 'From Node', 'To Node', 'From Clock',
                        'To Clock', 'Relation', 'Clock Skew', 'Data Delay'],
                       [1, slack, 'stage_a/Q', 'stage_b/D', 'clk_50m:[R]', 'clk_50m:[R]', period, 0, period-slack]])
    if include_reset:
        for kind, slack in [('recovery', recovery), ('removal', removal)]:
            text += '<h4>Report Command:report_timing -' + kind + ' -max_paths 25 -max_common_paths 1</h4>'
            text += table([['Path Number', 'Path Slack', 'From Node', 'To Node', 'From Clock',
                            'To Clock', 'Relation', 'Clock Skew', 'Data Delay'],
                           [1, slack, 'release/Q', 'stage_b/CLEAR', 'usb_48m:[R]', 'clk_50m:[R]', 0.833, 0, 0.5]])
    return text


class ReleaseGate(unittest.TestCase):
    def inspect(self, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            pnr = build / 'Prj1/impl/pnr'
            pnr.mkdir(parents=True)
            (pnr / 'Prj1_tr_content.html').write_text(report(**kwargs))
            return audit(build)

    def test_missing_frequency_cell_uses_20ns_period(self):
        result = self.inspect()
        self.assertEqual(result['clock_required_mhz'], 50)
        self.assertTrue(result['clk50_closed'])

    def test_missing_hold_report_cannot_release(self):
        self.assertFalse(self.inspect(include_hold=False)['clk50_closed'])

    def test_setup_and_hold_failures_are_independent(self):
        self.assertFalse(self.inspect(setup=-0.001)['clk50_closed'])
        self.assertFalse(self.inspect(hold=-0.001)['clk50_closed'])

    def test_missing_reset_checks_cannot_release(self):
        self.assertFalse(self.inspect(include_reset=False)['clk50_closed'])

    def test_reset_failure_cannot_hide_behind_positive_setup_hold(self):
        result = self.inspect(recovery=-0.001)
        self.assertTrue(result['clk50_setup_hold_closed'])
        self.assertFalse(result['clk50_closed'])
        self.assertFalse(self.inspect(removal=-0.001)['clk50_closed'])

    def test_relaxed_clock_cannot_release_as_50mhz(self):
        self.assertFalse(self.inspect(period=24)['clk50_closed'])


if __name__ == '__main__':
    unittest.main()
