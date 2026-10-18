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
    'impl', 'reports', 'builds', '__pycache__', '.git', '.venv',
    'build', 'archive', '.DS_Store', '*.vvp'))
stage_project = (stage_prj/relative_script).parent
result = {'started_at': datetime.datetime.now().astimezone().isoformat(),
          'script': str(relative_script), 'stage_directory': str(stage),
          'passed': False, 'phases': {}, 'artifacts': [],
          'sha256': {x.relative_to(prj).as_posix(): hashlib.sha256(x.read_bytes()).hexdigest()
                     for directory in ('rtl', 'constraints', 'config', 'tools')
                     for x in (prj/directory).rglob('*')
                     if x.is_file() and '__pycache__' not in x.parts}}

for name in ('sources.f', 'build.tcl', 'build.sh'):
    result['sha256'][name] = hashlib.sha256((prj/name).read_bytes()).hexdigest()

def save_result(name):
    (report_dir/name).write_text(json.dumps(result, indent=2)+'\n')

def fail(message, code=1):
    result['error'] = message
    save_result('build_'+run_id+'.json')
    save_result('last_failure.json')
    print(message, flush=True)
    print('Diagnostic files retained at '+str(stage), flush=True)
    raise SystemExit(code)

# Gowin resolves $readmemh relative to its synthesis work directory rather
# than the launching project. Only the ASCII staged copy gets an absolute ROM
# path; the checked-in RTL keeps its portable project-relative simulation path.
patch_relative = 'rtl/ble_board/rtl8723ds_patch.mem'
patch_path = stage_project/patch_relative
if not patch_path.is_file() or len(patch_path.read_text().splitlines()) != 32768:
    fail('BLE ROM image is missing or has the wrong depth.')
firmware_manifest = json.loads((stage_project/'rtl/ble_board/firmware_manifest.json').read_text())
rom_bytes = bytes(int(value, 16) for value in patch_path.read_text().split())
if (hashlib.sha256(rom_bytes).hexdigest() != firmware_manifest['image_sha256'] or
        hashlib.sha256(rom_bytes[:firmware_manifest['payload_bytes']]).hexdigest() != firmware_manifest['payload_sha256']):
    fail('BLE firmware ROM content does not match the checked-in vendor manifest.')
link_source = stage_project/'rtl/ble_board/midi_ble_link.v' 
link_text = link_source.read_text()
needle = 'PATCH_FILE="'+patch_relative+'"'
if link_text.count(needle) != 1:
    fail('Expected exactly one portable BLE patch parameter in link source.')
link_source.write_text(link_text.replace(needle, 'PATCH_FILE="'+str(patch_path)+'"'))
result['staging_transform'] = {'file': 'rtl/ble_board/midi_ble_link.v',
    'parameter': 'PATCH_FILE', 'absolute_ascii_path': str(patch_path),
    'rom_sha256': hashlib.sha256(patch_path.read_bytes()).hexdigest()}
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
                               'log': saved_log.relative_to(prj).as_posix()}
    if process.returncode or re.search(r'(^|\n)(?:ERROR\s*\(|Error:)', output_text):
        print('\n'.join(output_text.splitlines()[-12:]), flush=True)
        fail(phase+' failed; existing successful artifacts were preserved.',
             128-process.returncode if process.returncode < 0 else (process.returncode or 1))
    if phase == 'syn' and re.search(r'Cannot open file|failed to (?:open|read)|EX3988', output_text, re.I):
        fail('Synthesis failed to load an input/ROM; refusing to publish artifacts.')
    if phase == 'syn':
        from xml.etree import ElementTree
        resources = list((stage_project/'impl/gwsynthesis').glob('*_syn_rsc.xml'))
        if len(resources) != 1:
            fail('Synthesis resource report is missing.')
        resource_tree = ElementTree.parse(resources[0])
        initializer = [node for node in resource_tree.iter('SubModule') if node.get('name') == 'initializer']
        if len(initializer) != 1 or int(initializer[0].get('Bsram', '0')) < 16:
            fail('BLE firmware ROM did not map to its required 16 block RAMs.')
        result['synthesis_resources'] = resource_tree.getroot().attrib
    if phase == 'pnr' and 'GowinSynthesis start' in output_text:
        fail('PnR unexpectedly repeated synthesis; refusing to publish artifacts.')
    if phase == 'pnr' and 'Skip synthesis, because there is only one netlist file' not in output_text:
        fail('PnR did not confirm the netlist-only flow; refusing to publish artifacts.')
    completion = 'GowinSynthesis finish' if phase == 'syn' else 'Bitstream generation completed'
    if completion not in output_text:
        fail(phase+' did not report completion; refusing to publish artifacts.')

