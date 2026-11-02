#!/usr/bin/env python3
"""Offline merge of frozen 3BE2 audio workstation and accepted 8FC3 USB-A Host.
No programming, UART, or board discovery operations are performed.
"""
from pathlib import Path
from datetime import datetime
import argparse,hashlib,json,os,shutil,subprocess,sys,xml.etree.ElementTree as ET
from tools.workstation_memory import audit as audit_workstation_memory
from tools.stage_usb_firmware import compiler_prefix, stage_usb_firmware
ROOT=Path(__file__).resolve().parent
TF_AUDIO=ROOT/'rtl/tf_audio'
WORK=ROOT.parent/'results/workstation_20260911_174045_306332'
USB=ROOT/'vendor/usb_host_fs_8fc3'
WORKSTATION_MANIFEST=ROOT/'vendor/workstation_inputs.json'
DDR_REFERENCE=ROOT/'vendor/ddr3_reference/ddr3_memory_interface.vo'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frozen_sha(p):
    data=p.read_bytes()
    if b'\0' not in data:data=data.replace(b'\r\n',b'\n')
    return hashlib.sha256(data).hexdigest()
def replace(s,a,b):
    assert s.count(a)==1,('ambiguous source edit',a)
    return s.replace(a,b)
def replace_n(s,a,b,count):
    assert s.count(a)==count,('unexpected source edit count',a,s.count(a),count)
    return s.replace(a,b)
def replace_between(s,start,end,a,b):
    first=s.index(start);last=s.index(end,first) if end else len(s)
    return s[:first]+replace(s[first:last],a,b)+s[last:]
