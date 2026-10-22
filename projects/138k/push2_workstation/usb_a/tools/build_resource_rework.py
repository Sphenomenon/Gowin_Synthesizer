#!/usr/bin/env python3
"""Explicit candidate: 4-Hz guidance, frequency tiles, SDP buffers and spatial FDN.

Uses the current complete-workstation prepare flow, preserves its immutable
accepted baseline, then records an explicit live-CNN source manifest. Never
programs hardware or changes LATEST_WORKSTATION.json.
"""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,os,re,shutil,subprocess,sys
import xml.etree.ElementTree as ET
from workstation_baselines import load_baseline
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(timing_fixes=False,output_directory=None):
    if output_directory is not None and not timing_fixes:
        raise ValueError('explicit output requires the native resource-timing prepare policy')
    if timing_fixes:
        # A new timing candidate branches from the immutable, fully routed
        # 234-block source. Do not weaken the accepted builder's input guard.
        reference=load_baseline(ROOT,'resource_rework_route0')
        output=Path(output_directory).resolve() if output_directory is not None else ROOT/'results'/datetime.now().strftime('resource_timing_%Y%m%d_%H%M%S_%f')
        output.mkdir()
        stage=output/'Prj1'
        reference.materialize(stage)
        reference.copy_metadata(output)
    else:
        p=subprocess.run([sys.executable,str(ROOT/'tools/build_current_workstation.py'),
                          '--prepare-only','--cnn-timing85'],cwd=ROOT,text=True,capture_output=True)
        if p.returncode:raise RuntimeError(p.stdout+p.stderr)
        paths=[Path(l) for l in p.stdout.splitlines() if l.startswith(str(ROOT/'results'))]
        if not paths:raise RuntimeError('prepare output omitted staging path: '+p.stdout)
        output=paths[0];stage=output/'Prj1'
    overlays={
      'rtl/display_data/video_ddr_scanout.v':'src/video/video_ddr_scanout.v',
      'rtl/audio/audio_capture_fifo.sv':'legacy/rtl/audio/audio_capture_fifo.sv',
      'rtl/input/score_led_player.sv':'legacy/rtl/input/score_led_player.sv',
      'rtl/audio/stereo_effects.sv':'legacy/rtl/audio/stereo_effects.sv',
      'rtl/audio/serial_spatial_reverb.sv':'rtl/audio/serial_spatial_reverb.sv',
      'rtl/audio/spatial_room_preset.svh':'rtl/audio/spatial_room_preset.svh',
      'rtl/memory/workstation_sdp.sv':'rtl/memory/workstation_sdp.sv',
      'rtl/memory/workstation_sdp_banked.sv':'rtl/memory/workstation_sdp_banked.sv',
    }
    if timing_fixes:
        overlays['rtl/resource_timing/delay_ddr_dma.sv']='rtl/audio/delay_ddr/delay_ddr_dma.sv'
        overlays['rtl/audio/scope_vec/scope_vec_engine.sv']='rtl/audio/scope_vec/scope_vec_engine.sv'
        overlays['rtl/display_data/push2_surface_pixels.sv']='src/push2/push2_surface_pixels.sv'
    # This is a new, explicit CNN candidate. Never silently overlay live CNN
    # sources in the accepted full83/current-workstation builder.
    for f in sorted((ROOT/'rtl/music').rglob('*')):
        if f.is_file():overlays[f.relative_to(ROOT).as_posix()]=f.relative_to(ROOT).as_posix()
    for src,dst in overlays.items():
        (stage/dst).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/src,stage/dst)
    link=stage/'rtl/music/basic_pitch_workstation_link.sv'
    s=link.read_text();old='.WIN_LEN(43844),.FRAME_LIMIT(172),.OCTAVE_LIMIT(9),'
    if s.count(old)!=1:raise ValueError('analysis configuration anchor drift')
    from workstation_cnn_cdc import transform as synchronize_diagnostics
    link.write_text(synchronize_diagnostics(s.replace(old,'.WIN_LEN(44100),.FRAME_LIMIT(8),.OCTAVE_LIMIT(9),\n'
        '        .CQT_HOP_NUMERATOR(22050),.CQT_HOP_DENOMINATOR(4),\n'
        '        .FEATURE_TILE_COLS(16),.COARSE_GUIDANCE(1\'b1),')))
    timing_evidence={}
    if timing_fixes:
        from workstation_resource_timing import apply
        timing_evidence=apply(stage,native_composition=True)
        from workstation_composition import install,verify
        composition=install(stage)
        verify(stage,composition)
    tree=ET.parse(stage/'Prj1.gprj');files=tree.find('FileList');names={f.get('path') for f in files}
    included=set(re.findall(r'`include\s+"([^"]+)"',(stage/'legacy_audio.sv').read_text()))
    standalone_excluded={'rtl/music/basic_pitch_tf_board_top.sv',
        'rtl/music/basic_pitch_ddr_arbiter_pipeline.sv','rtl/music/basic_pitch_ddr_client_queues.sv'}
    for name in sorted(set(overlays.values())):
        if name in included or name in standalone_excluded:continue
        if Path(name).suffix in ('.sv','.v') and name not in names:
            ET.SubElement(files,'File',path=name,type='file.verilog',enable='1');names.add(name)
    tree.write(stage/'Prj1.gprj',encoding='UTF-8',xml_declaration=True)
    meta=json.loads((output/'build_metadata.json').read_text())
    if timing_fixes:meta['source_baselines']=[reference.evidence()]
    if timing_fixes:
        meta['composition']=composition
        (output/'workstation_composition.json').write_text(json.dumps(composition,indent=2)+'\n')
    meta.update(candidate='resource_rework_4hz_tiles_spatial',cnn_source_policy='explicit_live_candidate',
        analysis=dict(audio_rate_hz=22050,judgments_per_second=4,window_samples=44100,frames=8,
                      frequency_tile_columns=16,loaded_columns_with_halo=20),
        usb_cpu_ram_kib=64,hardware_tested=False,timing_fixes=timing_fixes,timing_structure=timing_evidence)
    meta['accepted_music_sha256']=meta['music_sha256']
    meta['music_sha256']={name:sha(stage/name) for name in overlays.values() if name.startswith('rtl/music/')}
    prepared_audit=output/'cnn_source_audit.json'
    shutil.copy2(prepared_audit,output/'prepared_cnn_source_audit.json')
    prepared_audit.write_text(json.dumps(dict(policy='explicit_live_candidate',
        ancestry='prepared_cnn_source_audit.json',sources=meta['music_sha256'],
        transforms=['8 frames per 2 seconds; 16 frequency columns per tile',
                    'retain seven diagnostic DDR level receivers']),indent=2)+'\n')
    meta['cnn_source_audit_sha256']=sha(prepared_audit)
    (output/'resource_rework_overlays.json').write_text(json.dumps({src:dict(destination=dst,sha256=sha(stage/dst)) for src,dst in overlays.items()},indent=2)+'\n')
    return output,stage,meta

