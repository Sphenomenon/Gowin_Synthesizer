#!/usr/bin/env python3
"""Bounded real-path source quiesce publication and last-edge cancellation proof."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from run_workstation_tf_runtime_service import run as run_nominal

ROOT = Path(__file__).resolve().parents[2]
digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(output):
    output.mkdir(parents=True, exist_ok=False)
    run_nominal(output / 'nominal')
    nominal = json.loads((output / 'nominal/verification.json').read_text())
    tb = Path(__file__).with_name('tb_workstation_tf_source_quiesce.sv')
    service = ROOT / 'rtl/tf_audio/workstation_tf_runtime_service.sv'
    sources = nominal['compile_argv'][nominal['compile_argv'].index('-o') + 2:] + [str(tb)]
    inputs = dict(nominal['input_sha256'])
    inputs.update({str(p): digest(p) for p in [tb, Path(__file__).resolve()]})
    identity = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    result = dict(schema=1, passed=False, identity='native-tf-source-quiesce-v1-' + identity[:16],
                  source_set_sha256=identity, input_sha256=inputs, nominal=nominal,
                  validation_stage='offline-real-runtime-source-quiesce-last-edge-cancellation',
                  registered_quiesce=True, same_edge_invalidate_preserved=True,
                  source_release_extra_cycle_ns=20, clock_or_exception_changes=False,
                  synthesis_run=False, place_route_run=False, hardware_operated=False,
                  deployment_allowed=False, cases={}, negatives={},
                  limits='Ideal digital clocked protocol and subcycle decode checks with actual maintained service, DDR path, token clear, WAV decoder, frame bridge and control ACK. SD endpoint is the maintained byte fixture; DDR is ordered single-outstanding. No metastability, actual VG, routed timing/CDC/reset, resource, hardware or deployment acceptance.')
    def execute(name, selected, buffered=0, extra=(), rejection=None):
        command = ['iverilog', '-g2012', '-Wall', '-I', str(output / 'nominal'), '-s',
                   'tb_workstation_tf_source_quiesce',
                   '-Ptb_workstation_tf_source_quiesce.USE_COMMAND_BUFFER=' + str(buffered),
                   *extra, '-o', str(output / (name + '.vvp')), *selected]
        compiled = subprocess.run(command, cwd=output / 'nominal', capture_output=True, text=True, timeout=90)
        clog = output / (name + '_compile.log'); clog.write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise RuntimeError('compile ' + name + ': ' + clog.read_text()[-7000:])
        executed = subprocess.run(['vvp', str(output / (name + '.vvp'))], cwd=output / 'nominal',
                                  capture_output=True, text=True, timeout=90)
        rlog = output / (name + '_run.log'); log = executed.stdout + executed.stderr; rlog.write_text(log)
        record = dict(compile_argv=command, returncode=executed.returncode,
                      compile_log_sha256=digest(clog), run_log_sha256=digest(rlog))
        if rejection is None:
            if executed.returncode or 'PASS tf_source_quiesce:' not in log:
                raise RuntimeError('run ' + name + ': ' + log[-7000:])
            record['metrics'] = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', log)}
            result['cases'][name] = record; print(log, end='')
        else:
            record['rejected'] = executed.returncode != 0 and any(x in log for x in rejection)
            record['expected_reasons'] = rejection
            result['negatives'][name] = record
            if not record['rejected']:
                raise ValueError('mutation escaped ' + name + ': ' + log[-7000:])
        return record
    try:
        for buffered in (0, 1):
            execute('registered_' + str(buffered), sources, buffered)
        text = service.read_text()
        block = ('    (* syn_preserve=1 *) reg source_quiesce;\n'
                 '    always @(posedge clk_50m_i or negedge rst_ni)\n'
                 '        if(!rst_ni)source_quiesce<=1;\n'
                 '        else source_quiesce<=state==IDLE || state==QUIESCE || state==RESTART_SETTLE || invalidate;\n')
        if text.count(block) != 1:
            raise ValueError('source publisher exact anchor drift')
        mutations = [
            ('old_combinational', block,
             '    wire source_quiesce=state==IDLE || state==QUIESCE || state==RESTART_SETTLE || invalidate;\n',
             ['quiesce publisher changed between source edges', 'subcycle epoch decode published asynchronous quiesce'],
             ['-Ptb_workstation_tf_source_quiesce.CHECK_REGISTER_POLICY=0']),
            ('delayed_cancel_invalidate', '    wire bridge_source_ready,source_quiet,generation_pending;\n',
             '    reg delayed_cancel_invalidate;\n    always @(posedge clk_50m_i or negedge rst_ni)\n'
             '        if(!rst_ni)delayed_cancel_invalidate<=0;else delayed_cancel_invalidate<=allowed_cancel;\n'
             '    wire bridge_source_ready,source_quiet,generation_pending;\n',
             ['same-edge generation barrier was delayed or duplicated'], []),
            ('publisher_omits_event',
             'else source_quiesce<=state==IDLE || state==QUIESCE || state==RESTART_SETTLE || invalidate;',
             'else source_quiesce<=state==IDLE || state==QUIESCE || state==RESTART_SETTLE;',
             ['quiesce publisher did not sample source policy', 'last source edge failed to retain quiesce'], []),
            ('reset_deasserted', 'if(!rst_ni)source_quiesce<=1;', 'if(!rst_ni)source_quiesce<=0;',
             ['asserted reset quiesce missing'], []),
            ('bridge_raw_bypass', '.source_quiesce_i(source_quiesce)',
             '.source_quiesce_i(state==IDLE || state==QUIESCE || state==RESTART_SETTLE || invalidate)',
             ['bridge quiesce input changed between source edges', 'subcycle epoch decode published asynchronous quiesce'], []),
            ('native_hold_omits_event',
             '.native_source_hold_i(state==QUIESCE || state==RESTART_SETTLE || invalidate || stop_latched || (state==IDLE && mode_i))',
             '.native_source_hold_i(state==QUIESCE || state==RESTART_SETTLE || stop_latched || (state==IDLE && mode_i))',
             ['same-edge source admission or native input hold missing'], []),
        ]
        for name, anchor, replacement, rejection, extra in mutations:
            if text.count(anchor) != 1:
                raise ValueError('mutation exact anchor drift: ' + name)
            changed = text.replace(anchor, replacement)
            if name == 'delayed_cancel_invalidate':
                connection = '.invalidate_i(invalidate)'
                if changed.count(connection) != 1:
                    raise ValueError('frame generation publisher connection drift')
                changed = changed.replace(connection, '.invalidate_i((invalidate && !allowed_cancel) || delayed_cancel_invalidate)')
            mutant = output / ('workstation_tf_runtime_service_' + name + '.sv'); mutant.write_text(changed)
            selected = [str(mutant) if x == str(service) else x for x in sources]
            record = execute(name, selected, 0, extra, rejection)
            record.update(mutant_sha256=digest(mutant), exact_anchor_replacement=True)
        result['inputs_unchanged_during_run'] = inputs == {p: digest(p) for p in inputs}
        if not result['inputs_unchanged_during_run']:
            raise ValueError('source input drift')
        result['passed'] = True
    finally:
        (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
