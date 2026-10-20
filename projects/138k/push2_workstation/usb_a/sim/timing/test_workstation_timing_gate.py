"""The timing gate must not accept missing clocks, hold/reset failures or relaxed targets."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from audit_workstation_timing import TARGETS, audit
from workstation_memory import check_feature_storage, REQUIRED
from workstation_timing_constraints import timing_reports
from build_workstation_timing import strip_owned_timing_reports


def table(rows):
    return '<table>' + ''.join('<tr>' + ''.join('<td>' + str(x) + '</td>' for x in row) + '</tr>' for row in rows) + '</table>'


def fixture(missing_clock=None, relaxed=False, kind=None, negative_summary=False, missing_reset=False, missing_detailed=None):
    clocks = [(name, freq) for name, freq in TARGETS.items() if name != missing_clock]
    text = table([['NO.', 'Clock Name', 'Constraint', 'Actual Fmax', 'Logic Level', 'Entity']] +
                 [[i, name, str(freq - 1 if relaxed and name == 'usb_48m' else freq) + '(MHz)',
                   str(freq + 10) + '(MHz)', 4, 'TOP'] for i, (name, freq) in enumerate(clocks)])
    text += table([['Clock Name', 'Analysis Type', 'Endpoints TNS', 'Number of Endpoints']] +
                  [[name, check, -0.001 if negative_summary and name == 'audio_76m8' and check == 'Hold' else 0,
                    int(negative_summary and name == 'audio_76m8' and check == 'Hold')]
                   for name, _ in clocks for check in ['Setup', 'Hold']])
    for check in ['setup', 'hold', 'recovery', 'removal']:
        if check == missing_detailed or (missing_reset and check in ['recovery', 'removal']):
            continue
        text += '<h4>Report Command:report_timing -' + check + ' -max_paths 100</h4>'
        text += table([['Path Number', 'Path Slack', 'From Node', 'To Node', 'From Clock',
                        'To Clock', 'Relation', 'Clock Skew', 'Data Delay'],
                       [1, -0.001 if kind == check else 0.1, 'a/Q', 'b/D', 'clk_50m:[R]', 'clk_50m:[R]', 20, 0, 19]])
    return text


class WorkstationTimingGate(unittest.TestCase):
    def inspect(self, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            pnr = build / 'Prj1/impl/pnr'
            pnr.mkdir(parents=True)
            (pnr / 'Prj1_tr_content.html').write_text(fixture(**kwargs))
            return audit(build)

    def test_complete_positive_evidence_passes(self):
        self.assertTrue(self.inspect()['timing_closed'])

    def test_missing_required_clock_cannot_pass(self):
        for clock in TARGETS:
            with self.subTest(clock=clock):
                self.assertFalse(self.inspect(missing_clock=clock)['timing_closed'])

    def test_relaxed_target_cannot_pass(self):
        self.assertFalse(self.inspect(relaxed=True)['timing_closed'])

    def test_positive_fmax_does_not_hide_summary_hold_failure(self):
        self.assertFalse(self.inspect(negative_summary=True)['timing_closed'])

    def test_each_negative_path_check_fails(self):
        for kind in ['setup', 'hold', 'recovery', 'removal']:
            with self.subTest(kind=kind):
                self.assertFalse(self.inspect(kind=kind)['timing_closed'])

    def test_missing_global_data_reports_fail(self):
        for kind in ['setup', 'hold']:
            with self.subTest(kind=kind):
                self.assertFalse(self.inspect(missing_detailed=kind)['timing_closed'])

    def test_missing_reset_reports_fail(self):
        self.assertFalse(self.inspect(missing_reset=True)['timing_closed'])


class ExperimentReportRefresh(unittest.TestCase):
    def test_report_refresh_keeps_trailing_constraints(self):
        # A stricter budget appended by an experiment must remain an input.
        reports=timing_reports()
        suffix='\nset_max_delay 9.700 -from [get_clocks {ddr_ui100}] -to [get_clocks {ddr_ui100}]\n'
        original='create_clock -period 20 clk_50m\n'+reports+suffix
        refreshed=strip_owned_timing_reports(original)+reports
        self.assertIn(suffix,refreshed)
        self.assertEqual(refreshed.count('report_timing -setup -max_paths 100'),1)

    def test_unknown_report_block_fails_without_discarding_constraints(self):
        altered=timing_reports().replace('-max_paths 100','-max_paths 101')
        with self.assertRaisesRegex(ValueError,'refusing to discard'):
            strip_owned_timing_reports('create_clock -period 20 clk_50m\n'+altered+'set_max_delay 9.7\n')


class SynthesizedFeatureGate(unittest.TestCase):
    def test_retained_empty_hierarchy_row_does_not_hide_swept_vector_engine(self):
        for rows in ({}, {REQUIRED['vector_voices']: {'subtree_bsram': 0}}):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, 'vector geometry ROM swept'):
                check_feature_storage(rows)
        check_feature_storage({REQUIRED['vector_voices']: {'subtree_bsram': 9}})


if __name__ == '__main__':
    unittest.main()
