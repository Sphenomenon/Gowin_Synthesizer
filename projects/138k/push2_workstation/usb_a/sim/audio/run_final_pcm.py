#!/usr/bin/env python3
"""Final PCM arithmetic, real render/WAV versus old routing, physical I2S taps."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    inputs = [Path(__file__).resolve()]
    results = dict(schema=1, passed=False, hardware_tested=False, profile_changed=False,
                   scope='Independent final compute PCM and physical-frame fanout; no production/top/CDC selection',
                   real_tf_scope='Actual native WAV decoder in coherent compute clock; not the production asynchronous TF bridge',
                   legacy_scope='Actual prepared PT serializers, current serial router/observer, actual FPC at stable48 gain; old startup preserved',
                   runs={})
    try:
        fixtures = []
        for rate in (48000, 44100):
            data = io.BytesIO()
            with wave.open(data, 'wb') as stream:
                stream.setnchannels(2)
                stream.setsampwidth(2)
                stream.setframerate(rate)
                stream.writeframes(b''.join(int(value).to_bytes(2, 'little', signed=True)
                                           for n in range(1024)
                                           for value in (10000+(n*97)%18000, -12000-(n*53)%16000)))
            target = output / f'tf{rate}.mem'
            target.write_text('\n'.join(f'{value:02x}' for value in data.getvalue()) + '\n')
            fixtures.append(target)
        router = ROOT / 'rtl/audio/workstation_final_pcm_router.sv'
        fanout = ROOT / 'rtl/audio/workstation_pcm_frame_fanout.sv'
        for name, sources in (
            ('tb_workstation_final_pcm_router', [router]),
            ('tb_workstation_pcm_physical_fanout', [router, fanout, ROOT / 'rtl/audio/workstation_pcm_frame_bridge.sv',
                                                   ROOT / 'rtl/audio/workstation_i2s_serializer.sv'])):
            tb = Path(__file__).with_name(name + '.sv')
            sources = sources + [tb]
            inputs += sources
            phase_hashes = {str(path): digest(path) for path in sources}
            command = ['iverilog', '-g2012', '-s', name, '-o', str(output / (name + '.vvp')), *map(str, sources)]
            with (output / (name + '.compile.log')).open('w') as stream:
                subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=60)
            with (output / (name + '.run.log')).open('w') as stream:
                subprocess.run(['vvp', str(output / (name + '.vvp'))], cwd=output,
                               stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=90)
            log = (output / (name + '.run.log')).read_text()
            if 'PASS ' not in log:
                raise ValueError('Missing verification: ' + name)
            results['runs'][name] = dict(passed=True, compile_argv=command,
                                        input_sha256=phase_hashes,
                                        inputs_unchanged_during_run=phase_hashes == {str(path): digest(path) for path in sources},
                                        metrics={key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)},
                                        run_log_sha256=digest(output / (name + '.run.log')), log=log)
            print(log, end='')
            if not results['runs'][name]['inputs_unchanged_during_run']:
                raise ValueError('Input identity drifted: ' + name)
        sources = sorted((project / 'legacy/rtl/audio').glob('*.sv'),
                         key=lambda path: (not path.name.endswith('_pkg.sv'), str(path)))
        sources += [project / name for name in (
            'legacy/rtl/input/midi_stream_decoder.sv', 'src/ae350/gw138k_three_event_arbiter.sv',
            'rtl/music/music_async_fifo.sv', 'rtl/audio/serial_spatial_reverb.sv',
            'rtl/memory/workstation_sdp.sv', 'rtl/memory/workstation_sdp_banked.sv',
            'src/audio/pt8211_tx.v', 'src/audio/tf_rate_pt8211_tx.v', 'src/audio/pt8211_observer.v',
            'src/migration/gw138k_stream_cdc.sv')]
        for folder in ('rtl/audio/scope_vec', 'rtl/control', 'rtl/audio/delay_ddr'):
            sources += sorted((project / folder).glob('*.sv'))
        sources += [ROOT / name for name in (
            'rtl/audio/gw138k_event_workstation.sv', 'rtl/audio/workstation_audio_render_service.sv',
            'rtl/audio/workstation_frame_delivery.sv', 'rtl/audio/workstation_final_pcm_router.sv',
            'rtl/audio/workstation_output_router.sv', 'rtl/audio/workstation_fpc_audio.sv',
            'rtl/tf_audio/storage/tf_wav_chunk_parser.v', 'rtl/tf_audio/storage/tf_wav_pcm_decoder.v',
            'sim/audio/tb_workstation_final_pcm_sources.sv')]
        inputs += sources + fixtures
        inputs += sorted((project / 'sim/data').rglob('*.mem'))
        inputs += sorted((project / 'sim/matlab/output').rglob('*.mem'))
        inputs += sorted((project / 'rtl/audio/scope_vec/data').glob('*.mem'))
        inputs += [project / 'rtl/audio/spatial_room_preset.svh']
        hashes = {str(path): digest(path) for path in inputs}
        results['input_sha256'] = hashes
        # Current mem paths remain relative to the exact prepared project;
        # fixture names are absolute defines, leaving that project untouched.
        tb = output / 'source_fixture_tb.sv'
        original = sources[-1].read_text()
        for rate in (48000, 44100):
            if original.count(f'"tf{rate}.mem"') != 1:
                raise ValueError('Fixture filename anchor drifted')
            original = original.replace(f'"tf{rate}.mem"', '"' + str(output / f'tf{rate}.mem') + '"')
        tb.write_text(original)
        compile_sources = sources[:-1] + [tb]
        command = ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                   '--top-module', 'tb_workstation_final_pcm_sources', '--Mdir', str(output / 'obj'),
                   '-I' + str(project), *map(str, compile_sources)]
        with (output / 'sources.compile.log').open('w') as stream:
            subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)
        with (output / 'sources.run.log').open('w') as stream:
            subprocess.run([str(output / 'obj/Vtb_workstation_final_pcm_sources')], cwd=project,
                           stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)
        log = (output / 'sources.run.log').read_text()
        if 'PASS final_pcm_sources:' not in log:
            raise ValueError('Missing real-source verification')
        warnings = {}
        for name in re.findall(r'^%Warning-(\w+):', (output / 'sources.compile.log').read_text(), re.M):
            warnings[name] = warnings.get(name, 0) + 1
        if 'UNOPTFLAT' in warnings:
            raise ValueError('Combinational output scheduling loop')
        results['runs']['real_sources'] = dict(passed=True, compile_argv=command, metrics={key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)},
                                              warning_counts=warnings, run_log_sha256=digest(output / 'sources.run.log'), log=log,
                                              test_fixture_adaptation='Only two WAV fixture filename literals become absolute paths in an output copy')
        results['runs']['real_sources']['fixture_tb_sha256'] = digest(tb)
        for run in results['runs'].values():
            for path, expected in run.get('input_sha256', {}).items():
                if digest(Path(path)) != expected:
                    raise ValueError('Earlier phase source changed: ' + path)
        results['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        if not results['inputs_unchanged_during_run']:
            raise ValueError('Input identity drifted')
        results['passed'] = True
        print(log, end='')
    finally:
        (output / 'verification.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
