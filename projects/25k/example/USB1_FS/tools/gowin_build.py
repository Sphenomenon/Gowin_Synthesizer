#!/usr/bin/env python3
"""Build in a clean ASCII directory, with separate synthesis/PnR processes."""
from pathlib import Path
import datetime
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

prj = Path(__file__).resolve().parents[1]
script = Path(sys.argv[1]).resolve()
relative_script = script.relative_to(prj)
text = script.read_text()
if len(re.findall(r'^run all\s*$', text, re.M)) != 1:
    raise SystemExit('Expected exactly one standalone run all in the build script.')
setup = re.sub(r'^run all\s*$', '', text, flags=re.M)
ide = Path(os.environ.get('GW25K_IDE_DIR', '/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE'))
env = dict(os.environ, DYLD_LIBRARY_PATH=str(ide/'lib'), DYLD_FRAMEWORK_PATH=str(ide/'lib'))
run_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
report_dir = script.parent/'reports'
report_dir.mkdir(exist_ok=True)

# All projects share the same tool installation and license state. Fail fast
# rather than starting concurrent compiler processes or silently retrying.
lock = open('/private/tmp/gw25k-build.lock', 'a')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('Another GW25K build is active; this build was not started.')

stage = Path(tempfile.mkdtemp(prefix='gw25k-build-', dir='/private/tmp'))
stage_prj = stage/'prj'
shutil.copytree(prj, stage_prj, ignore=shutil.ignore_patterns(
    'impl', 'generated', 'reports', 'builds', '__pycache__', '.git', '.venv',
    'build', '.DS_Store', '*.vvp'))
stage_project = (stage_prj/relative_script).parent
result = {'started_at': datetime.datetime.now().astimezone().isoformat(),
          'script': str(relative_script), 'stage_directory': str(stage),
          'passed': False, 'phases': {}, 'artifacts': []}

def save_result(name):
    (report_dir/name).write_text(json.dumps(result, indent=2)+'\n')

def fail(message, code=1):
    result['error'] = message
    save_result('build_'+run_id+'.json')
    save_result('last_failure.json')
    print(message, flush=True)
    print('Diagnostic files retained at '+str(stage), flush=True)
    raise SystemExit(code)

print('ASCII build directory: '+str(stage), flush=True)
for phase in ('syn', 'pnr'):
    phase_script = stage_project/('.gw25k_'+phase+'.tcl')
    if phase == 'syn':
        # Export only explicit settings. This release exports some unsupported
        # device defaults (for example vccaux) with saveto -all_options.
        phase_script.write_text(setup+'\nrun syn\nsaveto frozen_setup.tcl\n')
    else:
        netlists = list((stage_project/'impl/gwsynthesis').glob('*.vg'))
        if len(netlists) != 1:
            fail('Expected exactly one fresh synthesized top-level netlist.')
        # Reuse the frozen project settings, but give PnR ONLY the synthesized
        # netlist and constraints. Keeping RTL in the file list can cause this
        # Gowin release to silently synthesize again in the second process.
        phase_script.write_text('''rename add_file gw25k_add_file
proc add_file {args} {
    set source_file [lindex $args end]
    if {[file extension $source_file] eq ".rao"} {
        error "RTL GAO .rao is incompatible with this isolated PnR flow. Use a post-synthesis .gao capture definition."
    } elseif {[file extension $source_file] in {.cst .sdc .gao}} {
        gw25k_add_file {*}$args
    }
}
source frozen_setup.tcl
gw25k_add_file -type netlist {'''+str(netlists[0])+'''}
run pnr
''')
    log = stage/(phase+'.log')
    print('Starting '+phase+' in a fresh gw_sh process.', flush=True)
    with log.open('w') as output:
        process = subprocess.run([str(ide/'bin/gw_sh'), str(phase_script)],
                                 cwd=stage_project, env=env, stdout=output,
                                 stderr=subprocess.STDOUT)
    output_text = log.read_text(errors='replace')
    saved_log = report_dir/('build_'+run_id+'_'+phase+'.log')
    shutil.copy2(log, saved_log)
    result['phases'][phase] = {'returncode': process.returncode,
                              'log': str(saved_log.relative_to(prj))}
    if process.returncode or re.search(r'(^|\n)(?:ERROR\s*\(|Error:)', output_text):
        print('\n'.join(output_text.splitlines()[-12:]), flush=True)
        fail(phase+' failed; existing successful artifacts were preserved.',
             128-process.returncode if process.returncode < 0 else (process.returncode or 1))
    if phase == 'pnr' and 'GowinSynthesis start' in output_text:
        fail('PnR unexpectedly repeated synthesis; refusing to publish artifacts.')
    if phase == 'pnr' and 'Skip synthesis, because there is only one netlist file' not in output_text:
        fail('PnR did not confirm the netlist-only flow; refusing to publish artifacts.')
    completion = 'GowinSynthesis finish' if phase == 'syn' else 'Bitstream generation completed'
    if completion not in output_text:
        fail(phase+' did not report completion; refusing to publish artifacts.')

