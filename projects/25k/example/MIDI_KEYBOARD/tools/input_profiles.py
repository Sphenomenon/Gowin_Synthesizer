"""Explicit accessory profiles; common USB/BLE/display functions stay enabled."""
import re


TOUCH_PORTS = ('touch1_scl', 'touch1_sda', 'touch2_scl', 'touch2_sda', 'touch_change_n')


def select_panel(requested=None, pluck_alias=False, probe=False):
    if requested not in (None, 'touch', 'pluck'):
        raise ValueError('Input panel must be touch or pluck.')
    if probe and (requested is not None or pluck_alias):
        raise ValueError('Accessory profiles cannot be combined with temporary probes.')
    if pluck_alias and requested == 'touch':
        raise ValueError('--pluck conflicts with --input-panel touch.')
    return 'pluck' if pluck_alias else (requested or 'touch')


def panel_defines(panel):
    if panel not in ('touch', 'pluck'):
        raise ValueError('Input panel must be touch or pluck.')
    return ['MIDI_PLUCK_ADC', 'MIDI_PLUCK_ONLY'] if panel == 'pluck' else []


def remove_touch_constraints(text, suffix):
    if suffix not in ('cst', 'sdc'):
        raise ValueError('Only CST and SDC accessory constraints are supported.')
    removed = []
    for port in TOUCH_PORTS:
        if suffix == 'cst':
            patterns = [r'^IO_LOC "' + port + r'" [A-Z][0-9]+;$',
                        r'^IO_PORT "' + port + r'" IO_TYPE=LVCMOS33 PULL_MODE=(?:NONE|UP);$']
        else:
            patterns = [r'^set_false_path -from \[get_ports \{' + port +
                        r'\}\] -to \[get_pins \{touch\*/[^\n]+_meta_s0/D\}\]$']
        for pattern in patterns:
            matches = re.findall(pattern, text, re.M)
            if len(matches) != 1:
                raise ValueError('Touch constraint anchor drift: ' + port + '.' + suffix)
            removed.append(matches[0])
            text = text.replace(matches[0] + '\n', '', 1)
    return text, removed