def main():
    from tools.workstation_profile import PROFILE_REGISTRY
    ap=argparse.ArgumentParser();ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--reuse-synthesis',type=Path)
    ap.add_argument('--synthesis-only',action='store_true',help='Offline synthesis only; no place/route or programming')
    ap.add_argument('--no-update-latest',action='store_true',help='Keep the local latest-build pointer unchanged')
    ap.add_argument('--prepare-task3-framework',action='store_true',help='Prepare an offline logical dual-138K source snapshot only; no board profile, physical flow or deployment')
    ap.add_argument('--task3-framework-output',type=Path,help='Required new output directory for --prepare-task3-framework')
    ap.add_argument('--prepare-pinout',choices=['custom-138k'],help='Offline custom-board locations only; not a workstation synthesis path')
    ap.add_argument('--netlist-dir',type=Path,help='Explicit directory containing the three locked custom-board netlists')
    ap.add_argument('--pinout-output',type=Path,help='New output directory for --prepare-pinout; refuses existing paths')
    ap.add_argument('--logic-only', action='store_true', help='Native full RTL synthesis preparation without PCB netlists or pin constraints; never P&R')
    ap.add_argument('--prepare-custom-board',action='store_true',help='Prepare native 138K board integration for offline synthesis only; electrical and full physical gates remain blocked')
    ap.add_argument('--workstation-profile',choices=tuple(PROFILE_REGISTRY),help='Explicit locked native workstation source/feature checkpoint; requires --prepare-custom-board')
    ap.add_argument('--custom-board-output',type=Path,help='Required new output directory for --prepare-custom-board')
    ap.add_argument('--hdmi-mode',choices=['1080p60','720p30','720p60'],help='Explicit native-board HDMI mode; never changes accepted workstation profiles')
    ap.add_argument('--hdmi-isolation',action='store_true',help='Standalone current native UI through shared DDR; no CPU, USB, BLE or recognition')
    ap.add_argument('--hdmi-output',type=Path,help='New output directory for --hdmi-isolation')
    ap.add_argument('--hdmi-input',choices=['static','dynamic'],help='Deterministic display inputs; default dynamic')
    ap.add_argument('--prepare-usb2-soc',action='store_true',help='Prepare native CPU/USB2 component with explicit probe or workstation firmware; not an integrated board candidate')
    ap.add_argument('--usb2-soc-output',type=Path,help='Required new output directory for --prepare-usb2-soc')
    ap.add_argument('--usb2-firmware-profile',choices=['probe','workstation'],help='Explicit USB2 CPU firmware; default probe, never changes accepted workstation profiles')
    ap.add_argument('--usb2-component',choices=['soc','workstation-input','workstation-audio','workstation-hotplug'],help='Explicit component composition; input/audio/hotplug require workstation firmware')
    ap.add_argument('--usb2-hdmi-status',action='store_true',help='USB device and voice status on explicit combined diagnostic')
    ap.add_argument('--usb2-hdmi-baseline',type=Path,help='Compose workstation-hotplug with the explicitly checked accepted C11028D5 HDMI baseline')
    ap.add_argument('--usb2-observer-profile',choices=['owner','phy','port'],help='Explicit combined HDMI/USB observer; port retains attempt history and packet counters')
    ap.add_argument('--usb2-observer-trigger',choices=['reset','clock-failure'],help='Combined observer trigger; clock-failure requires the phy profile')
    ap.add_argument('--usb2-full-speed-only',action='store_true',help='Explicit native workstation diagnostic policy; HS remains enabled by default')
    ap.add_argument('--ulpi-selftest',action='store_true',help='Standalone PHY register/clock test; no CPU, DDR, HDMI or programming')
    ap.add_argument('--ulpi-output',type=Path,help='New output directory for --ulpi-selftest')
    ap.add_argument('--ulpi-clock-pull',choices=['NONE','UP','DOWN'],help='Standalone self-test CLK input weak pull experiment only; default unchanged')
    ap.add_argument('--ulpi-clock-probe',action='store_true',help='Standalone self-test only: receive CLKOUT through FPC2.8/C17; unplug amplifier cable and use a temporary probe wire')
    ap.add_argument('--usb1-identify',action='store_true',help='Explicit USB1 FS host/keyboard candidate; no accepted profile switch or programming')
    ap.add_argument('--usb1-board',choices=['138k','25k'],help='USB1 candidate target; default 138k host')
    ap.add_argument('--usb1-output',type=Path,help='New USB1 candidate output directory')
    ap.add_argument('--current-workstation',action='store_true',
                    help='Merge scope into accepted full83; full requires UserCode, never changes board latest')
    ap.add_argument('--tf-audio-kind',choices=['mp3','wav','flac'],default='wav',
                    help='TF decoder profile to elaborate (default: wav)')
    ap.add_argument('--cnn-timing85',action='store_true',help='Current workstation: six pinned CNN timing fixes')
    ap.add_argument('--resource-rework',action='store_true',
                    help='Complete candidate with 4-Hz guidance, tiled CNN, SDP buffers and spatial reverb')
    ap.add_argument('--resource-timing',action='store_true',
                    help='Resource candidate: measured structural timing fixes and route0; keeps all clocks/features')
    ap.add_argument('--replicate-resources',action='store_true',help='Resource candidate only: explicit high-fanout resource replication')
    ap.add_argument('--place-option',type=int,choices=range(5),help='Resource candidate only: explicit Arora V placement algorithm')
    ap.add_argument('--max-fanout',type=int,help='Resource candidate only: explicit synthesis fanout limit')
    ap.add_argument('--user-code',help='Optional eight hexadecimal digits identifying a release without changing RTL')
    ap.add_argument('--riscv-prefix',help='GNU bare-metal RISC-V prefix before -gcc; also GW138K_RISCV_PREFIX')
    ap.add_argument('--ae350-local-memory-probe',action='store_true',help='Prepare only a minimal same-hard-IP ILM/DLM/boot64 diagnostic')
    ap.add_argument('--ae350-probe-output',type=Path,help='New output directory for the explicit AE350 local-memory probe')
    ap.add_argument('--ae350-probe-gao',choices=('full64','banked4','bsram4','bsram8'),help='Explicit GAO transport for the standalone AE350 probe; default full64')
    ap.add_argument('--ae350-probe-program',choices=('local-memory','cache-pma-v1'),help='Explicit standalone probe program; default local-memory')
    args=ap.parse_args()
    if args.prepare_task3_framework:
        allowed={'prepare_task3_framework','task3_framework_output','prepare_only','tf_audio_kind'}
        explicit_options={'--prepare-task3-framework','--prepare-only','--task3-framework-output'}
        if (not args.prepare_only or args.task3_framework_output is None or args.tf_audio_kind!='wav' or
                any(option.split('=',1)[0] not in explicit_options for option in sys.argv[1:] if option.startswith('--')) or
                any(value is not None and value is not False for key,value in vars(args).items() if key not in allowed)):
            ap.error('--prepare-task3-framework requires --prepare-only and --task3-framework-output; cannot mix profiles, synthesis or hardware parameters')
        from tools.workstation_task3_framework import prepare as prepare_task3_framework
        try:
            output,result=prepare_task3_framework(ROOT,args.task3_framework_output)
            print(output,flush=True)
            print(json.dumps(result),flush=True)
        except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as error:
            ap.error(str(error))
        return
    if args.task3_framework_output is not None:
        ap.error('--task3-framework-output requires --prepare-task3-framework')
    if args.ae350_local_memory_probe:
        allowed={'ae350_local_memory_probe','ae350_probe_output','ae350_probe_gao','ae350_probe_program','prepare_only','netlist_dir','user_code','riscv_prefix','tf_audio_kind'}
        if (args.tf_audio_kind!='wav' or not args.prepare_only or args.ae350_probe_output is None or
                args.netlist_dir is None or args.user_code is None or
                any(value for key,value in vars(args).items() if key not in allowed)):
            ap.error('--ae350-local-memory-probe requires --prepare-only, --ae350-probe-output, --netlist-dir, new --user-code; cannot mix profiles')
        from tools.workstation_ae350_local_probe import prepare as prepare_ae350_probe
        try:
            output,metadata=prepare_ae350_probe(ROOT,args.netlist_dir,args.ae350_probe_output,args.user_code,args.riscv_prefix,
                gao_mode=args.ae350_probe_gao or 'full64',program=args.ae350_probe_program or 'local-memory')
            print(output,flush=True)
            print(json.dumps(dict(identity=metadata['identity'],validation_stage=metadata['validation_stage'],
                                 sources=len(metadata['source_paths']),full_workstation=False)),flush=True)
        except (ValueError,OSError,subprocess.CalledProcessError) as error:
            ap.error(str(error))
        return
    if args.ae350_probe_output is not None or args.ae350_probe_gao is not None or args.ae350_probe_program is not None:
        ap.error('--ae350-probe-output/--ae350-probe-gao require --ae350-local-memory-probe')
    if args.workstation_profile is not None and not args.prepare_custom_board:
        ap.error('--workstation-profile requires --prepare-custom-board')
    if args.usb1_identify:
        allowed={'usb1_identify','usb1_board','usb1_output','netlist_dir','user_code','riscv_prefix','prepare_only','synthesis_only','tf_audio_kind'}
        if args.tf_audio_kind!='wav' or any(value for key,value in vars(args).items() if key not in allowed):
            ap.error('--usb1-identify cannot be mixed with other build profiles')
        if args.usb1_output is None or args.user_code is None or args.prepare_only==args.synthesis_only:
            ap.error('--usb1-identify requires --usb1-output, new --user-code, and exactly one of --prepare-only/--synthesis-only')
        from tools.workstation_usb1 import prepare as prepare_usb1, build as build_usb1
        try:
            output,metadata=prepare_usb1(ROOT,args.usb1_output,args.user_code,args.usb1_board or '138k',args.netlist_dir,args.riscv_prefix)
            print(output,flush=True)
            print(json.dumps(build_usb1(output) if args.synthesis_only else metadata),flush=True)
        except (ValueError,OSError,subprocess.CalledProcessError) as error:
            ap.error(str(error))
        return
    if args.usb1_board is not None or args.usb1_output is not None:
        ap.error('--usb1-board/--usb1-output requires --usb1-identify')
    if args.ulpi_selftest:
        if args.ulpi_output is None or args.netlist_dir is None or args.user_code is None:
            ap.error('--ulpi-selftest requires --ulpi-output, --netlist-dir and a new --user-code')
        if (args.prepare_custom_board or args.prepare_pinout or args.prepare_usb2_soc or args.current_workstation or
                args.cnn_timing85 or args.resource_rework or args.resource_timing or args.reuse_synthesis or
                args.hdmi_isolation or args.hdmi_output or args.hdmi_input or args.hdmi_mode or
                args.usb2_hdmi_baseline or args.usb2_observer_profile or args.usb2_observer_trigger or
                args.usb2_firmware_profile or args.usb2_component or args.usb2_soc_output or
                args.custom_board_output or args.pinout_output or args.usb2_full_speed_only or
                args.replicate_resources or args.place_option is not None or args.max_fanout is not None or
                args.riscv_prefix or args.tf_audio_kind!='wav' or (args.prepare_only and args.synthesis_only)):
            ap.error('--ulpi-selftest cannot be mixed with other component or workstation profiles')
        from tools.workstation_ulpi_selftest import prepare as prepare_ulpi, build as build_ulpi
        try:
            output,metadata=prepare_ulpi(ROOT,args.netlist_dir,args.ulpi_output,args.user_code,args.ulpi_clock_pull,args.ulpi_clock_probe)
            print(output,flush=True)
            print(json.dumps(dict(identity=metadata['identity'],sources=len(metadata['source_paths']),
                                  full_workstation=False)),flush=True)
            if not args.prepare_only:
                result=build_ulpi(output,args.synthesis_only)
                print(json.dumps(result))
                if result['returncode']:
                    raise SystemExit(result['returncode'])
        except (ValueError,OSError,subprocess.CalledProcessError) as error:
            ap.error(str(error))
        return
    if args.ulpi_output is not None:
        ap.error('--ulpi-output requires --ulpi-selftest')
    if args.ulpi_clock_pull is not None:
        ap.error('--ulpi-clock-pull requires --ulpi-selftest')
    if args.ulpi_clock_probe:
        ap.error('--ulpi-clock-probe requires --ulpi-selftest')
    if (args.usb2_observer_profile is not None or args.usb2_observer_trigger is not None) and args.usb2_hdmi_baseline is None:
        ap.error('--usb2-observer-profile/--usb2-observer-trigger requires --usb2-hdmi-baseline')
    if args.usb2_hdmi_status and args.usb2_hdmi_baseline is None:
        ap.error('--usb2-hdmi-status requires --usb2-hdmi-baseline')
    if args.usb2_hdmi_baseline is not None and not (args.prepare_usb2_soc and args.usb2_component=='workstation-hotplug'):
        ap.error('--usb2-hdmi-baseline requires --prepare-usb2-soc --usb2-component workstation-hotplug')
    if args.hdmi_isolation:
        if args.hdmi_output is None or args.netlist_dir is None or args.user_code is None:
            ap.error('--hdmi-isolation requires --hdmi-output, --netlist-dir and a new --user-code')
        if (args.prepare_custom_board or args.prepare_pinout or args.prepare_usb2_soc or args.current_workstation or
                args.cnn_timing85 or args.resource_rework or args.resource_timing or args.reuse_synthesis or
                args.hdmi_mode or args.usb2_full_speed_only or args.replicate_resources or
                args.place_option is not None or args.max_fanout is not None or args.riscv_prefix or
                args.custom_board_output or args.pinout_output or args.usb2_soc_output or
                args.usb2_firmware_profile or args.usb2_component or args.tf_audio_kind!='wav' or
                (args.prepare_only and args.synthesis_only)):
            ap.error('--hdmi-isolation cannot be mixed with workstation or other component profiles')
        from tools.workstation_hdmi_isolation import prepare as prepare_hdmi, build as build_hdmi
        try:
            output,metadata=prepare_hdmi(ROOT,args.netlist_dir,args.hdmi_output,args.user_code,args.hdmi_input!='static')
            print(output,flush=True)
            print(json.dumps(dict(identity=metadata['identity'],sources=len(metadata['enabled_inputs']),full_workstation=False)),flush=True)
            if not args.prepare_only:
                result=build_hdmi(output,args.synthesis_only)
                print(json.dumps(result))
                if result['returncode']:
                    raise SystemExit(result['returncode'])
        except (ValueError,OSError,subprocess.CalledProcessError) as error:
            ap.error(str(error))
        return
    if args.hdmi_output is not None or args.hdmi_input is not None:
        ap.error('--hdmi-output and --hdmi-input require --hdmi-isolation')
    if args.hdmi_mode is not None and not args.prepare_custom_board:
        ap.error('--hdmi-mode requires --prepare-custom-board')
    if args.usb2_full_speed_only and not (args.prepare_custom_board or
            (args.prepare_usb2_soc and args.usb2_firmware_profile=='workstation')):
        ap.error('--usb2-full-speed-only requires explicit native workstation firmware preparation')
    if args.logic_only and not args.prepare_custom_board:
        ap.error('--logic-only requires --prepare-custom-board')
    if args.prepare_custom_board:
        if args.custom_board_output is None or (args.netlist_dir is None and not args.logic_only):
            ap.error('--prepare-custom-board requires --custom-board-output and --netlist-dir')
        if (args.prepare_pinout or args.pinout_output is not None or args.prepare_usb2_soc or
                args.usb2_soc_output is not None or args.usb2_firmware_profile is not None or args.usb2_component is not None or
                args.prepare_only or args.synthesis_only or args.reuse_synthesis or args.no_update_latest or
                args.current_workstation or args.cnn_timing85 or args.resource_rework or args.resource_timing or
                args.replicate_resources or args.place_option is not None or args.max_fanout is not None or
                args.user_code is not None or args.tf_audio_kind!='wav'):
            ap.error('--prepare-custom-board cannot be mixed with component, pinout-only, workstation or release options')
        from tools.workstation_custom_board import prepare as prepare_custom_board
        try:
            output,metadata=prepare_custom_board(ROOT,args.netlist_dir,args.custom_board_output,
                                                 args.riscv_prefix,not args.usb2_full_speed_only,args.hdmi_mode or '1080p60',
                                                 workstation_profile=args.workstation_profile,logic_only=args.logic_only)
        except (ValueError,OSError,subprocess.CalledProcessError) as error:
            ap.error(str(error))
        print(output)
        print(json.dumps(dict(identity=metadata['identity'],validation_stage=metadata['validation_stage'],
                              sources=len(metadata['enabled_inputs']),electrical_blocked=metadata['electrical_blocked'],
                              electrical_status=metadata.get('electrical_status'),
                              deployment_allowed=False,workstation_profile=metadata.get('workstation_profile'))))
        return
    if args.custom_board_output is not None:
        ap.error('--custom-board-output requires --prepare-custom-board')
    if args.prepare_usb2_soc:
        if args.usb2_soc_output is None:
            ap.error('--prepare-usb2-soc requires --usb2-soc-output')
        hotplug = args.usb2_component == 'workstation-hotplug'
        if hotplug and args.usb2_firmware_profile != 'workstation':
            ap.error('workstation-hotplug requires explicit --usb2-firmware-profile workstation')
        if (args.prepare_pinout or (args.netlist_dir is not None and not hotplug) or args.pinout_output is not None or
                args.prepare_only or args.synthesis_only or args.reuse_synthesis or args.no_update_latest or
                args.current_workstation or args.cnn_timing85 or args.resource_rework or args.resource_timing or
                args.replicate_resources or args.place_option is not None or args.max_fanout is not None or
                (args.user_code is not None and not hotplug) or args.tf_audio_kind!='wav'):
            ap.error('--prepare-usb2-soc cannot be mixed with pinout, workstation, synthesis or release options')
        from tools.workstation_usb2_soc import prepare as prepare_usb2_soc
        try:
            if hotplug:
                if args.usb2_hdmi_baseline is not None:
                    from tools.workstation_usb2_hdmi import prepare as prepare_usb2_hdmi
                    output,metadata=prepare_usb2_hdmi(ROOT,args.usb2_soc_output,args.netlist_dir,args.user_code,
                                                    args.usb2_hdmi_baseline,args.riscv_prefix,not args.usb2_full_speed_only,
                                                    args.usb2_observer_profile or 'owner',args.usb2_observer_trigger or 'reset',
                                                    usb_status=args.usb2_hdmi_status)
                else:
                    from tools.workstation_usb2_hotplug import prepare as prepare_hotplug
                    output,metadata=prepare_hotplug(ROOT,args.usb2_soc_output,args.netlist_dir,args.user_code,
                                                   args.riscv_prefix,not args.usb2_full_speed_only)
            else:
                output,metadata=prepare_usb2_soc(ROOT,args.usb2_soc_output,args.riscv_prefix,
                                               args.usb2_firmware_profile or 'probe',not args.usb2_full_speed_only,
                                               args.usb2_component or 'soc')
        except (ValueError,OSError,subprocess.CalledProcessError) as error:
            ap.error(str(error))
        print(output)
        print(json.dumps(dict(identity=metadata['identity'],validation_stage=metadata['validation_stage'],
                              sources=len(metadata['source_paths']),
                              rom_sha256=metadata['firmware']['rom_sha256'],deployment_allowed=False)))
        return
    if args.usb2_soc_output is not None or args.usb2_firmware_profile is not None or args.usb2_component is not None:
        ap.error('--usb2-soc-output, --usb2-firmware-profile and --usb2-component require --prepare-usb2-soc')
    if args.prepare_pinout:
        if not args.netlist_dir:
            ap.error('--prepare-pinout requires --netlist-dir')
        if (args.prepare_only or args.synthesis_only or args.reuse_synthesis or args.current_workstation or
                args.cnn_timing85 or args.resource_rework or args.resource_timing or args.replicate_resources or
                args.place_option is not None or args.max_fanout is not None or args.user_code is not None or
                args.riscv_prefix is not None or args.tf_audio_kind!='wav'):
            ap.error('--prepare-pinout cannot be mixed with workstation preparation, synthesis or release options')
        from tools.workstation_pinout import prepare as prepare_pinout
        try:
            output,plan=prepare_pinout(ROOT,args.netlist_dir,args.pinout_output)
        except (ValueError,OSError) as error:
            ap.error(str(error))
        print(output)
        print(json.dumps(dict(identity=plan['identity'],ports=len(plan['ports']),
                              validation_stage=plan['validation_stage'],synthesis_allowed=False,
                              electrical_status=plan['electrical_check']['status'])))
        return
    if args.netlist_dir is not None or args.pinout_output is not None:
        ap.error('--netlist-dir and --pinout-output require --prepare-pinout')
    if args.resource_rework and (args.current_workstation or args.cnn_timing85):
        ap.error('--resource-rework cannot be mixed with --current-workstation or --cnn-timing85')
    if args.cnn_timing85 and not args.current_workstation:
        ap.error('--cnn-timing85 requires --current-workstation')
    if args.resource_timing and not args.resource_rework:
        ap.error('--resource-timing requires --resource-rework')
    if args.replicate_resources and not args.resource_rework:
        ap.error('--replicate-resources requires --resource-rework')
    if args.place_option is not None and not args.resource_rework:
        ap.error('--place-option requires --resource-rework')
    if args.max_fanout is not None and not args.resource_rework:
        ap.error('--max-fanout requires --resource-rework')
    if args.resource_rework:
        if ((args.prepare_only and args.synthesis_only) or args.reuse_synthesis or
            args.tf_audio_kind!='wav' or args.riscv_prefix is not None):
            ap.error('--resource-rework supports the complete WAV workstation; no synthesis reuse or compiler override')
        flow='prepare' if args.prepare_only else 'syn' if args.synthesis_only else 'all'
        command=[sys.executable,str(ROOT/'tools/build_resource_rework.py'),'--flow',flow]
        if args.resource_timing:command+=['--timing-fixes','--route-option','0']
        if args.replicate_resources:command+=['--replicate-resources']
        if args.place_option is not None:command+=['--place-option',str(args.place_option)]
        if args.max_fanout is not None:command+=['--max-fanout',str(args.max_fanout)]
        if args.user_code is not None:command+=['--user-code',args.user_code]
        raise SystemExit(subprocess.run(command).returncode)
    if args.current_workstation:
        if ((args.prepare_only and args.synthesis_only) or args.reuse_synthesis or
            args.tf_audio_kind!='wav'):
            ap.error('--current-workstation supports accepted WAV only, no reuse-synthesis; '
                     '--prepare-only and --synthesis-only are mutually exclusive')
        flag='--prepare-only' if args.prepare_only else '--synthesis-only' if args.synthesis_only else '--full'
        command=[sys.executable,str(ROOT/'tools/build_current_workstation.py'),flag]
        if args.user_code is not None: command+=['--user-code',args.user_code]
        if args.riscv_prefix is not None: command+=['--riscv-prefix',args.riscv_prefix]
        if args.cnn_timing85: command+=['--cnn-timing85']
        raise SystemExit(subprocess.run(command).returncode)
    tf_audio_kind={'mp3':1,'wav':2,'flac':3}[args.tf_audio_kind]
    build_mode='synthesis_only' if args.synthesis_only else 'place_route_reuse' if args.reuse_synthesis else 'full'
    if args.user_code is not None:
        if len(args.user_code)!=8 or any(c not in '0123456789abcdefABCDEF' for c in args.user_code):
            ap.error('--user-code requires eight hexadecimal digits')
    if args.synthesis_only and args.reuse_synthesis:
        ap.error('--synthesis-only cannot reuse synthesis')
    for base,manifest in [(WORK/'Prj1',WORKSTATION_MANIFEST),(USB,USB/'inputs.json')]:
        hashes=json.loads(manifest.read_text())
        assert all(frozen_sha(base/p)==h for p,h in hashes.items()),'frozen inputs changed: '+str(base)
    out=ROOT/'results'/datetime.now().strftime('build_%Y%m%d_%H%M%S_%f');out.mkdir(parents=True)
    stage=out/'Prj1'
    shutil.copytree(WORK/'Prj1',stage,ignore=shutil.ignore_patterns('impl','build','__pycache__','*.user'))
    ddr_ip=stage/'vendor/gowin_ddr3/ddr3_memory_interface.v'
    ddr_ip.write_bytes(ddr_ip.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
    assert sha(ddr_ip)=='4a6e26d2ccb8d01221103df4cdf71f3517d2700614020e0c414aafec04a495bc'
    if args.user_code is not None:
        tcl=stage/'scripts/build.tcl'
        tcl.write_text(replace(tcl.read_text(),'set flow all',
            'set_option -user_code '+args.user_code.upper()+'\nset flow all'))
    reference=out/'reference';reference.mkdir()
    shutil.copy2(ddr_ip,reference/'ddr3_memory_interface.v')
    shutil.copy2(DDR_REFERENCE,reference/'ddr3_memory_interface.vo')
    # Display-data overlays are kept outside the frozen workstation
    # source tree. The P10 baseline remains hash-checked and untouched.
    display_overlay={
        'src/video/output_audio_analysis.v':'output_audio_analysis.v',
        'src/video/feedback_renderer.v':'feedback_renderer.v',
        'src/video/hdmi_display.v':'hdmi_display.v',
        'src/memory/display_data_writer.v':'display_data_writer.v',
        'src/memory/display_data_reader.v':'display_data_reader.v',
        'src/ae350/gw138k_ddr_arbiter.sv':'gw138k_ddr_arbiter.sv',
        'src/push2/push2_surface_pixels.sv':'push2_surface_pixels.sv',
    }
    for rel,name in display_overlay.items():
        shutil.copy2(ROOT/'rtl/display_data'/name,stage/rel)
    # C-mode voice allocator/storage overlay.  The frozen P10/P13 workstation
    # tree remains hash-checked; this local copy is the only source changed by
    # the 32-voice experiment.
    audio_overlay={
        'legacy/rtl/audio/unified_oscillator_engine.sv': ROOT/'rtl/audio/unified_oscillator_engine.sv',
        'src/ae350/gw138k_event_workstation.sv': ROOT/'rtl/audio/gw138k_event_workstation.sv',
        'src/push2/push2_controls.sv': ROOT/'rtl/audio/push2_controls.sv',
        'src/push2/push2_lights.sv': ROOT/'rtl/push2/push2_lights.sv',
        'src/push2/push2_led_tx.sv': ROOT/'rtl/push2/push2_led_tx.sv',
    }
    for rel,src in audio_overlay.items():
        shutil.copy2(src,stage/rel)
    # Geometry-only scope vector engine and its portable readmemh inputs.
    scope_data=ROOT/'rtl/audio/scope_vec/data'
    scope_manifest=json.loads((scope_data/'manifest.json').read_text())
    assert scope_manifest['path_bytes']<=16384 and scope_manifest['shape_count']==8 and scope_manifest['points_per_shape']==512,'scope geometry budget/configuration mismatch'
    assert scope_manifest['harmonics']==8 and scope_manifest['maximum_scan_hz']==2000 and not scope_manifest['contains_pcm_audio'],'unsupported scope geometry profile'
    assert all(sha(scope_data/name)==digest for name,digest in scope_manifest['artifacts'].items()),'scope geometry/control artifacts changed: rerun compiler'
    path_words=(scope_data/'paths.mem').read_text().split()
    assert len(path_words)==4096 and all(len(word)==8 and all(c in '0123456789abcdefABCDEF' for c in word) for word in path_words),'scope path table requires exactly 4096 X/Y words'
    scope_dest=stage/'rtl/audio/scope_vec'
    shutil.copytree(ROOT/'rtl/audio/scope_vec',scope_dest)
    cue_rtl=scope_dest/'scope_control_player.sv'
    cue_rtl.write_text(replace(cue_rtl.read_text(),'parameter integer CUE_COUNT=69,',
        'parameter integer CUE_COUNT='+str(scope_manifest['cue_count'])+','))
    # Self-contained TF/FAT audio subsystem.  Do not reach back into the
    # separate Mega_138K/Dev working tree: the staged project and Git checkout
    # must contain the exact same RTL, decoder tables and license records.
    storage_dest=stage/'src/storage'
    shutil.copytree(TF_AUDIO/'storage',storage_dest)
    shutil.copy2(ROOT/'rtl/ddr_address_map.vh',stage/'src/memory/ddr_address_map.vh')
    shutil.copy2(ROOT/'rtl/ddr_address_map_guard.v',stage/'src/memory/ddr_address_map_guard.v')
    shutil.copy2(TF_AUDIO/'tf_async_pcm_fifo.v',stage/'src/storage/tf_async_pcm_fifo.v')
    shutil.copy2(TF_AUDIO/'tf_workstation_audio_bridge.v',stage/'src/storage/tf_workstation_audio_bridge.v')
    shutil.copy2(TF_AUDIO/'pt8211_tx.v',stage/'src/audio/tf_rate_pt8211_tx.v')
    # The verified Basic Pitch graph shares this workstation DDR controller.
    music_dest=stage/'rtl/music'
    shutil.copytree(ROOT/'rtl/music',music_dest)
    # Bind legacy workstation clients to the shared map without changing their
    # protocols or page sizes.
    p=stage/'src/memory/ddr3_bist.v';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'parameter integer BURSTS = 262144, // 8 MiB',
        'parameter integer BURSTS = `PRJ1_DDR_BIST_BEATS, // 8 MiB')
    p.write_text(s)
    p=stage/'src/memory/ddr_frame_writer.v';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'parameter integer FRAME_STRIDE_WORDS=1048576',
        'parameter integer FRAME_STRIDE_WORDS=`PRJ1_DDR_VIDEO_FRAME_APP_WORDS')
    s=replace(s,'req_addr<=29\'d2097152;',
        'req_addr<=`PRJ1_DDR_DISPLAY_DATA_APP_BASE;')
    p.write_text(s)
    p=stage/'src/video/video_ddr_scanout.v';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'parameter integer FRAME_STRIDE_WORDS = 1048576,',
        'parameter integer FRAME_STRIDE_WORDS = `PRJ1_DDR_VIDEO_FRAME_APP_WORDS,')
    p.write_text(s)
    p=stage/'src/ae350/gw138k_view_select.sv';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'?29\'d1048576:29\'d0;',
        '?`PRJ1_DDR_VIDEO_FRAME1_APP_BASE:`PRJ1_DDR_VIDEO_FRAME0_APP_BASE;')
    p.write_text(s)
    p=stage/'src/ae350/gw138k_ui_services.sv';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'front_address[22]?29\'h0500000:29\'h0400000',
        'front_address[22]?`PRJ1_DDR_WORK_PAGE1_APP_BASE:`PRJ1_DDR_WORK_PAGE0_APP_BASE')
    s=replace(s,'staged_address[22]?29\'h0500000:29\'h0400000',
        'staged_address[22]?`PRJ1_DDR_WORK_PAGE1_APP_BASE:`PRJ1_DDR_WORK_PAGE0_APP_BASE')
    p.write_text(s)
    p=stage/'src/ae350/gw138k_ahb_ddr.sv';s=p.read_text()
    s='`include "src/memory/ddr_address_map.vh"\n'+s
    s=replace(s,'assign req_address=29\'d4194304+{8\'d0,byte_address[22:5],3\'b000};',
        'assign req_address=`PRJ1_DDR_WORK_PAGE0_APP_BASE+{8\'d0,byte_address[22:5],3\'b000};')
    p.write_text(s)
    # P24 preserves every profile's harmonic ratios and applies one fixed row
    # scale while loading the existing gain ROM.  The scale is independent of
    # active voice count, so notes do not pump when polyphony changes.
    level_config=json.loads((ROOT/'rtl/audio/p24_mode_gain_scale.json').read_text())
    level_scale=level_config['scale_q16']
    assert len(level_scale)==3 and all(len(row)==5 for row in level_scale)
    gain_mem=stage/'sim/matlab/output/stage15_unified_modes/stage15_mode_gain_q15.mem'
    gain_words=[int(word,16) for word in gain_mem.read_text().split()]
    assert len(gain_words)==3*5*32
    for mode in range(3):
        for profile in range(5):
            scale=level_scale[mode][profile]
            assert 0<scale<2**18
            base=(mode*5+profile)*32
            for partial in range(32):
                value=(gain_words[base+partial]*scale+32768)//65536
                gain_words[base+partial]=min(value,32767)
    gain_mem.write_text(''.join(f'{value:04X}\n' for value in gain_words))
    # P23 PANIC carries a compact epoch in the previously-zero upper bits of
    # control_pitch.  Pitch remains the unchanged low 22-bit Q20 value.
    p=stage/'src/ae350/gw138k_controlled_adapter.sv';s=p.read_text()
    s=replace(s,'assign control_pitch_o={10\'d0,pitch};',
        'wire [9:0] panic_epoch;\n    assign control_pitch_o={panic_epoch,pitch};')
    s=replace(s,'.held_notes_o(held_notes_o),.applied_events_o(applied_events_o),.pc_overflow_o(pc_overflow),.control_options_o(control_options_o),',
        '.held_notes_o(held_notes_o),.applied_events_o(applied_events_o),.pc_overflow_o(pc_overflow),.control_options_o(control_options_o),.panic_epoch_o(panic_epoch),')
    s=replace(s,'output wire [31:0] applied_events_o,pc_health_o,',
        'output wire [31:0] applied_events_o,pc_health_o,\n    output wire [31:0] scope_status_o,tf_scope_control_o,\n    output wire panel_event_valid_o,output wire [6:0] panel_command_o,')
    s=replace(s,'.control_options_o(control_options_o),.panic_epoch_o(panic_epoch),.cpu_event_valid_i(cpu_event_valid_i),',
        '.control_options_o(control_options_o),.panic_epoch_o(panic_epoch),\n        .panel_event_valid_o(panel_event_valid_o),.panel_command_o(panel_command_o),.scope_status_o(scope_status_o),.tf_scope_control_o(tf_scope_control_o),.cpu_event_valid_i(cpu_event_valid_i),')
    p.write_text(s)
    p=stage/'src/ae350/gw138k_controlled_audio.sv';s=p.read_text()
    s=replace(s,'.control_options_o(control_options),',
        '.control_options_o(control_options),.scope_status_o(),.tf_scope_control_o(),')
    p.write_text(s)
    p=stage/'src/usb_host/gw138k_usb_controlled_audio.sv';s=p.read_text()
    s=replace(s,'gw138k_three_event_arbiter u_usb_cpu_events(',
        'gw138k_usb_lifecycle_merge u_usb_cpu_events(')
    s=replace(s,'    output wire sample_ce_o, sample_valid_o,',
        '    output wire sample_ce_o, sample_valid_o,\n    output wire [31:0] scope_status_o,tf_scope_control_o,')
    s=replace(s,'.control_options_o(control_options),',
        '.control_options_o(control_options),.scope_status_o(scope_status_o),.tf_scope_control_o(tf_scope_control_o),')
    p.write_text(s)
    # P27 keeps the Push panel commands inside the accepted event stream.  The
    # workstation emits a one-cycle pulse only after kind 6 reaches dispatch;
    # the existing audio-domain service remains the single score/record owner.
    p=stage/'src/ae350/gw138k_controlled_services.sv';s=p.read_text()
    s=replace(s,'input wire cpu_event_ready,',
        'input wire cpu_event_ready,\n    input wire panel_event_valid,input wire [6:0] panel_command,output wire panel_event_ready,')
    s=replace(s,'logic [8:0] loaded;\n    wire event_address=command_address==12\'h180;',
        '''logic [8:0] loaded;
    assign panel_event_ready=1'b1;
    wire panel_score_toggle=panel_event_valid && panel_command==0;
    wire panel_record_toggle=panel_event_valid && panel_command==1;
    wire event_address=command_address==12'h180;''')
    s=replace(s,'assign score_start=legal_write && command_address==SCORE_START;\n    assign score_stop=legal_write && command_address==SCORE_STOP;',
        '''assign score_start=(legal_write && command_address==SCORE_START) ||
        (panel_score_toggle && !score_running && score_length!=0 && score_length<=loaded);
    assign score_stop=(legal_write && command_address==SCORE_STOP) ||
        (panel_score_toggle && score_running);''')
    s=replace(s,'12\'h180: response_error=command_data[31:18]!=0 || command_data[17:14]>4 ||\n                    (command_data[17:14]==1 && command_data[6:0]==0);',
        '''12'h180: response_error=command_data[31:18]!=0 || command_data[17:14]>6 ||
                    (command_data[17:14]==1 && command_data[6:0]==0) ||
                    (command_data[17:14]==6 && command_data[13:7]>1);''')
    s=replace(s,'if(score_done) done_sticky<=1;\n            if(legal_write) case(command_address)',
        '''if(score_done) done_sticky<=1;
            if(score_start) done_sticky<=0;
            if(panel_record_toggle) record_enable<=~record_enable;
            if(legal_write) case(command_address)''')
    p.write_text(s)
    p=stage/'src/ae350/gw138k_controlled_audio.sv';s=p.read_text()
    s=replace(s,'.cpu_event_valid(cpu_event_valid),.cpu_event_ready(cpu_event_ready),.cpu_event(cpu_event),',
        '.cpu_event_valid(cpu_event_valid),.cpu_event_ready(cpu_event_ready),.cpu_event(cpu_event),\n        .panel_event_valid(1\'b0),.panel_command(7\'d0),.panel_event_ready(),')
    p.write_text(s)
    p=stage/'src/usb_host/gw138k_usb_controlled_audio.sv';s=p.read_text()
    s=replace(s,'output wire score_running_o, score_done_o,',
        'output wire score_running_o, score_done_o,record_enabled_o,')
    s=replace(s,'wire record_enable,record_valid,record_ready,score_write,score_start,score_stop;',
        '''wire record_enable,record_valid,record_ready,score_write,score_start,score_stop;
    wire panel_event_valid,panel_event_ready;wire [6:0] panel_command;
    assign record_enabled_o=record_enable;''')
    s=replace(s,'.cpu_event_valid(cpu_event_valid),.cpu_event_ready(cpu_event_ready),.cpu_event(cpu_event),',
        '.cpu_event_valid(cpu_event_valid),.cpu_event_ready(cpu_event_ready),.cpu_event(cpu_event),\n        .panel_event_valid(panel_event_valid),.panel_command(panel_command),.panel_event_ready(panel_event_ready),')
    s=replace(s,'.pc_uart_rx_i(pc_uart_rx_i),.held_notes_o(held_notes),.applied_events_o(applied_events),.pc_health_o(pc_health),',
        '.pc_uart_rx_i(pc_uart_rx_i),.held_notes_o(held_notes),.applied_events_o(applied_events),.pc_health_o(pc_health),\n        .panel_event_valid_o(panel_event_valid),.panel_command_o(panel_command),')
    # The effect status enters the always-running 50 MHz display domain.  Its
    # old reset came directly from the audio clock domain and left six
    # synchronous RESET endpoints outside STA.  These registers are only a
    # display mirror, so initialize both stages and let audio-domain reset
    # state propagate through the ordinary two-stage data path.
    s=replace(s,
        '''    (* ASYNC_REG="TRUE" *) reg [2:0] effect_mask_meta, effect_mask_sync;
    (* ASYNC_REG="TRUE" *) reg [5:0] effect_order_meta=6'b10_01_00, effect_order_sync=6'b10_01_00;
    always @(posedge clk_50m) begin
        if(!reset_n) begin effect_mask_meta<=0; effect_mask_sync<=0; end
        else begin effect_mask_meta<=effect_mask_audio; effect_mask_sync<=effect_mask_meta; end''',
        '''    wire [2:0] effect_mask_sample /* synthesis syn_keep=1 */;
    assign effect_mask_sample=effect_mask_audio;
    (* ASYNC_REG="TRUE", syn_preserve=1 *) reg [2:0] effect_mask_meta=0, effect_mask_sync=0;
    (* ASYNC_REG="TRUE" *) reg [5:0] effect_order_meta=6'b10_01_00, effect_order_sync=6'b10_01_00;
    always @(posedge clk_50m) begin
        effect_mask_meta<=effect_mask_sample; effect_mask_sync<=effect_mask_meta;''')
    p.write_text(s)
    # Clear effect state without resetting BSRAM contents.  Resetting each
    # history length/pointer makes old RAM words unreachable until replaced.
    p=stage/'legacy/rtl/audio/stereo_effects.sv';s=p.read_text()
    s=replace_n(s,'input logic clk_i,rst_ni,valid_i,enabled_i,',
        'input logic clk_i,rst_ni,clear_i,valid_i,enabled_i,',3)
    s=replace(s,'input logic clk_i,rst_ni,valid_i,\n    input logic signed [31:0] synth_i,pcm_left_i,pcm_right_i,',
        'input logic clk_i,rst_ni,clear_i,valid_i,\n    input logic signed [31:0] synth_i,pcm_left_i,pcm_right_i,')
    s=replace_n(s,'if(state==1) begin','if(!clear_i && state==1) begin',3)
    s=replace(s,'if(state==4) begin memory_l[pointer]<=feedback_l;memory_r[pointer]<=feedback_r;end',
        'if(!clear_i && state==4) begin memory_l[pointer]<=feedback_l;memory_r[pointer]<=feedback_r;end')
    s=replace(s,'if(state==3) begin memory_l[pointer]<=input_l;memory_r[pointer]<=input_r;end',
        'if(!clear_i && state==3) begin memory_l[pointer]<=input_l;memory_r[pointer]<=input_r;end')
    s=replace(s,'if(state==6) begin comb_a[pointer]<=feedback_a;comb_b[pointer]<=feedback_b;end',
        'if(!clear_i && state==6) begin comb_a[pointer]<=feedback_a;comb_b[pointer]<=feedback_b;end')
    s=replace_n(s,'.clk_i,.rst_ni,.valid_i(','.clk_i,.rst_ni,.clear_i,.valid_i(',3)
    stage_body='''end else begin
      valid_o<=0;clip_o<=0;
      case(state)'''
    stage_clear='''end else begin
      valid_o<=0;clip_o<=0;
      if(clear_i) begin
        pointer<=0;frames<=0;state<=0;gain<=0;valid_o<=0;clip_o<=0;
      end else case(state)'''
    s=replace_between(s,'module serial_delay_effect','module serial_chorus_effect',stage_body,stage_clear)
    s=replace_between(s,'module serial_chorus_effect','module serial_reverb_effect',stage_body,stage_clear)
    reverb_clear=stage_clear.replace('valid_o<=0;clip_o<=0;\n      end else case(state)',
        'valid_o<=0;clip_o<=0;damping_a<=0;damping_b<=0;\n      end else case(state)')
    s=replace_between(s,'module serial_reverb_effect','module stereo_effects',stage_body,reverb_clear)
    top_clear='''end else begin
      valid_o<=0;clip_o<=0;
      if(clear_i) begin
        state<=IDLE;valid_o<=0;clip_o<=0;
      end else case(state)'''
    s=replace_between(s,'module stereo_effects',None,stage_body,top_clear)
    # Minimal stereo injection at the P10 mixer boundary. Legacy synth remains mono.
    s=replace(s,'module stereo_effects #(\n',
        'module stereo_effects #(\n    parameter integer VECTOR_ENABLE=0,\n')
    s=replace(s,'input logic signed [31:0] synth_i,pcm_left_i,pcm_right_i,',
        'input logic signed [31:0] synth_i,pcm_left_i,pcm_right_i,\n    input logic signed [31:0] vector_left_i,vector_right_i,')
    s=replace(s,'logic signed [48:0] input_s,input_l,input_r;',
        'logic signed [48:0] input_s,input_l,input_r,input_vl,input_vr;')
    s=replace(s,'input_s<=0;input_l<=0;input_r<=0;',
        'input_s<=0;input_l<=0;input_r<=0;input_vl<=0;input_vr<=0;')
    s=replace(s,'input_s<=$signed(synth_i)*$signed({1\'b0,sg});',
        'input_s<=$signed(synth_i)*$signed({1\'b0,sg});\n          input_vl<=$signed(VECTOR_ENABLE?vector_left_i:32\'sd0)*$signed({1\'b0,sg});\n          input_vr<=$signed(VECTOR_ENABLE?vector_right_i:32\'sd0)*$signed({1\'b0,sg});')
    s=replace(s,'input_mix_l<=input_s+input_l;input_mix_r<=input_s+input_r;',
        'input_mix_l<=input_s+input_l+input_vl;input_mix_r<=input_s+input_r+input_vr;')
    p.write_text(s)
    p=stage/'legacy/rtl/audio/audio_workstation.sv';s=p.read_text()
    s=replace(s,'.pcm_left_i($signed(held_pcm_l)),.pcm_right_i($signed(held_pcm_r)),',
        '.vector_left_i(32\'sd0),.vector_right_i(32\'sd0),\n      .pcm_left_i($signed(held_pcm_l)),.pcm_right_i($signed(held_pcm_r)),')
    p.write_text(s)
    # Rebuild the existing AE350 UI ROM from a staged copy.  A new PANIC epoch
    # clears its local gate and blocks an already-down touch until release.
    p=stage/'firmware/ui_model.h';s=p.read_text()
    s=replace(s,'unsigned mode,sound,route,gate,sw,note,keyboard,old_down;',
        'unsigned mode,sound,route,gate,sw,note,keyboard,old_down,panic_epoch,panic_latched;')
    s=replace(s,'static inline unsigned ui_touch(ui_model*m,unsigned x,unsigned y,unsigned down) {\n unsigned result=0;int hit=ui_hit(x,y);',
        '''static inline unsigned ui_touch(ui_model*m,unsigned x,unsigned y,unsigned down) {
 unsigned result=0;int hit=ui_hit(x,y);
 if(m->panic_latched) {m->old_down=!!down;if(!down)m->panic_latched=0;return 0;}''')
    s=replace(s,'static inline unsigned ui_active(const ui_model*m,unsigned note) {',
        '''static inline unsigned ui_panic(ui_model*m,unsigned epoch) {
 if(m->panic_epoch==epoch)return 0;
 m->panic_epoch=epoch;m->gate=0;m->keyboard=0;m->panic_latched=m->old_down;
 return UI_CHANGED;
}
static inline unsigned ui_active(const ui_model*m,unsigned note) {''')
    p.write_text(s)
    p=stage/'firmware/ui_main.c';s=p.read_text()
    s=replace(s,'unsigned sequence=a138_read(AUDIO_BASE,0x1a0),state=a138_read(AUDIO_BASE,0x184),options=a138_read(AUDIO_BASE,0x18c);',
        'unsigned sequence=a138_read(AUDIO_BASE,0x1a0),state=a138_read(AUDIO_BASE,0x184),pitch=a138_read(AUDIO_BASE,0x188),options=a138_read(AUDIO_BASE,0x18c);')
    s=replace(s,'unsigned changed=m->pc_faults!=faults||m->mode!=((state>>3)&3u)||m->sound!=((state>>7)&7u)||m->route!=((state>>5)&3u)||m->sw!=sw||m->voices!=((state>>10)&63u);',
        'unsigned changed=ui_panic(m,pitch>>22)|(m->pc_faults!=faults)||m->mode!=((state>>3)&3u)||m->sound!=((state>>7)&7u)||m->route!=((state>>5)&3u)||m->sw!=sw||m->voices!=((state>>10)&63u);')
    s=replace(s,'ddr_checks();audio_checks();model_check();',
        '''ddr_checks();audio_checks();model_check();
    // Reload a visible LED-only guide after the short service self-test.  It
    // remains stopped until Push Play (CC85) and never creates note/PCM data.
    static const a138_cue guide[9]={{0,0x0000000f},{24000,0x000000f0},
        {48000,0x00000f00},{72000,0x0000f000},{96000,0x000f0000},
        {120000,0x00f00000},{144000,0x0f000000},{168000,0xf0000000},
        {192000,0}};
    if(!a138_score_load(AUDIO_BASE,guide,9))fail(0xbad03107);''')
    p.write_text(s)
    ui_cc=compiler_prefix(args.riscv_prefix)
    with (out/'ui_firmware_build.log').open('w') as log:
        subprocess.run([ui_cc+'-gcc','-march=rv32im_zicsr','-mabi=ilp32','-msmall-data-limit=0','-O2','-ffreestanding',
            '-Wall','-Wextra','-Werror','-Wno-unused-function','-nostdlib','-nostartfiles','-Wl,--build-id=none','-Wl,-T,firmware/boot.ld',
            '-o','firmware/boot.elf','firmware/start.S','firmware/ui_main.c','firmware/ui_render.c','firmware/ui_runtime.c'],
            cwd=stage,stdout=log,stderr=subprocess.STDOUT,check=True)
        subprocess.run([ui_cc+'-objcopy','-O','binary','firmware/boot.elf','firmware/boot.bin'],cwd=stage,
            stdout=log,stderr=subprocess.STDOUT,check=True)
    ui_binary=(stage/'firmware/boot.bin').read_bytes();assert len(ui_binary)<=16384,'AE350 UI ROM overflow'
    ui_binary=ui_binary.ljust(16384,b'\0')
    (stage/'firmware/boot.mem').write_text(''.join(f'{int.from_bytes(ui_binary[i:i+4],"little"):08x}\n' for i in range(0,len(ui_binary),4)))
    shutil.copy2(ROOT/'rtl/display_data_layout_pkg.svh',stage/'src/memory/display_data_layout_pkg.sv')
    dest=stage/'src/usb_a';dest.mkdir()
    tree=ET.parse(stage/'Prj1.gprj');fl=tree.find('FileList')
    fl.insert(0,ET.Element('File',path='src/memory/display_data_layout_pkg.sv',type='file.verilog',enable='1'))
    shutil.copy2(ROOT/'rtl/audio/gw138k_usb_lifecycle_merge.sv',stage/'src/usb_a/gw138k_usb_lifecycle_merge.sv')
    for source in sorted(scope_dest.glob('*.sv')):
        ET.SubElement(fl,'File',path=source.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    tf_sources=[stage/'src/memory/ddr_address_map_guard.v',stage/'src/audio/tf_rate_pt8211_tx.v']
    tf_sources+=sorted(storage_dest.rglob('*.v'))
    for source in tf_sources:
        ET.SubElement(fl,'File',path=source.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    for source in sorted(music_dest.glob('*.sv')):
        if source.name != 'basic_pitch_tf_board_top.sv':
            ET.SubElement(fl,'File',path=source.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    shutil.copy2(ROOT/'p11.gsc',stage/'constraints/p11.gsc')
    ET.SubElement(fl,'File',path='constraints/p11.gsc',type='file.gsc',enable='1')
    kept_push={'gw138k_push_performance_uart.sv','gw138k_push_workstation_top.v','push2_controls.sv',
               'push2_midi_rx.sv','push2_surface_pixels.sv','push2_led_tx.sv','push2_lights.sv'}
    kept_usb={'gw138k_usb_controlled_audio.sv','gw138k_usb_event_fifo.v'}
    for f in list(fl):
        name=f.get('path','');p=Path(name)
        if (name.startswith('src/push2/') and p.name not in kept_push) or (name.startswith('src/usb_host/') and p.name not in kept_usb):
            fl.remove(f)
    for f in sorted((USB/'src').glob('*')):
        if f.suffix not in ['.v','.sv'] or f.name in ['reference_top.v','gw138k_cpu_pll_cell.v','reset_release.v','video_pll_init.v']:continue
        shutil.copy2(f,dest/f.name)
    ET.SubElement(fl,'File',path='src/memory/display_data_writer.v',type='file.verilog',enable='1')
    ET.SubElement(fl,'File',path='src/memory/display_data_reader.v',type='file.verilog',enable='1')
    shutil.copy2(ROOT/'rtl/push2_usb_a_control.sv',dest/'push2_usb_a_control.sv')
    shutil.copy2(ROOT/'rtl/push2/push2_score_guide.sv',dest/'push2_score_guide.sv')
    ET.SubElement(fl,'File',path='src/usb_a/push2_score_guide.sv',type='file.verilog',enable='1')
    shutil.copy2(ROOT/'rtl/push2_screen_packet_loader.sv',dest/'push2_screen_packet_loader.sv')
    shutil.copy2(ROOT/'rtl/push2_screen_fifo_streamer.sv',dest/'push2_screen_fifo_streamer.sv')
    # The screen streamer and USB FIFO share the 48 MHz host clock.  Give the
    # staged USB core a direct byte input so the existing FIFO need not route
    # every pixel byte through the CPU register acknowledge protocol.
    p=dest/'usbh_core.sv';s=p.read_text()
    s=replace(s,'    input logic [3:0]       reg_be,',
        '    input logic [3:0]       reg_be,\n    input logic             screen_fifo_push_i,\n    input logic [7:0]       screen_fifo_data_i,')
    s=replace(s,'    .data_i(usb_wr_data_data_out_w),\n    .push_i(usb_wr_data_wr_req_w),',
        '    .data_i(screen_fifo_push_i ? screen_fifo_data_i : usb_wr_data_data_out_w),\n    .push_i(screen_fifo_push_i || usb_wr_data_wr_req_w),')
    p.write_text(s)
    for f in sorted(dest.iterdir()):ET.SubElement(fl,'File',path=f.relative_to(stage).as_posix(),type='file.verilog',enable='1')
    ET.indent(tree,space='    ');tree.write(stage/'Prj1.gprj',encoding='utf-8',xml_declaration=True)
    # Add the Push MMIO window and a same-clock screen packet bus master.
    p=dest/'iosys2.v';s=p.read_text()
    s=replace(s,'inout             usb_dp        // USB D+','inout             usb_dp,       // USB D+\n    output mmio_select,mmio_write,output [7:0] mmio_address,\n    output [31:0] mmio_wdata,input mmio_ready,input [31:0] mmio_rdata')
    s=replace(s,'localparam string ROM_FILE = "firmware.hex";','localparam ROM_FILE = "push2_usb_a.hex";')
    s=replace(s,'// Interface to USB host controller','''wire screen_load=dbus_cmd_valid && dbus_cmd_wr && dbus_cmd_a==32'h02000250;
wire screen_active,screen_done,screen_read,screen_write;
wire [7:0] screen_byte;
push2_screen_fifo_streamer screen_loader(
    .clk(clk),.reset_n(resetn),.start(screen_load),
    .pixel_read(screen_read),.pixel_ready(mmio_ready),.pixel_data(mmio_rdata),
    .fifo_push(screen_write),.fifo_data(screen_byte),
    .active(screen_active),.done(screen_done));
assign mmio_select=screen_active?screen_read:
    dbus_cmd_valid && dbus_cmd_a[31:8]==24'h020002 && !screen_load;
assign mmio_write=screen_active?1'b0:dbus_cmd_wr;
assign mmio_address=screen_active?8'h2c:dbus_cmd_a[7:0];
assign mmio_wdata=dbus_cmd_data;
reg mmio_response;
reg [31:0] mmio_result;
always @(posedge clk) begin
    mmio_response<=mmio_select && mmio_ready && !dbus_cmd_wr && !screen_active;
    if(mmio_select && mmio_ready && !dbus_cmd_wr && !screen_active)mmio_result<=mmio_rdata;
end
// Interface to USB host controller''')
    s=replace(s,'usb_sel ? usb_ack :','screen_load ? screen_done : mmio_select ? mmio_ready : usb_sel ? usb_ack :')
    s=replace(s,'wire [31:0] dbus_rdata = dbus_mem_ready ? mem_rdata :','wire [31:0] dbus_rdata = mmio_response ? mmio_result : dbus_mem_ready ? mem_rdata :')
    s=replace(s,'.reg_wdata(dbus_cmd_data), .reg_be(mem_wstrb),',
        '.reg_wdata(dbus_cmd_data), .reg_be(mem_wstrb),\n    .screen_fifo_push_i(screen_write),.screen_fifo_data_i(screen_byte),')
    p.write_text(s)
    p=stage/'src/push2/gw138k_push_workstation_top.v';s=p.read_text()
    start=s.index('    output wire push_htclk');end=s.index('    inout wire usb1_dp',start);s=s[:start]+s[end:]
    start=s.index('    wire usb_event_valid');end=s.index('    wire [31:0] output_pcm',start)
    s=s[:start]+'''    wire mmio_select,mmio_write,mmio_ready;
    wire [7:0] mmio_address;wire [31:0] mmio_wdata,mmio_rdata;
    wire [223:0] usb_words;
    iosys2 u_usb_host(.clk(usb_clk),.resetn(usb_reset_n),.uart_rx(1'b1),.uart_tx(),
        .usb_dp(usb1_dp),.usb_dm(usb1_dn),.mmio_select(mmio_select),.mmio_write(mmio_write),
        .mmio_address(mmio_address),.mmio_wdata(mmio_wdata),.mmio_ready(mmio_ready),.mmio_rdata(mmio_rdata));
'''+s[end:]
    start=s.index('    wire push_valid');end=s.index('    gw138k_usb_controlled_audio u_managed',start)
    s=s[:start]+'''    wire all_usb_valid,all_usb_ready;wire [17:0] all_usb_event;
    wire [447:0] push_snapshot;
    wire [31:0] score_led_mask;wire score_running,record_enabled;
    wire [33:0] service_state_usb;wire service_state_usb_valid;
    wire music_score_valid,music_score_ready,score_usb_valid,score_usb_ready;
    wire [6:0] music_score_note,score_usb_note;
    music_async_fifo #(.WIDTH(7),.ADDRESS_BITS(2)) u_score_push_cdc(
        .write_clk_i(clk_50m),.write_rst_ni(reset_n),
        .write_valid_i(music_score_valid),.write_ready_o(music_score_ready),
        .write_data_i(music_score_note),
        .read_clk_i(usb_clk),.read_rst_ni(usb_reset_n),
        .read_valid_o(score_usb_valid),.read_ready_i(score_usb_ready),
        .read_data_o(score_usb_note));
    gw138k_stream_cdc #(.WIDTH(34)) u_service_push_cdc(
        .reset_n(reset_n && audio_reset_n && usb_reset_n),.source_clk(audio_clk),.destination_clk(usb_clk),
        .source_valid(audio_sample_valid),.source_data({record_enabled,score_running,score_led_mask}),
        .destination_valid(service_state_usb_valid),.destination_data(service_state_usb));
    wire [63:0] display_summary,display_summary_usb;wire display_summary_valid,display_summary_usb_valid;
    gw138k_stream_cdc #(.WIDTH(64)) u_display_push_cdc(
        .reset_n(reset_n && memory_reset_n && usb_reset_n),.source_clk(memory_clk),.destination_clk(usb_clk),
        .source_valid(display_summary_valid),.source_data(display_summary),
        .destination_valid(display_summary_usb_valid),.destination_data(display_summary_usb));
    push2_usb_a_control u_push(.clk(usb_clk),.reset_n(usb_reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .feedback_clk(clk_50m),.feedback_reset_n(reset_n),.performance_words(push_snapshot),
        .display_meta_data(display_summary_usb),.display_meta_valid(display_summary_usb_valid),
        .service_state_data(service_state_usb),.service_state_valid(service_state_usb_valid),
        .score_valid(score_usb_valid),.score_ready(score_usb_ready),.score_note(score_usb_note),
        .analysis_done(music_analysis_done),
        .select(mmio_select),.write(mmio_write),.address(mmio_address),.wdata(mmio_wdata),.ready(mmio_ready),.rdata(mmio_rdata),
        .audio_valid(all_usb_valid),.audio_ready(all_usb_ready),.audio_event(all_usb_event),.telemetry(usb_words));
'''+s[end:]
    s=replace(s,'.app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),\n        .sample_data(output_mid)',
             '.app_wrdy(app_wrdy),.app_rdata(app_rdata),.app_rvalid(app_rvalid),.memory_flags(memory_flags),\n        .push_display_summary(display_summary),.push_display_summary_valid(display_summary_valid),\n        .sample_data(output_mid)')
    s=replace(s,'.pc_uart_rx_i(pc_uart_rx_i),.performance_words_o(performance_words),',
        '.pc_uart_rx_i((music_model_status==4\'d14 || tf_scope_control_audio[12]) ? pc_uart_rx_i : 1\'b1),.performance_words_o(performance_words),\n        .led_mask_o(score_led_mask),.score_running_o(score_running),.record_enabled_o(record_enabled),\n        .scope_status_o(scope_status_audio),.tf_scope_control_o(tf_scope_control_audio),.sample_ce_o(synth_sample_ce),')
    s=replace(s,'.push_words(push_words),','.push_words(224\'d0),')
    s=replace(s,'module gw138k_push_workstation_top (',f'''module gw138k_push_workstation_top #(
    parameter integer TF_AUDIO_KIND={tf_audio_kind}
) (''')
    s=replace(s,'    input wire pc_uart_rx_i,',
        '''    input wire pc_uart_rx_i,
    input wire sd_miso,
    output wire sd_mosi,sd_sck,sd_cs_n,''')
    s=replace(s,'    wire [31:0] output_pcm,output_reference,active_voices,display_status;',
        '''    wire [31:0] output_pcm,output_reference,active_voices,display_status;
    wire synth_hp_bck,synth_hp_ws,synth_hp_din,synth_pa_en,synth_sample_ce;
    wire [31:0] scope_status_audio,tf_scope_control_audio;
    wire tf_mode_audio=tf_scope_control_audio[12];
    wire tf_run_audio=tf_scope_control_audio[13];
    wire [31:0] tf_scope_control_50;
    wire tf_control_valid;
    reg [4:0] tf_control_divider;
    always @(posedge audio_clk or negedge audio_reset_n)
        if(!audio_reset_n) tf_control_divider<=0;else tf_control_divider<=tf_control_divider+1'b1;
    // Periodic held-state publication retries changes; epoch differences alone
    // at the destination restart playback. Audio is never backpressured.
    gw138k_stream_cdc #(.WIDTH(32)) u_tf_control_cdc(
        .reset_n(reset_n && audio_reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(tf_control_divider==31),.source_data(tf_scope_control_audio),
        .drop_count(),.destination_valid(tf_control_valid),.destination_data(tf_scope_control_50));
    reg [15:0] tf_epoch_50;
    always @(posedge clk_50m or negedge reset_n)
        if(!reset_n) tf_epoch_50<=0;else if(tf_control_valid) tf_epoch_50<=tf_scope_control_50[31:16];
    wire tf_scope_restart=tf_control_valid && tf_scope_control_50[31:16]!=tf_epoch_50;
    wire tf_mode_50=tf_scope_control_50[12];
    wire tf_run_50=tf_scope_control_50[13];
    wire synth_display_valid;
    wire [31:0] synth_display_pcm,synth_display_reference,synth_display_voices,synth_display_status;
    wire final_tf_selected,final_switching;
    wire final_sample_valid;
    wire [31:0] final_pcm;
    pt8211_observer u_final_output_observer(
        .clk(audio_clk),.reset_n(audio_reset_n && !final_switching),
        .bck(hp_bck),.ws(hp_ws),.din(hp_din),.frame_reference(32'd0),
        .pcm_pair(final_pcm),.sample_valid(final_sample_valid),.trigger_reference());
    gw138k_stream_cdc #(.WIDTH(32)) u_final_output_cdc(
        .reset_n(reset_n && audio_reset_n),.source_clk(audio_clk),.destination_clk(clk_50m),
        .source_valid(final_sample_valid && !final_switching),.source_data(final_pcm),
        .drop_count(),.destination_valid(output_sample_valid),.destination_data(output_pcm));
    assign output_reference=tf_mode_50 ? 32'd0 : synth_display_reference;
    assign active_voices=tf_mode_50 ? 32'd0 : synth_display_voices;
    assign display_status=synth_display_status;
    wire [3:0] music_model_status;
    wire music_report_sending,music_report_serial,runtime_serial;
    wire music_pcm_ready;
    wire music_analysis_done;
    reg music_model_ready_q;
    reg [21:0] music_restart_delay;
    wire music_model_ready=music_model_status==4'd14;
    wire music_restart=music_model_ready && !music_model_ready_q;
    wire tf_restart=tf_scope_restart || (music_restart && !tf_mode_50);
    reg music_capture_interrupted;
    // An incomplete NN capture cannot splice unrelated tracks together.
    // A system reset/model upload rearms recognition after playback interrupts it.
    always @(posedge clk_50m or negedge reset_n)
        if(!reset_n) music_capture_interrupted<=0;
        else if(tf_mode_50 && music_model_ready_q && !music_analysis_done) music_capture_interrupted<=1;
    wire music_analysis_enable=music_model_ready_q && music_restart_delay==0 &&
        !tf_mode_50 && !music_capture_interrupted;
    always @(posedge clk_50m or negedge reset_n) begin
        if(!reset_n) begin music_model_ready_q<=0;music_restart_delay<=0;end
        else begin
            music_model_ready_q<=music_model_ready;
            if(music_restart) music_restart_delay<=22'd2_500_000;
            else if(music_restart_delay!=0) music_restart_delay<=music_restart_delay-1'b1;
        end
    end
    assign debug_uart_tx=music_report_sending ? music_report_serial : runtime_serial;''')
    s=replace(s,'.hp_bck(hp_bck),.hp_ws(hp_ws),.hp_din(hp_din),.pa_en(pa_en),',
        '.hp_bck(synth_hp_bck),.hp_ws(synth_hp_ws),.hp_din(synth_hp_din),.pa_en(synth_pa_en),')
    s=replace(s,'.display_valid_o(output_sample_valid),.display_pcm_o(output_pcm),.display_reference_o(output_reference),',
        '.display_valid_o(synth_display_valid),.display_pcm_o(synth_display_pcm),.display_reference_o(synth_display_reference),')
    s=replace(s,'.display_voices_o(active_voices),.display_status_o(display_status),',
        '.display_voices_o(synth_display_voices),.display_status_o(synth_display_status),')
    s=replace(s,'.video_diagnostics(video_diagnostics),.serial_out(debug_uart_tx),',
        '.video_diagnostics(video_diagnostics),.serial_out(runtime_serial),')
    s=replace(s,'    wire [31:0] app_wmask;\n    ddr3_platform u_memory (',
        '''    wire [31:0] app_wmask;
    wire audio_ddr_req,audio_ddr_write,audio_ddr_ready,audio_ddr_response;
    wire [28:0] audio_ddr_address;wire [255:0] audio_ddr_data;
    wire signed [31:0] tf_pcm_left,tf_pcm_right;
    wire analysis_pcm_valid,analysis_pcm_end;
    wire signed [15:0] analysis_pcm_left,analysis_pcm_right;
    wire [19:0] analysis_sample_rate;
    wire tf_pcm_valid,tf_source_active,tf_format_ready,tf_unsupported,tf_ddr_error;
    wire [19:0] tf_sample_rate;wire [31:0] tf_file_size;wire [4:0] tf_track_count;
    wire tf_sample_ce,tf_hp_bck,tf_hp_ws,tf_hp_din,tf_pa_en;
    tf_workstation_audio_bridge #(
        .AUDIO_KIND(TF_AUDIO_KIND),
        .FILE_EXT(TF_AUDIO_KIND==1 ? "MP3" : (TF_AUDIO_KIND==3 ? "FLA" : "WAV"))
    ) u_tf_audio(
        .clk_50m(clk_50m),.reset_n(reset_n),.audio_clk(audio_clk),.audio_reset_n(audio_reset_n),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_ready(memory_calibrated && memory_reset_n),.restart(tf_restart),.track_index(tf_scope_control_50[11:8]),
        .sd_miso(sd_miso),.sd_cs_n(sd_cs_n),.sd_sck(sd_sck),.sd_mosi(sd_mosi),
        .sample_ce(tf_sample_ce),.pcm_left(tf_pcm_left),.pcm_right(tf_pcm_right),
        .analysis_pcm_valid(analysis_pcm_valid),.analysis_pcm_end(analysis_pcm_end),
        .playback_hold_i(tf_scope_control_50[14] && (!tf_mode_50 || !tf_run_50)),
        .analysis_hold_i(music_model_ready_q && !music_analysis_done && !tf_mode_50 && !music_capture_interrupted),
        .analysis_enable_i(music_analysis_enable),
        .analysis_pcm_ready_i(music_pcm_ready),
        .analysis_pcm_left(analysis_pcm_left),.analysis_pcm_right(analysis_pcm_right),
        .analysis_sample_rate(analysis_sample_rate),
        .pcm_active(tf_pcm_valid),.source_active(tf_source_active),
        .sample_rate_hz(tf_sample_rate),.format_ready(tf_format_ready),.unsupported(tf_unsupported),
        .ddr_error(tf_ddr_error),.file_size(tf_file_size),.track_count(tf_track_count),
        .ddr_valid(audio_ddr_req),.ddr_write(audio_ddr_write),.ddr_address(audio_ddr_address),
        .ddr_data(audio_ddr_data),.ddr_ready(audio_ddr_ready),.ddr_response(audio_ddr_response),
        .ddr_response_data(app_rdata));
    wire music_ddr_req,music_ddr_write,music_ddr_ready,music_ddr_response;
    wire [28:0] music_ddr_address;
    wire [255:0] music_ddr_data;
    wire [31:0] music_ddr_mask;
    wire music_result_valid;
    wire [6:0] music_result_note;
    wire [15:0] music_result_frame;
    basic_pitch_workstation_link u_music (
        .clk_50m(clk_50m),.reset_n(reset_n),
        .memory_clk(memory_clk),.memory_reset_n(memory_reset_n),
        .memory_calibrated(memory_calibrated),.model_serial(pc_uart_rx_i),
        .flash_miso(1'b1),.flash_cs_n(),.flash_clk(),.flash_mosi(),
        .analysis_enable(music_analysis_enable),
        .pcm_valid(analysis_pcm_valid),.pcm_end(analysis_pcm_end),
        .pcm_left(analysis_pcm_left),
        .pcm_right(analysis_pcm_right),.sample_rate(analysis_sample_rate),
        .format_ready(tf_format_ready),.source_active(tf_source_active),
        .pcm_ready(music_pcm_ready),
        .model_status(music_model_status),.result_valid(music_result_valid),
        .result_note(music_result_note),.result_frame(music_result_frame),
        .score_valid(music_score_valid),.score_ready(music_score_ready),.score_note(music_score_note),
        .analysis_done(music_analysis_done),
        .report_sending(music_report_sending),.report_serial(music_report_serial),
        .ddr_req(music_ddr_req),.ddr_write(music_ddr_write),
        .ddr_address(music_ddr_address),.ddr_data(music_ddr_data),
        .ddr_mask(music_ddr_mask),.ddr_ready(music_ddr_ready),
        .ddr_response(music_ddr_response),.ddr_read_data(app_rdata));
    wire [19:0] tf_dac_rate=(tf_format_ready && !tf_unsupported &&
        tf_sample_rate>=20'd8000 && tf_sample_rate<=20'd96000) ? tf_sample_rate : 20'd0;
    tf_rate_pt8211_tx #(.BCK_HALF_CYCLES(25),.STEREO_ENABLE(1),.RATE_MUL(916260)) u_tf_dac(
        .clk(audio_clk),.reset_n(audio_reset_n),.sample_data(tf_mode_audio && !tf_run_audio ? 32'sd0 : tf_pcm_left),
        .sample_right(tf_mode_audio && !tf_run_audio ? 32'sd0 : tf_pcm_right),
        .sample_valid(tf_pcm_valid || (tf_mode_audio && !tf_run_audio)),.rate_hz(tf_dac_rate),.sample_tick(tf_sample_ce),
        .hp_bck(tf_hp_bck),.hp_ws(tf_hp_ws),.hp_din(tf_hp_din),.pa_en(tf_pa_en),
        .underrun_count(),.frame_count(),.sample_revision(24'd0),.sample_nonzero_voices(32'd0),
        .trace_dac_done(),.trace_dac_revision(),.trace_dac_nonzero_voices(),
        .sample_trigger_reference(32'd0),.frame_trigger_reference());
    scope_dac_select u_scope_output(
        .clk_i(audio_clk),.rst_ni(audio_reset_n),
        .scope_enable_i(scope_status_audio[8]),.tf_source_active_i(tf_mode_audio || (!tf_scope_control_audio[14] && tf_source_active)),
        .synth_frame_tick_i(synth_sample_ce),.tf_frame_tick_i(tf_sample_ce),
        .synth_bck_i(synth_hp_bck),.synth_ws_i(synth_hp_ws),.synth_din_i(synth_hp_din),.synth_pa_i(synth_pa_en),
        .tf_bck_i(tf_hp_bck),.tf_ws_i(tf_hp_ws),.tf_din_i(tf_hp_din),.tf_pa_i(tf_pa_en),
        .hp_bck_o(hp_bck),.hp_ws_o(hp_ws),.hp_din_o(hp_din),.pa_en_o(pa_en),
        .tf_selected_o(final_tf_selected),.switching_o(final_switching));
    ddr_address_map_guard u_ddr_address_map_guard();
    ddr3_platform u_memory (''')
    s=replace(s,'.cpu_data(cpu_mem_data),.cpu_mask(cpu_mem_mask),.cpu_ready(cpu_mem_ready),.cpu_response(cpu_mem_response),',
        '''.cpu_data(cpu_mem_data),.cpu_mask(cpu_mem_mask),.cpu_ready(cpu_mem_ready),.cpu_response(cpu_mem_response),
        .audio_req(audio_ddr_req),.audio_write(audio_ddr_write),.audio_address(audio_ddr_address),
        .audio_data(audio_ddr_data),.audio_ready(audio_ddr_ready),.audio_response(audio_ddr_response),
        .music_req(music_ddr_req),.music_write(music_ddr_write),.music_address(music_ddr_address),
        .music_data(music_ddr_data),.music_mask(music_ddr_mask),
        .music_ready(music_ddr_ready),.music_response(music_ddr_response),''')
    p.write_text(s)
    p=stage/'src/video/hdmi_display.v';s=p.read_text()
    s=replace(s,'    output wire audio_ready,audio_response,',
        '''    output wire audio_ready,audio_response,
    input wire music_req,music_write,
    input wire [28:0] music_address,
    input wire [255:0] music_data,
    input wire [31:0] music_mask,
    output wire music_ready,music_response,''')
    s=replace(s,'        .audio_data(audio_data),.audio_ready(audio_ready),.audio_response(audio_response),',
        '''        .audio_data(audio_data),.audio_ready(audio_ready),.audio_response(audio_response),
        .music_valid(music_req),.music_write(music_write),.music_address(music_address),
        .music_data(music_data),.music_mask(music_mask),
        .music_ready(music_ready),.music_response(music_response),''')
    p.write_text(s)
    # Reuse existing USB->50MHz telemetry snapshot for the new P138 record.
    p=stage/'src/push2/gw138k_push_performance_uart.sv';s=p.read_text()
    s=replace(s,'payload<={usb_snapshot,sequence_count-32\'d1};','payload<={224\'d0,sequence_count-32\'d1};')
    s=replace(s,'payload<={push_words,sequence_count-32\'d1};','payload<={usb_snapshot,sequence_count-32\'d1};');p.write_text(s)
    p=stage/'constraints/tang_mega_138k.cst';s=p.read_text()
    s='\n'.join(line for line in s.splitlines() if '"push_' not in line)+'\n'+(ROOT/'p11.cst').read_text()
    # The merged netlist names this PLL helper output pll_reset_s1.
    s=s.replace('u_audio_clock/g_hardware.u_pll/u_pll_init/pll_reset_s"',
                'u_audio_clock/g_hardware.u_pll/u_pll_init/pll_reset_s1"')
    p.write_text(s)
    p=stage/'constraints/tang_mega_138k.sdc';s=p.read_text().split('# CH569 HSPI16')[0]
    s='\n'.join(line for line in s.splitlines() if 'u_usb_host/u_fifo' not in line)+'\n'
    s=replace(s,'set_false_path -to [get_pins {u_managed/effect_mask_sync*/RESET u_managed/effect_mask_meta*/RESET}]\n','')
    # Same reset and opposite-direction mailbox can share local release FFs.
    s=s.replace('u_runtime/u_usb_cdc/source_release*/CLEAR u_runtime/u_usb_cdc/destination_release*/CLEAR',
        'u_runtime/u_usb_cdc/source_release*/CLEAR u_runtime/u_usb_cdc/destination_release*/CLEAR u_push/feedback/source_release*/CLEAR u_push/feedback/destination_release*/CLEAR')
    # The merged netlist shares the performance mailbox release flops with
    # another CDC instance. Keep the surviving synchronizer endpoints only.
    s=s.replace('u_runtime/u_performance_cdc/source_release*/CLEAR u_runtime/u_performance_cdc/destination_release*/CLEAR ', '')
    # Identical audio/50-MHz release chains are now retained in the TF
    # mailbox; synthesized telemetry mailboxes reuse these exact reset nets.
    s=s.replace('u_runtime/u_performance_cdc/source_release*/CLEAR u_runtime/u_performance_cdc/destination_release*/CLEAR',
        'u_tf_control_cdc/source_release*/CLEAR u_tf_control_cdc/destination_release*/CLEAR')
    s+=(ROOT/'usb_a.sdc').read_text();p.write_text(s)
    usb_firmware=stage_usb_firmware(ROOT,stage,out,args.riscv_prefix)
    (out/'usb_firmware_metadata.json').write_text(json.dumps(usb_firmware,indent=2)+'\n')
    hashes={str(p.relative_to(stage)):sha(p) for p in stage.rglob('*') if p.is_file()}
    (out/'workstation_inputs.json').write_text(json.dumps(hashes,indent=2)+'\n')
    origins=dict(
        workstation=WORK.relative_to(ROOT.parents[3]).as_posix(),
        usb_host=USB.relative_to(ROOT.parents[3]).as_posix(),hardware_tested=False,
        usb_host_implementation='VexRiscv firmware + RTL PHY/Host; no CH569',
        build_mode=build_mode,tf_decoder=args.tf_audio_kind,usb_firmware=usb_firmware,
        sources={str(p.relative_to(ROOT)):sha(p) for p in ROOT.rglob('*') if p.is_file() and 'results' not in p.relative_to(ROOT).parts and '__pycache__' not in p.parts})
    (out/'origins.json').write_text(json.dumps(origins,indent=2)+'\n');print(out,flush=True)
    # A prepared or failed project must not become the latest workstation.
    if args.prepare_only:return
    if args.reuse_synthesis:
        previous=args.reuse_synthesis.resolve();old=json.loads((previous/'workstation_inputs.json').read_text())
        # boot.elf carries linker metadata and is not a Gowin project input;
        # boot.mem is the exact synthesized ROM image and remains compared.
        assert all(old.get(p)==h and sha(previous/'Prj1'/p)==h for p,h in hashes.items()
                   if not p.startswith('constraints/') and not p.endswith('.elf')),'changed RTL/firmware cannot reuse synthesis'
        shutil.copytree(previous/'Prj1/impl/gwsynthesis',stage/'impl/gwsynthesis')
        (out/'reused_synthesis.json').write_text(json.dumps(dict(source=str(previous),non_constraint_inputs_identical=True),indent=2)+'\n')
    with (out/'gowin.log').open('w') as log:
        r=subprocess.run([str(Path.home()/'.local/bin/gw_sh'),'scripts/build.tcl'],cwd=stage,env=dict(os.environ,PRJ1_FLOW='syn' if args.synthesis_only else 'pnr' if args.reuse_synthesis else 'all'),stdout=log,stderr=subprocess.STDOUT)
    changed=[p for p,h in hashes.items() if sha(stage/p)!=h]
    (out/'tool_result.json').write_text(json.dumps(dict(exit_code=r.returncode,inputs_unchanged=not changed,changed=changed,hardware_tested=False),indent=2)+'\n')
    print('Gowin exit',r.returncode,'changed inputs',changed,flush=True)
    if r.returncode or changed:raise SystemExit(1)
    memory=audit_workstation_memory(out,build_mode)
    print('Full workstation SYN BSRAM',memory['bsram'],'/',memory['bsram_capacity'],flush=True)
    if not args.no_update_latest:
        (ROOT/'LATEST_BUILD.txt').write_text(out.relative_to(ROOT).as_posix()+'\n')
        latest=dict(build=out.relative_to(ROOT).as_posix(),build_mode=build_mode,
                    memory_report=(out/'workstation_memory.json').relative_to(ROOT).as_posix(),
                    bsram=memory['bsram'],bsram_measurement_stage='synthesis',
                    tf_decoder=args.tf_audio_kind,basic_pitch_elaborated=memory['basic_pitch_elaborated'],
                    timing_closed=None,hardware_tested=False)
        (ROOT/'LATEST_WORKSTATION.json').write_text(json.dumps(latest,indent=2)+'\n')
if __name__=='__main__':main()
