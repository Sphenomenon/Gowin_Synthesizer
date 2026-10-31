#!/usr/bin/env python3
"""Check D-only native effects and retirement while preserving FFT/context.

The prepared project supplies versioned reconstructed support/ROM inputs. Every
selected control/delay source is replaced by the maintained source under test;
no historical build output or synthesized result becomes a production input.
This is offline functional evidence, not physical audio or board acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from run_runtime_controlled import runtime_sources

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    project, output = args.project.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    selected = []
    for path in runtime_sources(project, ROOT / 'sim/audio/tb_workstation_demo_d_only.sv'):
        if path.is_relative_to(project):
            relative = path.relative_to(project)
            if relative.parts[:2] == ('rtl', 'control') or relative.parts[:3] == ('rtl', 'audio', 'delay_ddr'):
                path = ROOT / relative
        if path not in selected:
            selected.append(path)
    memory_reference = ROOT / 'sim/audio/tb_workstation_runtime_effects.sv'
    memory_text = memory_reference.read_text()
    anchor = '\nmodule tb_workstation_runtime_effects;'
    if memory_text.count(anchor) != 1:
        raise ValueError('ordered DDR model extraction anchor drift')
    memory = output / 'ordered_posted_ddr_model.sv'
    memory.write_text(memory_text.split(anchor)[0])
    selected.append(memory)
    retired = [project / 'legacy/rtl/audio/audio_math_pkg.sv',
               project / 'legacy/rtl/audio/spectrum_fft256.sv']
    retired += [ROOT / path for path in ('rtl/services/workstation_controlled_services.sv',
        'rtl/audio/workstation_observation_consumers.sv', 'rtl/memory/workstation_sdp.sv',
        'sim/audio/tb_workstation_demo_retirement.sv')]
    inputs = list(dict.fromkeys(selected + retired + [Path(__file__).resolve(), memory_reference]))
    inputs += sorted((project / 'sim/data').rglob('*.mem'))
    report = dict(passed=False, hardware_tested=False, synthesis_tested=False,
                  scope='D-only native render/effects/ordered-DDR and retired local REC/cue; true FFT/context retained',
                  limits='Synthetic decoder PCM fixture tests functional DSP only; no A2DP, physical I2S/HDMI, P&R or hardware acceptance',
                  input_sha256={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
                  stages=[])
    try:
        stages = [
            ('render_compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
                '--top-module', 'tb_workstation_demo_d_only', '--Mdir', str(output / 'obj'),
                '-I' + str(ROOT), '-I' + str(project), *map(str, selected)]),
            ('render_run', [str(output / 'obj/Vtb_workstation_demo_d_only')]),
            ('retirement_compile', ['iverilog', '-g2012', '-s', 'tb_workstation_demo_retirement',
                '-o', str(output / 'retirement.vvp'), *map(str, retired)]),
            ('retirement_run', ['vvp', str(output / 'retirement.vvp')]),
        ]
        for name, command in stages:
            log = output / (name + '.log')
            with log.open('w') as stream:
                process = subprocess.run(command, cwd=project, stdout=stream, stderr=subprocess.STDOUT, timeout=300)
            report['stages'].append(dict(name=name, argv=command, exit_code=process.returncode, log=str(log)))
            process.check_returncode()
            contents = log.read_text()
            if '%Error' in contents or 'ERROR:' in contents or 'FATAL:' in contents or 'UNOPTFLAT' in contents:
                raise ValueError('error or combinational admission loop: ' + name)
            if name.endswith('_run'):
                passes = [line for line in contents.splitlines() if line.startswith('PASS ')]
                if len(passes) != 1:
                    raise ValueError('missing unique functional result: ' + name)
                report['stages'][-1]['result'] = passes[0]
                print(passes[0])
        report['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
