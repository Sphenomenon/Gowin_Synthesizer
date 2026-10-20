#!/usr/bin/env python3
"""Build an isolated full-workstation timing experiment; no board access.

The input build is immutable. PNR-only reuse requires its successful synthesis
and identical logic inputs. This is a diagnostic candidate without a release
UserCode; no board-state records are updated.
"""
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from workstation_memory import audit, hierarchy, check_feature_storage
from workstation_sources import verify_cnn_inputs
from workstation_timing_constraints import constraints as cdc_constraints,physical_constraints,timing_reports


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strip_owned_timing_reports(text):
    """Keep constraints that follow our report block; reject unknown variants."""
    marker='\n# Timing experiment: reports only; preserve all clocks and exceptions.\n'
    if marker not in text:return text
    reports=timing_reports()
    if text.count(marker)!=1 or text.count(reports)!=1:
        raise ValueError('owned report commands differ; refusing to discard trailing constraints')
    return text.replace(reports,'',1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--flow', choices=['prepare', 'syn', 'pnr', 'all'], default='all')
    parser.add_argument('--label', default='candidate')
    parser.add_argument('--reuse-synthesis-from', type=Path, help='Copy completed immutable SYN outputs from matching logic, even while its PNR runs')
    parser.add_argument('--opt-goal',choices=['auto','area','timing'],help='Documented synthesis optimization goal')
    parser.add_argument('--place-option',type=int,choices=[0,1,2,3,4],help='Vendor placement strategy; same logical inputs')
    parser.add_argument('--replicate-resources',action='store_true',help='Vendor physical high-fanout replication; no RTL or clock change')
    parser.add_argument('--route-option', type=int, choices=[0,1], help='Explicit physical routing strategy; no logic or clock change')
    parser.add_argument('--refresh-cdc', action='store_true', help="Replace this builder family's targeted CDC block")
    parser.add_argument('--incremental-from', type=Path, help='Reuse a completed placement/route with identical logic')
    parser.add_argument('--route-reference', type=Path, help='Fresh SYN, then seed routing from an immutable matching device/CST reference')
    args = parser.parse_args()
    if args.route_reference and (args.incremental_from or args.flow != 'all'):
        parser.error('--route-reference requires fresh --flow all, without --incremental-from')
    source = args.source.resolve()
    inputs = json.loads((source / 'workstation_inputs.json').read_text())
    metadata = json.loads((source / 'build_metadata.json').read_text())
    for name, digest in inputs.items():
        if not (source / 'Prj1' / name).is_file() or sha(source / 'Prj1' / name) != digest:
            raise ValueError('source build input changed: ' + name)
    if metadata.get('user_code_assigned'):
        raise ValueError('use an unassigned diagnostic source build')
    if args.reuse_synthesis_from and args.flow!='pnr':
        parser.error('--reuse-synthesis-from requires --flow pnr')
    if args.flow == 'pnr' and not args.reuse_synthesis_from:
        result = json.loads((source / 'tool_result.json').read_text())
        if result['exit_code'] or not result['inputs_unchanged']:
            raise ValueError('PNR reuse requires successful immutable synthesis')
    if args.incremental_from and args.flow not in ('pnr', 'all'):
        parser.error('--incremental-from requires pnr/all')
    output = ROOT / 'results' / ('timing_' + args.label + '_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    stage = output / 'Prj1'
    shutil.copytree(source / 'Prj1', stage,
                    ignore=shutil.ignore_patterns('impl', 'build', '*.user', '__pycache__'))
    reused = {}
    synthesis_reference={}
    if args.flow == 'pnr':
        syn_source=(args.reuse_synthesis_from or source).resolve()
        if args.reuse_synthesis_from:
            syn_inputs=json.loads((syn_source/'workstation_inputs.json').read_text())
            for name,digest in syn_inputs.items():
                if sha(syn_source/'Prj1'/name)!=digest:raise ValueError('mutated synthesis source: '+name)
            compare=lambda m:{n:h for n,h in m.items() if not n.endswith(('.sdc','.p','.pr')) and n!='scripts/build.tcl'}
            if compare(inputs)!=compare(syn_inputs):raise ValueError('synthesis reuse logical inputs differ')
            if 'GowinSynthesis finish' not in (syn_source/'gowin.log').read_text(errors='replace'):
                raise ValueError('reference synthesis has not finished')
            normalize=lambda p:[line for line in p.read_text().splitlines() if not line.startswith(('set_option -inc_pnr','set_option -route_option'))]
            if normalize(source/'Prj1/scripts/build.tcl')!=normalize(syn_source/'Prj1/scripts/build.tcl'):
                raise ValueError('synthesis tool options differ')
            synthesis_reference=dict(source=str(syn_source.relative_to(ROOT)),complete_synthesis_log_sha256=sha(syn_source/'gowin.log'),logic_inputs_identical=True)
        old_syn = syn_source / 'Prj1/impl/gwsynthesis'
        before={p.relative_to(old_syn).as_posix():sha(p) for p in old_syn.rglob('*') if p.is_file()}
        shutil.copytree(old_syn, stage / 'impl/gwsynthesis')
        reused = {p.relative_to(old_syn).as_posix(): sha(p) for p in old_syn.rglob('*') if p.is_file()}
        if before!=reused or any(sha(stage/'impl/gwsynthesis'/n)!=h for n,h in reused.items()):
            raise ValueError('synthesis outputs changed during copy')
    sdc = stage / 'constraints/tang_mega_138k.sdc'
    reports = timing_reports()
    sdc_text = sdc.read_text()
    sdc_text = strip_owned_timing_reports(sdc_text)
    if args.refresh_cdc:
        markers=['\n# Workstation timing constraints: bounded CDC entries and PLL control routes.\n',
                 '\n# USB reset enters the audio domain only through the local release chain.\n',
                 '\n# TF diagnostic level flags: audio -> 50MHz, explicit two-stage receivers.\n']
        marker=next((item for item in markers if item in sdc_text),None)
        if marker is None or sdc_text.count(marker) != 1:
            raise ValueError('missing/ambiguous owned CDC block')
        sdc_text = sdc_text.split(marker, 1)[0] + cdc_constraints(diagnostic_cdc='u_music/u_trace_cdc' in sdc_text)
    sdc.write_text(sdc_text + reports)
    tcl = stage / 'scripts/build.tcl'
    if 'set_option -user_code' in tcl.read_text():
        raise ValueError('diagnostic project must not assign a release UserCode')
    if args.route_option is not None:
        text=tcl.read_text();lines=[line for line in text.splitlines() if line.startswith('set_option -route_option ')]
        if len(lines)!=1:raise ValueError('ambiguous routing strategy')
        tcl.write_text(text.replace(lines[0],f'set_option -route_option {args.route_option}'))
    if args.opt_goal is not None:
        text=tcl.read_text()
        text='\n'.join(line for line in text.splitlines() if not line.startswith('set_option -opt_goal '))+'\n'
        tcl.write_text(text.replace('set flow all',f'set_option -opt_goal {args.opt_goal}\nset flow all'))
    if args.place_option is not None:
        text=tcl.read_text();lines=[line for line in text.splitlines() if line.startswith('set_option -place_option ')]
        if len(lines)!=1:raise ValueError('ambiguous placement strategy')
        tcl.write_text(text.replace(lines[0],f'set_option -place_option {args.place_option}'))
    if args.replicate_resources:
        text=tcl.read_text()
        text='\n'.join(line for line in text.splitlines() if not line.startswith('set_option -replicate_resources '))+'\n'
        tcl.write_text(text.replace('set flow all','set_option -replicate_resources 1\nset flow all'))
    incremental = {}
    if args.incremental_from or args.route_reference:
        previous = (args.incremental_from or args.route_reference).resolve()
        old_inputs = json.loads((previous / 'workstation_inputs.json').read_text())
        old_result = json.loads((previous / 'tool_result.json').read_text())
        if old_result['exit_code'] or not old_result['inputs_unchanged']:
            raise ValueError('incremental reference is incomplete')
        if any(not (previous / 'Prj1' / n).is_file() or sha(previous / 'Prj1' / n) != h
               for n, h in old_inputs.items()):
            raise ValueError('incremental reference input drift')
        exceptions = {'constraints/tang_mega_138k.sdc', 'scripts/build.tcl'}
        cst_name='constraints/tang_mega_138k.cst'
        cst_locality=False
        if inputs.get(cst_name)!=old_inputs.get(cst_name):
            current=(stage/cst_name).read_text();old=(previous/'Prj1'/cst_name).read_text()
            if current!=old+physical_constraints():
                raise ValueError('physical reference allows only the exact internal PLL driver locality suffix')
            cst_locality=True;exceptions.add(cst_name)
        logic = lambda data: {n: h for n, h in data.items() if n not in exceptions and not n.startswith('build/')}
        changed_logic = sorted(n for n in logic(inputs).keys() | logic(old_inputs).keys()
                               if logic(inputs).get(n) != logic(old_inputs).get(n))
        if args.incremental_from and changed_logic:
            raise ValueError('incremental reference logic/IP/memory differs')
        if args.route_reference:
            # Reference contains physical hints only; SYN is always regenerated.
            # No IP, memory initialization, device or pin reassignment may drift.
            for name in inputs.keys() | old_inputs.keys():
                if (name.endswith(('.cst','.mem','.mi','.hex','.bin','.ip','.gao')) or
                        '/IP/' in name or '/ip/' in name) and inputs.get(name) != old_inputs.get(name) and not (name==cst_name and cst_locality):
                    raise ValueError('route reference pin/IP/memory mismatch: ' + name)
            a=ET.parse(stage/'Prj1.gprj').getroot().find('Device')
            b=ET.parse(previous/'Prj1/Prj1.gprj').getroot().find('Device')
            if a is None or b is None or ET.tostring(a)!=ET.tostring(b):
                raise ValueError('route reference device mismatch')

        options = lambda text: [line for line in text.splitlines() if not line.startswith('set_option -inc_pnr')]
        if options(tcl.read_text()) != options((previous / 'Prj1/scripts/build.tcl').read_text()):
            raise ValueError('incremental tool/synthesis options differ')
        pnr = previous / 'Prj1/impl/pnr'
        point = pnr / ('Prj1.pr' if (pnr / 'Prj1.pr').is_file() else 'Prj1.p')
        dest = stage / 'build' / ('timing_reference' + point.suffix)
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(point, dest)
        text = '\n'.join(line for line in tcl.read_text().splitlines() if not line.startswith('set_option -inc_pnr')) + '\n'
        if text.count('set flow all') != 1:
            raise ValueError('missing flow anchor for incremental P&R')
        tcl.write_text(text.replace('set flow all',
            f'set_option -inc_pnr [file join $root build {dest.name}]\nset flow all'))
        incremental = dict(source=str(previous.relative_to(ROOT)), point=dest.relative_to(stage).as_posix(),
                           point_sha256=sha(dest), changed_logic=changed_logic,internal_pll_locality=cst_locality,io_pin_constraints_unchanged=True,
                           fresh_synthesis=True if args.route_reference else args.flow=='all',
                           basis='fresh SYN; identical device/CST/IP/memory and options; physical hints only' if args.route_reference else
                           'identical RTL/IP/memory and tool options; SDC may differ')
    selected = metadata['music_sha256']
    verify_cnn_inputs(stage, selected)
    staged = {p.relative_to(stage).as_posix(): sha(p) for p in stage.rglob('*')
              if p.is_file() and 'impl' not in p.relative_to(stage).parts}
    changed = sorted(k for k in staged.keys() | inputs.keys() if staged.get(k) != inputs.get(k))
    allowed = {'constraints/tang_mega_138k.sdc'}
    if args.route_option is not None or args.place_option is not None or args.opt_goal is not None or args.replicate_resources:allowed.add('scripts/build.tcl')
    if incremental:
        allowed.update({'scripts/build.tcl', incremental['point']})
    if not set(changed) <= allowed:
        raise ValueError('unexpected diagnostic staging changes: ' + repr(changed))
    metadata.update(timing_source=str(source.relative_to(ROOT)), build_mode=args.flow,
                    changed_for_timing=changed, reused_synthesis_sha256=reused, synthesis_reference=synthesis_reference, incremental=incremental,
                    hardware_tested=False, release_candidate=False)
    (output / 'build_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (output / 'workstation_inputs.json').write_text(json.dumps(staged, indent=2) + '\n')
    if (source / 'cnn_source_audit.json').exists():
        shutil.copy2(source / 'cnn_source_audit.json', output / 'cnn_source_audit.json')
    print(output, flush=True)
    if args.flow == 'prepare':
        return
    storage_checked = False
    storage_error = None
    log_path = output / 'gowin.log'
    with log_path.open('w') as log:
        process = subprocess.Popen([str(Path.home() / '.local/bin/gw_sh'), 'scripts/build.tcl'],
                                   cwd=stage, env=dict(os.environ, PRJ1_FLOW=args.flow),
                                   stdout=log, stderr=subprocess.STDOUT)
        while process.poll() is None:
            if not storage_checked and 'GowinSynthesis finish' in log_path.read_text(errors='replace'):
                try:
                    _, rows = hierarchy(ET.parse(stage / 'impl/gwsynthesis/Prj1_syn_rsc.xml').getroot())
                    check_feature_storage(rows)
                    storage_checked = True
                except (ValueError, OSError, ET.ParseError) as exc:
                    storage_error = str(exc)
                    process.terminate()
                    break
            time.sleep(1)
        returncode = process.wait()
    if returncode == 0 and not storage_checked:
        try:
            _, rows = hierarchy(ET.parse(stage / 'impl/gwsynthesis/Prj1_syn_rsc.xml').getroot())
            check_feature_storage(rows)
            storage_checked = True
        except (ValueError, OSError, ET.ParseError) as exc:
            storage_error = str(exc)
    altered = [name for name, digest in staged.items()
               if not (stage / name).is_file() or sha(stage / name) != digest]
    regenerated = [name for name, digest in reused.items()
                   if not (stage / 'impl/gwsynthesis' / name).is_file() or
                   sha(stage / 'impl/gwsynthesis' / name) != digest]
    record = dict(exit_code=returncode, inputs_unchanged=not altered,
                  changed=altered, build_mode=args.flow, hardware_tested=False,
                  regenerated_synthesis_outputs=regenerated,
                  synthesis_reused_bitwise=bool(reused) and not regenerated,
                  synthesis_storage_checked=storage_checked, synthesis_storage_error=storage_error)
    (output / 'tool_result.json').write_text(json.dumps(record, indent=2) + '\n')
    verify_cnn_inputs(stage, selected)
    if returncode or altered or storage_error:
        raise SystemExit('timing build failed; see ' + str(output / 'gowin.log'))
    memory = audit(output, 'synthesis_only' if args.flow == 'syn' else 'full')
    print('SYN BSRAM', memory['bsram'], 'PNR BSRAM', memory['pnr_bsram'], flush=True)


if __name__ == '__main__':
    main()
