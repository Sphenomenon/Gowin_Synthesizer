"""Prevent repeating the U16 contact/function confusion in CNN-DEMO."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.workstation_cnn_demo import adapt_tf_pins
from tools.workstation_pinout import parse_locations


class TfPins(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = json.loads((ROOT/'boards/custom_138k/cnn_demo_tf_spi.json').read_text())
        self.inputs = self.root/'inputs'
        self.inputs.mkdir()
        self.carrier = self.inputs/self.profile['carrier_filename']
        self.carrier.write_text("$NETS\n'BANK5_V15' ; U16.7\n'BANK5_Y16' ; U16.3\n'BANK5_W15' ; U16.5\n'BANK5_AB15' ; U16.2\n$END\n")
        self.profile['carrier_sha256'] = hashlib.sha256(self.carrier.read_bytes()).hexdigest()
        profile = self.root/'boards/custom_138k/cnn_demo_tf_spi.json'
        profile.parent.mkdir(parents=True)
        profile.write_text(json.dumps(self.profile))
        self.stage = self.root/'stage'
        (self.stage/'constraints').mkdir(parents=True)
        self.inherited = '\n'.join(f'IO_LOC "{port}" {pin["inherited_ball"]};' for port,pin in self.profile['ports'].items())+'\n'
        for name in ('custom_138k.cst', 'custom_138k.locations.cst'):
            (self.stage/'constraints'/name).write_text(self.inherited)

    def test_spi_protocol_uses_standard_sd_contacts(self):
        expected = {'sd_miso': ('7','DAT0'), 'sd_mosi': ('3','CMD'),
                    'sd_sck': ('5','CLX'), 'sd_cs_n': ('2','CD/DAT3')}
        for port,(number,function) in expected.items():
            self.assertEqual(self.profile['ports'][port]['node'], 'U16.'+number)
            self.assertEqual(self.profile['symbol_evidence']['pin_names'][number], function)
        adapt_tf_pins(self.root,self.inputs,self.stage)
        locations = parse_locations((self.stage/'constraints/custom_138k.cst').read_text())
        self.assertEqual(locations, {'sd_miso':['V15'],'sd_mosi':['Y16'],
                                    'sd_sck':['W15'],'sd_cs_n':['AB15']})

    def test_carrier_drift_rejected(self):
        self.carrier.write_text(self.carrier.read_text().replace('V15','AA15'))
        with self.assertRaisesRegex(ValueError,'source drift'):
            adapt_tf_pins(self.root,self.inputs,self.stage)

    def test_inherited_anchor_drift_rejected(self):
        (self.stage/'constraints/custom_138k.cst').write_text(self.inherited.replace('AA15','AA16'))
        with self.assertRaisesRegex(ValueError,'anchor drift'):
            adapt_tf_pins(self.root,self.inputs,self.stage)

    def test_other_io_collision_rejected(self):
        with (self.stage/'constraints/custom_138k.cst').open('a') as f:
            f.write('IO_LOC "other" Y16;\n')
        with self.assertRaisesRegex(ValueError,'collides'):
            adapt_tf_pins(self.root,self.inputs,self.stage)


if __name__=='__main__': unittest.main()
