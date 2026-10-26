"""Synthesize only BLE from a prepared native candidate; no P&R or deployment."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import xml.etree.ElementTree as ElementTree

from workstation_synthesis_netlist import SynthesisNetlist


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True, help='Prepared workstation/Prj1 directory')
    parser.add_argument('--output', type=Path, required=True, help='New component output directory')
    arguments = parser.parse_args()
    stage, output = arguments.stage.resolve(), arguments.output.resolve()
    sources = sorted((stage / 'native_bluetooth').glob('*.v'))
    wrapper = stage / 'rtl/bluetooth/workstation_bluetooth.sv'
    if not sources or not wrapper.is_file():
        parser.error('--stage must contain native_bluetooth and the native BLE wrapper')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(stage / 'native_bluetooth', output / 'native_bluetooth')
    shutil.copyfile(wrapper, output / wrapper.name)
    patch_path = output / 'native_bluetooth/patch_path.vh'
    patch_path.write_text('`define WORKSTATION_BLE_PATCH_FILE ' +
                         json.dumps(str(output / 'native_bluetooth/rtl8723ds_patch.mem')) + '\n')
    inputs = {str(source.relative_to(output)): hashlib.sha256(source.read_bytes()).hexdigest()
              for source in sorted((output / 'native_bluetooth').iterdir()) if source.is_file()}
    inputs[wrapper.name] = hashlib.sha256((output / wrapper.name).read_bytes()).hexdigest()
    script = output / 'run.tcl'
    script.write_text(f'''cd {{{output}}}
set_device GW5AST-LV138PG484AC2/I1 -device_version C
set_option -synthesis_tool gowinsynthesis
set_option -top_module workstation_bluetooth
set_option -output_base_name bluetooth
set_option -verilog_std sysv2017
add_file -type verilog {{{output / wrapper.name}}}
''' + ''.join(f'add_file -type verilog {{{output / "native_bluetooth" / source.name}}}\n'
              for source in sources) + 'run syn\n')
    started = time.monotonic()
    result = subprocess.run(['gw_sh', str(script)], cwd=output, capture_output=True, text=True)
    (output / 'synthesis.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit('BLE synthesis failed; see ' + str(output / 'synthesis.log'))
    base = output / 'impl/gwsynthesis/bluetooth'
    resource = ElementTree.parse(base.with_name('bluetooth_syn_rsc.xml')).getroot()
    netlist = SynthesisNetlist(base.with_suffix('.vg').read_text(), 'workstation_bluetooth')
    primitives = Counter(cell['kind'] for cell in netlist.cells.values()
                         if cell['kind'] not in netlist.modules)
    memories = {name: {'kind': cell['kind'], 'parameters': cell['parameters']}
                for name, cell in netlist.cells.items()
                if cell['kind'] in ('SP', 'SPB', 'SPX9B', 'SDP', 'SDPB', 'SDPX9B',
                                    'DP', 'DPB', 'DPX9B', 'pROM', 'pROMX9B', 'RAM16S4', 'RAM16SDP4')}
    summary = dict(stage=str(stage), scope='isolated_ble_synthesis_not_physical_implementation',
                   seconds=round(time.monotonic() - started, 3), inputs_sha256=inputs,
                   resources={key: int(resource.get('T_' + key, '0').split('(')[0])
                              for key in ('Lut', 'Alu', 'Register', 'Bsram', 'Ssram')},
                   primitives=dict(sorted(primitives.items())), memories=memories)
    (output / 'resources.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({key: summary[key] for key in ('scope', 'seconds', 'resources', 'primitives')}, indent=2))


if __name__ == '__main__':
    main()
