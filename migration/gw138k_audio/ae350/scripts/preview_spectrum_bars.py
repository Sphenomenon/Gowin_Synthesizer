#!/usr/bin/env python3
"""Validate a frozen --with-ui build; write a new timestamped evidence directory.
Usage: preview_spectrum_bars.py /absolute/build/directory
"""
import sys
from pathlib import Path
import datetime,json,hashlib,subprocess
root=Path(__file__).resolve().parents[4];r=root/'migration/gw138k_audio';build=Path(sys.argv[1]).resolve();stage=build/'Prj1';out=r/'results'/datetime.datetime.now().strftime('bar_preview_%Y%m%d_%H%M%S_%f');out.mkdir();print(out,flush=True)
tb=(root/'Mega_138K/Dev/Prj1/sim/tb_analysis_renderer.sv').read_text().replace('$ln(419.0)','$ln(427.0)')
tb=tb.replace('    integer bin_map', '''    integer image_file,anchor[0:511],lo,hi,point,span_h,diff_l,diff_r;
    initial begin image_file=$fopen("analysis.ppm","wb");$fwrite(image_file,"P6\\n1920 1080\\n255\\n");end
    integer bin_map''')
tb=tb.replace('                if(x>=64', '                $fwrite(image_file,"%c%c%c",actual_color[23:16],actual_color[15:8],actual_color[7:0]);\n                if(x>=64',1).replace('stalls);$finish;', 'stalls);$fclose(image_file);$finish;')
start=tb.index('        // Independently cover');end=tb.index('        @(negedge clk);start=1;',start)
tb=tb[:start]+'''        // Independent closed-form model, not the DUT incremental algorithm.
        for(n=0;n<512;n=n+1) begin anchor[n]=0;expected_left[n]=0;expected_right[n]=0;end
        for(scan_bin=2;scan_bin<=853;scan_bin=scan_bin+1) begin
            point=$rtoi(511*$ln(1.0*scan_bin/2)/$ln(853.0/2)+0.5);anchor[point]=1;
            if(dut.g_analysis.u_analysis.levels_left[scan_bin]>expected_left[point]) expected_left[point]=dut.g_analysis.u_analysis.levels_left[scan_bin];
            if(dut.g_analysis.u_analysis.levels_right[scan_bin]>expected_right[point]) expected_right[point]=dut.g_analysis.u_analysis.levels_right[scan_bin];
        end
''' +tb[end:]
tb=tb.replace('n<1024','n<2048').replace('*16*n/1024','*32*n/2048').replace('*37*n/1024','*74*n/2048')
tb=tb.replace('if(hl!=0 &&','if(x%2==0 && hl!=0 &&').replace('if(hr!=0 &&','if(x%2==0 && hr!=0 &&')
tb=tb.replace('integer image_file,', 'integer expected_wave[0:511],wave_gain_model,wh,wp,wave_pixels=0;\n    integer image_file,')
tb=tb.replace('        @(negedge clk);start=1;', """        wave_gain_model=0;
        if(dut.snapshot_peak!=0)while(wave_gain_model<6 && {1'b0,dut.snapshot_peak}*(33'd1<<wave_gain_model)<33'h040000000)wave_gain_model=wave_gain_model+1;
        for(n=0;n<512;n=n+1)begin
            wh=$signed(dut.u_align.trace_samples[n]) >>> (24-wave_gain_model);
            expected_wave[n]=wh>127 ? 127 : wh< -127 ? -127 : wh;
        end
        @(negedge clk);start=1;""")
tb=tb.replace('                if(x>=1248', """                if(x>=64 && x<1088 && y>=208 && y<464)begin
                    column=(x-64)/2;wh=expected_wave[column];wp=expected_wave[column==0?0:column-1];
                    expected_color=32'h000b1420;
                    if(x%128==64 || y%64==16)expected_color=32'h001c3145;
                    if(y==336)expected_color=32'h0031506c;
                    if((y>=335-wh && y<=337-wp)||(y>=335-wp && y<=337-wh))expected_color=32'h003cdbab;
                    if(actual_color!==expected_color)$fatal(1,"wave raster mismatch x=%0d y=%0d got=%h expected=%h",x,y,actual_color,expected_color);
                    wave_pixels=wave_pixels+1;
                end
                if(x>=1248""",1)
tb=tb.replace('beats!=1036800 ||', 'wave_pixels!=262144 || beats!=1036800 ||')
test=out/'tb_analysis_renderer.sv';test.write_text(tb)
sources=list((stage/'src/video').glob('*.v'))+[test];hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources};(out/'inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
for name,cmd in [('compile',['verilator','--binary','--timing','-j','4','-Wno-fatal','--top-module','tb_analysis_renderer','--Mdir',str(out/'obj'),*map(str,sources)]),('simulation',[str(out/'obj/Vtb_analysis_renderer')])]:
 with (out/(name+'.log')).open('w') as f:p=subprocess.run(cmd,cwd=out,stdout=f,stderr=subprocess.STDOUT)
 print(name,p.returncode,flush=True)
 if p.returncode:raise SystemExit(p.returncode)
from PIL import Image
from array import array
pixels=array('H');pixels.frombytes((r/'results/ae350_ui_sim_20260910_144403_422221/ui.rgb565').read_bytes());im=Image.new('RGB',(1920,1080));im.putdata([((v>>11)*255//31,((v>>5)&63)*255//63,(v&31)*255//31)for v in pixels]);analysis=Image.open(out/'analysis.ppm');im.paste(analysis.crop((0,160,1920,832)),(0,160));im.save(out/'performance_preview.png')
old=Image.open(r/'results/waveform_preview_20260910_150003_419060/performance_preview.png');comparison=Image.new('RGB',(1024,520));comparison.paste(old.crop((64,536,1088,796)),(0,0));comparison.paste(im.crop((64,536,1088,796)),(0,260));comparison.save(out/'spectrum_before_after.png')
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
(out/'verification.json').write_text(json.dumps(dict(passed=True,inputs_unchanged=True,build=str(build),hardware_screenshot=False,scope='Actual staged analysis RTL, independent per-bin logarithmic peak pooling with 1 pixel bars and 1 pixel gaps, full raster with stalls; Scaled waveform pixels checked independently; CPU raster updated for SNAP DONE.'),indent=2)+'\n')
