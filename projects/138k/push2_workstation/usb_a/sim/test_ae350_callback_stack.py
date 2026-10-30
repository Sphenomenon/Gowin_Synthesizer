#!/usr/bin/env python3
"""Bind a manual callback target closure to actual GCC JALR sites and stack frames."""
from pathlib import Path
import copy
import hashlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.stage_ae350_firmware import compiler_prefix
from tools.ae350_local_memory import call_chain_report


class CallbackStackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        sources = {
            'dispatch.c': '''typedef int (*fn)(unsigned); struct bus {fn read;fn write;};
int dispatch(const struct bus *b){volatile unsigned v=7;return b->read(v)+b->write(v);}
''',
            'entry.c': '''typedef int (*fn)(unsigned); struct bus {fn read;fn write;};extern int dispatch(const struct bus *);
int test_read(unsigned v){volatile unsigned a[8];a[0]=v;return a[0];}
int test_write(unsigned v){volatile unsigned a[16];a[0]=v;return a[0]+1;}
void services_main(void){const struct bus b={test_read,test_write};for(;;){volatile int out=dispatch(&b);(void)out;}}
'''}
        prefix = compiler_prefix()
        flags = ['-march=rv32im_zicsr_zifencei', '-mabi=ilp32', '-msmall-data-limit=0', '-O2',
                 '-ffreestanding', '-fcallgraph-info=su', '-fstack-usage']
        for name, code in sources.items():
            (cls.directory / name).write_text(code)
            subprocess.run([prefix + '-gcc', *flags, '-c', name, '-o', name[:-2] + '.o'],
                           cwd=cls.directory, check=True, capture_output=True)
        subprocess.run([prefix + '-gcc', *flags, '-nostdlib', '-nostartfiles',
            '-Wl,--build-id=none,-Ttext=0xa0000000,-e,services_main',
            'dispatch.o', 'entry.o', '-o', 'firmware.elf'], cwd=cls.directory, check=True, capture_output=True)
        cls.disassembly = subprocess.check_output([prefix + '-objdump', '-d', 'firmware.elf'],
                                                  cwd=cls.directory, text=True)
        cls.frames = []
        for path in sorted(cls.directory.glob('*.su')):
            for line in path.read_text().splitlines():
                name, size, kind = line.split('\t')
                cls.frames.append(dict(function=name, bytes=int(size), kind=kind))
        cls.identities = {name: hashlib.sha256((cls.directory / name).read_bytes()).hexdigest() for name in sources}
        sites = [dict(caller='dispatch', address='0x' + match[1], instruction=match[2], targets=[target])
            for match, target in zip(re.finditer(r'^([0-9a-f]{8}):\s+([0-9a-f]{8})\s+jalr\b',
                                               cls.disassembly, re.MULTILINE), ('test_read', 'test_write'))]
        if len(sites) != 2:
            raise AssertionError('fixture must emit two distinct actual machine callback calls')
        cls.review = dict(schema=1, input_sha256=cls.identities,
            disassembly_sha256=hashlib.sha256(cls.disassembly.encode()).hexdigest(),
            source_target_review='The only service-root bus initializer is the const local b in entry.c; '
                'dispatch.c calls read then write, bound respectively to test_read and test_write. '
                'Neither source stores or replaces a callback after that initializer.', sites=sites)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def report(self, review=None, *, frames=None, capacity=16384, identities=None, disassembly=None):
        return call_chain_report(self.directory, self.frames if frames is None else frames,
            self.disassembly if disassembly is None else disassembly, capacity,
            reviewed_indirect_calls=review, input_sha256=self.identities if identities is None else identities)

    def test_actual_indirect_calls_fail_without_review_and_both_targets_enter_the_stack_bound(self):
        with self.assertRaises(ValueError):self.report()
        result = self.report(self.review)
        self.assertEqual(result['conservative_peak_bytes'], 128)
        self.assertEqual(result['longest_chain'], ['services_main', 'dispatch', 'test_write'])
        self.assertEqual(result['reachable_functions'], ['dispatch', 'services_main', 'test_read', 'test_write'])
        self.assertEqual(result['reviewed_indirect_calls']['sites'], self.review['sites'])
        self.assertFalse(result['hardware_watermark_verified'])
        with self.assertRaisesRegex(ValueError, 'exceeds'):self.report(self.review, capacity=127)

    def test_input_and_entire_machine_disassembly_are_bound(self):
        identities = dict(self.identities, **{'entry.c': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'identity'):self.report(self.review, identities=identities)
        with self.assertRaisesRegex(ValueError, 'identity'):self.report(self.review, disassembly=self.disassembly + '\n')
        for key, value in (('schema', True), ('source_target_review', ''), ('input_sha256', {}),
                           ('disassembly_sha256', '0' * 64)):
            changed = copy.deepcopy(self.review);changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):self.report(changed)

    def test_every_site_instruction_caller_and_target_are_checked(self):
        for kind in ('missing', 'duplicate', 'wrong_address', 'wrong_instruction', 'wrong_caller',
                     'missing_target', 'duplicate_target', 'unknown_target', 'extra_key'):
            changed = copy.deepcopy(self.review);site = changed['sites'][0]
            if kind == 'missing':changed['sites'].pop()
            elif kind == 'duplicate':changed['sites'].append(copy.deepcopy(site))
            elif kind == 'wrong_address':site['address'] = '0xa000ffff'
            elif kind == 'wrong_instruction':site['instruction'] = '000080e7'
            elif kind == 'wrong_caller':site['caller'] = 'services_main'
            elif kind == 'missing_target':site['targets'] = []
            elif kind == 'duplicate_target':site['targets'] *= 2
            elif kind == 'unknown_target':site['targets'] = ['unknown_callback']
            else:site['approved'] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):self.report(changed)

    def test_review_does_not_excuse_recursion_missing_or_dynamic_target_frames(self):
        changed = copy.deepcopy(self.review);changed['sites'][0]['targets'] = ['services_main']
        with self.assertRaisesRegex(ValueError, 'recursive'):self.report(changed)
        for kind in ('unknown', 'dynamic'):
            frames = copy.deepcopy(self.frames)
            if kind == 'unknown':frames = [frame for frame in frames if not frame['function'].endswith(':test_write')]
            else:next(frame for frame in frames if frame['function'].endswith(':test_write'))['kind'] = 'dynamic'
            with self.subTest(kind=kind), self.assertRaises(ValueError):self.report(self.review, frames=frames)


if __name__ == '__main__':
    unittest.main()
