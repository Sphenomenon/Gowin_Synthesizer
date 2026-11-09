"""Actual broker/FIFO retirement, reset and corruption negative controls."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import workstation_cnn_staging_retirement as selection


class RetirementTests(unittest.TestCase):
    def run_flow(self, reset=0, mutation=None):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)
            helper=(ROOT/selection.HELPER).read_text()
            if mutation:
                before,after=mutation
                self.assertEqual(helper.count(before),1)
                helper=helper.replace(before,after,1)
            selected=output/'retirement.sv'
            selected.write_text(helper)
            command=['iverilog','-g2012','-s','tb_cnn_staging_retirement',
                     '-Ptb_cnn_staging_retirement.RESET_MIDFLIGHT='+str(reset),
                     '-o',str(output/'sim.vvp'),
                     str(ROOT/'rtl/music/music_async_fifo.sv'),
                     str(ROOT/'rtl/music/workstation_cnn_ddr_broker.sv'),
                     str(selected),str(ROOT/'sim/music/tb_cnn_staging_retirement.sv')]
            built=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            return subprocess.run(['vvp',str(output/'sim.vvp')],
                                  capture_output=True,text=True,timeout=30)

    def test_async_broker_native_scoreboard_and_reset(self):
        for reset in (0,1):
            with self.subTest(reset=reset):
                result=self.run_flow(reset)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('native=64 completion=64 reads=32 writes=32',result.stdout)

    def test_completion_corruption_and_lost_retirement_rejected(self):
        for mutation in [
            ('request_retire_o<=commit_i;','request_retire_o<=0;'),
            ('completion_data_o<={write_complete,response_data_i};',
             'completion_data_o<={!write_complete,response_data_i};'),
        ]:
            with self.subTest(mutation=mutation[0]):
                result=self.run_flow(mutation=mutation)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertRegex(result.stdout,'duplicate/lost/corrupt')

    def test_checked_selection_and_inverse(self):
        original=(ROOT/selection.SOURCE).read_text()
        self.assertEqual(selection.restore(selection.adapt(original)),original)
        with self.assertRaisesRegex(ValueError,'parent source drift'):
            selection.adapt(original+'\n')
        with self.assertRaisesRegex(ValueError,'requires locally released W'):
            selection.configured({selection.KEY:selection.POLICY,'demo_role':'M'})


if __name__=='__main__':
    unittest.main()