impl = stage_project/'impl'
# Bitstream generation alone is not timing closure. Require every reported
# setup/hold endpoint and each analysis type to pass before publication.
timing_files = list((impl/'pnr').glob('*.tr'))
if len(timing_files) != 1:
    fail('Expected one complete text timing report.')
timing_text = timing_files[0].read_text(errors='replace')
timing = {}
for kind in ('Setup', 'Hold'):
    match = re.search(r'<Numbers of '+kind+r' Violated Endpoints>:(\d+)', timing_text)
    if not match:
        fail('Timing report lacks '+kind+' violation count.')
    timing[kind.lower()+'_violated_endpoints'] = int(match.group(1))
for kind in ('Setup', 'Hold', 'Recovery', 'Removal'):
    match = re.search(r'^3\.1\.\d '+kind+r' Paths Table(.*?)(?=\n3\.)', timing_text, re.S | re.M)
    values = re.findall(r'^\s*\d+\s+(-?\d+\.\d+)\s+', match.group(1), re.M) if match else []
    if not values:
        fail('Timing report lacks '+kind+' slack table.')
    timing[kind.lower()+'_worst_slack_ns'] = min(map(float, values))
frequency = re.search(r'^2\.3 Max Frequency Summary(.*?)(?=\n2\.4)', timing_text, re.S | re.M)
timing['clocks'] = [{'name': name, 'constraint_mhz': float(target), 'actual_fmax_mhz': float(actual)}
    for name, target, actual in re.findall(r'^\s*\d+\s+(\S+)\s+([\d.]+)\(MHz\)\s+([\d.]+)\(MHz\)', frequency.group(1) if frequency else '', re.M)]
timing['passed'] = (timing['setup_violated_endpoints'] == 0 and timing['hold_violated_endpoints'] == 0
    and all(timing[k+'_worst_slack_ns'] >= 0 for k in ('setup','hold','recovery','removal'))
    and {clock['name'] for clock in timing['clocks']} == {'clk_50mhz','clk_ulpi60'})
result['timing'] = timing
if not timing['passed']:
    fail('Timing did not close; generated files remain diagnostic and were not published.')
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
    result['gao'] = [{'definition': str(p),
                      'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                     for p in gao_files]

# Publish each successful run separately. The original impl and previous good
# builds stay intact; later downloads use the manifest path and SHA256.
published_impl = script.parent/'builds'/run_id/'impl'
shutil.copytree(impl, published_impl)
for path in bitstreams:
    published = published_impl/path.relative_to(impl)
    result['artifacts'].append({'path': published.relative_to(prj).as_posix(),
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
changed_inputs = [name for name, digest in result['sha256'].items()
                  if not (prj/name).is_file() or hashlib.sha256((prj/name).read_bytes()).hexdigest() != digest]
if changed_inputs:
    fail('Inputs changed during build: '+', '.join(changed_inputs))
result['passed'] = True
result['finished_at'] = datetime.datetime.now().astimezone().isoformat()
save_result('build_'+run_id+'.json')
temporary_manifest = report_dir/'.last_build.json.tmp'
temporary_manifest.write_text(json.dumps(result, indent=2)+'\n')
temporary_manifest.replace(report_dir/'last_build.json')
print('Build completed in separate synthesis/PnR processes.', flush=True)
for artifact in result['artifacts']:
    print(artifact['path']+' sha256='+artifact['sha256'], flush=True)
