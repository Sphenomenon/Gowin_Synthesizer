"""Explicit paired-W USB termination and exact constraint retirement.

Select a versioned constant-output input composition, retaining the original
input, firmware, reset source and all fallback profiles. The USB telemetry
mailbox also becomes constant and is proved absent before retiring its SDC.
Never alter the top, HCI firmware, wire contracts, clocks or other selectors.
"""
from pathlib import Path
import fnmatch
import hashlib
import re
import xml.etree.ElementTree as ET

KEY = 'usb_adapter_policy'
POLICY = 'task3_paired_W_USB_retired_v1'
TOOL = 'tools/workstation_task3_w_usb_retirement.py'
SOURCE = 'rtl/workstation/workstation_task3_w_usb_retired.sv'
ORIGINAL = 'rtl/workstation/workstation_usb2_input.sv'
DEPENDENCIES = (TOOL, SOURCE)
RETIRED_PREFIXES = ('u_native_usb/', 'u_runtime/u_usb_cdc/')
QUERY = re.compile(r'\[(get_pins|get_regs|get_ports|get_clocks)\s+\{([^{}]+)\}\]')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('paired W USB retirement: ' + message)


def configured(configuration):
    value = configuration.get(KEY)
    if value != POLICY:
        return False
    require(configuration.get('demo_role') == 'W' and
            configuration.get('phone_batch_policy') == 'full_key_atomic_owner_snapshot_command_v1' and
            configuration.get('interboard_transport_policy') == 'task3_lcd_reqack_crc_session_budget_gated_v1' and
            configuration.get('interboard_business_default_enabled') is False,
            'requires bounded paired W with business initially closed')
    return True


def select_sources(stage, files, configuration):
    if not configured(configuration):
        return None
    originals = [row for row in files if row.get('path') == ORIGINAL]
    require(len(originals) == 1 and originals[0].get('enable') == '1',
            'original input must be selected exactly once')
    require(not any(row.get('path') == SOURCE for row in files), 'termination already listed')
    originals[0].set('enable', '0')
    ET.SubElement(files, 'File', path=SOURCE, type='file.verilog', enable='1')
    return dict(policy=POLICY, original=ORIGINAL, original_sha256=sha(Path(stage)/ORIGINAL),
                source=SOURCE, source_sha256=sha(Path(stage)/SOURCE),
                native_top_unchanged=True, firmware_unchanged=True)


def verify_selection(stage, configuration, evidence, enabled):
    selected = configured(configuration)
    if not selected:
        require(evidence is None and SOURCE not in enabled, 'unselected profile claims termination')
        return None
    require(isinstance(evidence, dict), 'selection evidence missing')
    expected = dict(policy=POLICY, original=ORIGINAL, original_sha256=sha(Path(stage)/ORIGINAL),
                    source=SOURCE, source_sha256=sha(Path(stage)/SOURCE),
                    native_top_unchanged=True, firmware_unchanged=True)
    require(evidence.get('selection') == expected, 'input source identity changed')
    require(ORIGINAL not in enabled and list(enabled).count(SOURCE) == 1,
            'exactly one input implementation required')
    return expected


def adapt_constraints(sdc):
    """Remove only USB/input telemetry members; preserve mixed-query peers."""
    lines = sdc.splitlines()
    output, changes = [], []
    for index, original in enumerate(lines):
        removed, empty = [], []
        def replace(match):
            members = match[2].split()
            retired = [m for m in members if match[1] in ('get_pins','get_regs') and
                       m.startswith(RETIRED_PREFIXES)]
            kept = [m for m in members if m not in retired]
            removed.extend(dict(query=match[1], member=m) for m in retired)
            if retired and not kept:
                empty.append(match[1])
            return '[' + match[1] + ' {' + ' '.join(kept) + '}]'
        selected = QUERY.sub(replace, original)
        require(not any(p in QUERY.sub('', original).split('#',1)[0] for p in RETIRED_PREFIXES),
                'unparsed USB selector')
        if removed:
            require(re.match(r'^set_(?:false_path|max_delay|min_delay)\b', original) is not None,
                    'unreviewed constraint command')
            selected = None if empty else selected
            changes.append(dict(line=index, original=original, selected=selected, removed=removed))
        else:
            selected = original
        if selected is not None:
            output.append(selected)
    result = '\n'.join(output) + ('\n' if output and sdc.endswith('\n') else '')
    return result, dict(policy=POLICY, original_sha256=digest(sdc), selected_sha256=digest(result),
                        original_lines=len(lines), trailing_newline=sdc.endswith('\n'), changes=changes)


