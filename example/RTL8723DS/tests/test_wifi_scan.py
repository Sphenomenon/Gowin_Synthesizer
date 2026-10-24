"""RX descriptor and 802.11 IE parsing, including captured board beacons."""
import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from wifi_scan import parse_beacon


def packet(ssid=b'test', extra=b'', subtype=0x80):
    frame=bytearray(36)
    frame[0]=subtype
    frame[16:22]=bytes.fromhex('001122334455')
    frame+=bytes([0,len(ssid)])+ssid+bytes([3,1,6])+extra
    return struct.pack('<6I',len(frame),0,0,0,0,0)+frame


class BeaconTests(unittest.TestCase):
    def test_captured_board_beacons(self):
        fixtures=json.loads((Path(__file__).parent/'fixtures/wifi_beacons.json').read_text())
        for item in fixtures['frames']:
            with self.subTest(bssid=item['expected']['bssid']):
                self.assertEqual(parse_beacon(bytes.fromhex(item['hex']),1),item['expected'])

    def test_hidden_and_binary_ssid(self):
        self.assertEqual(parse_beacon(packet(b''),1)['ssid'],'')
        self.assertEqual(parse_beacon(packet(b'\xff\x00'),1)['ssid_hex'],'ff00')
        self.assertEqual(parse_beacon(packet(subtype=0x50),1)['frame_type'],'probe_response')

    def test_descriptor_errors_and_truncation(self):
        good=packet()
        for flags in (0x4000,0x8000):
            bad=bytearray(good)
            struct.pack_into('<I',bad,0,int.from_bytes(bad[:4],'little')|flags)
            self.assertIsNone(parse_beacon(bad,1))
        bad=bytearray(good);struct.pack_into('<I',bad,8,1<<28)
        self.assertIsNone(parse_beacon(bad,1))
        for n in range(len(good)):
            self.assertIsNone(parse_beacon(good[:n],1))

    def test_malformed_ies_and_non_beacons(self):
        for data in (packet(b'a'*33),packet(extra=b'\x30\x20\x01'),
                     packet(subtype=0x08),packet(subtype=0x81)):
            self.assertIsNone(parse_beacon(data,1))
        for flags in (1,2,0x40):
            bad=bytearray(packet());bad[25]=flags
            self.assertIsNone(parse_beacon(bad,1))


if __name__=='__main__':
    unittest.main()
