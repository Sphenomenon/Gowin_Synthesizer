#!/usr/bin/env python3
"""Native full effects: exact48k and independent dual-rate wet/maintenance."""
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_baselines import load_baseline
from workstation_chorus_provenance import verify as verify_chorus, NARROW_POLICY, ADAPTATION
from workstation_reverb_provenance import restore as restore_reverb, ADAPTATION as REVERB_ADAPTATION
from workstation_delay_storage_provenance import (
    verify as verify_delay_storage, STORAGE_POLICY, ADAPTATION as DELAY_STORAGE_ADAPTATION,
    source_bundle as delay_storage_source_bundle, PREPARED_SOURCE as DELAY_PREPARED_SOURCE,
    REFERENCE as DELAY_STORAGE_REFERENCE,
    restore_delay_native,
)
from test_workstation_runtime_reverb import FixedRoom, sat, signed


def digest(data):
    return hashlib.sha256(data).hexdigest()


def rounded(value, shift):
    magnitude = (abs(value) + (1 << (shift - 1))) >> shift
    return -magnitude if value < 0 else magnitude


def slew(value, target, step):
    return min(target, value + step) if target > value else max(target, value - step)


class Delay:
    def __init__(self):
        self.rate = 48000
        self.gain = self.fraction = 0
        self.clear()

    def clear(self, legacy=False, rate=None):
        if rate is not None:
            self.rate = rate
        if legacy:
            self.gain = self.fraction = 0
        self.echo = self.rate // 5
        self.memory = [(0, 0)] * self.echo
        self.pointer = self.frames = 0

    def frame(self, left, right, enable):
        increment = 128
        if self.rate == 44100:
            self.fraction += 47
            increment = 139 + (self.fraction >= 147)
            self.fraction %= 147
        self.gain = slew(self.gain, 8192 if enable else 0, increment)
        wet = self.memory[self.pointer] if self.frames >= self.echo else (0, 0)
        feedback = tuple(sat(value + rounded(delayed, 1)) for value, delayed in zip((left, right), wet))
        mixed = tuple(value + rounded(delayed * self.gain, 15) for value, delayed in zip((left, right), wet))
        self.memory[self.pointer] = feedback
        self.pointer = (self.pointer + 1) % self.echo
        self.frames += 1
        return sat(mixed[0]), sat(mixed[1]), int(any(v != sat(v) for v in mixed))


class Chorus:
    def __init__(self):
        self.rate = 48000
        self.gain = self.fraction = self.phase = self.phase_fraction = 0
        self.clear()

    def clear(self, legacy=False, rate=None):
        if rate is not None:
            self.rate = rate
        if legacy:
            self.gain = self.fraction = 0
        self.memory = [(0, 0)] * 1024
        self.pointer = self.frames = 0

    def frame(self, left, right, enable):
        triangle = (self.phase >> 7) & 65535
        if self.phase & (1 << 23):
            triangle = 65535 - triangle
        if self.rate == 44100:
            delay = ((480 * 65536 + triangle * 96) * 44100 + 48000 * 32768) // (48000 * 65536)
            self.fraction += 47
            gain_step = 139 + (self.fraction >= 147)
            self.fraction %= 147
            self.phase_fraction += 127
            phase_step = 379 + (self.phase_fraction >= 147)
            self.phase_fraction %= 147
        else:
            delay, gain_step, phase_step = 480 + triangle * 96 // 65536, 128, 349
        self.gain = slew(self.gain, 8192 if enable else 0, gain_step)
        wet = self.memory[(self.pointer - delay) % 1024] if self.frames >= delay else (0, 0)
        mixed = tuple(value + rounded(delayed * self.gain, 15) for value, delayed in zip((left, right), wet))
        self.memory[self.pointer] = (left, right)
        self.pointer = (self.pointer + 1) % 1024
        self.frames += 1
        self.phase = (self.phase + phase_step) % (1 << 24)
        return sat(mixed[0]), sat(mixed[1]), int(any(v != sat(v) for v in mixed))