def restore_constraints(sdc, evidence):
    require(isinstance(evidence,dict) and evidence.get('policy') == POLICY and
            digest(sdc) == evidence.get('selected_sha256'), 'selected SDC identity changed')
    require(type(evidence.get('original_lines')) is int and evidence['original_lines']>=0 and
            type(evidence.get('trailing_newline')) is bool and isinstance(evidence.get('changes'),list),
            'invalid SDC inverse receipt')
    selected = iter(sdc.splitlines());changes={}
    for row in evidence['changes']:
        require(isinstance(row,dict) and type(row.get('line')) is int and
                0<=row['line']<evidence['original_lines'] and row['line'] not in changes,
                'invalid or duplicate changed line')
        changes[row['line']]=row
    missing=object()
    restored=[]
    for index in range(evidence['original_lines']):
        row=changes.get(index)
        if row is None:
            line=next(selected,missing)
            require(line is not missing,'missing unchanged SDC line')
            restored.append(line)
        else:
            if row['selected'] is not None:
                require(next(selected,missing)==row['selected'], 'mixed selector peers changed')
            restored.append(row['original'])
    require(next(selected,None) is None, 'extra SDC lines')
    result='\n'.join(restored)+ ('\n' if evidence['trailing_newline'] else '')
    require(digest(result)==evidence['original_sha256'] and adapt_constraints(result)==(sdc,evidence),
            'SDC inverse or unchanged selectors drift')
    return result


def restore_selected_sdc(sdc, metadata):
    preboard = metadata.get('task3_w_preboard_cdc')
    if preboard is not None:
        from tools.workstation_task3_w_preboard_cdc import restore
        sdc = restore(sdc, preboard)
    evidence=metadata.get('task3_w_usb_retirement')
    if evidence is None:
        return sdc
    require(metadata.get('task3_paired',{}).get('role')=='W' and
            metadata.get('native_usb') is False and
            evidence.get('selection',{}).get('policy')==POLICY,
            'SDC retirement requires explicit paired W selection')
    return restore_constraints(sdc,evidence.get('constraints'))


def audit_absence(netlist, rows=None, constraints=None):
    """Actual mapped evidence is mandatory before treating USB checks as absent."""
    prefixes=('u_native_usb/host','u_native_usb/input_owner','u_native_usb/services')
    names=set(netlist.cells)|set(netlist.frames)|set(rows or {})
    require(not any(p==prefix or p.startswith(prefix+'/') for p in names for prefix in prefixes),
            'retired USB host/CPU/input owner remains')
    require(not any(p.startswith(RETIRED_PREFIXES) for p in netlist.cells),
            'termination or retired USB telemetry contains live logic')
    if constraints is not None:
        universes=dict(get_regs={p for p,c in netlist.cells.items() if c['kind'].startswith('DFF')},
            get_pins={p+'/'+pin for p,c in netlist.cells.items() for pin in c['ports']})
        for change in constraints['changes']:
            for row in change['removed']:
                require(not any(fnmatch.fnmatchcase(p,row['member']) for p in universes[row['query']]),
                        'retired selector still resolves: '+row['member'])
    return dict(policy=POLICY, no_host_CPU_input_owner_or_USB_state=True,
                no_USB_telemetry_mailbox=True,
                mapped_retirement_verified=True, firmware_artifacts_not_elaborated=True,
                IO_behavior='data high impedance,STP0,UART1,no events or lifecycle,no ready/device',
                hardware_electrical_acceptance=False)
