#!/usr/bin/env python3
"""Prove the private admission union and compare complete native services."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import workstation_event_admission as admission
from run_runtime_controlled import runtime_sources
from run_event_config_contract import wrapper


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def one(text, pattern):
    found = re.findall(pattern, text, re.S)
    assert len(found) == 1, pattern
    return found[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--role', choices=('M','W'), default='M', help='Exact role-specific native queue policy')
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out, project = args.output.resolve(), args.project.resolve()
    out.mkdir(parents=True, exist_ok=False)
    role=args.role
    policy=admission.W_POLICY if role=='W' else admission.POLICY
    manifest=admission.manifest(role)
    parents = {s: admission.parent_source(ROOT,s,role) for s in manifest['sources']}
    selected = {s: admission.adapt(s, t,role) for s, t in parents.items()}
    assert admission.configured({admission.KEY:policy,'demo_role':role})
    queue_default='parameter bit INNER_EVENT_QUEUE_ENABLE='+('0' if role=='W' else '1')
    assert queue_default in parents['rtl/audio/gw138k_event_workstation.sv']
    assert queue_default in selected['rtl/audio/gw138k_event_workstation.sv']
    assert all(admission.restore(s, t) == parents[s] for s, t in selected.items())
    assert not admission.configured({})
    for bad in ({admission.KEY: 'unknown'}, {admission.KEY: policy, 'demo_role': 'M' if role=='W' else 'W'}, {admission.KEY:admission.W_POLICY,'demo_role':'W','inner_event_queue_policy':'task3_M_two_slot_inner_event_queue_v1'}):
        try:
            admission.configured(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid role/policy accepted')
    for s, t in parents.items():
        try:
            admission.adapt(s, t + '\n',role)
        except ValueError:
            pass
        else:
            raise AssertionError('source drift accepted')
    service = parents['rtl/audio/workstation_audio_render_service.sv']
    event = parents['rtl/audio/gw138k_event_workstation.sv']
    new_service = selected['rtl/audio/workstation_audio_render_service.sv']
    names = ('external_free', 'external_config', 'external_history', 'active_automatic_config',
             'accepted', 'automatic_config', 'core_config', 'event_config_request',
             'render_ready_o', 'sample_ce_o')
    equations = 'wire '+','.join(names)+';\n'
    equations += ''.join('assign '+n+'='+one(service, r'\b(?:wire|assign)\s+'+n+r'\s*=\s*(.*?);')+';\n' for n in names)
    known = one(event, r"1'b0,1'b1: event_config_block=(.*?);")
    known = known.replace('runtime_config_busy', 'core_rate_busy').replace('event_rate_commit_i', 'event_config_request').replace('history_clear_i', 'external_history')
    body = one(new_service, r'(    reg combined_event_admission;.*?\n    end)\n    wire requested_rate=')
    flags = 'rst_ni active external_busy core_fault config_valid_i history_clear_i core_rate_busy cancel_delivery_pending render_request_i response_sent cancelled held_rate core_rate render_44k1_i'.split()
    bench = 'module tb;localparam RUNTIME_EFFECTS_ENABLE=1;\nreg '+','.join(flags)+';\n'+equations+body+'''
reg old_block;
always @* begin
    case(sample_ce_o)
        1'b0,1'b1: old_block='''+known+''';
        default: old_block=!core_rate_busy && (core_config || external_history);
    endcase
end
wire old_union=sample_ce_o || old_block;
reg [13:0] vector;
integer v,b,count=0,unknowns=0;
task drive; begin {'''+','.join(flags)+'''}=vector; end endtask
task check;begin #1;
    if(old_union !== combined_event_admission)$fatal(1,"admission union mismatch vector=%b",{'''+','.join(flags)+'''});
end endtask
initial begin
    for(v=0;v<16384;v=v+1)begin vector=v;drive();check();count=count+1;end
    for(v=0;v<10000;v=v+1)begin
        vector=$random;b=v%14;vector[b]=v[0]?1'bx:1'bz;drive();check();unknowns++;
    end
    $display("PASS admission union binary=%0d unknowns=%0d",count,unknowns);$finish;
end
endmodule
'''
    (out/'union.sv').write_text(bench)
    # The event edits change only the two private consumers and add guarded
    # wiring. The exact inverse above binds every other byte, including CE,
    # PANIC, parameter application and the complete configuration state body.
    new_event = selected['rtl/audio/gw138k_event_workstation.sv']
    assert new_event.count('!event_admission_block &&') == 2
    for s, t in selected.items():
        (out/Path(s).name).write_text(t)
    for s, t in parents.items():
        for name in ('gw138k_event_workstation', 'workstation_audio_render_service'):
            t = re.sub(r'\b'+name+r'\b', name+'_before_event_config', t)
        (out/(Path(s).stem+'_before_event_config.sv')).write_text(t)
    tb_path = Path(__file__).with_name('tb_event_config_service_contract.sv')
    tb = tb_path.read_text().replace('wire w_done,legacy_done;', 'wire w_done,m_done,legacy_done;')
    anchor = '  event_config_service_case #(.NATIVE(0),.D_ONLY(0)) legacy_case(legacy_done);'
    assert tb.count(anchor) == 1
    tb = tb.replace(anchor, '  event_config_service_case #(.NATIVE(1),.D_ONLY(0)) full_engine_case(m_done);\n'+anchor)
    tb = tb.replace('wait(w_done && legacy_done)', 'wait(w_done && m_done && legacy_done)')
    (out/'tb.sv').write_text(tb)
    (out/'miter.sv').write_text(wrapper(new_service))
    memory_path = ROOT/'sim/audio/tb_workstation_runtime_effects.sv'
    (out/'memory.sv').write_text(memory_path.read_text().split('\nmodule tb_workstation_runtime_effects;', 1)[0])
    sources = runtime_sources(project, out/'tb.sv')
    replacements = {ROOT/s: out/Path(s).name for s in selected}
    sources = [replacements.get(p, p) for p in sources]
    sources += [out/(Path(s).stem+'_before_event_config.sv') for s in parents]
    sources += [out/'miter.sv', out/'memory.sv']
    inputs = list(dict.fromkeys(sources + [ROOT/s for s in parents] +
                 [ROOT/admission.TOOL, ROOT/admission.MANIFEST, ROOT/admission.W_MANIFEST, Path(__file__).resolve(),
                  tb_path, memory_path, ROOT/'sim/audio/run_event_config_contract.py',
                  ROOT/'sim/audio/run_runtime_controlled.py']))
    hashes = {str(p): sha(p) for p in inputs}
    result = dict(passed=False, role=role, policy=policy, inner_event_queue_enabled=role=="M", input_sha256=hashes, physical_timing_verified=False,
                  hardware_tested=False, commands={})

    def run(name, command, timeout=120):
        result['commands'][name] = list(map(str, command))
        with (out/(name+'.log')).open('w') as log:
            subprocess.run(command, cwd=project, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=timeout)
        return (out/(name+'.log')).read_text()

    try:
        run('union_compile', ['iverilog', '-g2012', '-s', 'tb', '-o', out/'union.vvp', out/'union.sv'])
        log = run('union_run', ['vvp', out/'union.vvp'])
        assert 'PASS admission union binary=16384 unknowns=10000' in log
        assert bench.count('!active && !external_busy && !core_fault &&') == 1
        (out/'bad.sv').write_text(bench.replace('!active && !external_busy && !core_fault &&', '!active && !external_busy &&'))
        run('negative_compile', ['iverilog', '-g2012', '-s', 'tb', '-o', out/'bad.vvp', out/'bad.sv'])
        bad = subprocess.run(['vvp', str(out/'bad.vvp')], capture_output=True, text=True, timeout=30)
        (out/'negative_run.log').write_text(bad.stdout+bad.stderr)
        assert bad.returncode != 0 and 'admission union mismatch' in bad.stdout
        log = run('compile', ['verilator', '--binary', '--timing', '-j', '4', '-Wno-fatal',
            '--top-module', 'tb_event_config_service_contract', '--Mdir', out/'obj',
            '-I'+str(ROOT), '-I'+str(project), *sources], 300)
        assert '%Warning-UNOPTFLAT' not in log, 'combinational admission loop'
        log = run('run', [out/'obj/Vtb_event_config_service_contract'], 180)
        assert log.count('CONTRACT_MITER native=') == 3 and log.count('PASS event_config_contract ') == 3
        assert all(sha(p) == h for p, h in hashes.items()), 'input drift'
        result.update(passed=True, full_service_contract_log=log, exhaustive_binary_states=16384,
                      four_state_cases=10000, fault_veto_negative_control_rejected=True,
                      compared_public_outputs=50, common_boundaries=25, native_boundaries=7)
        print(log, end='')
    finally:
        result['logs_sha256'] = {p.name: sha(p) for p in out.glob('*.log')}
        (out/'verification.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
