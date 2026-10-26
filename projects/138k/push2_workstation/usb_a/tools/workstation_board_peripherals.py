"""Bind reviewed remote examples to the native workstation, not their test tops."""

from pathlib import Path
import json

from tools.stage_usb_firmware import sha
from tools.workstation_pinout import parse_locations, render_constraints, digest


PROFILE = 'boards/custom_138k/peripherals.json'
LCD_SDC = (
    'set_max_delay 10.000 -from [get_regs {u_lcd/u_feedback/held_data*}] '
    '-to [get_regs {u_lcd/u_feedback/destination_data*}]\n'
    'set_false_path -hold -from [get_regs {u_lcd/u_feedback/held_data*}] '
    '-to [get_regs {u_lcd/u_feedback/destination_data*}]\n'
    'set_false_path -to [get_pins {u_lcd/u_feedback/req_meta*/D u_lcd/u_feedback/ack_meta*/D}]\n'
    'set_false_path -to [get_pins {u_lcd/u_feedback/source_release*/CLEAR '
    'u_lcd/u_feedback/destination_release*/CLEAR u_lcd/release_pipe*/CLEAR}]\n'
)


def reviewed_profile(root):
    root = Path(root).resolve()
    repository = root.parents[3]
    profile = json.loads((root / PROFILE).read_text())
    if profile.get('schema') != 1 or profile.get('identity') != 'custom138k-workstation-peripherals-20261024-v1':
        raise ValueError('native peripheral profile changed')
    for relative, expected in profile['reviewed_sources'].items():
        source = (repository / relative).resolve()
        if not source.is_relative_to(repository) or sha(source) != expected:
            raise ValueError('reviewed remote peripheral input changed: ' + relative)
    return profile


def prepare(root, pinout_output, plan, stage):
    root = Path(root).resolve()
    repository = root.parents[3]
    profile = reviewed_profile(root)
    audio = parse_locations((repository / 'example/AK4493_AMP/constraints/audio.cst').read_text())
    pinout_profile = json.loads((root / 'boards/custom_138k/pinout.json').read_text())
    audio_by_pin = {channel['pin']: plan['ports'][channel['port']]['balls']
                    for channel in pinout_profile['audio']}
    for original, port in profile['audio_aliases'].items():
        channel = next(channel for channel in pinout_profile['audio'] if channel['port'] == port)
        balls = audio_by_pin[25-channel['pin']]
        if balls != audio[original]:
            raise ValueError('native audio pin differs from reviewed remote chain: ' + port)
        plan['ports'][port] = dict(balls=balls, origin='reviewed_audio_fpc_reversed_25_minus_n')
    plan['assumptions'] = dict(plan['assumptions'],
        audio_cable='carrier FPC2.n -> amplifier FPC1.(25-n); remote reviewed bring-up mapping')
    lcd_source = repository / 'example/LCD_RGB/constraints/lcd.cst'
    lcd = parse_locations(lcd_source.read_text())
    occupied = {ball for record in plan['ports'].values() for ball in record['balls']}
    reserved = set(plan['reserved_balls'].values())
    additions = {'clk_12m288': audio['clk_12m288']}
    additions.update({port: balls for port, balls in lcd.items() if port.startswith('lcd_')})
    for port, balls in additions.items():
        if port in plan['ports'] or occupied.intersection(balls):
            raise ValueError('native peripheral ball or port collision: ' + port)
        if port != 'clk_12m288' and reserved.intersection(balls):
            raise ValueError('native peripheral uses reserved ball: ' + port)
        if port == 'clk_12m288' and balls != ['K18']:
            raise ValueError('native audio oscillator mapping changed')
        plan['ports'][port] = dict(balls=balls, origin='reviewed_remote_peripheral')
        occupied.update(balls)
    plan['reserved_balls'] = {node: ball for node, ball in plan['reserved_balls'].items() if ball != 'K18'}
    plan['identity'] += '_workstation_peripherals_v1'
    plan['peripherals'] = profile
    constraints = render_constraints(plan)
    plan['constraints_sha256'] = digest(constraints.encode())
    (pinout_output / 'pinout.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
    (pinout_output / 'custom_138k.locations.cst').write_text(constraints)
    electrical = '\n'.join(line for line in lcd_source.read_text().splitlines() if line.startswith('IO_PORT "lcd_'))+'\n'
    electrical += 'IO_PORT "clk_12m288" IO_TYPE=LVCMOS33 PULL_MODE=NONE;\n'
    (stage / 'constraints/custom_138k.peripherals.cst').write_text(electrical)
    reviewed_profile(root)
    return dict(profile_source=PROFILE, profile_sha256=sha(root / PROFILE), **profile)