class Effects:
    def __init__(self, banks):
        self.rate = 48000
        self.sg = self.pg = self.fraction = 0
        self.applied_order = 63
        self.work_enabled = False
        self.stages = [Delay(), Chorus(), FixedRoom(banks)]

    def clear(self, operation):
        next_rate = 44100 if operation == 1 else 48000 if operation == 2 else None
        if next_rate is not None:
            self.rate = next_rate
        for i, stage in enumerate(self.stages):
            stage.clear(legacy=operation == 4, rate=str(next_rate) if i == 2 and next_rate else next_rate)

    def frame(self, synth, pl, pr, vl, vr, sg, pg, mask, order):
        dry = [sat(rounded((synth + vl) * self.sg + pl * self.pg, 15)),
               sat(rounded((synth + vr) * self.sg + pr * self.pg, 15))]
        increment = 128
        if self.rate == 44100:
            self.fraction += 47
            increment = 139 + (self.fraction >= 147)
            self.fraction %= 147
        self.sg, self.pg = slew(self.sg, sg, increment), slew(self.pg, pg, increment)
        if mask:
            self.applied_order = order
        frame_order = self.applied_order
        done, clip, chain = set(), 0, dry
        for slot in range(3):
            index = (frame_order >> (2 * slot)) & 3
            if index < 3 and index not in done and ((mask & (1 << index)) or self.stages[index].gain or self.work_enabled):
                self.work_enabled = bool(mask & (1 << index))
                l, r, stage_clip = self.stages[index].frame(*chain, self.work_enabled)
                chain = [l, r]
                clip |= stage_clip
                done.add(index)
        for index in range(3):
            if index not in done:
                self.work_enabled = bool(mask & (1 << index))
                _, _, stage_clip = self.stages[index].frame(*dry, self.work_enabled)
                clip |= stage_clip
        return chain[0], chain[1], clip


