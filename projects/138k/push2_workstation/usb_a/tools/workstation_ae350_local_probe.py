"""Prepare a minimal same-platform AE350 local-memory probe; never run EDA or a board."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zlib

from tools.stage_usb_firmware import compiler_prefix, sha
from tools.stage_ae350_firmware import decode_rom
from tools.workstation_baselines import load_baseline
from tools.workstation_custom_clocks import clock_bundle
from tools.workstation_hdmi_isolation import gao_configuration as base_gao
from tools.workstation_audio_probe import load_config as audio_config, pin_constraints as audio_constraints
from tools.workstation_pinout import prepare as prepare_pinout, render_constraints, parse_locations
from tools.ae350_local_memory import local_memory_report, verify_elf_image, call_chain_report
from tools.workstation_synthesis_netlist import SynthesisNetlist

TOP='workstation_ae350_local_memory_probe_top'
BASE='ae350_local_memory_probe'
FIRMWARE=('start.S','start_ilm_dlm.inc','boot_ilm_dlm.ld',
          'probes/local_memory_probe.c','probes/local_memory_probe_trap.S')
NATIVE=('rtl/memory/workstation_ae350_boot_memory.sv',
        'rtl/clock/workstation_ae350_rtc.sv',
        'rtl/probe/workstation_ae350_probe_uart.sv','rtl/probe/'+TOP+'.sv')
LOCKED=('riscv_ae350_config.v','src/ae350/riscv_ae350_config.v',
        'src/ae350/riscv_ae350_top.v','src/ae350/riscv_ae350_soc.v',
        'src/ae350/gw138k_cpu_pll_cell.v','vendor/sipeed_dvi/video_pll_init.v')
SAFE_DAC_PINS=dict(ak_pdn=['C13'],ak_mclk=['B13'],ak_bick=['A13'],ak_lrck=['B15'],ak_sdata=['A14'],ak_smute=['A15'])
CPU_PLL_INSTANCE='u_cpu_pll/PLL_inst'
CPU_PLL_SITE='PLL_R[0]'
CPU_PLL_CONSTRAINT=f'INS_LOC "{CPU_PLL_INSTANCE}" {CPU_PLL_SITE};'
RTC_CLOCK_PIN='u_rtc/rtc_tick_s1/Q'
RTC_CLOCK_SDC=('create_generated_clock -name cpu_rtc_bound -source [get_ports {clk_50m}] '
               '-divide_by 1524 [get_pins {'+RTC_CLOCK_PIN+'}]')
BSRAM_METADATA=('rtl/probe/AE350_BSRAM_SNAPSHOT_CONTRACT.md',
    'tools/workstation_ae350_snapshot_ram_audit.py','tools/workstation_synthesis_netlist.py',
    'tools/decode_ae350_banked_gao.py','tools/decode_ae350_local_probe.py')

def native_sources(gao_mode):
    if gao_mode not in ('full64','banked4','bsram4'):raise ValueError('unknown probe GAO mode')
    if gao_mode=='bsram4':
        return tuple(n for n in NATIVE if n!='rtl/probe/workstation_ae350_probe_uart.sv')+(
            'rtl/memory/workstation_sdp.sv','rtl/probe/workstation_ae350_probe_snapshot_ram.sv')
    return NATIVE+(('rtl/probe/workstation_ae350_probe_gao_banks.sv',) if gao_mode=='banked4' else ())

def gao_record(gao_mode):
    native_sources(gao_mode)
    result=dict(schema='A1386401',capture_bits=2208,word_count=64,storage_depth=128,
        snapshot='same clk_50m published bank and sequence as UART; word61 bit4 marks timeout',
        io='registered RTL output-drive level and modulo2^30 edge count; no pad or external receiver readback')
    if gao_mode=='banked4':
        result.update(mode='banked4',schema='A1386402',capture_bits=704,pages=4,page_words=16,page_cycles=4,
            snapshot='four fixed pages of one frozen UART snapshot; only a new sequence replaces it at page3-to0',
            io='frozen with the new UART sequence at a sweep boundary; no pad or external receiver readback')
    if gao_mode=='bsram4':
        result.update(mode='bsram4',schema='A1386403',capture_bits=704,pages=4,page_words=16,page_cycles=4,
            snapshot='canonical double-buffered synchronous RAM, prepared before publication; new sequence selected only at page3-to0',
            io='frozen at adoption of the new sequence at sweep boundary; no pad or external receiver readback',
            storage=dict(logical_lanes=8,lane_bits=16,banks=2,words_per_snapshot=64,group_bits=128,
                prepare_copy_cycles=16,read_latency_cycles=1,physical_bsram_verified=False),
            publication_delay='16 reference copy clocks plus one publish edge after settled held capture; initial timeout also initializes one zero bank',
            uart_payload_wait='tagged32-bit cache; matching response within one16-clock sweep, launch at most one further edge later; no read-port stealing')
    return result

def audit_gao_synthesis(netlist_text,gao_mode='full64'):
    """Require every declared GAO bit to survive as a 50MHz register.

    Source/prepare checks cannot establish this. Root calls this on the new
    actual synthesis netlist before accepting a new physical capture identity.
    """
    n=SynthesisNetlist(netlist_text,TOP)
    bits={}
    for name,cell in n.cells.items():
        if not cell['kind'].startswith('DFF'):continue
        match=re.fullmatch(r'status_50mhz\[(\d+)\]',n.pin(name,'Q'))
        if match:
            bit=int(match[1])
            if bit in bits or n.pin(name,'CLK')!='clk_50m':
                raise ValueError('GAO bit has duplicate ownership or wrong clock')
            bits[bit]=name
    width=gao_record(gao_mode)['capture_bits']
    if set(bits)!=set(range(width)):
        raise ValueError(f'complete {width}-bit GAO register bank not present in actual netlist')
    result=dict(registered_bits=width,clock='clk_50m',snapshot_words=64,gao_mode=gao_mode,
        physical_timing_verified=False,external_uart_reception_verified=False)
    if gao_mode=='bsram4':
        from tools.workstation_ae350_snapshot_ram_audit import audit
        result['snapshot_ram']=audit(n)
    return result

def audit_rtc_synthesis(netlist_text):
    n=SynthesisNetlist(netlist_text,TOP)
    instance=RTC_CLOCK_PIN.rpartition('/')[0]
    if (n.cells.get(instance,{}).get('kind')!='DFFCE' or
            n.pin(instance,'CLK')!='clk_50m' or
            n.pin(instance,'Q')!=n.pin('u_cpu','rtc_tick') or
            n.pin(instance,'Q') in ('clk_50m','core_clk','ram_clk')):
        raise ValueError('probe RTC register/constraint target or hard-IP wiring changed')
    return dict(pin=RTC_CLOCK_PIN,cell='DFFCE',source='clk_50m',
                hard_ip_wrapper_port='u_cpu/rtc_tick',average_hz=32768,sta_minimum_period_cycles=1524)

def audit_cpu_pll_constraint(cst):
    # MUG1031 v1.3.1 section 7.3: CORE_CLK must use PLL_R[0].clkout1;
    # an explicit PLL_ADV location constraint is mandatory, even with passing STA.
    locations=[line.strip() for line in cst.splitlines() if line.lstrip().startswith('INS_LOC')]
    if locations!=[CPU_PLL_CONSTRAINT]:
        raise ValueError('AE350 CORE_CLK requires one explicit '+CPU_PLL_CONSTRAINT)

def audit_cpu_pll_placement(timing_report):
    """Fail closed on actual routed PLL location; this is not a complete STA gate."""
    rows=re.findall(r'\b(PLL_[A-Z]+\[\d+\])\s+'+re.escape(CPU_PLL_INSTANCE)+r'/(CLKOUT\d+)\s*$',
                    timing_report,re.M)
    if not rows or not any(pin=='CLKOUT1' for _,pin in rows):
        raise ValueError('routed AE350 CORE_CLK PLL evidence missing')
    if any(site!=CPU_PLL_SITE for site,_ in rows):
        raise ValueError('routed AE350 CORE_CLK PLL violates mandatory '+CPU_PLL_SITE)
    return dict(instance=CPU_PLL_INSTANCE,site=CPU_PLL_SITE,core_output='CLKOUT1',
                reported_rows=len(rows),outputs=sorted(set(pin for _,pin in rows)))

def safe_dac_constraints(root):
    text,references=audio_constraints(root,audio_config(root))
    selected='\n'.join(line for line in text.splitlines()
        if (match:=re.match(r'IO_(?:LOC|PORT)\s+"([^"]+)"',line)) and match[1] in SAFE_DAC_PINS)+'\n'
    if parse_locations(selected)!=SAFE_DAC_PINS:raise ValueError('B7 audited DAC safety pin mapping changed')
    return selected,references

def payload():
    words=[]
    for index in range(8192):
        value=index^0xa1386401
        value^=(value<<13)&0xffffffff;value^=value>>17;value^=(value<<5)&0xffffffff
        words.append(value&0xffffffff)
    if 0 in words or len(set(words))!=8192:raise ValueError('probe payload lost uniqueness')
    raw=b''.join(value.to_bytes(4,'little') for value in words)
    return words,dict(words=8192,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
        crc32=zlib.crc32(raw),first=words[0],last=words[-1],algorithm='xorshift32(index xor 0xa1386401), shifts 13/17/5, little endian')

def firmware(root,output,prefix):
    output.mkdir(parents=True,exist_ok=False)
    prefix=compiler_prefix(prefix)
    identities={}
    for name in FIRMWARE:
        source=root/'firmware/ae350'/name;target=output/Path(name).name
        identities['firmware/ae350/'+name]=sha(source);shutil.copyfile(source,target)
    words,data=payload()
    (output/'probe_payload.inc').write_text(''.join(f'0x{word:08x}u,\n' for word in words))
    (output/'probe_payload.h').write_text(''.join(f'#define PROBE_PAYLOAD_{name} 0x{data[key]:08x}u\n'
        for name,key in [('CRC','crc32'),('FIRST','first'),('LAST','last')]))
    commands=[];versions={}
    for tool in ('gcc','objcopy','objdump','size','nm'):
        versions[tool]=subprocess.check_output([prefix+'-'+tool,'--version'],text=True).splitlines()[0]
    flags=['-march=rv32im_zicsr_zifencei','-mabi=ilp32','-msmall-data-limit=0','-O2','-ffreestanding',
           '-fno-jump-tables','-fcallgraph-info=su','-fstack-usage','-Wall','-Wextra','-Werror','-DA138_ILM64K_DLM64K']
    with (output/'build.log').open('w') as log:
        def run(command):
            commands.append(command);subprocess.run(command,cwd=output,stdout=log,stderr=subprocess.STDOUT,check=True)
        for name in ('start.S','local_memory_probe.c','local_memory_probe_trap.S'):
            run([prefix+'-gcc',*flags,'-c',name,'-o',Path(name).stem+'.o'])
        run([prefix+'-gcc',*flags,'-nostdlib','-nostartfiles',
            '-Wl,--build-id=none,--defsym=__boot_rom_bytes=65536,-Map=firmware.map,-T,boot_ilm_dlm.ld',
            'start.o','local_memory_probe.o','local_memory_probe_trap.o','-o','firmware.elf'])
        run([prefix+'-objcopy','-O','binary','firmware.elf','firmware.bin'])
    for tool,name in [('size','firmware.size'),('nm','firmware.nm'),('objdump','firmware.dis')]:
        option=['-n'] if tool=='nm' else ['-d'] if tool=='objdump' else []
        (output/name).write_text(subprocess.check_output([prefix+'-'+tool,*option,'firmware.elf'],cwd=output,text=True))
    raw=(output/'firmware.bin').read_bytes()
    capacity=local_memory_report((output/'firmware.size').read_text(),(output/'firmware.nm').read_text(),len(raw),65536)
    if not 16384<len(raw)<60000 or capacity['ilm_runtime_bytes']>=60000:
        raise ValueError('probe must exercise upper ROM while leaving safe ILM pattern space')
    elf=verify_elf_image(output/'firmware.elf',raw,capacity['symbols'],65536)
    image=raw.ljust(65536,b'\0')
    (output/'boot.mem').write_text(''.join(f'{int.from_bytes(image[i:i+4],"little"):08x}\n' for i in range(0,65536,4)))
    frames=[]
    for path in output.glob('*.su'):
        for line in path.read_text().splitlines():
            name,count,kind=line.split('\t');frames.append(dict(function=name,bytes=int(count),kind=kind))
    stack=call_chain_report(output,frames,(output/'firmware.dis').read_text(),16384)
    for name,expected in identities.items():
        if sha(root/name)!=expected or sha(output/Path(name).name)!=expected:
            raise ValueError('probe firmware source changed during compilation: '+name)
    symbols={}
    for line in (output/'firmware.nm').read_text().splitlines():
        fields=line.split()
        if len(fields)==3 and re.fullmatch('[0-9a-f]+',fields[0]):symbols[fields[2]]=int(fields[0],16)
    result=dict(input_sha256=identities,tool_versions=versions,commands=commands,payload=data,capacity=capacity,probe_symbols=symbols,
        elf_image_validation=elf,call_chain_stack=stack,compiler_stack_frames=frames,
        elf_sha256=sha(output/'firmware.elf'),binary_sha256=sha(output/'firmware.bin'),rom_sha256=sha(output/'boot.mem'),
        loader_policy='unchanged maintained A138_ILM64K_DLM64K loader, explicit 64KiB cold ROM',
        counter_policy='read-only mcycle/minstret high-low-high snapshots; no enable/inhibit write; optional CSR exact-site recovery',
        trap_policy='stackless probe handler after services_main only; precise illegal-CSR recovery; all other traps halt',
        hardware_tested=False)
    (output/'build_metadata.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def constraints(root,gao_mode='full64'):
    selected=('clk_50m','cpu_ram50','cpu_core100')
    lines=[line for line in clock_bundle(root)['sdc'].splitlines() if any('-name '+name+' ' in line for name in selected)]
    if len(lines)!=3:raise ValueError('probe clock policy drift')
    # The fractional RTC has bounded edge jitter. Use its minimum possible
    # two-half-period length as a conservative periodic STA bound (not its
    # 32.768kHz average), without removing paths or changing other clocks.
    lines.append(RTC_CLOCK_SDC)
    first=('u_uart/request_meta_s0/D u_uart/ack_meta_s0/D u_uart/flags_meta*_s0/D '
           'upper_sync_0_s0/D unmapped_sync_0_s0/D rom_health_sync_0_s0/D upper_health_sync_0_s0/D')
    lines += [f'set_max_delay 15.000 -to [get_pins {{{first}}}]',
              f'set_false_path -hold -to [get_pins {{{first}}}]',
              'set_max_delay 20.000 -from [get_regs {u_uart/held_words*}] -to [get_regs {u_uart/words*}]',
              'set_false_path -hold -from [get_regs {u_uart/held_words*}] -to [get_regs {u_uart/words*}]',
              'set_false_path -to [get_pins {core_reset_pipe*_s0/CLEAR core_reset_pipe*_s0/PRESET}]']
    if gao_mode=='bsram4':
        lines=[line.replace('[get_regs {u_uart/words*}]','[get_pins {u_uart/lanes*/ram/ram/DI*}]') for line in lines]
    lines += [f'report_timing -{kind} -max_paths 2000 -max_common_paths 1' for kind in ('setup','hold','recovery','removal')]
    return '\n'.join(lines)+'\n'

def gao(user_code,gao_mode='full64'):
    document=ET.fromstring(base_gao(user_code));core=document.find('AoCore');core.set('module_name',TOP)
    core.set('storage_depth','128');core.set('capture_amount','128')
    document.find('GAO_ID').text=format(int(user_code[-4:],16),'016b')
    signals=core.find('SignalList');signals.clear()
    bus=ET.SubElement(signals,'Bus',capture_enable='true',name='status_50mhz')
    for bit in reversed(range(gao_record(gao_mode)['capture_bits'])):ET.SubElement(bus,'Signal').text=f'status_50mhz[{bit}]'
    core.find('Triggers/Trigger/SignalList/Signal').text='status_50mhz[0]'
    # Match the working B7 schema: expressions belong to the acquisition core.
    expressions=document.find('Expressions');document.remove(expressions);core.append(expressions)
    expressions.find('Expression').text='M0|!M0'
    return ET.tostring(document,encoding='unicode')+'\n'

def audit_prepare(output):
    """Recheck the immutable prepared inputs before root runs EDA or a board.

    This checks prepared bytes and declared composition, not synthesis, CDC,
    routed timing, JTAG identity, or hardware acceptance.
    """
    output=Path(output).resolve();record=json.loads((output/'inputs.json').read_text())
    gao_mode=record['gao'].get('mode','full64')
    native=native_sources(gao_mode)
    if record['gao']!=gao_record(gao_mode):raise ValueError('probe GAO contract changed')
    if gao_mode=='bsram4':
        if set(record.get('noncompiled_sha256',{}))!=set(BSRAM_METADATA):
            raise ValueError('BSRAM noncompiled contract/audit/decoder closure changed')
        for name,expected in record['noncompiled_sha256'].items():
            if record['input_sha256'].get(name)!=expected or sha(output/name)!=expected:
                raise ValueError('BSRAM noncompiled dependency drift: '+name)
    for name,expected in record['input_sha256'].items():
        path=(output/name).resolve()
        if not path.is_relative_to(output) or not path.is_file() or sha(path)!=expected:
            raise ValueError('prepared probe input drift: '+name)
    selected=[name for name in LOCKED if not name.endswith('riscv_ae350_config.v')]+list(native)
    if record['source_paths']!=selected:raise ValueError('prepared probe compiled closure changed')
    tcl=(output/'run.tcl').read_text()
    if re.findall(r'add_file -type verilog \[file join \$root ([^\]]+)\]',tcl)!=selected:
        raise ValueError('probe TCL source selection differs from manifest')
    for name,expected in record['locked_sha256'].items():
        if name not in LOCKED or sha(output/name)!=expected:raise ValueError('probe locked input changed')
    if set(record['locked_sha256'])!=set(LOCKED):raise ValueError('probe locked inventory changed')
    if record['clocks_hz']!=dict(core=100000000,bus=50000000,reference=50000000):
        raise ValueError('probe clock declaration changed')
    names=re.findall(r'^create_(?:generated_)?clock -name (\S+)',(output/'probe.sdc').read_text(),re.M)
    if names!=['clk_50m','cpu_ram50','cpu_core100','cpu_rtc_bound']:raise ValueError('probe SDC clock inventory changed')
    if (output/'probe.sdc').read_text().splitlines().count(RTC_CLOCK_SDC)!=1:
        raise ValueError('probe RTC timing target or minimum period changed')
    if (output/'probe.gao').read_text()!=gao(record['user_code'][2:],gao_mode):
        raise ValueError('probe complete diagnostic GAO schema changed')
    identity="`define AE350_PROBE_USER_CODE 32'h"+record['user_code'][2:].upper()+'\n'
    if gao_mode=='banked4':identity+='`define AE350_PROBE_BANKED_GAO\n'
    if gao_mode=='bsram4':identity+='`define AE350_PROBE_BSRAM_GAO\n'
    if (output/'probe_identity.vh').read_text()!=identity:raise ValueError('probe identity or explicit GAO mode changed')
    cst=(output/'probe.cst').read_text()
    audit_cpu_pll_constraint(cst)
    if parse_locations(cst)!=record['port_locations']:
        raise ValueError('probe staged pin locations changed')
    if any(record['port_locations'].get(name)!=balls for name,balls in SAFE_DAC_PINS.items()):
        raise ValueError('probe DAC safety pin mapping changed')
    fw=record['firmware'];raw=(output/'firmware/firmware.bin').read_bytes()
    if (sha(output/'firmware/firmware.elf')!=fw['elf_sha256'] or
            sha(output/'firmware/firmware.bin')!=fw['binary_sha256'] or
            sha(output/'firmware/boot.mem')!=fw['rom_sha256']):
        raise ValueError('probe firmware artifact identity changed')
    if bytes(decode_rom(output/'firmware/boot.mem',65536))!=raw.ljust(65536,b'\0'):
        raise ValueError('probe cold ROM no longer matches binary')
    verify_elf_image(output/'firmware/firmware.elf',raw,fw['capacity']['symbols'],65536)
    if fw['payload']!=payload()[1]:raise ValueError('probe independent host payload identity changed')
    return dict(manifest_sha256=sha(output/'inputs.json'),verified_inputs=len(record['input_sha256']),
        compiled_sources=len(selected),rom_bytes=65536,cold_binary_bytes=len(raw),
        synthesis_verified=False,physical_timing_verified=False,hardware_verified=False)

def prepare(root,netlists,output,user_code,prefix=None,gao_mode='full64'):
    root,output=Path(root).resolve(),Path(output).resolve()
    if not re.fullmatch('[0-9a-fA-F]{8}',user_code or ''):raise ValueError('probe requires an explicit new eight-hex UserCode')
    if output.exists():raise FileExistsError(str(output))
    native=native_sources(gao_mode)
    baseline=load_baseline(root,'resource_rework_route0')
    # Read and check every selected frozen input before creating a candidate.
    locked={name:baseline.read_bytes(name) for name in LOCKED}
    for relative in native:
        if not (root/relative).is_file():raise FileNotFoundError(relative)
    output.mkdir(parents=True)
    _,plan=prepare_pinout(root,netlists,output/'pinout')
    lines=[line for line in render_constraints(plan).splitlines()
           if (m:=re.match(r'IO_(?:LOC|PORT)\s+"([^"]+)"',line)) and m[1] in ('clk_50m','debug_uart_tx')]
    dac_cst,dac_references=safe_dac_constraints(root)
    cst='\n'.join(lines)+'\n'+dac_cst+CPU_PLL_CONSTRAINT+'\n'
    audit_cpu_pll_constraint(cst)
    expected={name:plan['ports'][name]['balls'] for name in ('clk_50m','debug_uart_tx')}
    expected.update(SAFE_DAC_PINS)
    if parse_locations(cst)!=expected:raise ValueError('probe pin selection changed')
    (output/'probe.cst').write_text(cst);(output/'probe.sdc').write_text(constraints(root,gao_mode))
    (output/'probe.gao').write_text(gao(user_code.upper(),gao_mode))
    identity="`define AE350_PROBE_USER_CODE 32'h"+user_code.upper()+'\n'
    if gao_mode=='banked4':identity+='`define AE350_PROBE_BANKED_GAO\n'
    if gao_mode=='bsram4':identity+='`define AE350_PROBE_BSRAM_GAO\n'
    (output/'probe_identity.vh').write_text(identity)
    selected=[]
    for name,data in locked.items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        if sha(target)!=baseline.descriptor['files'][name]['sha256']:raise ValueError('locked probe copy changed: '+name)
        if name.endswith(('.v','.sv')) and not name.endswith('riscv_ae350_config.v'):selected.append(name)
    for relative in native:
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/relative,target)
        if sha(target)!=sha(root/relative):raise ValueError('probe source copy changed')
        selected.append(relative)
    if gao_mode=='bsram4':
        for relative in BSRAM_METADATA:
            target=output/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/relative,target)
    fw=firmware(root,output/'firmware',prefix)
    common=['set root [file dirname [file normalize [info script]]]','cd $root',f'set_device {plan["device"]} -device_version C',
        'set_option -synthesis_tool gowinsynthesis',f'set_option -top_module {TOP}',f'set_option -output_base_name {BASE}',
        'set_option -verilog_std sysv2017','set_option -include_path $root',
        'set_option -use_jtag_as_gpio 0','set_option -use_cpu_as_gpio 1','set_option -use_mspi_as_gpio 1',
        'set_option -unused_pin default','set_option -cst_warn_to_error 1',
        *[f'add_file -type verilog [file join $root {name}]' for name in selected],
        *[f'add_file -type {kind} [file join $root probe.{kind}]' for kind in ('cst','sdc','gao')],
        f'set_option -user_code {user_code.upper()}','set_option -bit_security 0','set_option -secure_mode 0',
        'set_option -gen_text_timing_rpt 1','set_option -gen_verilog_sim_netlist 1',
        'set_option -gen_io_cst 1','set_option -gen_sdf 1',
        'set_option -timing_driven 1','set_option -correct_hold_violation 1','set_option -place_option 2','set_option -route_option 1']
    (output/'run.tcl').write_text('\n'.join([*common,'run all'])+'\n')
    record=dict(schema=1,identity='custom138k-ae350-local-memory-probe-'+user_code.upper(),user_code='0x'+user_code.upper(),
        top_module=TOP,source_policy='minimal locked hard-IP/config/PLL plus maintained boot64 and unchanged formal loader',
        parent_baseline=baseline.evidence(),source_paths=selected,locked_sha256={k:baseline.descriptor['files'][k]['sha256'] for k in LOCKED},
        native_sha256={name:sha(root/name) for name in native},tool_sha256=sha(Path(__file__)),firmware=fw,
        clocks_hz=dict(core=100000000,bus=50000000,reference=50000000),
        core_clock_requirement=dict(instance=CPU_PLL_INSTANCE,site=CPU_PLL_SITE,output='CLKOUT1',
            reference='MUG1031 v1.3.1 section 7.3, PDF page 56 / printed page 48'),
        rtc_use='reference-derived 32768Hz average; half-periods 762/763 reference cycles; no CPU/APB dependency',
        rtc_clock=dict(average_hz=32768,reference_hz=50000000,half_period_cycles=[762,763],
            sta_minimum_period_cycles=1524,sta_policy='conservative minimum period bound, not the average rate',
            phase_error_bound_reference_cycles=1,measurement_timebase=False),
        uart=dict(baud_divisor=434,reference_hz=50000000,baud=50000000/434,format='8N1',frame_bytes=280,
            header='A138LM01',word_count=64,crc='reflected CRC32/ISO-HDLC over first276bytes, final xor, LE tail'),
        gao=gao_record(gao_mode),
        port_locations=expected,electrical_check=plan['electrical_check'],
        dac_safety=dict(pins=SAFE_DAC_PINS,reference_sha256=dac_references,
            levels=dict(ak_smute=1,ak_pdn=0,ak_mclk=0,ak_bick=0,ak_lrck=0,ak_sdata=0),
            policy='B7 audited digital audio pin mapping; permanent SMUTE, held PDN, zero clocks/data; no analog silence claim'),
        validation_stage='prepare_only',
        synthesis_passed=False,physical_gates_passed=False,hardware_tested=False,sram_programmed=False,flash_programmed=False,
        full_workstation=False,cache_policy='disabled; only reads MMSC/PMA/cache configuration',
        omissions=['DDR controller','HDMI','audio','USB','BLE','workstation business'],
        rollback='Root selects a hash-checked prior SRAM candidate; Flash is not changed by this preparation.',
        input_sha256={str(path.relative_to(output)):sha(path) for path in output.rglob('*') if path.is_file()})
    if gao_mode=='bsram4':
        record['source_policy']+='; explicit bsram4 canonical synchronous RAM publisher/exporter, schema A1386403'
        record['noncompiled_sha256']={name:sha(root/name) for name in BSRAM_METADATA}
    (output/'inputs.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    audit_prepare(output)
    return output,record