impl = stage_project/'impl'
bitstreams = sorted((impl/'pnr').glob('*.fs'))
if not bitstreams:
    fail('No fresh bitstream was produced; existing artifacts were preserved.')
frozen_lines = (stage_project/'frozen_setup.tcl').read_text().splitlines()
gao_files = []
for frozen_line in frozen_lines:
    # saveto emits quoted absolute input paths. Inspect the actual enabled
    # project files, independent of the build script's name or their folder.
    if frozen_line.startswith('add_file ') and '-disable' not in frozen_line:
        match = re.search(r'"([^"\n]+\.(?:gao|rao))"\s*$', frozen_line)
        if match:
            gao_files.append(Path(match.group(1)))
if ('build_gao' in script.stem or script.stem.endswith('_gao')) and not gao_files:
    fail('GAO build has no enabled capture definition; refusing to publish artifacts.')
if gao_files:
    from xml.etree import ElementTree
    expected_ids = [e.text for p in gao_files for e in ElementTree.parse(p).iter()
                    if e.tag.lower() == 'gao_id']
    cmd_file = impl/'pnr/cmd.do'
    pnr_command = cmd_file.read_text() if cmd_file.exists() else ''
    generated_gao = stage_project/'impl/gao/gao.v'
    if (not expected_ids or '-gao_crc' not in pnr_command or
            not re.search(r'^-gao\s+', pnr_command, re.M) or
            not generated_gao.is_file() or '-rtl_gao' in pnr_command):
        fail('GAO metadata was not preserved in PnR; refusing to publish artifacts.')
    command_ids = re.findall(r'^-gao_crc\s+([01]+)\s*$', pnr_command, re.M)
    if set(command_ids) != set(expected_ids):
        fail('PnR GAO CRC differs from the active capture definition.')
    if any(not all('//GAOCRC: '+expected in p.read_text()[:2000] for p in bitstreams)
           for expected in expected_ids):
        fail('GAO ID does not match the new bitstream; refusing to publish artifacts.')
    result['gao'] = [{'definition': str(p.relative_to(stage_prj)),
                      'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                     for p in gao_files]

# Publish each successful run separately. The original impl and previous good
# builds stay intact; later downloads use the manifest path and SHA256.
published_impl = script.parent/'builds'/run_id/'impl'
shutil.copytree(impl, published_impl)
for path in bitstreams:
    published = published_impl/path.relative_to(impl)
    result['artifacts'].append({'path': str(published.relative_to(prj)),
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
result['passed'] = True
result['finished_at'] = datetime.datetime.now().astimezone().isoformat()
save_result('build_'+run_id+'.json')
temporary_manifest = report_dir/'.last_build.json.tmp'
temporary_manifest.write_text(json.dumps(result, indent=2)+'\n')
temporary_manifest.replace(report_dir/'last_build.json')
print('Build completed in separate synthesis/PnR processes.', flush=True)
for artifact in result['artifacts']:
    print(artifact['path']+' sha256='+artifact['sha256'], flush=True)
