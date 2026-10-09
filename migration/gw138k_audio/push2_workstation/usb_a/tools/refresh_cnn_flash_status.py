#!/usr/bin/env python3
"""Refresh recorded candidate outcomes from actual build/gate files, never touches LATEST or hardware."""
from datetime import datetime
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'reports/CNN_FLASH_BOOT_RELEASE_COMPARISON.json'
report=json.loads(path.read_text())
for row in report['rows']:
    build=ROOT/row['build']
    tool=build/'tool_result.json'
    acceptance=build/'automatic_acceptance/result.json'
    if acceptance.exists():
        gate=json.loads(acceptance.read_text())
        if gate.get('finished_at'):
            row.update(status='hardware_verified' if gate.get('hardware_tested') else ('local_gate_passed' if gate['passed'] else 'routed_rejected'),
                release_gate_passed=gate['passed'],programming_started=gate['programming_started'],
                checks=gate['checks'],error=gate.get('error'))
            # Preserve explicitly recorded historical temporary AD diagnosis.
            if gate.get('hardware_tested'):row['hardware_auto_boot_verified']=True
            summary=gate.get('previous_positive_clock_audit',{}).get('candidate_clocks',{})
            if 'clk_50m' in summary:row['clk50_fmax_mhz']=summary['clk_50m'][1]
            if 'video_pixel148' in summary:row['video_fmax_mhz']=summary['video_pixel148'][1]
            pll=build/'automatic_acceptance/video_pll.json'
            if pll.exists():
                evidence=json.loads(pll.read_text())
                row['PLL_all_endpoints_passed']=evidence.get('passed',not evidence.get('errors'))
            ddr=build/'automatic_acceptance/ddr_ui_timing.json'
            if ddr.exists():
                evidence=json.loads(ddr.read_text())
                for kind in ('setup','hold'):row[f'ddr_ui_{kind}_wns_ns']=evidence['checks'][kind]['wns_ns']
    elif tool.exists():
        evidence=json.loads(tool.read_text());row['status']='routed_waiting_gate' if evidence['exit_code']==0 and evidence['inputs_unchanged'] else 'build_failed'
    else:
        log=build/'gowin_all.log'
        if log.exists():
            text=log.read_text();row['status']='routing' if 'Running routing' in text else 'placement' if 'Running placement' in text else 'synthesizing'
    memory=build/'workstation_memory.json'
    if memory.exists():
        evidence=json.loads(memory.read_text());row['synthesis_bsram']=evidence['bsram']
        if evidence.get('pnr_available'):row['physical_bsram']=evidence['pnr_bsram']
report['generated_at']=datetime.now().astimezone().isoformat()
path.write_text(json.dumps(report,indent=2)+'\n')
current=ROOT/'reports/CNN_FLASH_BOOT_CURRENT.md'
text=current.read_text()
start=text.index('| 候选 |')
end=text.index('\n\n',start)
lines=['| 候选 | 实际状态 | clk50 MHz | 视频 MHz | DDR UI setup ns | 物理BSRAM | 写板 |',
       '|---|---|---:|---:|---:|---:|---|']
for row in report['rows']:
    if row['user_code'] not in ['B3','B4','B5','B6','B7','B8','B9','BA','BB','BC','BD','BE']:continue
    values=[str(row.get(key,'待报告')) for key in ['clk50_fmax_mhz','video_fmax_mhz','ddr_ui_setup_wns_ns','physical_bsram']]
    hardware='已验收' if row.get('hardware_auto_boot_verified') else ('已尝试，见回滚证据' if row.get('programming_started') else '未烧录')
    lines.append('| '+ ' | '.join([row['user_code'],row['status'],*values,hardware])+' |')
text=text[:start]+'\n'.join(lines)+text[end:]
marker='状态表从实际构建和验收工件生成：'
if marker in text:
    beginning=text.index(marker); ending=text.index('\n',beginning)
    text=text[:beginning]+marker+report['generated_at']+'。'+text[ending:]
else:
    text=text.replace('\n\n## 已完成的验证','\n\n'+marker+report['generated_at']+'。\n\n## 已完成的验证')
current.write_text(text)
print('Updated actual local candidate statuses and current table; no hardware/LATEST operations')
