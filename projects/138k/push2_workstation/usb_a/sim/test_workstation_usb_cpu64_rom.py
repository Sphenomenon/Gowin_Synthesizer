"""Mapped 64 KiB ROM proof: strict old/new inventories and corruptions."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.stage_usb_firmware import sha
from tools.workstation_custom_board_audit import check_rom


def fixture(words, prefix):
    lines = ['module workstation_usb2_cpu_bus ();']
    for byte in range(4):
        for bit in range(8):
            offset = byte*8+bit
            name = f'{prefix}memory_{byte}_{prefix}memory_{byte}_0_{bit}_s'
            token = '\\' + name + ' ' if prefix else name
            output = f'\\g_ram64.read_q [{offset}]' if prefix else f'memory_read_q[{offset}]'
            data = '{' + ','.join(['GND']*31 + [f'data_write_data[{offset}]']) + '}'
            lines.extend((f'  SDPB {token} (',
                f'    .DO({{DO_{offset}[31:1],{output}}}),',
                '    .CLKA(usb_clk), .CLKB(usb_clk),',
                '    .ADA(data_address[15:2]), .ADB(memory_address[13:0]),',
                f'    .DI({data}), .CEA(byte_we_{byte}),',
                '    .CEB(VCC), .OCE(GND), .RESET(GND),',
                '    .BLKSELA({GND,GND,GND}), .BLKSELB({GND,GND,GND})', '  );'))
            for key, value in (('BIT_WIDTH_0', '1'), ('BIT_WIDTH_1', '1'),
                               ('READ_MODE', "1'b0"), ('RESET_MODE', '"SYNC"'),
                               ('BLK_SEL_0', "3'b000"), ('BLK_SEL_1', "3'b000")):
                lines.append(f'defparam {token}.{key}={value};')
            packed = sum(((value >> offset) & 1) << address for address, value in enumerate(words))
            for chunk in range(64):
                value = (packed >> (256*chunk)) & ((1 << 256)-1)
                lines.append(f"defparam {token}.INIT_RAM_{chunk:02X}=256'h{value:064X};")
    return '\n'.join([*lines, 'endmodule', ''])


class UsbCpu64MappedRom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Nontrivial data at every address, including the high address/bit, makes
        # a partial or truncated initialization proof observably incorrect.
        cls.words = [int.from_bytes(hashlib.sha256(address.to_bytes(4, 'little')).digest()[:4], 'little')
                     for address in range(16384)]
        cls.images = {prefix: fixture(cls.words, prefix) for prefix in ('', 'g_ram64.')}

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='usb-cpu64-rom-')
        self.addCleanup(self.temporary.cleanup)
        self.stage = Path(self.temporary.name)
        self.rom = self.stage / 'usb2_cpu.hex'
        self.rom.write_text(''.join(f'{value:08x}\n' for value in self.words))
        self.digest = sha(self.rom)

    def verify(self, text):
        return check_rom(self.stage, text, self.digest)

    def test_both_complete_hierarchies_prove_every_word(self):
        for prefix, text in self.images.items():
            with self.subTest(prefix=prefix):
                self.assertEqual(self.verify(text), 16384)

    def test_mixed_missing_extra_and_colliding_inventory_rejected(self):
        text = self.images['g_ram64.']
        first = 'g_ram64.memory_0_g_ram64.memory_0_0_0_s'
        for changed in (text.replace('\\' + first + ' ', 'memory_0_memory_0_0_0_s'),
                        text.replace('SDPB \\' + first, 'DPB \\' + first),
                        text.replace('endmodule', '  SDPB extra (.DO(unused));\nendmodule'),
                        text.replace('g_ram64.memory_0_g_ram64.memory_0_0_1_s', first)):
            with self.subTest(change=changed[:90]), self.assertRaises(ValueError):
                self.verify(changed)

    def test_width_clock_address_data_output_and_mode_drift_rejected(self):
        text = self.images['g_ram64.']
        mutations = {
            '.BIT_WIDTH_1=1;': '.BIT_WIDTH_1=2;',
            '.CLKB(usb_clk)': '.CLKB(audio_clk)',
            '.ADA(data_address[15:2])': '.ADA(data_address[14:1])',
            '.ADB(memory_address[13:0])': '.ADB(memory_address[12:0])',
            'data_write_data[31]': 'data_write_data[30]',
            '\\g_ram64.read_q [31]': '\\g_ram64.read_q [30]',
            '.READ_MODE=1\'b0;': '.READ_MODE=1\'b1;',
            '.BLK_SEL_0=3\'b000;': '.BLK_SEL_0=3\'b001;',
            '.CEA(byte_we_0)': '.CEA(GND)',
        }
        for before, after in mutations.items():
            with self.subTest(before=before), self.assertRaises(ValueError):
                self.verify(text.replace(before, after, 1))
        with self.assertRaisesRegex(ValueError, 'groups aliased'):
            self.verify(text.replace('byte_we_1', 'byte_we_0'))
        with self.assertRaisesRegex(ValueError, 'grouping changed'):
            self.verify(text.replace('.CEA(byte_we_0)', '.CEA(other_we)', 1))

    def test_last_word_corruption_and_invalid_chunk_rejected(self):
        text = self.images['g_ram64.']
        token = '\\g_ram64.memory_3_g_ram64.memory_3_0_7_s '
        marker = f'defparam {token}.INIT_RAM_3F='
        start = text.index(marker)
        end = text.index(';', start)
        literal = text[start+len(marker):end]
        value = int(literal.split("'h")[1], 16) ^ (1 << 255)
        changed = text[:start+len(marker)] + f"256'h{value:064X}" + text[end:]
        with self.assertRaisesRegex(ValueError, 'word 16383'):
            self.verify(changed)
        with self.assertRaisesRegex(ValueError, 'chunks changed'):
            self.verify(text.replace('.INIT_RAM_3F=', '.INIT_RAM_40=', 1))
        line = text[start:end+1]
        with self.assertRaises(ValueError):
            self.verify(text.replace('endmodule', line + '\nendmodule'))

    def test_wrong_input_identity_capacity_or_duplicate_module_rejected(self):
        text = self.images['']
        with self.assertRaisesRegex(ValueError, 'input identity'):
            check_rom(self.stage, text, '0'*64)
        self.rom.write_text(''.join(f'{value:08x}\n' for value in self.words[:-1]))
        self.digest = sha(self.rom)
        with self.assertRaisesRegex(ValueError, 'input identity'):
            self.verify(text)
        with self.assertRaisesRegex(ValueError, 'module missing or duplicated'):
            self.verify(text + text)


if __name__ == '__main__':
    unittest.main()
