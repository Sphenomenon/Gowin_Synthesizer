"""Read the explicitly identified USB2/HDMI GAO observer; never program a device."""

from collections import Counter
from pathlib import Path
import argparse
import csv
import fcntl
import json
import os
import runpy
import stat
import subprocess

from tools.workstation_usb2_hdmi import PHY_FIELDS, PORT_FIELDS, observer_layout
from tools.stage_usb_firmware import sha


ROOT = Path(__file__).resolve().parents[1]


def decode(values, profile='owner'):
    layout = observer_layout(profile)
    if len(values) != len(layout['signals']) or any(value not in (0, 1) for value in values):
        raise ValueError('expected the complete binary USB2/HDMI observer layout')
    observed = dict(zip(layout['signals'], values))
    values = [observed[source] if isinstance(source, str) else source for source in layout['sources']]
    words, offset = {}, 0
    for name, _, width, _ in layout['fields']:
        words[name] = int(''.join(map(str, values[offset:offset + width])), 2)
        offset += width
    flags, telemetry, events = words['flags'], words['telemetry'], words['events']
    connected = bool(telemetry & 2)
    if connected and words['gw25k'] and not words['generic_midi']:
        raise ValueError('inconsistent owner classification')
    transaction_ready = bool(flags & 16)
    device = (('25k' if words['gw25k'] else 'generic_midi' if words['generic_midi'] else 'push')
              if connected and transaction_ready else None)
    fault = (flags >> 8) & 15
    stage = ('reset' if not words['reset_released'] else 'cpu_fault' if fault else
             'phy_failed' if flags & 2 else 'phy_initializing' if not flags & 1 else
             'waiting_for_link' if not transaction_ready else 'configured' if connected else
             'enumerating_or_unrecognized')
    diagnostics = (telemetry >> 160) & 0xffffffff
    result = dict(stage=stage, recognized_device=device, enumeration_complete=connected,
                transaction_ready=transaction_ready, phy_ready=bool(flags & 1),
                high_speed=bool(flags & 4), traffic_enabled=bool(flags & 8),
                usb_pll_locked=bool(flags & 32), audio_pll_locked=bool(flags & 64),
                cpu_fault=fault, fault_address=f'0x{words["fault_address"]:08X}',
                instruction_address=f'0x{words["instruction_address"]:08X}',
                sof_count=words['sof_count'], out_errors=(telemetry >> 192) & 0xffffffff,
                in_errors=diagnostics & 255, duplicate_packets=(diagnostics >> 8) & 255,
                naks=(diagnostics >> 16) & 255, disconnects=(diagnostics >> 24) & 255,
                push_frames=(telemetry >> 128) & 0xffffffff,
                commands=(telemetry >> 96) & 0xffffffff,
                mapped_events=(telemetry >> 64) & 0xffffffff,
                received_events=(telemetry >> 32) & 0xffffffff,
                accepted_events=events >> 82, lifecycle_events=(events >> 50) & 0xffffffff,
                cancel_events=(events >> 18) & 0xffffffff, last_event=f'0x{events & 0x3ffff:05X}',
                  canceled_requests=words['canceled_requests'])
    if profile in ('phy', 'port'):
        result['phy'] = {name: words[name] for name, *_ in PHY_FIELDS}
        if not fault and words['reset_released']:
            if not words['reference_reset_released']:
                result['stage'] = 'reference_reset'
            elif not words['reference_enabled']:
                result['stage'] = 'host_disabled'
            elif words['clock_supervisor_state'] == 4:
                result['stage'] = 'ulpi_clock_failed'
            elif words['init_failure']:
                result['stage'] = 'ulpi_init_failed'
        if result['stage'] in ('reference_reset', 'host_disabled', 'ulpi_clock_failed', 'ulpi_init_failed'):
            result.update(recognized_device=None, enumeration_complete=False, transaction_ready=False)
    if profile == 'port':
        result['port'] = {name: words[name] for name, *_ in PORT_FIELDS}
        result['port']['states_seen'] = [state for state in range(19) if words['state_history'] & (1 << state)]
        result['port']['failures_seen'] = [code for code in range(1, 16) if words['failure_history'] & (1 << code)]
        result['port']['counter_scope'] = 'maximum_single_attempt_since_global_reset_not_sum'
    return result


