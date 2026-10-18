#!/usr/bin/env python3
"""Check that managed audio services and recorder/score BSRAM survived synthesis."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET


def inspect(build):
    stage=build/'Prj1'
    manifest=json.loads((build/'migration_inputs.json').read_text())
    if manifest.get('top_module')!='gw138k_managed_audio':
        raise ValueError('Not a managed audio subsystem build')
    for relative,digest in manifest['staged_sha256'].items():
        if hashlib.sha256((stage/relative).read_bytes()).hexdigest()!=digest:
            raise ValueError('Frozen input changed: '+relative)
    resource=stage/'impl/gwsynthesis/Prj1_syn_rsc.xml'
    root=ET.parse(resource).getroot()
    if root.attrib['name']!='gw138k_managed_audio': raise ValueError('Wrong synthesized top')
    modules={node.attrib['name']:node.attrib for node in root.iter('SubModule')}
    for name in ('u_control_cdc','u_services','recorder','score'):
        if name not in modules: raise ValueError('Required module optimized away: '+name)
    if int(modules['recorder'].get('Bsram','0'))!=3: raise ValueError('Recorder no longer uses three BSRAMs')
    if int(modules['score'].get('Bsram','0'))!=2: raise ValueError('Score no longer uses two BSRAMs')
    return {'synthesis_audit_passed':True,'top_resource':root.attrib,
            'retained_modules':{name:modules[name] for name in ('u_control_cdc','u_services','recorder','score')},
            'frozen_input_count':len(manifest['staged_sha256']),
            'resource_report_sha256':hashlib.sha256(resource.read_bytes()).hexdigest(),
            'routed':False,'ae350_instantiated':False,'hardware_tested':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Refusing to replace evidence')
    result=inspect(args.build.resolve())
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS managed synthesis: control retained; recorder=3 BSRAM, score=2 BSRAM; not routed')


if __name__=='__main__': main()
