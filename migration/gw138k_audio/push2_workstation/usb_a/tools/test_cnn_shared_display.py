#!/usr/bin/env python3
"""Exercise actual shared snapshot writer/cache and full raster against frozen pixels."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/song_guide_full85_clk50_20261007_084539_884006_route1/Prj1'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--output',type=Path)
p.add_argument('--quiet-shared-analysis',action='store_true')
a=p.parse_args();build=a.build.resolve();stage=build/'Prj1'
metadata=json.loads((build/'build_metadata.json').read_text())
assert metadata.get('full_workstation') and metadata.get('predecoded_dashboard')
from build_workstation_flash_boot import audit_serial_compatibility
audit_serial_compatibility(build)
source_names=['src/memory/display_data_layout_pkg.sv',
    'src/video/feedback_renderer.v','src/video/feedback_dashboard.v',
    'src/video/feedback_capture.v','src/video/feedback_wave_align.v',
    'src/video/video_font_5x7.v','src/video/output_audio_analysis.v',
    'src/video/output_audio_capture.v','src/video/audio_analysis_rom.v',
    'src/memory/display_data_writer.v','src/memory/display_data_reader.v']
for name in source_names:
    if name not in ['src/video/feedback_renderer.v','src/video/feedback_dashboard.v']:
        assert (stage/name).read_bytes()==(BASE/name).read_bytes(),'frozen source drift '+name
fixture=(ROOT/'sim/p11/tb_shared_display.sv').read_text()
anchor='p10_feedback_renderer #(.ENABLE_ANALYSIS(1)) reference('
assert fixture.count(anchor)==1
fixture=fixture.replace(anchor,'renderer_original #(.ENABLE_ANALYSIS(1)) reference(',1)
# Valid but deliberately irregular front-RAM contents expose every address;
# preserve actual FFT publication/bank ownership and the writer/cache protocol.
fixture_anchor='        @(negedge clk);start=1;ref_start=1;'
assert fixture.count(fixture_anchor)==1
fixture=fixture.replace(fixture_anchor,"""        @(negedge clk);
        for(i=0;i<1024;i=i+1)begin
            render.g_analysis.u_analysis.display_left[i]=(i*73+19)&255;
            render.g_analysis.u_analysis.display_right[i]=(i*29+167)&255;
            reference.g_analysis.u_analysis.display_left[i]=(i*73+19)&255;
            reference.g_analysis.u_analysis.display_right[i]=(i*29+167)&255;
        end
        for(i=0;i<131072;i=i+1)begin
            render.g_analysis.u_analysis.image_pixels[i]=^32'(i*7919+313);
            reference.g_analysis.u_analysis.image_pixels[i]=^32'(i*7919+313);
        end
        start=1;ref_start=1;""",1)

with tempfile.TemporaryDirectory(prefix='cnn_shared_display_') as tmp:
    folder=Path(tmp);tb=folder/'tb.sv';tb.write_text(fixture)
    old_renderer=folder/'original_renderer.v';old_renderer.write_text((BASE/'src/video/feedback_renderer.v').read_text().replace('module feedback_renderer #','module renderer_original #').replace('feedback_dashboard #','dashboard_original #'))
    old_dashboard=folder/'original_dashboard.v';old_dashboard.write_text((BASE/'src/video/feedback_dashboard.v').read_text().replace('module feedback_dashboard #','module dashboard_original #'))
    sources=[stage/name for name in source_names]+[old_renderer,old_dashboard,tb]
    tested_renderer=stage/'src/video/feedback_renderer.v'
    if a.quiet_shared_analysis:
        from cnn_ddr_pipeline_patch import quiet_shared_analysis_column
        tested_renderer=folder/'quiet_renderer.v'
        tested_renderer.write_text(quiet_shared_analysis_column((stage/'src/video/feedback_renderer.v').read_text()))
        sources=[tested_renderer if source==stage/'src/video/feedback_renderer.v' else source for source in sources]
    renderer_sha256=hashlib.sha256(tested_renderer.read_bytes()).hexdigest()
    command=['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_shared_display',
        '-I'+str(stage),'--Mdir',str(folder/'obj'),*map(str,sources)]
    compile=subprocess.run(command,cwd=stage,capture_output=True,text=True,timeout=180)
    assert compile.returncode==0,compile.stdout[-6000:]+compile.stderr[-6000:]
    run=subprocess.run([str(folder/'obj/Vtb_shared_display')],cwd=stage,capture_output=True,text=True,timeout=300)
    assert run.returncode==0 and 'PASS shared DDR HDMI source:' in run.stdout and 'PASS startup invalid analysis:' in run.stdout,run.stdout+run.stderr
report=dict(passed=True,source_bound=not a.quiet_shared_analysis,quiet_shared_analysis=a.quiet_shared_analysis,tested_renderer_sha256=renderer_sha256,build=str(build),hardware_tested=False,pcm_saved=False,
    front_ram_address_poisoned=True,scope='actual FFT/XY bank ownership with nonuniform front arrays -> DDR publication -> coherent cache reload -> complete raster against frozen original; 3frames + cold invalid-analysis reset',
    fixture_sha256=hashlib.sha256(fixture.encode()).hexdigest(),
    source_sha256={name:hashlib.sha256((stage/name).read_bytes()).hexdigest() for name in source_names},
    log=run.stdout.strip())
if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