def decode_csv(path, depth=1024, profile='owner', trigger='reset'):
    layout = observer_layout(profile)
    rows = [[value.strip() for value in row if value.strip()]
            for row in csv.reader(Path(path).read_text().splitlines(), skipinitialspace=True)]
    header = next((index for index, row in enumerate(rows) if row and row[0].startswith('time unit:')), None)
    if header is None or rows[header][1:] != list(layout['signals']):
        raise ValueError('USB2/HDMI capture signal order changed')
    samples = []
    for row in rows[header + 1:]:
        if not row:
            continue
        if (len(row) != len(layout['signals']) + 1 or int(row[0]) != len(samples) or
                any(value not in ('0', '1') for value in row[1:])):
            raise ValueError('invalid or noncontiguous USB2/HDMI sample row')
        samples.append(decode(list(map(int, row[1:])), profile))
    if len(samples) != depth:
        raise ValueError('incomplete USB2/HDMI capture window')
    if trigger == 'clock-failure':
        if profile != 'phy' or not any(sample['phy']['clock_failure'] & 1 for sample in samples):
            raise ValueError('clock-failure trigger not observed in returned window; not valid fault evidence')
    elif trigger != 'reset':
        raise ValueError('unknown USB2/HDMI observer trigger')
    diagnostics = {}
    if profile in ('phy', 'port'):
        transitions = lambda name: sum(before['phy'][name] != after['phy'][name]
                                       for before, after in zip(samples, samples[1:]))
        diagnostics = dict(reference_heartbeat_edges=transitions('reference_heartbeat'),
                           ulpi_heartbeat_changes=transitions('ulpi_heartbeat'),
                           link_snapshot_updates=transitions('link_acknowledge'),
                           direction_edges=transitions('raw_direction'), next_edges=transitions('raw_next'),
                           stop_edges=transitions('raw_stop'),
                           line_states=sorted({sample['phy']['raw_line_state'] for sample in samples}),
                           supervisor_states=sorted({sample['phy']['clock_supervisor_state'] for sample in samples}),
                           init_stages=sorted({sample['phy']['init_stage'] for sample in samples}),
                           port_states=sorted({sample['phy']['port_state'] for sample in samples}),
                           sample_policy='raw existing nets sampled at CPU 48 MHz; stable states and observed edges only')
        clock_not_observed = (not diagnostics['reference_heartbeat_edges'] and
                              not diagnostics['ulpi_heartbeat_changes'] and
                              all(sample['usb_pll_locked'] and sample['phy']['reference_reset_released'] and
                                  sample['phy']['destination_reset_released'] and
                                  not sample['phy']['heartbeat_reset_released'] and
                                  not sample['phy']['source_reset_released'] for sample in samples))
        diagnostics['ulpi_domains_still_in_reset'] = clock_not_observed
        for sample in samples:
            sample['snapshot_observed'] = bool(diagnostics['link_snapshot_updates'])
            if not sample['snapshot_observed']:
                sample.update(recognized_device=None, enumeration_complete=False, transaction_ready=False)
                if clock_not_observed and sample['stage'] not in ('reset', 'cpu_fault', 'reference_reset',
                                                                  'ulpi_clock_failed', 'ulpi_init_failed'):
                    sample['stage'] = 'ulpi_clock_not_observed'
                elif sample['stage'] not in ('reset', 'cpu_fault', 'reference_reset', 'host_disabled',
                                             'ulpi_clock_failed', 'ulpi_init_failed'):
                    sample['stage'] = 'snapshot_unavailable'
    return dict(samples=len(samples), first=samples[0], last=samples[-1], phy_diagnostics=diagnostics,
                stages=dict(Counter(sample['stage'] for sample in samples)),
                recognized_devices=sorted({sample['recognized_device'] for sample in samples
                                           if sample['recognized_device'] is not None}),
                cpu_instruction_addresses=len({sample['instruction_address'] for sample in samples}),
                counter_scope='cumulative_since_reset_not_per_connection', csv_sha256=sha(Path(path)))


