#!/usr/bin/env python3
"""Exercise rejection paths against in-memory mutations of a real routed build."""
from pathlib import Path
import argparse,json,re
from unittest.mock import patch
from check_audio_build import inspect

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('project',type=Path)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    if a.output.exists(): parser.error('Refusing to replace evidence')
    root=a.project.resolve();pnr=root/'impl/pnr';vo=pnr/'Prj1.vo';sdf=pnr/'Prj1.sdf'
    original_read=Path.read_text;v=vo.read_text();s=sdf.read_text();cases=[]
    def rejected(name,path,value,reason):
        def reader(p,*args,**kwargs):
            return value if p==path else original_read(p,*args,**kwargs)
        with patch.object(Path,'read_text',reader):
            try: inspect(root)
            except ValueError as error:
                assert reason in str(error),(name,str(error))
                cases.append({'name':name,'rejected':True,'reason':str(error)})
            else: raise AssertionError(name+' unexpectedly passed')
    target='defparam \\u_audio_clock/g_hardware.u_pll/PLL_inst .ODIV0_FRAC_SEL=5;'
    assert target in v
    rejected('wrong_audio_frequency',vo,v.replace(target,target.replace('=5;','=4;'),1),'ODIV0_FRAC_SEL')
    def replace_route(text,predicate):
        for line in text.splitlines():
            if '(INTERCONNECT ' in line and predicate(line):
                changed=re.sub(r'\([\d.eE+:-]+\)\)\s*$', '(30.000:30.000:30.000))',line)
                assert changed!=line
                return text.replace(line,changed,1)
        raise AssertionError('test route missing')
    rejected('pll_control_over_10ns',sdf,replace_route(s,lambda line:'u_audio_clock' in line and '/PLL_inst/RESET (' in line),'exceeds 10ns')
    rejected('payload_over_20ns',sdf,replace_route(s,lambda line:'u_display_cdc' in line and 'held_data' in line and 'destination_data' in line),'exceeds 20ns')
    a.output.write_text(json.dumps({'passed':True,'mutations':cases,'files_modified':False},indent=2)+'\n')
    print('PASS 3 audio audit negative mutations; routed artifacts unchanged')

if __name__=='__main__': main()
