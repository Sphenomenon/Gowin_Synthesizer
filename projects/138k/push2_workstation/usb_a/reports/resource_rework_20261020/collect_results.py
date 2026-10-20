#!/usr/bin/env python3
"""Read immutable routed reports/netlists; compare disjoint physical RAM groups."""
from pathlib import Path
import argparse,json,re,sys,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from bsram_hierarchy_audit import audit,PRIM
GROUPS={
 'CNN feature cache':'u_music/u_basic_pitch/g_ddr_features.u_feature_ddr/',
 'Viterbi':'u_music/u_basic_pitch/g_full_dp.u_cnn_stream/u_viterbi/',
 'Recorder packets':'u_managed/u_audio/u_extensions/recorder/',
 'LED score cues':'u_managed/u_audio/u_extensions/score/',
 'Video scanout':'u_video/u_scanout/',
 'Reverb':'u_managed/u_audio/u_workstation/effects/reverb_stage/',
 'Chorus':'u_managed/u_audio/u_workstation/effects/chorus_stage/',
}
def collect(build):
 result=audit(build,1);stage=build/'Prj1'
 if not result['pnr_utilization']:raise ValueError('missing routed report: '+str(build))
 total=result['pnr_utilization']['used'];cells=[m[2].lstrip('\\') for m in PRIM.finditer((stage/'impl/pnr/Prj1.vo').read_text())]
 if len(cells)!=total:raise ValueError('physical netlist/report count mismatch')
 result['groups']={key:sum(c.startswith(prefix) for c in cells) for key,prefix in GROUPS.items()}
 result['groups']['Other retained RAM']=total-sum(result['groups'].values())
 lines=(stage/'impl/pnr/Prj1.rpt.txt').read_text().splitlines();res={}
 for line in lines:
  m=re.fullmatch(r'\s*(Logic|Register|CLS|BSRAM|DSP)\s*\|\s*([\d.]+)/([\d.]+)\s*\|\s*(\d+)%\s*',line)
  if m:res[m[1]]=dict(used=float(m[2]),capacity=float(m[3]))
 result['resources']=res
 result['evidence_sha256']={str(p.relative_to(build)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [stage/'impl/pnr/Prj1.rpt.txt',stage/'impl/pnr/Prj1.vo',stage/'impl/gwsynthesis/Prj1_syn_rsc.xml']}
 return result

def main():
 a=argparse.ArgumentParser();a.add_argument('--old',type=Path,default=ROOT/'results/timing_p27_uart_cdc_route1_20261018_142516_456857');a.add_argument('--new',type=Path,required=True);args=a.parse_args()
 old,new=collect(args.old),collect(args.new);old_bs=old['pnr_utilization']['used'];new_bs=new['pnr_utilization']['used']
 output=Path(__file__).resolve().parent
 d=dict(old=old,new=new,saved_physical_bsram=old_bs-new_bs,physical_reduction_percent=(old_bs-new_bs)/old_bs*100,remaining_physical_bsram=340-new_bs,hardware_tested=False)
 (output/'resource_comparison.json').write_text(json.dumps(d,indent=2)+'\n')
 lines=['## 最终资源核对','',f'比较基准：`{args.old.name}`。新候选：`{args.new.name}`。两者均使用完整工作站顶层。','',
 '| 同口径资源 | 旧 | 新 | 变化 |','|---|---:|---:|---:|',
 f"| SYN BSRAM | {old['synthesis']['syn_bsram']} | {new['synthesis']['syn_bsram']} | {new['synthesis']['syn_bsram']-old['synthesis']['syn_bsram']:+d} |",
 f'| PNR 物理 BSRAM / 340 | {old_bs} | {new_bs} | {new_bs-old_bs:+d} |',
 f'| 剩余物理 BSRAM | {340-old_bs} | {340-new_bs} | {old_bs-new_bs:+d} |']
 for key in ['Logic','Register','CLS','DSP']:
  if key in old['resources'] and key in new['resources']:
   x,y=old['resources'][key]['used'],new['resources'][key]['used'];lines.append(f'| PNR {key} | {x:g} | {y:g} | {y-x:+g} |')
 lines+=['',f'物理 BSRAM 净减少 **{old_bs-new_bs} 块（{d["physical_reduction_percent"]:.2f}%）**。下面按互不重叠的叶节点核对，既不重复累加父子层级，也不以综合网表数代替物理数。','',
 '| 物理 BSRAM 子系统 | 旧 | 新 | 变化 |','|---|---:|---:|---:|']
 for key in old['groups']:
  x,y=old['groups'][key],new['groups'][key];lines.append(f'| {key} | {x} | {y} | {y-x:+d} |')
 lines+=['','完整工具报告、物理网表和文件哈希见 [资源对照 JSON](resource_comparison.json)。所有本轮构建均未烧录；资源节省不等于时序闭合或板上验收。','']
 text='\n'.join(lines);(output/'resource_comparison.md').write_text(text);print(text)
if __name__=='__main__':main()
