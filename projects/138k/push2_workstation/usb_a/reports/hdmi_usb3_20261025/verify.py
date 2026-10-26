"""Verify the isolated HDMI candidate without rebuilding or programming it."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import runpy
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def digest(source):
    return hashlib.sha256(Path(source).read_bytes()).hexdigest()


def load_checker(stage,metadata,relative,adaptations):
    source=stage/relative
    if digest(source)!=metadata['staged_input_sha256'][relative]:
        raise ValueError('cached checker changed: '+relative)
    text=source.read_text()
    for original,replacement in adaptations:
        if text.count(original)!=1:
            raise ValueError('checker adaptation anchor changed: '+original)
        text=text.replace(original,replacement)
    namespace=dict(__file__=str(source),__name__='isolated_hdmi_audit')
    exec(compile(text,str(source)+':isolated-hdmi-adaptation','exec'),namespace)
    return namespace,dict(source_sha256=digest(source),exact_adaptations=adaptations,
                          adapted_sha256=hashlib.sha256(text.encode()).hexdigest())


def verify(candidate):
    if not __debug__:
        raise ValueError('normal Python execution is required by the routed audit')
    candidate=Path(candidate).resolve()
    prepare=runpy.run_path(str(Path(__file__).with_name('prepare.py')))
    parent=ROOT/prepare['PARENT']
    if digest(parent/'integration_inputs.json')!=prepare['MANIFEST_SHA']:
        raise ValueError('reference source manifest changed')
    metadata=json.loads((parent/'integration_inputs.json').read_text())
    inputs=json.loads((candidate/'inputs.json').read_text())
    if inputs['reference_source_manifest_sha256']!=prepare['MANIFEST_SHA']:
        raise ValueError('candidate uses a different parent')
    for name,expected in inputs['input_sha256'].items():
        if digest(candidate/name)!=expected:
            raise ValueError('diagnostic input changed: '+name)
    if (candidate/'build_returncode.txt').read_text().strip()!='0':
        raise ValueError('diagnostic implementation did not complete successfully')
    gao_evidence=None
    bitstream=candidate/'impl/pnr/hdmi_usb3_diagnostic.fs'
    if inputs.get('post_synthesis_gao_requested'):
        bitstream=candidate/'impl/pnr/ao_0.fs'
        configuration=ET.parse(candidate/'diagnostic.gao').getroot()
        cores=configuration.findall('AoCore')
        if len(cores)!=1 or cores[0].get('index')!='0':
            raise ValueError('only one explicitly audited GAO core is supported')
        signals=[signal.text for signal in cores[0].find('SignalList')]
        if signals!=inputs['signals'] or cores[0].get('sample_clock')!='clk_50m_d':
            raise ValueError('GAO observation signals or sampling clock changed')
        wrapper=candidate/'impl/gao/gw_gao_top.v'
        generated=wrapper.read_text()
        data=re.search(r'\.data_i\(\{([^}]*)\}\)',generated)
        if (data is None or [signal.strip().lstrip('\\') for signal in data[1].split(',')]!=signals
                or '.clk_i(clk_50m_d)' not in generated):
            raise ValueError('generated GAO wrapper does not capture the requested signals')
        if digest(candidate/'hdmi_usb3_diagnostic.vg')!=inputs['reused_synthesis_netlist_sha256']:
            raise ValueError('reused D3 synthesis netlist changed')
        if 'Skip synthesis, because there is only one netlist file' not in (candidate/'build.log').read_text():
            raise ValueError('tool did not confirm the synthesis-netlist reuse path')
        with bitstream.open() as stream:
            header=stream.read(2048)
        if '//UserCode: '+inputs['user_code'].lower() not in header:
            raise ValueError('GAO bitstream header has a different UserCode')
        gao_evidence=dict(sample_clock='clk_50m_d',signals=signals,video_rtl_resynthesized=False,
            wrapper_sha256=digest(wrapper),generated_core_sha256=digest(candidate/'impl/gao/gao.v'),
            bitstream_relative_path=str(bitstream.relative_to(candidate)),jtag_capture_tested=False,
            scope='generated wrapper and tool synthesis-skip evidence; GAO is omitted from the vendor simulation netlist, and live JTAG capture is not verified')
    stage=parent/'workstation/Prj1'
    startup_adaptations=[
        ('u_video/u_dvi/clock_phy/tmds_serdes_inst0','u_dvi/clock_lane/serializer'),
        ('u_video/u_dvi/gen_enc[{i}].dvi_tx_tmds_phy_inst/tmds_serdes_inst0',
         'u_dvi/data_lanes[{i}].serializer/serializer'),
        ('+ "/tmds_bufds_isnt0"','+ "/differential"'),
        ('(ground if bit < 5 else power)','(power if bit < 5 else ground)'),
        ("10'b1111100000 clock word","10'b0000011111 clock word"),
        ('"word_d9_to_d0": "1111100000"','"word_d9_to_d0": "0000011111"')]
    startup,startup_source=load_checker(stage,metadata,'scripts/check_serializer_startup.py',
                                        startup_adaptations)
    pll,pll_source=load_checker(stage,metadata,'scripts/check_video_pll_init.py',[
        ('PREFIX = "u_video/u_clock/g_hardware.u_pll"','PREFIX = "u_clock/g_hardware.u_pll"')])
    base=candidate/'impl/pnr/hdmi_usb3_diagnostic'
    sdf=base.with_suffix('.sdf').read_text()
    netlist=base.with_suffix('.vo').read_text()
    constraints=(candidate/'diagnostic.sdc').read_text()
    startup_errors,startup_evidence=startup['inspect_serializer_startup'](sdf,netlist,None,constraints)
    pll_errors,pll_evidence=pll['inspect_video_pll_init'](sdf,netlist,stage)
    errors=startup_errors+pll_errors
    negative_checks={}
    for kind,name,pin,reason in [
        ('OSER10','u_dvi/clock_lane/serializer','D0','clock word'),
        ('ELVDS_OBUF','u_dvi/clock_lane/differential','I','directly drives')]:
        match=re.search(r'^'+kind+r'\s+\\'+re.escape(name)+r'\s*\((.*?)^\);',netlist,re.M|re.S)
        if match is None:
            raise ValueError('negative-check target missing: '+name)
        changed,count=re.subn(r'(\.'+pin+r'\()([^)]*)',r'\g<1>GND',match[0])
        if count!=1 or changed==match[0]:
            raise ValueError('negative-check mutation did not change exactly one pin')
        broken=netlist[:match.start()]+changed+netlist[match.end():]
        rejected,unused=startup['inspect_serializer_startup'](sdf,broken,None,constraints)
        if not any(reason in error for error in rejected):
            raise ValueError('negative control was not rejected: '+name+'/'+pin)
        negative_checks[name+'/'+pin]=rejected
    timing=base.with_suffix('.tr').read_text()
    raw_slack={}
    for analysis in ('Setup','Hold','Recovery','Removal'):
        section=re.search(r'^3\.1\.\d '+analysis+r' Paths Table\n<Report Command>.*?(?=\n3\.)',
                          timing,re.M|re.S)
        if section is None:
            raise ValueError('timing table missing: '+analysis)
        values=[float(match[1]) for match in re.finditer(r'^\s+\d+\s+(-?\d+\.\d+)\s+',
                                                         section[0],re.M)]
        if not values:
            raise ValueError('timing table contains no paths: '+analysis)
        raw_slack[analysis.lower()]=min(values)
    record=dict(identity=inputs['identity'],user_code=inputs['user_code'],
        scope='isolated HDMI source identity, routed PLL/startup and negative controls; not board acceptance',
        input_manifest_sha256=digest(candidate/'inputs.json'),verifier_sha256=digest(__file__),
        gao_observer=gao_evidence,
        routed_checks_passed=not errors,errors=errors,raw_reported_min_slack_ns=raw_slack,
        timing_closed=all(value>=0 for value in raw_slack.values()),
        serializer_startup=startup_evidence,video_pll=pll_evidence,negative_checks=negative_checks,
        checker_sources=dict(serializer_startup=startup_source,video_pll=pll_source),
        output_sha256={source.name:digest(source) for source in
                       (bitstream,*(base.with_suffix(suffix) for suffix in ('.sdf','.vo','.tr')))},
        hardware_tested=False,sram_programmed=False,flash_programmed=False,release_ready=False,
        remaining_gaps=['Raw STA recovery violations are retained, not hidden or declared closed.',
                        'Startup proof covers four OSER10 resets and CLKDIV only; pixel reset CDC remains separate.',
                        'No measured PLL lock, HPD, voltage, TMDS waveform or displayed picture.',
                        'UART is receive-only diagnostic telemetry and requires the actual U15 UART connection.'],
        adapter_exit_plan='Retire the isolated probe after HDMI board diagnosis; do not select it as a workstation profile.')
    (candidate/'verification.json').write_text(json.dumps(record,indent=2)+'\n')
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate',type=Path)
    args=parser.parse_args()
    result=verify(args.candidate)
    print(json.dumps({key:result[key] for key in ('user_code','routed_checks_passed','errors',
                                                'raw_reported_min_slack_ns','timing_closed')},indent=2))
    raise SystemExit(0 if result['routed_checks_passed'] else 1)
