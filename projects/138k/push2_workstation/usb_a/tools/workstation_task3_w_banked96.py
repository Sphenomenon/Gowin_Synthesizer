"""Explicit physical 96 KiB W storage, preserving paired firmware addresses."""
from pathlib import Path
import hashlib
import json

KEY = 'ae350_boot_storage_policy'
POLICY = 'task3_W_three_bank32k_physical96_v1'
PROVIDER = 'rtl/workstation/workstation_profile_task3_w_paired_banked96.sv'
SOURCE = 'rtl/memory/workstation_ae350_boot_memory_banked96.sv'
REFERENCE = 'tools/ae350_task3_w_banked96_reference.json'
DEPENDENCIES = ('tools/workstation_task3_w_banked96.py', SOURCE, PROVIDER, REFERENCE)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configured(configuration):
    value = configuration.get(KEY)
    if value is None:
        return False
    if (value != POLICY or configuration.get('ae350_boot_rom_bytes') != 98304 or
            configuration.get('demo_role') != 'W' or
            configuration.get('ae350_firmware_policy') != 'task3_w_paired_phone_batch_single_recording_60s_v1' or
            configuration.get('phone_batch_policy') != 'full_key_atomic_owner_snapshot_command_v1' or
            configuration.get('usb_adapter_policy') != 'task3_paired_W_USB_retired_v1' or
            configuration.get('interboard_business_default_enabled') is not False or
            configuration.get('interboard_physical_acceptance_required') is not True):
        raise ValueError('unsupported paired W banked96 configuration')
    return True


def physical_report(root, evidence):
    from tools.workstation_classic_runtime import physical96_report
    return physical96_report(root, evidence, reference_path=REFERENCE,
        reference_policy='paired_W_rom96_same_elf_bin_layout_reference_v1', headless_worker=True)


def split_image(path):
    """Write three exact contiguous images; the combined image stays authoritative."""
    from tools.workstation_classic_runtime import decode_rom
    path = Path(path)
    decode_rom(path, 98304)
    words = path.read_text().splitlines(keepends=True)
    result = {}
    for bank in range(3):
        target = path.with_name(path.name + '.bank' + str(bank))
        target.write_text(''.join(words[bank*8192:(bank+1)*8192]))
        result[target.name] = sha(target)
    return result


def verify_banks(path):
    from tools.workstation_classic_runtime import decode_rom
    path = Path(path)
    image = decode_rom(path, 98304)
    result = {}
    for bank in range(3):
        target = path.with_name(path.name + '.bank' + str(bank))
        words = target.read_text().splitlines()
        if len(words) != 8192:
            raise ValueError('banked96 physical bank depth changed')
        try:
            raw = b''.join(int(word, 16).to_bytes(4, 'little') for word in words)
        except (ValueError, OverflowError) as error:
            raise ValueError('banked96 invalid physical word') from error
        if raw != image[bank*32768:(bank+1)*32768]:
            raise ValueError('banked96 physical bank differs from firmware')
        result[target.name] = sha(target)
    return result


def apply_storage(root, evidence):
    """Bound an unchanged linked ELF and remove only the zero padding above 96K."""
    from tools.workstation_classic_runtime import decode_rom
    root, evidence = Path(root), Path(evidence)
    capacity, report = physical_report(root, evidence)
    reference = json.loads((root/REFERENCE).read_text())
    image = decode_rom(evidence/'boot.mem', 131072)
    if sha(evidence/'boot.mem') != reference['layout128_rom_sha256'] or any(image[98304:]):
        raise ValueError('banked96 original ROM/padding identity changed')
    words = (evidence/'boot.mem').read_text().splitlines(keepends=True)
    (evidence/'boot.mem').write_text(''.join(words[:24576]))
    banks = split_image(evidence/'boot.mem')
    return capacity, dict(policy=POLICY, physical=report, banks_sha256=banks)


def verify_storage(root, evidence, record):
    from tools.workstation_classic_runtime import decode_rom
    root, evidence = Path(root), Path(evidence)
    capacity, report = physical_report(root, evidence)
    expected = dict(policy=POLICY, physical=report, banks_sha256=verify_banks(evidence/'boot.mem'))
    if record.get('banked96_storage') != expected or record.get('capacity') != capacity:
        raise ValueError('banked96 actual ELF/storage receipt changed')
    image = decode_rom(evidence/'boot.mem', 98304)
    binary = (evidence/'firmware.bin').read_bytes()
    if image != binary.ljust(98304, b'\0'):
        raise ValueError('banked96 image differs from actual binary')
    reference = json.loads((root/REFERENCE).read_text())
    words = image + bytes(32768)
    legacy = ''.join(f'{int.from_bytes(words[i:i+4],"little"):08x}\n' for i in range(0,131072,4))
    if hashlib.sha256(legacy.encode()).hexdigest() != reference['layout128_rom_sha256']:
        raise ValueError('banked96 original padded image cannot be reconstructed')
    return capacity


def check_mapped_rom(stage, netlist):
    """Prove all 24,576 initialized words and retain eight scratch SDPB blocks.

    This checks packing/initialization, not mapped AHB behavior or routed CDC.
    """
    import re
    path=Path(stage)/'firmware/boot.mem'
    verify_banks(path)
    memories={name:cell for name,cell in netlist.cells.items()
              if name.startswith('u_boot_memory/') and cell['kind']=='pROM'}
    scratch={name:cell for name,cell in netlist.cells.items()
             if name.startswith('u_boot_memory/') and cell['kind']=='SDPB'}
    if len(memories)!=48 or len(scratch)!=8:
        raise ValueError('banked96 must map to 48 physical ROM and 8 scratch blocks')
    actual=[0]*24576;covered=set()
    for name,cell in memories.items():
        match=re.fullmatch(r'u_boot_memory/rom([012])_rom\1_0_(\d+)_s',name)
        if match is None:
            raise ValueError('banked96 unreviewed ROM packing: '+name)
        bank,lane=map(int,match.groups())
        if lane>=16 or (bank,lane) in covered or cell['parameters'].get('BIT_WIDTH')!='2':
            raise ValueError('banked96 duplicated bank/lane or incorrect physical width')
        covered.add((bank,lane));packed=0
        for label,value in cell['parameters'].items():
            if not label.startswith('INIT_RAM_'):continue
            index=int(label.removeprefix('INIT_RAM_'),16)
            literal=re.fullmatch(r"256'h([0-9a-fA-F]{1,64})",value)
            if index>=64 or literal is None:
                raise ValueError('banked96 invalid ROM initialization')
            packed |= int(literal[1],16) << (256*index)
        for address in range(8192):
            actual[bank*8192+address] |= ((packed>>(2*address))&3)<<(2*lane)
    expected=[int(word,16) for word in path.read_text().splitlines()]
    for address,(got,wanted) in enumerate(zip(actual,expected)):
        if got!=wanted:
            raise ValueError('banked96 mapped ROM word mismatch at '+hex(0x80000000+address*4))
    return dict(ROM_blocks=48,scratch_SDPB_blocks=8,words=24576,every_initialization_word_matches=True,
        physical_capacity_bytes=98304,mapped_AHB_behavior_verified=False,routed_CDC_verified=False)