class DelayStorageProvenance(unittest.TestCase):
    def setUp(self):
        import workstation_delay_storage_provenance as storage
        self.storage=storage
        self.live_source=(ROOT/storage.SOURCE).read_bytes()
        self.source=storage.restore_remote_reverb_partition(self.live_source)
        self.provenance=(ROOT/storage.PROVENANCE).read_bytes()
        self.adaptation=(ROOT/storage.ADAPTATION).read_bytes()

    def test_remote_partition_exact_parent_macro_off_and_drift(self):
        m=self.storage
        self.assertEqual(digest(self.live_source),m.REMOTE_REVERB_SOURCE_SHA256)
        self.assertEqual(digest(self.source),m.REMOTE_REVERB_PARENT_SHA256)
        self.assertEqual(m.REMOTE_REVERB_PARENT_SHA256,m.EFFECT_RELEASE_SOURCE_SHA256)
        self.assertEqual(m.verify(self.live_source,self.provenance,STORAGE_POLICY,self.adaptation)[0],
                         m.verify(self.source,self.provenance,STORAGE_POLICY,self.adaptation)[0])
        partition=(ROOT/m.REMOTE_REVERB_ADAPTATION).read_bytes()
        bridge=json.loads(partition)
        self.assertEqual(len(bridge['exact_changes']),3)
        for change in bridge['exact_changes']:
            for mutant in (self.live_source.replace(change['after'].encode(),change['before'].encode()),
                           self.live_source.replace(change['after'].encode(),change['after'].encode()*2)):
                with self.assertRaises(ValueError):
                    m.verify(mutant,self.provenance,STORAGE_POLICY,self.adaptation)
        with self.assertRaises(ValueError):
            m.restore_remote_reverb_partition(self.live_source,partition+b'\n')
        with self.assertRaises(ValueError):
            m.verify(self.live_source+b'// unrelated drift\n',self.provenance,STORAGE_POLICY,self.adaptation)
        # The production macro-off token stream and reverb hierarchy stay exact.
        # The original source's identity is independently pinned above.
        with tempfile.TemporaryDirectory(prefix='effect-partition-default-') as directory:
            path=Path(directory)
            tokens=[]
            for index,payload in enumerate((self.source,self.live_source)):
                source=path/f'input{index}.sv';output=path/f'output{index}.sv'
                source.write_bytes(payload)
                subprocess.run(['iverilog','-g2012','-E','-o',str(output),str(source)],
                               check=True,capture_output=True,text=True)
                value=re.sub(r'/\*.*?\*/|//[^\n]*','',output.read_text(),flags=re.S)
                tokens.append(re.findall(r'[A-Za-z_$][\w$]*|\d+|[^\s]',value))
            self.assertEqual(tokens[0],tokens[1])

    def test_exact_original_native_and_prepared_chain(self):
        m=self.storage
        old=m.restore_native(self.source,self.provenance,STORAGE_POLICY,self.adaptation)
        self.assertEqual(digest(old.encode()),'d8a0d2c787bc8c222bf4dde74069db41163988a646fd70c32774387bfe23a689')
        prepared,evidence=m.verify(self.source,self.provenance,STORAGE_POLICY,self.adaptation)
        self.assertEqual(prepared,m.verify(old.encode(),self.provenance)[0])
        bundle=m.source_bundle(ROOT)
        self.assertEqual(bundle['exact_prepared_sha256'],'5fcabe0bb792efb13a791b3e6f91b6d156dd074d8a89421dedde09a124539742')
        self.assertEqual(bundle['storage_instances'],['delay_stage.u_write_fifo','delay_stage.u_read_fifo'])
        self.assertTrue(bundle['original_locked_prepared_slice_verified'])
        self.assertEqual(bundle['added_clock_latency'],0)
        for key in ('physical_ram_mapping_verified','physical_timing_verified','hardware_acceptance_inherited','accepted_baseline_storage_selection_inherited'):
            self.assertFalse(bundle[key],key)

    def test_release_policy_restores_previous_source_and_rejects_drift(self):
        from unittest import mock
        m=self.storage
        self.assertEqual(digest(self.source),m.EFFECT_RELEASE_SOURCE_SHA256)
        parent=m.restore_effect_release_policy(self.source)
        self.assertEqual(digest(parent),m.EFFECT_RELEASE_PARENT_SHA256)
        self.assertEqual(m.EFFECT_RELEASE_PARENT_SHA256,m.EFFECT_SLOT_SOURCE_SHA256)
        reconstructed=parent.decode()
        for before,after in m.EFFECT_RELEASE_EDITS:
            self.assertEqual(reconstructed.count(before),1)
            reconstructed=reconstructed.replace(before,after)
        self.assertEqual(reconstructed.encode(),self.source)
        self.assertEqual(m.restore_effect_release_policy(parent),parent)
        self.assertEqual(m.verify(self.source,self.provenance,STORAGE_POLICY,self.adaptation)[0],
                         m.verify(parent,self.provenance,STORAGE_POLICY,self.adaptation)[0])
        # Only the parameter and SELECT predicate changed. Inactive stages still
        # execute the exact prior maintenance body and every NBA/state is kept.
        self.assertEqual(len(m.EFFECT_RELEASE_EDITS),2)
        self.assertIn('parameter bit RELEASE_TAILS_ENABLE=1',self.source.decode())
        for before,after in m.EFFECT_RELEASE_EDITS:
            mutants=[self.source.replace(after.encode(),before.encode()),
                     self.source.replace(after.encode(),after.encode()*2),
                     self.source+b'// unrelated drift\n']
            for mutant in mutants:
                with self.subTest(identity=digest(mutant)),self.assertRaises(ValueError):
                    m.verify(mutant,self.provenance,STORAGE_POLICY,self.adaptation)
                with mock.patch.object(m,'EFFECT_RELEASE_SOURCE_SHA256',digest(mutant)),self.assertRaises(ValueError):
                    m.restore_effect_release_policy(mutant)
        with mock.patch.object(m,'EFFECT_RELEASE_PARENT_SHA256','0'*64),self.assertRaises(ValueError):
            m.restore_effect_release_policy(self.source)

    def test_release_predicate_default_four_state_and_d_momentary(self):
        # Execute SystemVerilog four-state operators, including X/Z selected id,
        # mask, active and processed. Default 1 must be bit-exact to old SELECT;
        # D's explicit 0 is exactly the committed-mask predicate.
        text="""module release_predicate;
          reg [1:0] selected_id;reg [2:0] frame_mask,processed;
          reg selected_active;reg [3:0] values;integer a,b,c,d;
          wire old_select=selected_id<3&&(frame_mask[selected_id]||selected_active)&&!processed[selected_id];
          wire default_select=selected_id<3&&(frame_mask[selected_id]||(1'b1&&selected_active))&&!processed[selected_id];
          wire d_select=selected_id<3&&(frame_mask[selected_id]||(1'b0&&selected_active))&&!processed[selected_id];
          wire mask_select=selected_id<3&&frame_mask[selected_id]&&!processed[selected_id];
          initial begin
            values=4'bzx10;
            for(a=0;a<16;a=a+1)for(b=0;b<64;b=b+1)for(c=0;c<64;c=c+1)for(d=0;d<4;d=d+1)begin
              selected_id={values[(a>>2)&3],values[a&3]};
              frame_mask={values[(b>>4)&3],values[(b>>2)&3],values[b&3]};
              processed={values[(c>>4)&3],values[(c>>2)&3],values[c&3]};
              selected_active=values[d];#1;
              if(old_select!==default_select||d_select!==mask_select)$fatal(1,"release predicate");
            end
            $display("PASS release_predicate four_state_cases=262144");
          end
        endmodule
        """
        with tempfile.TemporaryDirectory(prefix='effect-release-') as directory:
            path=Path(directory);(path/'tb.sv').write_text(text)
            subprocess.run(['iverilog','-g2012','-s','release_predicate','-o',str(path/'sim'),str(path/'tb.sv')],check=True,capture_output=True)
            result=subprocess.run(['vvp',str(path/'sim')],check=True,capture_output=True,text=True)
            self.assertIn('PASS release_predicate four_state_cases=262144',result.stdout)

    def test_sample_slot_restores_exact_previous_d_source(self):
        m=self.storage
        source=m.restore_effect_release_policy(self.source)
        self.assertEqual(digest(source),m.EFFECT_SLOT_SOURCE_SHA256)
        parent=m.restore_effect_sample_slot(source)
        self.assertEqual(digest(parent),m.EFFECT_SLOT_PARENT_SHA256)
        self.assertEqual(m.EFFECT_SLOT_PARENT_SHA256,m.D_CONTROL_ADAPTATIONS[m.SOURCE]['source_sha256'])
        reconstructed=parent.decode()
        for before,after in m.EFFECT_SLOT_EDITS:
            self.assertEqual(reconstructed.count(before),1)
            reconstructed=reconstructed.replace(before,after)
        self.assertEqual(reconstructed.encode(),source)
        self.assertEqual(m.restore_effect_sample_slot(parent),parent)
        self.assertEqual(m.verify(source,self.provenance,STORAGE_POLICY,self.adaptation)[0],
                         m.verify(parent,self.provenance,STORAGE_POLICY,self.adaptation)[0])

    def test_sample_slot_changed_bytes_and_broken_reverse_anchors_rejected(self):
        from unittest import mock
        m=self.storage
        source=m.restore_effect_release_policy(self.source)
        assign=b'  assign sample_slot_ready_o=state==IDLE && !barrier_busy;\n'
        mutations=[
            source.replace(b'Stored slot state only.',b'Stored slot state drift.'),
            source.replace(assign,b'  assign sample_slot_ready_o=state==IDLE;\n'),
            source.replace(assign,b''),
            source.replace(assign,assign+assign),
            source.replace(b'output wire sample_slot_ready_o,',b'output wire changed_slot_ready_o,'),
            source+b'// unreviewed unrelated change\n',
        ]
        for mutant in mutations:
            self.assertNotEqual(mutant,source)
            with self.subTest(identity=digest(mutant)),self.assertRaises(ValueError):
                m.verify(mutant,self.provenance,STORAGE_POLICY,self.adaptation)
        # Even if an input hash were mistakenly rebased, missing/duplicate
        # anchors or unrelated bytes must still fail before the original chain.
        for mutant in (mutations[0],mutations[3],mutations[-1]):
            with self.subTest(rebased_identity=digest(mutant)),mock.patch.object(
                    m,'EFFECT_SLOT_SOURCE_SHA256',digest(mutant)),self.assertRaises(ValueError):
                m.restore_effect_sample_slot(mutant)
        with mock.patch.object(m,'EFFECT_SLOT_PARENT_SHA256','0'*64),self.assertRaises(ValueError):
            m.restore_effect_sample_slot(source)

    def test_old_policy_and_changed_original_provenance_rejected(self):
        m=self.storage
        for source,provenance,policy,adaptation in [
            (self.source,self.provenance,m.STRICT_POLICY,None),
            (self.source,self.provenance,m.STRICT_POLICY,self.adaptation),
            (self.source,self.provenance,STORAGE_POLICY,None),
            (self.source,self.provenance+b'\n',STORAGE_POLICY,self.adaptation),
            (self.source,self.provenance,'automatic',self.adaptation),
        ]:
            with self.subTest(policy=policy),self.assertRaises(ValueError):m.verify(source,provenance,policy,adaptation)

    def test_changed_source_or_adaptation_rejected(self):
        m=self.storage
        for source,adaptation in [
            (self.source.replace(b'u_write_fifo.RAM_STYLE="block_ram"',b'u_write_fifo.RAM_STYLE="distributed_ram"'),self.adaptation),
            (self.source.replace(b'u_read_fifo.RAM_STYLE="block_ram"',b'u_write_fifo.RAM_STYLE="block_ram"'),self.adaptation),
            (self.source+b'//unreviewed change\n',self.adaptation),
            (self.source,self.adaptation+b'\n'),
            (self.source,self.adaptation.replace(b'"added_clock_latency": 0',b'"added_clock_latency": 1')),
        ]:
            with self.subTest(source=digest(source),adaptation=digest(adaptation)),self.assertRaises(ValueError):
                m.verify(source,self.provenance,STORAGE_POLICY,adaptation)

    def test_actual_fifo_reference_and_prepared_source_bytes_fail_closed(self):
        from unittest import mock
        m=self.storage;original=Path.read_bytes
        for name in (m.FIFO,m.REFERENCE,m.PREPARED_SOURCE):
            def changed(path):
                value=original(path)
                return value+b'\n' if path==ROOT/name else value
            with self.subTest(path=name),mock.patch.object(Path,'read_bytes',changed),self.assertRaises(ValueError):
                m.source_bundle(ROOT)

    def test_scratch_product_lineage_keeps_originals_and_rejects_drift(self):
        import workstation_chorus_provenance as chorus
        m = self.storage
        current = (ROOT / m.DELAY_SCRATCH_SOURCE).read_bytes()
        provenance = (ROOT / m.DELAY_SCRATCH_PROVENANCE).read_bytes()
        parent = m.restore_delay_native(current, provenance)
        self.assertEqual(digest(parent), json.loads(provenance)['native_sha256'])
        self.assertEqual(m.restore_delay_native(parent, provenance), parent)
        with self.assertRaises(ValueError):
            m.restore_delay_native(current.replace(b'!local_history_clear && state==2',
                                                  b'!local_history_clear && state==3'), provenance)
        with self.assertRaises(ValueError):
            m.restore_delay_native(current, provenance + b'\n')
        source = (ROOT / chorus.SOURCE).read_bytes()
        narrowed = chorus.restore_scratch_products(chorus.restore_affine44(source))
        self.assertEqual(digest(narrowed), json.loads((ROOT / chorus.ADAPTATION).read_bytes())['current_source_sha256'])
        with self.assertRaises(ValueError):
            chorus.restore_scratch_products(source + b'\n')


class RuntimeEffectsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('verilator'):
            raise RuntimeError('Verilator is required for the full native effects chain')
        cls.temp = tempfile.TemporaryDirectory(prefix='runtime-effects-')
        cls.stage = Path(cls.temp.name)
        cls.source_hashes = {}
        sources, restored = [], {}
        baseline = load_baseline(ROOT, 'resource_rework_route0')
        names = ['rtl/audio/workstation_runtime_stereo_effects.sv',
                 'rtl/audio/workstation_runtime_chorus_effect.sv',
                 'rtl/audio/workstation_runtime_spatial_reverb.sv',
                 'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv',
                 'rtl/audio/delay_ddr/workstation_runtime_delay_ddr_dma.sv']
        for name in names:
            native = ROOT / name
            provenance_path = native.with_suffix('.provenance.json')
            provenance = json.loads(provenance_path.read_text())
            payload = native.read_bytes()
            if name == 'rtl/audio/workstation_runtime_stereo_effects.sv':
                adaptation_path = ROOT / DELAY_STORAGE_ADAPTATION
                old, cls.delay_storage_provenance_evidence = verify_delay_storage(
                    payload, provenance_path.read_bytes(), STORAGE_POLICY, adaptation_path.read_bytes())
                cls.delay_storage_provenance_evidence = delay_storage_source_bundle(ROOT)
                for path in (adaptation_path, ROOT / 'tools/workstation_delay_storage_provenance.py',
                             ROOT / 'rtl/audio/workstation_runtime_stereo_effects.remote_reverb_partition.json',
                             ROOT / DELAY_PREPARED_SOURCE, ROOT / DELAY_STORAGE_REFERENCE):
                    cls.source_hashes[str(path.relative_to(ROOT))] = digest(path.read_bytes())
            elif name == 'rtl/audio/workstation_runtime_chorus_effect.sv':
                adaptation_path = ROOT / ADAPTATION
                old, cls.chorus_provenance_evidence = verify_chorus(
                    payload, provenance_path.read_bytes(), NARROW_POLICY, adaptation_path.read_bytes())
                for path in (adaptation_path, ROOT / 'tools/workstation_chorus_provenance.py'):
                    cls.source_hashes[str(path.relative_to(ROOT))] = digest(path.read_bytes())
            else:
                if name == 'rtl/audio/delay_ddr/workstation_runtime_delay_effect_ddr.sv':
                    payload = restore_delay_native(payload, provenance_path.read_bytes())
                elif name == 'rtl/audio/workstation_runtime_spatial_reverb.sv':
                    adaptation_path = ROOT / REVERB_ADAPTATION
                    payload = restore_reverb(payload, provenance_path.read_bytes(), adaptation_path.read_bytes())
                    for path in (adaptation_path, ROOT / 'tools/workstation_reverb_provenance.py'):
                        cls.source_hashes[str(path.relative_to(ROOT))] = digest(path.read_bytes())
                if digest(payload) != provenance['native_sha256']:
                    raise ValueError('native identity drifted: ' + name)
                old = payload.decode()
                for edit in reversed(provenance['forward_edits']):
                    if old.count(edit['after']) != edit['count']:
                        raise ValueError('reverse provenance drifted: ' + name)
                    old = old.replace(edit['after'], edit['before'])
                if digest(old.encode()) != provenance['prepared_sha256']:
                    raise ValueError('prepared identity drifted: ' + name)
            restored[name] = old
            sources.append(native)
            for path in (native, provenance_path):
                cls.source_hashes[str(path.relative_to(ROOT))] = digest(path.read_bytes())
        dependencies = ['legacy/rtl/audio/audio_math_pkg.sv', 'rtl/audio/serial_spatial_reverb.sv',
                        'rtl/audio/spatial_room_preset.svh', 'rtl/memory/workstation_sdp.sv',
                        'rtl/memory/workstation_sdp_banked.sv']
        baseline_sources = []
        for name in dependencies:
            path = cls.stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(baseline.read_bytes(name))
            if path.suffix == '.sv':
                baseline_sources.append(path)
        original_effects = baseline.read_bytes('legacy/rtl/audio/stereo_effects.sv').decode()
        prefix = original_effects[:original_effects.index('module stereo_effects #(')]
        chain = restored[names[0]].replace('module stereo_effects #(', 'module prepared_stereo_effects #(')
        reference = cls.stage / 'prepared_stereo_effects.sv'
        reference.write_text(prefix + chain)
        baseline_sources.append(reference)
        for name in names[-2:]:
            path = cls.stage / (Path(name).stem + '_prepared.sv')
            path.write_text(restored[name])
            baseline_sources.append(path)
        fifo = ROOT / 'rtl/music/music_async_fifo.sv'
        if digest(fifo.read_bytes()) != 'e5a190502bec8bb402ad3c44d45d9f61702ddbdbe144baeb67f4da416fe82792':
            raise ValueError('actual prepared FIFO identity drifted')
        bank_path = ROOT / 'rtl/audio/runtime_spatial_room_preset.json'
        header = ROOT / 'rtl/audio/runtime_spatial_room_preset.svh'
        (cls.stage / 'rtl/audio/runtime_spatial_room_preset.svh').write_bytes(header.read_bytes())
        cls.banks = json.loads(bank_path.read_text())['banks']
        tb = ROOT / 'sim/audio/tb_workstation_runtime_effects.sv'
        for path in (fifo, bank_path, header, tb, Path(__file__), ROOT / 'sim/test_workstation_runtime_reverb.py'):
            cls.source_hashes[str(path.relative_to(ROOT))] = digest(path.read_bytes())
        command = ['verilator', '--binary', '--timing', '-j', '2', '-Wno-fatal',
                   '--top-module', 'tb_workstation_runtime_effects', '--Mdir', str(cls.stage / 'obj'),
                   '-o', 'runtime_effects', *map(str, baseline_sources), *map(str, sources), str(fifo), str(tb)]
        result = subprocess.run(command, cwd=cls.stage, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout[-3000:] + result.stderr[-18000:])
        cls.warning_counts = {}
        for line in result.stderr.splitlines():
            if line.startswith('%Warning-'):
                key = line.split(':', 1)[0][9:]
                cls.warning_counts[key] = cls.warning_counts.get(key, 0) + 1
        if cls.warning_counts != {'TIMESCALEMOD': 1, 'WIDTHEXPAND': 55, 'WIDTHTRUNC': 16}:
            raise RuntimeError('unexpected compile warnings: ' + result.stderr)
        if any(str(ROOT / 'rtl/audio/workstation_runtime_spatial_reverb.sv') + ':' in line
               for line in result.stderr.splitlines() if line.startswith('%Warning-')):
            raise RuntimeError('maintained Reverb must compile without width warnings')
        # Inherited native/reference arithmetic, VECTOR_ENABLE integer, frozen
        # RAM indexing and exact prepared DMA address/debug widths only.
        print('COMPILE_WARNINGS', json.dumps(cls.warning_counts, sort_keys=True))
        cls.compile_warnings = result.stderr
        cls.binary = cls.stage / 'obj/runtime_effects'

    @classmethod
    def tearDownClass(cls):
        for name, expected in cls.source_hashes.items():
            if digest((ROOT / name).read_bytes()) != expected:
                raise ValueError('verified input changed during tests: ' + name)
        print('SOURCE_SHA256', json.dumps(cls.source_hashes, sort_keys=True))
        cls.temp.cleanup()

    @staticmethod
    def random_rows(count, mask, order, seed=0x6281b93a):
        rows, state = [], seed
        for _ in range(count):
            values = []
            for _ in range(5):
                state = (state >> 1) ^ (0x80200003 if state & 1 else 0)
                values.append(signed(state))
            rows.append((0, *values, 0x4000, 0x6000, mask, order))
        return rows

    def fixture(self, number, rows):
        path = self.stage / f'vectors{number}.txt'
        model = Effects(self.banks)
        with path.open('w') as stream:
            stream.write(str(len(rows)) + '\n')
            for row in rows:
                operation, *data = row
                if operation == 0:
                    left, right, clip = model.frame(*data)
                else:
                    model.clear(operation)
                    left, right, clip = 0, 0, 0
                stream.write(str(operation) + ' ' + ' '.join(f'{v & 0xffffffff:08x}' for v in data) +
                             f' {left & 0xffffffff:08x} {right & 0xffffffff:08x} {clip}\n')
        return path

    @staticmethod
    def operation(number):
        return (number, 0, 0, 0, 0, 0, 0x4000, 0x6000, 7, 0x24)

    def scenario(self, number, path=None, expected='PASS runtime full effects'):
        command = [str(self.binary), f'+SCENARIO={number}']
        if path:
            command.append('+VECTOR_FILE=' + str(path))
        result = subprocess.run(command, cwd=self.stage, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(expected, result.stdout)
        print(result.stdout.strip())

    def all_order_mask_rows(self):
        rows = self.random_rows(12000, 7, 0x24)
        for permutation in itertools.permutations(range(3)):
            order = sum(value << (2 * slot) for slot, value in enumerate(permutation))
            for mask in range(8):
                rows += self.random_rows(256, mask, order, 0x5918ab43 + 23 * order + mask)
        return rows

    def test_48k_exact_prepared_cycle_and_model_all_order_masks_maintenance(self):
        rows = self.all_order_mask_rows()
        rows += [self.operation(4)] + self.random_rows(12000, 7, 0x24)
        self.scenario(0, self.fixture(0, rows))

    def test_44100_complete_wet_all_order_masks_maintenance(self):
        rows = [self.operation(1)] + self.all_order_mask_rows()
        self.scenario(1, self.fixture(1, rows))

    def test_dual_rate_history_switches_complete_wet(self):
        rows = self.random_rows(11000, 7, 0x24)
        for operation in (1, 3, 2):
            rows += [self.operation(operation)] + self.random_rows(11000, 7, 0x18, 0x28cb4511)
        # Include bypass so each independent model/RTL maintains dry history.
        rows += self.random_rows(512, 0, 0x24)
        self.scenario(2, self.fixture(2, rows))

    def test_panic_while_fence_pending_does_not_retract_accepted_config(self):
        self.scenario(3, expected='PASS runtime effects PANIC collision')

    def test_panic_after_delay_ack_requires_second_fenced_clear(self):
        self.scenario(4, expected='PASS runtime effects PANIC collision')

    def test_missing_late_fence_sticky_failure(self):
        self.scenario(5, expected='PASS runtime effects missing/late fence')

    def test_memory_clock_stop_controlled_zero(self):
        self.scenario(6, expected='PASS runtime effects memory-clock stop')

    def test_audio_clock_stop_sticky_failure_after_resume(self):
        self.scenario(7, expected='PASS runtime effects audio-clock stop')

    def test_legacy_clear_all_chain_states_and_each_stage_wait(self):
        self.scenario(8, expected='PASS runtime effects legacy clear cancels9')


if __name__ == '__main__':
    unittest.main()
