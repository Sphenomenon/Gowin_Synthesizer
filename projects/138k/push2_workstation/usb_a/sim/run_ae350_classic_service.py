#!/usr/bin/env python3
"""Verify the unselected bounded classic sink source-stage, without hardware."""
from pathlib import Path
import argparse
import base64
import hashlib
import importlib.util
import json
import re
import shutil
import struct
import subprocess


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--riscv-prefix', default='/opt/homebrew/bin/riscv64-elf')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fw = root / 'firmware/ae350'
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(argv, name, expected=0):
        p = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=120)
        (out / (name + '.log')).write_text(p.stdout + p.stderr)
        commands.append(dict(argv=list(map(str, argv)), returncode=p.returncode))
        if expected is not None:
            assert p.returncode == expected, (name, p.returncode, p.stdout, p.stderr)
        return p

    cc = Path(shutil.which('cc')).resolve()
    common = [cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-I' + str(fw)]
    source = fw / 'classic_service.c'
    fixture = root / 'sim/ae350_classic_fixture.c'
    wire_results = []
    for tag, flags in [('native', []), ('sanitized', ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
        run([*common, *flags, source, fixture, '-o', out / tag], tag + '-compile')
        p = run([out / tag], tag + '-wire')
        assert 'runtime error:' not in p.stderr and 'Sanitizer' not in p.stderr
        wire_results.append(dict(tag=tag, summary=p.stdout.strip()))
    text = source.read_text()
    mutants = []
    for tag, old, new in [
        ('generation-ignored', 'if (e!=s->link_epoch || g!=s->generation) return A138_CLASSIC_STALE;', 'if (0) return A138_CLASSIC_STALE;'),
        ('uncertain-replayed', 'if (result==A138_CLASSIC_UNCERTAIN) return fence(s);', 'if (result==A138_CLASSIC_UNCERTAIN) return A138_CLASSIC_OK;'),
        ('start-before-rate', 'channel_open(s,2) && s->ready', 'channel_open(s,2) && 1'),
        ('duplicate-media-accepted', 'if (!delta || delta>0x8000u)', 'if (0)'),
        ('sbc-fragment-count-ignored', 'count!=s->fragment_remaining', '0'),
        ('config-not-committed', 'if (s->pending_config) {', 'if (0) {'),
        ('pending-rx-overwritten', 'if (s->rx_complete) return A138_CLASSIC_BUSY;', 'if (0) return A138_CLASSIC_BUSY;'),
        ('oversize-pdu-accepted', 'le16(p+4)>A138_CLASSIC_MTU', 'le16(p+4)>4095u'),
        ('queue-overflow-accepted', 'count>A138_CLASSIC_FRAMES-s->frame_count', '0'),
        ('sdp-sequence-add-wrap', 'bytes>(uint32_t)n-h', 'bytes+h>n'),
        ('cross-psm-cid-alias', 'if ((psm==1u)!=(j==0u) || s->channel[j].connection_id!=id) result=7;', '(void)psm;'),
        ('rtp-marker-ignored', '(p[1]&0x80u)', '0'),
        ('config-adjustment-ignored', '|| !supported', '|| 0'),
        ('controller-payload-limit-ignored', 'if (bytes>s->tx_payload_limit) bytes=s->tx_payload_limit;', 'if (bytes>276u) bytes=276;'),
        ('sdp-tid-bound-continuation', 'hash=query_hash(p+5,(uint16_t)(pos-5u))^p[0];', 'hash=query_hash(p,pos);'),
    ]:
        assert text.count(old) == 1, tag
        mutated = out / (tag + '.c')
        mutated.write_text(text.replace(old, new))
        exe = out / tag
        # Generation-ignored deliberately leaves unused input identity arguments.
        san = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if tag == 'sdp-sequence-add-wrap' else []
        run([*common, *san, '-Wno-unused-parameter', '-Wno-unused-but-set-variable', mutated, fixture, '-o', exe], tag + '-compile')
        p = run([exe], tag + '-run', expected=None)
        assert p.returncode != 0, ('surviving mutant', tag)
        mutants.append(dict(tag=tag, returncode=p.returncode, evidence=p.stderr.strip()))

    spec = importlib.util.spec_from_file_location('classic_sbc_prepare', root / 'tools/prepare_ae350_sbc.py')
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    adapted = out / 'adapted'
    adapter.prepare(root, adapted)
    decoder = adapted / 'decoder'
    sources = [source, fw / 'sbc_decoder_service.c', *sorted((decoder / 'srce').glob('*.c'))]
    decoder_flags = ['-Wno-unused-parameter', '-I' + str(decoder / 'include'), '-I' + str(decoder / 'srce')]
    for tag, flags in [('decode-native', []), ('decode-sanitized', ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
        run([*common, *decoder_flags, *flags, *sources, root / 'sim/ae350_classic_decode_fixture.c', '-o', out / tag], tag + '-compile')
    cases = []
    vector_file = root / 'sim/fixtures/ae350_sbc_reference.json'
    for row in json.loads(vector_file.read_text())['cases']:
        tag = row['name']
        sbc, reference = out / (tag + '.sbc'), out / (tag + '-reference.pcm')
        sbc.write_bytes(base64.b64decode(row['sbc_base64']))
        reference.write_bytes(base64.b64decode(row['reference_pcm_le_base64']))
        assert sha(sbc) == row['sbc_sha256'] and sha(reference) == row['reference_sha256']
        for kind in ('decode-native', 'decode-sanitized'):
            p = run([out / kind, sbc, out / (tag + '-' + kind + '.pcm')], tag + '-' + kind)
            assert 'runtime error:' not in p.stderr and 'Sanitizer' not in p.stderr
        a = (out / (tag + '-decode-native.pcm')).read_bytes()
        b = (out / (tag + '-decode-sanitized.pcm')).read_bytes()
        r = reference.read_bytes()
        assert a == b and len(a) == len(r)
        x = struct.unpack('<' + 'h' * (len(a)//2), a)
        y = struct.unpack('<' + 'h' * (len(r)//2), r)
        error = max(abs(v-w) for v, w in zip(x, y))
        assert error <= 8, (tag, error)
        cases.append(dict(case=tag, samples=len(x), max_abs_error=error, pcm_sha256=sha(out / (tag + '-decode-native.pcm'))))

    prefix = args.riscv_prefix
    rvinclude=out / 'rv32-include'
    rvinclude.mkdir()
    (rvinclude / 'string.h').write_text('#include <stddef.h>\nvoid *memset(void *,int,size_t);\nvoid *memcpy(void *,const void *,size_t);\nint memcmp(const void *,const void *,size_t);\n')
    rvflags = ['-march=rv32im_zicsr_zifencei', '-mabi=ilp32', '-msmall-data-limit=0', '-O2', '-ffreestanding',
               '-Wall', '-Wextra', '-Werror', '-fno-builtin', '-fstack-usage', '-fcallgraph-info=su', '-I' + str(fw), '-I' + str(rvinclude)]
    obj = out / 'classic_service.o'
    run([prefix + '-gcc', *rvflags, '-c', source, '-o', obj], 'rv32-compile')
    size = run([prefix + '-size', '-A', obj], 'rv32-size').stdout
    runtime_symbols=run([prefix + '-nm', '-u', obj], 'rv32-runtime-symbols').stdout
    budget_source=out / 'object_budget.c'
    budget_source.write_text('#include "classic_service.h"\nstruct a138_classic_service service;\n')
    run([prefix + '-gcc', *rvflags, '-c', budget_source, '-o', out / 'object_budget.o'], 'rv32-object-budget')
    budget_symbols=run([prefix + '-nm', '-S', out / 'object_budget.o'], 'rv32-budget-symbols').stdout
    object_bytes=int(re.search(r'\b([0-9a-f]+) B service',budget_symbols).group(1),16)
    sections = {m.group(1): int(m.group(2)) for m in re.finditer(r'^(\.\S+)\s+(\d+)\s+', size, re.M)}
    stack = (out / 'classic_service.su').read_text()
    frames = [{'function': line.split('\t')[0].split(':')[-1], 'bytes': int(line.split('\t')[1]), 'kind': line.split('\t')[2]}
              for line in stack.splitlines()]
    budget = dict(sections=sections, text_rodata_bytes=sum(v for k, v in sections.items() if k.startswith(('.text', '.rodata'))),
                  static_data_bytes=sum(v for k, v in sections.items() if k.startswith(('.data', '.bss'))),
                  caller_object_bytes=object_bytes, required_runtime_symbols=[line.split()[-1] for line in runtime_symbols.splitlines()], max_function_stack_frame=max(x['bytes'] for x in frames), function_stack_frames=frames,
                  limits='Incremental RV32 object only. Not linked firmware fit, call-chain stack proof, cycle/service deadline, or hardware acceptance.')
    inputs = [source, fw / 'classic_service.h', fixture, root / 'sim/ae350_classic_decode_fixture.c', Path(__file__).resolve(), vector_file,
              fw / 'sbc_decoder_service.c', fw / 'sbc_decoder_service.h', root / 'tools/prepare_ae350_sbc.py',
              *[p for p in (fw / 'third_party/sbc_oi').rglob('*') if p.is_file()]]
    adapted_identity={str(p.relative_to(adapted)):sha(p) for p in adapted.rglob('*') if p.is_file()}
    tools_identity={str(p):sha(p) for p in [cc,Path(prefix+'-gcc'),Path(prefix+'-size'),Path(prefix+'-nm')]}
    report = dict(schema='ae350-classic-source-stage-v1', selected_in_production=False, hardware_tested=False,
                  wire_results=wire_results, killed_behavioral_mutants=mutants, actual_decoder_cases=cases,
                  rv32_budget=budget, adapted_decoder_identity=adapted_identity, tool_identity=tools_identity, inputs={str(p.relative_to(root)): sha(p) for p in inputs}, commands=commands)
    (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('schema', 'wire_results', 'rv32_budget')}, indent=2))


if __name__ == '__main__':
    main()
