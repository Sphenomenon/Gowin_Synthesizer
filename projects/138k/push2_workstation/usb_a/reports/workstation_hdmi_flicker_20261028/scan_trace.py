from pathlib import Path
import argparse
import json
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import workstation_hdmi_isolation as hdmi


SCAN = 'u_display/u_video/u_scanout/'
VIDEO = 'u_display/u_video/'
FIELDS = [('fetch_line', 11), ('fetch_epoch', 8), ('issued', 9), ('received', 9),
          ('response_count', 4), ('write_quarter', 2)] + [
              (name, 1) for name in ('active', 'second_line', 'request_pending',
                                   'request_settled', 'ack_toggle', 'request_meta', 'request_sync',
                                   'done0_toggle', 'done1_toggle', 'front_valid')]


def probe_name(name, bit, width):
    if name == 'issued' and bit < 3:
        name = 'issued_0'
    if name == 'front_valid':
        name = 'front_valid_Z'
    return SCAN + (f'{name}[{bit}]' if width > 1 else name)


TRACE_SIGNALS = [probe_name(name, bit, width)
                 for name, width in FIELDS for bit in reversed(range(width))] + [
                     'u_display/' + name for name in ('command_full', 'command_write', 'push',
                                                      'controller_rvalid', 'app_cmd_Z[0]')] + [
                     'u_display/u_memory/' + name for name in ('full', 'controller_wrdy',
                                                              'state[0]', 'state[1]', 'state[2]')] + [
                     VIDEO + 'frame_swap_Z']
SIGNALS = list(hdmi.SIGNALS) + TRACE_SIGNALS
SCHEMA = 'hdmi-isolation-scan-ddr-trace-128-v1'


def decode_trace(values):
    if len(values) != 64:
        raise ValueError('expected 64 scan trace bits')
    position = 0
    result = {}
    for name, width in FIELDS:
        result[name] = int(''.join(map(str, values[position:position + width])), 2)
        position += width
    for name, value in zip(TRACE_SIGNALS[position:], values[position:]):
        result[name.rsplit('/', 1)[1]] = value
    return result


def prepare(output, netlist_directory, user_code):
    stage, manifest = hdmi.prepare(ROOT, netlist_directory, output, user_code)
    configuration = stage / 'display.gao'
    document = ET.fromstring(configuration.read_text())
    core = document.find('AoCore')
    core.set('sample_clock', 'u_display/memory_clk')
    core.set('storage_depth', '8192')
    core.set('capture_amount', '8192')
    signals = core.find('SignalList')
    for name in TRACE_SIGNALS:
        ET.SubElement(signals, 'Signal', capture_enable='true').text = name
    configuration.write_text(ET.tostring(document, encoding='unicode'))
    manifest.update(signal_schema=SCHEMA, signals=SIGNALS,
                    sample_clock='u_display/memory_clk', storage_depth=8192,
                    observer_scope='existing scanout and native DDR signals; no RTL change',
                    probe_alias_reference='D3 synthesis 0bca01410b12bdb380b9a3b8c903504e0fbbfc8f43a0585a385e0fe776f14bef; GAO fails on absent nets',
                    observer_retirement='diagnostic only; retain counter-only production observer')
    manifest['input_sha256']['display.gao'] = hdmi.digest(configuration)
    manifest['observer_script_sha256'] = hdmi.digest(Path(__file__))
    (stage / 'inputs.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return stage


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--netlist-dir', type=Path, required=True)
    parser.add_argument('--user-code', required=True)
    arguments = parser.parse_args()
    print(prepare(arguments.output, arguments.netlist_dir, arguments.user_code))
