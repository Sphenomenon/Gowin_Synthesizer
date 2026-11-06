"""Prepare a CST-only TMDS output locality experiment from exact mapped cells.

The caller seals the parent synthesis/route and the returned CST. This helper
does not select a build, change SDC/RTL, place the serializer hard blocks, or
grant deployment. Integrate only after full routed comparison; otherwise keep
the experiment as evidence and retain its parent.
"""
import re

from tools.workstation_pinout import digest, parse_locations
from tools.workstation_synthesis_netlist import SynthesisNetlist

TOP = 'workstation_custom_138k_top'
ROOT = 'u_video/u_dvi'
REGION = 'R[46:74]C[160:181]'
POLICY = 'tmds_full30_registered_words_and_polarity_gates_right_region_v1'
PIN_LOCATIONS = {
    'tmds_data_p[0]': ['J14', 'H14'],
    'tmds_data_p[1]': ['J15', 'H15'],
    'tmds_data_p[2]': ['K17', 'J17'],
    'tmds_clk_p': ['G15', 'G16'],
}


def require(condition, message):
    if not condition:
        raise ValueError('TMDS output placement: ' + message)


def output_boundary(netlist, *, routed):
    """Bind all thirty real FF -> polarity INV -> OSER10 D bit paths."""
    expected_registers = {f'{ROOT}/data_lanes[{lane}].encoder/tmds_{bit}_s0'
                          for lane in range(3) for bit in range(10)}
    observed_registers = {name for name in netlist.cells if re.fullmatch(
        re.escape(ROOT) + r'/data_lanes\[\d+\]\.encoder/tmds_\d+_s\d+', name)}
    expected_gates = {f'{ROOT}/data_lanes[{lane}].serializer/serial_word_{bit}_s2'
                      for lane in range(3) for bit in range(10)}
    observed_gates = {name for name in netlist.cells if re.fullmatch(
        re.escape(ROOT) + r'/data_lanes\[\d+\]\.serializer/serial_word_\d+_s\d+', name)}
    require(observed_registers == expected_registers, 'complete thirty-register inventory changed')
    require(observed_gates == expected_gates, 'complete thirty-polarity-gate inventory changed')
    power = {netlist.pin(name, 'V') for name, cell in netlist.cells.items() if cell['kind'] == 'VCC'}
    power.add("1'b1")
    words = []
    unique_q = set()
    pixel_clocks, serial_clocks, serializer_resets = set(), set(), set()
    for lane in range(3):
        serializer = f'{ROOT}/data_lanes[{lane}].serializer/serializer'
        hard = netlist.cells.get(serializer, {})
        require(hard.get('kind') == 'OSER10' and set(hard['ports']) ==
                {'Q', 'PCLK', 'FCLK', 'RESET'} | {'D'+str(bit) for bit in range(10)},
                'actual ten-bit serializer changed: ' + serializer)
        pixel_clocks.add(netlist.pin(serializer, 'PCLK'))
        serial_clocks.add(netlist.pin(serializer, 'FCLK'))
        serializer_resets.add(netlist.pin(serializer, 'RESET'))
        for bit in range(10):
            register = f'{ROOT}/data_lanes[{lane}].encoder/tmds_{bit}_s0'
            gate = f'{ROOT}/data_lanes[{lane}].serializer/serial_word_{bit}_s2'
            ff, inv = netlist.cells[register], netlist.cells[gate]
            require(ff['kind'] == 'DFFRE' and set(ff['ports']) == {'Q', 'D', 'CLK', 'CE', 'RESET'}
                    and ff['parameters'].get('INIT', "1'b0") == "1'b0",
                    'output FF type/reset/INIT changed: ' + register)
            require(netlist.pin(register, 'CLK') == netlist.pin(serializer, 'PCLK') and
                    netlist.pin(register, 'CE') in power,
                    'output FF clock/enable changed: ' + register)
            if routed:
                require(inv['kind'] == 'LUT1' and inv['parameters'] == {'INIT': "2'h1"} and
                        set(inv['ports']) == {'I0', 'F'}, 'routed polarity is not exact inversion: ' + gate)
                input_pin, output_pin = 'I0', 'F'
            else:
                require(inv['kind'] == 'INV' and inv['parameters'] == {} and
                        set(inv['ports']) == {'I', 'O'}, 'synthesis polarity is not exact inversion: ' + gate)
                input_pin, output_pin = 'I', 'O'
            q = netlist.pin(register, 'Q')
            require(q not in unique_q, 'output register bits alias')
            unique_q.add(q)
            require(q == netlist.pin(gate, input_pin) and
                    netlist.pin(gate, output_pin) == netlist.pin(serializer, 'D'+str(bit)),
                    'FF/polarity/serializer bit order changed: ' + gate)
            words.append(dict(lane=lane, bit=bit, register=register, gate=gate,
                              destination=serializer+'/D'+str(bit)))
    require(len(pixel_clocks) == len(serial_clocks) == len(serializer_resets) == 1 and
            pixel_clocks.isdisjoint(serial_clocks) and
            serializer_resets.isdisjoint(pixel_clocks | serial_clocks),
            'whole serializer pixel/serial/reset domain identity changed')
    return words


def output_region_constraints(payload, synthesis_text, routed_text):
    original = payload.decode('utf-8')
    locations = parse_locations(original)
    require(all(locations.get(port) == balls for port, balls in PIN_LOCATIONS.items()),
            'reviewed four differential HDMI pin pairs changed')
    native = SynthesisNetlist(synthesis_text, TOP)
    routed = SynthesisNetlist(routed_text, TOP)
    words = output_boundary(native, routed=False)
    require(words == output_boundary(routed, routed=True), 'synthesis/route boundary inventory differs')
    names = [word[key] for word in words for key in ('register', 'gate')]
    require(len(names) == len(set(names)) == 60, 'exact sixty-cell locality inventory changed')
    require(not any(name in original for name in names), 'an output target already has a parent constraint')
    constraints = [f'INS_LOC "{name}" {REGION};' for name in names]
    suffix = ('\n// Explicit offline TMDS output locality; no RTL/SDC/pad changes.\n' +
              '\n'.join(constraints) + '\n').encode('utf-8')
    result = payload + suffix
    require(result.startswith(payload) and parse_locations(result.decode()) == locations,
            'locality changed existing constraints or IO locations')
    return result, dict(policy=POLICY, region=REGION, words=words, constraints=constraints,
        register_count=30, gate_count=30, total_constrained_cells=60,
        before_sha256=digest(payload), after_sha256=digest(result),
        exact_appended_bytes_hex=suffix.hex(), parent_bytes_preserved=True,
        IO_and_hard_locations_unchanged=True, sdc_unchanged=True,
        RTL_and_synthesis_unchanged=True, full_bit_order_and_polarity_verified=True,
        source_evidence_scope='exact_same_synthesis_VG_and_hash_bound_parent_routed_VO',
        new_route_verified=False, full_timing_verified=False, hardware_tested=False,
        deployment_allowed=False,
        integration_criteria='Full new routed STA/PLL/CDC/resource comparison before selection; retain the original parent if the locality experiment regresses other paths')
