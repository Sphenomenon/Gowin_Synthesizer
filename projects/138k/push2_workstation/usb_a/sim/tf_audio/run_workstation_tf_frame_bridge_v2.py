#!/usr/bin/env python3
"""Real WAV48/44.1 decoder plus atomic TF transport/cancellation regression."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gray_bijection_proof():
    # g(x) = x XOR (x >> 1) is linear over GF(2). Full column rank proves
    # injectivity on every 32-bit input, hence bijectivity on this finite set.
    # Its inverse satisfies b[i] = XOR(g[31:i]); the complete 32-column inverse
    # identity proves binary(G) == E iff G == gray(E) for all 2**64 (G,E) pairs.
    columns = [(1 << bit) ^ ((1 << bit) >> 1) for bit in range(32)]
    pivots = {}
    for column in columns:
        value = column
        while value:
            bit = value.bit_length() - 1
            if bit in pivots:
                value ^= pivots[bit]
            else:
                pivots[bit] = value
                break
    inverse_columns = []
    for column in columns:
        binary = 0
        for bit in range(31, -1, -1):
            binary |= (((column >> bit) & 1) ^ ((binary >> (bit + 1)) & 1)) << bit
        inverse_columns.append(binary)
    assert len(pivots) == 32 and inverse_columns == [1 << bit for bit in range(32)]
    return dict(field='GF(2)', width=32, rank=len(pivots), gray_columns=columns,
                inverse_product_columns=inverse_columns, bijective=True,
                equality_equivalent_for_all_two_state_input_pairs=True,
                input_pair_count=2**64, four_state_metastability_proof=False,
                basis='linear full-rank Gray map and complete inverse-matrix identity')


def run(output,*,local_compute_release=False,empty_slot_refill=False):
    output.mkdir(parents=True, exist_ok=False)
    pcm = [(0x1234, -0x2345), (-1, 1), (32767, -32768), (0x4567, -0x5678),
           (-32000, 31001), (0x7a01, -0x7b02), (-0x3210, 0x210f), (0x0f01, -0x0e02)]
    fixtures = []
    for rate, name in ((48000, 'wav48'), (44100, 'wav44')):
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(b''.join(struct.pack('<hh', *pair) for pair in pcm))
        payload = stream.getvalue()
        assert len(payload) == 76
        fixture = output / (name + '.hex')
        fixture.write_text(''.join(f'{value:02x}\n' for value in payload))
        fixtures.append(fixture)
    golden = output / 'wav_gold.hex'
    golden.write_text(''.join(f'{left & 0xffff:04x}{right & 0xffff:04x}\n' for left, right in pcm))
    fixtures.append(golden)
    sources = [ROOT / name for name in (
        'rtl/tf_audio/workstation_tf_frame_bridge_v2.sv', 'rtl/music/music_async_fifo.sv',
        'rtl/audio/workstation_final_pcm_router.sv',
        'rtl/tf_audio/storage/tf_wav_chunk_parser.v', 'rtl/tf_audio/storage/tf_wav_pcm_decoder.v')]
    sources.append(Path(__file__).with_name('tb_workstation_tf_frame_bridge_v2.sv'))
    inputs = sources + fixtures + [Path(__file__).resolve(),ROOT/'rtl/tf_audio/workstation_tf_frame_bridge.sv',ROOT/'sim/tf_audio/tb_workstation_tf_frame_bridge.sv',ROOT/'sim/tf_audio/run_workstation_tf_frame_bridge.py',ROOT/'rtl/tf_audio/workstation_tf_frame_bridge_v2.provenance.json',ROOT/'rtl/tf_audio/provenance/workstation_tf_frame_bridge_v2.patch',ROOT/'rtl/tf_audio/WORKSTATION_TF_FRAME_BRIDGE_V2_CONTRACT.md']
    hashes = {str(path): digest(path) for path in inputs}
    result = dict(schema=1, passed=False,
                  source_identity='native-tf-LAST-session-frame-bridge-v2-' + digest(sources[0])[:16],
                  validation_stage='offline-real-decoder-and-transport-simulation',
                  hardware_tested=False, profile_changed=False, bitstream_sha256=None,
                  source_clock_hz=50000000, compute_clock_hz=76800000,
                  input_sha256=hashes, runs={}, negative_controls={},
                  gray_bijection_proof=gray_bijection_proof(),
                  local_compute_functional_release_selected=local_compute_release,
                  empty_slot_refill_selected=empty_slot_refill,
                  limits='Real WAV decoder, maintained FIFO, atomic LAST/session metadata and actual final-router mismatch/cancel boundary; no SD/FAT/DDR migration, complete runtime/top/profile selection, physical CDC, synthesis, P&R or board acceptance')
    try:
        for name, seed in (('default', 0), ('wrap', 0xfffffffd)):
            binary = output / (name + '.vvp')
            compile_command = ['iverilog', '-g2012', '-s', 'tb_workstation_tf_frame_bridge_v2',
                               '-Ptb_workstation_tf_frame_bridge_v2.LOCAL_COMPUTE_RESET_ENABLE='+str(int(local_compute_release)),
                               '-Ptb_workstation_tf_frame_bridge_v2.NO_SAME_EDGE_REFILL='+str(int(empty_slot_refill)),
                               '-Ptb_workstation_tf_frame_bridge_v2.START_GENERATION=' + str(seed),
                               '-o', str(binary), *map(str, sources)]
            run_command = ['vvp', str(binary)]
            record = dict(seed=seed, passed=False, compile_argv=compile_command, run_argv=run_command)
            result['runs'][name] = record
            for stage, command in (('compile', compile_command), ('run', run_command)):
                process = subprocess.run(command, cwd=output, text=True, capture_output=True, timeout=60)
                log = process.stdout + process.stderr
                path = output / (name + '_' + stage + '.log')
                path.write_text(log)
                record[stage + '_log_sha256'] = digest(path)
                if process.returncode:
                    raise RuntimeError(name + '/' + stage + ' failed:\n' + log[-6000:])
            log = (output / (name + '_run.log')).read_text()
            assert 'PASS tf_frame_bridge_v2:' in log, 'Missing verification marker'
            record['metrics'] = {key: int(value) for key, value in re.findall(r'(\w+)=(\d+)', log)}
            record['passed'] = True
            print(log, end='')
        original = sources[0].read_text()
        mutations=[
            ('lost_LAST', 'source_error_i || unsupported,source_last_i,',
             "source_error_i || unsupported,1'b0,", 'packet mismatch'),
            ('lost_session_generation', 'source_generation_o,source_session_generation_i,source_sample_rate_i,',
             "source_generation_o,32'd0,source_sample_rate_i,", 'packet mismatch'),
            ('stale_quiet_publication', 'quiet_published<=media_quiescent_o;',
             "quiet_published<=1'b1;", 'stale published quiet ACK preceded'),
            ('incomplete_gray_prefix', 'binary=prefix8^(prefix8>>16);',
             'binary=prefix8;', 'Gray decode failed'),
        ]
        if empty_slot_refill:
            mutations.append(('consumer_ready_feedback','NO_SAME_EDGE_REFILL ? !held_valid :',
                "1'b0 ? !held_valid :",'consumer ready re-entered payload capture CE'))
        for name, anchor, replacement, expected in mutations:
            assert original.count(anchor) == 1, 'Negative control anchor changed: ' + name
            mutant = output / (name + '.sv')
            mutant.write_text(original.replace(anchor, replacement))
            binary = output / (name + '.vvp')
            commands = (
                ('compile', ['iverilog', '-g2012', '-s', 'tb_workstation_tf_frame_bridge_v2',
                             '-Ptb_workstation_tf_frame_bridge_v2.LOCAL_COMPUTE_RESET_ENABLE='+str(int(local_compute_release)),
                             '-Ptb_workstation_tf_frame_bridge_v2.NO_SAME_EDGE_REFILL='+str(int(empty_slot_refill)),
                             '-o', str(binary), str(mutant), *map(str, sources[1:])]),
                ('run', ['vvp', str(binary)]),
            )
            record = dict(mutant_sha256=digest(mutant), rejected=False)
            result['negative_controls'][name] = record
            for stage, command in commands:
                process = subprocess.run(command, cwd=output, text=True, capture_output=True, timeout=60)
                log = process.stdout + process.stderr
                path = output / (name + '_' + stage + '.log')
                path.write_text(log)
                record[stage + '_argv'] = command
                record[stage + '_returncode'] = process.returncode
                record[stage + '_log_sha256'] = digest(path)
                if stage == 'compile':
                    assert process.returncode == 0, 'Negative control compile failed: ' + log[-6000:]
                else:
                    assert process.returncode != 0 and expected in log, 'Negative control escaped: ' + name + '\n' + log[-6000:]
                    record['rejected'] = True
                    print('PASS negative control: ' + name)
        result['inputs_unchanged_during_run'] = hashes == {str(path): digest(path) for path in inputs}
        assert result['inputs_unchanged_during_run'], 'Inputs changed during verification'
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--local-compute-release',action='store_true')
    parser.add_argument('--empty-slot-refill',action='store_true')
    args = parser.parse_args()
    if args.output:
        run(args.output.resolve(),local_compute_release=args.local_compute_release,empty_slot_refill=args.empty_slot_refill)
    else:
        with tempfile.TemporaryDirectory(prefix='gw138k-tf-frames-') as directory:
            run(Path(directory) / 'verification',local_compute_release=args.local_compute_release,empty_slot_refill=args.empty_slot_refill)


if __name__ == '__main__':
    main()
