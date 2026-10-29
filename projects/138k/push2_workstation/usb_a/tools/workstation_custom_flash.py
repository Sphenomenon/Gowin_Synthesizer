"""Native SOM model-Flash composition using the validated shared-pad contract."""

import ast
import json
import re

from tools.stage_usb_firmware import sha
from tools.workstation_pinout import parse_locations, render_constraints, digest


SOURCE = 'tools/build_workstation_flash_boot.py'
SOURCE_SHA256 = 'ec7c16106e4039685bd2c3c451e0a1bcb8dbadfeaee0421b1a715a5ac947243c'
CST = 'boards/custom_138k/model_flash.cst'
SDC = ('set_false_path -to [get_pins {u_music/model_memory_meta*/D}]\n'
       # The routed gate already requires CLK->Q + wire <=2ns. Constrain
       # the real first-to-second stage as well; never false-path stage two.
       'set_max_delay 2.000 -from [get_regs {u_music/model_memory_meta*}] '
       '-to [get_regs {u_music/model_memory_ready*}]\n'
       'set_input_delay 15.000 -clock [get_clocks {clk_50m}] [get_ports {flash_miso}]\n')
PINS = dict(flash_clk=['L12'], flash_cs_n=['T19'], flash_mosi=['P22'],
            flash_miso=['R22'], flash_wp_n=['P21'], flash_hold_n=['R21'])


def reviewed_cst(root):
    if sha(root / SOURCE) != SOURCE_SHA256:
        raise ValueError('validated SOM Flash reference identity changed')
    assignments = [node for node in ast.parse((root / SOURCE).read_text()).body
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'CST'
                                                          for target in node.targets)]
    if len(assignments) != 1:
        raise ValueError('validated SOM Flash CST reference ambiguous')
    reference = ast.literal_eval(assignments[0].value)
    selected = (root / CST).read_text()
    functional = lambda text: [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('//')]
    if functional(reference) != functional(selected) or parse_locations(selected) != PINS:
        raise ValueError('native SOM Flash pads differ from the validated read-only x1 contract')
    return selected


def prepare(root, pinout_output, plan, stage):
    constraints = reviewed_cst(root)
    occupied = {ball for record in plan['ports'].values() for ball in record['balls']}
    reserved = set(plan['reserved_balls'].values())
    for port, balls in PINS.items():
        if port in plan['ports'] or occupied.intersection(balls) or reserved.intersection(balls):
            raise ValueError('native model Flash pad collision: ' + port)
        plan['ports'][port] = dict(balls=balls, origin='validated_SOM_configuration_Flash_x1_shared_pads')
        occupied.update(balls)
    plan['identity'] += '_model_flash_v1'
    locations = render_constraints(plan)
    plan['constraints_sha256'] = digest(locations.encode())
    (pinout_output / 'pinout.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    (pinout_output / 'custom_138k.locations.cst').write_text(locations)
    electrical = '\n'.join(line for line in constraints.splitlines() if line.startswith('IO_PORT ')) + '\n'
    (stage / 'constraints/custom_138k.model_flash.cst').write_text(electrical)
    return dict(source=SOURCE, source_sha256=SOURCE_SHA256, constraints=CST, constraints_sha256=sha(root / CST),
                use_flash_weights=True, mspi_as_gpio=True, read_only=True, model_byte_address='0x600000',
                pad_guard='basic_pitch_flash_io_guard', fallback='existing_UART_model_loader', hardware_tested=False)