def capture(candidate, output):
    candidate, output = Path(candidate).resolve(), Path(output).resolve()
    manifest = json.loads((candidate / 'inputs.json').read_text())
    profile = manifest.get('observer_profile', 'owner')
    layout = observer_layout(profile)
    if (manifest.get('signal_schema') != layout['schema'] or manifest.get('signals') != list(layout['signals']) or
            manifest.get('logical_bit_sources') != list(layout['sources']) or
            manifest.get('fields') != [list(field) for field in layout['fields']]):
        raise ValueError('not the explicit USB2/HDMI observer')
    configuration = candidate / manifest['gao_file']
    if sha(configuration) != manifest['input_sha256'][manifest['gao_file']]:
        raise ValueError('USB2/HDMI GAO configuration changed')
    helper = runpy.run_path(str(ROOT / 'reports/hdmi_usb3_20261025/capture_ddr_jtag.py'))
    if (sha(helper['BINARY']) != '4717a2afa56893861de161207bc2c4f094f53227099763ebfa2f0025ab72515b' or
            sha(helper['RECIPE']) != '901f1c40d4679c54e1246226c33c2d33850c2a55bbebed496ed9c69f4b87de66'):
        raise ValueError('validated GAO host binary or WINUSB recipe changed')
    output.mkdir(parents=True, exist_ok=False)
    with Path('/tmp/gw138k_20261025.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        helper['identity'](output / 'identity_before.log', manifest['user_code'])
        socket = helper['TEMPORARY'] / 'gao1'
        if socket.exists():
            listeners = subprocess.run(['ss', '-xlpn'], capture_output=True, text=True, check=True).stdout
            if not stat.S_ISSOCK(socket.lstat().st_mode) or socket.lstat().st_uid != os.getuid() or str(socket) in listeners:
                raise ValueError('GAO socket is foreign or active')
            socket.unlink()
        environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_OPENGL='software',
                           LD_LIBRARY_PATH=str(helper['BINARY'].parents[1] / 'lib'),
                           LD_PRELOAD='/usr/lib64/libstdc++.so.6:/usr/lib64/libz.so.1:/usr/lib64/libfreetype.so.6',
                           TMPDIR=str(helper['TEMPORARY']))
        command = ['timeout', '--kill-after=5s', '60s', 'gdb', '-nx', '-q', '-batch', '-x',
                   str(helper['RECIPE']), '--args', str(helper['BINARY']), '-local', '-gao',
                   str(configuration), '-out', str(output / 'capture'), '-cable', 'FT2CH', '-location', '54']
        started = helper['timestamp']()
        with (output / 'gdb.log').open('x') as log:
            result = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=75)
        if result.returncode:
            raise RuntimeError('GAO capture failed: ' + str(result.returncode))
        files = list(output.glob('capture_core*_window*.csv'))
        if len(files) != 1:
            raise ValueError('expected one USB2/HDMI GAO capture window')
        record = decode_csv(files[0], manifest['storage_depth'], profile, manifest.get('observer_trigger', 'reset'))
        helper['identity'](output / 'identity_after.log', manifest['user_code'])
        record.update(identity=manifest['identity'], started_at=started, finished_at=helper['timestamp'](),
                      gao_sha256=sha(configuration), decoder_sha256=sha(Path(__file__)),
                      hardware_programmed=False, operation='read_only_GAO_capture')
        (output / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
        return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(capture(arguments.candidate, arguments.output), indent=2))