def audit_outputs(output,flow,exit_code,drift,tool_ok):
    """Resource success and release readiness are separate, explicit results."""
    sys.path.insert(0,str(ROOT/'tools'))
    from workstation_memory import audit as memory_audit
    common=dict(exit_code=exit_code,inputs_unchanged=not drift,changed=drift,
                build_mode='full' if flow in ('pnr','all') else 'synthesis_only',
                hardware_tested=False,tool_flow_passed=tool_ok)
    (output/'tool_result.json').write_text(json.dumps(common,indent=2)+'\n')
    if not tool_ok:return
    memory=memory_audit(output,common['build_mode'])
    required=['u_managed/u_audio/u_workstation/effects/'+n for n in
              ('delay_stage','chorus_stage','reverb_stage')]
    required+=['u_managed/u_audio/u_extensions/'+n for n in ('recorder','score')]
    missing=[n for n in required if n not in memory['hierarchy']]
    if missing:raise ValueError('feature removed: '+repr(missing))
    print('Full workstation BSRAM: SYN',memory['bsram'],'PNR',memory['pnr_bsram'],flush=True)
    if flow not in ('pnr','all'):return
    from audit_workstation_timing import audit as timing_audit
    from audit_workstation_cdc import audit as cdc_audit
    timing=timing_audit(output)
    (output/'workstation_timing.json').write_text(json.dumps(timing,indent=2)+'\n')
    cdc=cdc_audit(output)
    (output/'workstation_cdc.json').write_text(json.dumps(cdc,indent=2)+'\n')
    sys.path.insert(0,str(output/'Prj1/scripts'))
    from check_video_pll_init import inspect_video_pll_init
    stage=output/'Prj1'
    errors,evidence=inspect_video_pll_init((stage/'impl/pnr/Prj1.sdf').read_text(),
                                          (stage/'impl/pnr/Prj1.vo').read_text(),stage)
    (output/'pll_init_audit.json').write_text(json.dumps(dict(errors=errors,evidence=evidence),indent=2)+'\n')
    ready=timing['timing_closed'] and cdc['passed'] and not errors
    (output/'resource_readiness.json').write_text(json.dumps(dict(
        tool_flow_passed=True,timing_closed=timing['timing_closed'],cdc_passed=cdc['passed'],
        pll_init_passed=not errors,release_ready=ready,hardware_tested=False),indent=2)+'\n')
    print('Routed timing_closed:',timing['timing_closed'],'CDC:',cdc['passed'],
          'PLL:',not errors,'release_ready:',ready,flush=True)
    return ready

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--flow',choices=['prepare','syn','pnr','all'],default='prepare')
    a.add_argument('--timing-fixes',action='store_true',help='Measured structural setup fixes; clocks and CDC requirements unchanged')
    a.add_argument('--stage',type=Path,help='Reuse a previously prepared candidate')
    a.add_argument('--route-option',type=int,choices=(0,1),default=1,help='Gowin general or effort routing; clocks unchanged')
    a.add_argument('--replicate-resources',action='store_true',help='Explicit timing-driven high-fanout resource replication; clocks unchanged')
    a.add_argument('--place-option',type=int,choices=range(5),help='Explicit Arora V placement algorithm; preserves clocks and constraints')
    a.add_argument('--max-fanout',type=int,help='Explicit synthesis fanout limit (1..10000), not PNR resource replication')
    a.add_argument('--user-code',help='Required new eight-hex identity for PNR/all; not a release pointer')
    args=a.parse_args()
    if args.max_fanout is not None and not 1<=args.max_fanout<=10000:
        a.error('--max-fanout must be between 1 and 10000')
    if args.flow in ('pnr','all') and args.user_code is None:
        a.error('--user-code is required for a new PNR/all candidate')
    if args.user_code is not None and not re.fullmatch(r'[0-9A-Fa-f]{8}',args.user_code):
        a.error('eight hex digits required for --user-code')
    if args.stage:
        output=args.stage.resolve();stage=output/'Prj1';meta=json.loads((output/'build_metadata.json').read_text())
        if meta.get('candidate')!='resource_rework_4hz_tiles_spatial':raise ValueError('not a resource-rework stage')
        expected=json.loads((output/'workstation_inputs.json').read_text())
        bad=[n for n,h in expected.items() if not (stage/n).exists() or sha(stage/n)!=h]
        if bad:raise ValueError('candidate inputs drifted: '+repr(bad))
    else:output,stage,meta=prepare(args.timing_fixes)
    if meta.get('composition'):
        from workstation_composition import verify
        verify(stage,meta['composition'])
    tcl=stage/'scripts/build.tcl';s=tcl.read_text();s=re.sub(r'^set_option -user_code .*\n','',s,flags=re.M)
    if args.flow in ('pnr','all'):
        anchor='open_project [file join $root Prj1.gprj]\n'
        if s.count(anchor)!=1:raise ValueError('project open anchor drift')
        s=s.replace(anchor,anchor+'set_option -user_code '+args.user_code+'\n')
    s,n=re.subn(r'^set_option -route_option [01]$', 'set_option -route_option '+str(args.route_option),s,flags=re.M)
    if n!=1:raise ValueError('routing option anchor drift')
    s=re.sub(r'^set_option -replicate_resources [01]\n','',s,flags=re.M)
    route_anchor='set_option -route_option '+str(args.route_option)+'\n'
    if args.replicate_resources:s=s.replace(route_anchor,route_anchor+'set_option -replicate_resources 1\n',1)
    placement=re.findall(r'^set_option -place_option ([0-4])$',s,flags=re.M)
    if args.place_option is not None:
        if len(placement)!=1:raise ValueError('placement option anchor drift')
        s=re.sub(r'^set_option -place_option [0-4]$', 'set_option -place_option '+str(args.place_option),s,flags=re.M)
    selected_placement=args.place_option if args.place_option is not None else int(placement[0]) if len(placement)==1 else None
    s=re.sub(r'^set_option -max_fanout \d+\n','',s,flags=re.M)
    if args.max_fanout is not None:s=s.replace(route_anchor,route_anchor+'set_option -max_fanout '+str(args.max_fanout)+'\n',1)
    tcl.write_text(s)
    meta.update(route_option=args.route_option,place_option=selected_placement,synthesis_max_fanout=args.max_fanout,replicate_resources=args.replicate_resources,build_mode=args.flow,user_code='0x'+args.user_code if args.flow in ('pnr','all') else None,hardware_tested=False)
    (output/'build_metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    inputs={p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file() and 'impl' not in p.relative_to(stage).parts}
    (output/'workstation_inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    # Validate the actual source consumed by tools, independently of metadata.
    link_text=(stage/'rtl/music/basic_pitch_workstation_link.sv').read_text()
    tokens=['.WIN_LEN(44100),.FRAME_LIMIT(8),.OCTAVE_LIMIT(9),',
            '.CQT_HOP_NUMERATOR(22050),.CQT_HOP_DENOMINATOR(4),',
            ".FEATURE_TILE_COLS(16),.COARSE_GUIDANCE(1'b1),",'u_trace_cdc']
    missing=[x for x in tokens if x not in link_text]
    if missing:raise ValueError('actual candidate configuration drift: '+repr(missing))
    print(output,flush=True)
    if args.flow=='prepare':return
    with (output/('resource_'+args.flow+'.log')).open('w') as log:
        p=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,
             env=dict(os.environ,PRJ1_FLOW=args.flow),stdout=log,stderr=subprocess.STDOUT)
    drift=[n for n,h in inputs.items() if sha(stage/n)!=h]
    log=(output/('resource_'+args.flow+'.log')).read_text(errors='replace')
    ok=p.returncode==0 and not drift and not re.search(r'^ERROR\s*\(',log,re.M)
    (output/('resource_'+args.flow+'_result.json')).write_text(json.dumps(dict(passed=ok,exit_code=p.returncode,
              input_drift=drift,hardware_tested=False),indent=2)+'\n')
    ready=audit_outputs(output,args.flow,p.returncode,drift,ok)
    print('Tool flow PASS' if ok else 'Tool flow FAIL',args.flow,flush=True)
    if not ok:raise SystemExit(1)
    if args.flow in ('pnr','all') and not ready:
        print('Offline timing/CDC/PLL gates FAIL; candidate must not be deployed',flush=True)
        raise SystemExit(2)
if __name__=='__main__':main()
