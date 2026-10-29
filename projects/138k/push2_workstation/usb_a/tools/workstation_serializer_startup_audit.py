"""Maintained native/legacy routed serializer startup audit, without overlays.

Migrated from the frozen check_serializer_startup.py (SHA256
feff1f32a900bc2619c3e991a63aadd11ed48d6ffeaa597bc1741ed746b8c927).
The frozen file and its failed historical audit remain untouched. Native TMDS
lanes/polarity are explicit configuration; synthesized intermediate gates are
resolved by unique driver, exact input/output pins, polarity and fanout.
All original40ns/80ns budgets and primitive/endpoint checks remain required.
"""
import re
from fnmatch import fnmatchcase


def logic_driver(cells, parameters, output_net, kind, inputs, scope, init=None):
    """Resolve an exact combinational driver; never accept a name-only alias."""
    output_pin = {'LUT1': 'F', 'LUT3': 'F', 'INV': 'O'}[kind]
    drivers = [(name, cell_kind, ports) for name, (cell_kind, ports) in cells.items()
               if any(ports.get(pin) == output_net for pin in ('Q', 'F', 'O', 'CLKOUT'))]
    assert len(drivers) == 1, f"expected unique logic driver for {output_net}, found {len(drivers)}"
    name, actual_kind, ports = drivers[0]
    assert name.startswith(scope + '/') and actual_kind == kind, f"logic driver type/scope changed: {name}"
    assert ports == {**inputs, output_pin: output_net}, f"logic driver topology changed: {name}"
    if init is not None:
        assert parameters.get((name, 'INIT')) == init, f"logic driver polarity changed: {name}"
    return name


def inspect_serializer_startup(sdf, netlist, ddr_audit=None, sdc=None, lane_layout='native'):
    if not __debug__:
        return ["startup audit requires normal Python execution; -O disables validation assertions"], {}
    def unescape(value):
        return re.sub(r"\\(.)", r"\1", value)

    def numbers(value):
        return [float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", value)]

    try:
        scale = re.search(r"\(TIMESCALE\s+([\d.]+)\s*(ns|ps|us)\)", sdf)
        assert scale, "SDF timescale missing/unsupported"
        unit = float(scale[1]) * {"ns": 1, "ps": 0.001, "us": 1000}[scale[2]]
        routed = {}
        for match in re.finditer(r"\(INTERCONNECT\s+(\S+)\s+(\S+)\s+([^\n]+)", sdf):
            key = (unescape(match[1]), unescape(match[2]))
            assert key not in routed, f"duplicate SDF interconnect: {key}"
            routed[key] = max(numbers(match[3])) * unit
        sdf_cells = {}
        for block in re.split(r"\n\s*\(CELL\s*\n", sdf)[1:]:
            instance = re.search(r"\(INSTANCE\s+(\S+)\)", block)
            if instance:
                sdf_cells[unescape(instance[1])] = block

        # The post-route VO is flat; normalize escaped net names and bit-select
        # whitespace so connections can be compared directly.
        cells = {}
        for match in re.finditer(r"^(\w+)\s+(\\\S+|\w+)\s+\((.*?)^\);", netlist, re.M | re.S):
            name = match[2].lstrip("\\")
            ports = {p[1]: re.sub(r"\s+|\\", "", p[2]) for p in
                     re.finditer(r"\.(\w+)\s*\(([^)]*)\)", match[3])}
            cells[name] = (match[1], ports)
        parameters = {(match[1].lstrip("\\"), match[2]): match[3].strip()
                      for match in re.finditer(r"^defparam\s+(\\\S+|\w+)\s*\.(\w+)\s*=\s*([^;]+);", netlist, re.M)}

        def unique(pattern):
            names = [name for name in cells if re.search(pattern, name)]
            assert len(names) == 1, f"expected one routed cell for {pattern}, found {len(names)}"
            return names[0]

        source = unique(r"/u_startup/serializer_reset_s\d+$")
        prefix = source.rsplit("/u_startup/", 1)[0]
        stages = [unique(re.escape(prefix) + rf"/u_startup/startup_pipe_{i}_s\d+$") for i in range(5)]
        src_type, src = cells[source]
        assert src_type == "DFFPE", "serializer reset is not the preserved active-high reset FF"
        assert parameters[(source, "INIT")] == "1'b1", "serializer reset does not initialize asserted"
        ground = {ports["G"] for kind, ports in cells.values() if kind == "GND"}
        power = {ports["V"] for kind, ports in cells.values() if kind == "VCC"}
        assert src["D"] in ground and src["CE"] in power, "serializer reset is not a constant-zero release FF"
        for index, name in enumerate(stages):
            kind, ports = cells[name]
            assert kind == "DFFCE" and ports["CLK"] == src["CLK"], "startup stages must share the control clock"
            assert parameters[(name, "INIT")] == "1'b0", "startup gate/pipeline does not initialize disabled"
            assert ports["CLEAR"] == src["PRESET"] and ports["CE"] in power, "startup reset/enable mismatch"
            assert (ports["D"] in power if index == 0 else ports["D"] == cells[stages[index-1]][1]["Q"]), \
                "startup no longer waits four full control-clock cycles after reset release"

        pll_name = prefix + "/u_tmds/PLL_inst"
        divider_name = prefix + "/u_pixel_div"
        assert cells[pll_name][0] == "PLL" and cells[divider_name][0] == "CLKDIV", "dedicated clock primitives missing"
        pll, divider = cells[pll_name][1], cells[divider_name][1]
        assert parameters[(pll_name, "CLKOUT0_EN")] == '"TRUE"' and parameters[(divider_name, "DIV_MODE")] == '"5"', \
            "serial output or dedicated /5 divider configuration changed"
        assert pll["ENCLK0"] == cells[stages[4]][1]["Q"], "serial PLL output gate is not controlled by startup stage 4"
        assert divider["HCLKIN"] == pll["CLKOUT0"] and divider["RESETN"] == cells[stages[0]][1]["Q"], \
            "pixel divider does not share the stopped-clock startup sequence"
        serdes = [(name, ports) for name, (kind, ports) in cells.items() if kind == "OSER10"]
        assert len(serdes) == 4, f"expected four routed OSER10 lanes, found {len(serdes)}"
        for name, ports in serdes:
            assert ports["RESET"] == src["Q"], f"{name}: reset is not driven by the preserved startup FF"
            assert ports["FCLK"] == pll["CLKOUT0"] and ports["PCLK"] == divider["CLKOUT"], \
                f"{name}: clocks bypass the dedicated startup gate/divider"

        # Bind all four serializers to their actual differential package
        # ports. The clock is a serialized 00000/11111 word, not raw CLKDIV /5.
        assert lane_layout in {'native', 'legacy'}, 'unknown explicit TMDS layout'
        clock_serializer = ('u_video/u_dvi/clock_lane/serializer' if lane_layout == 'native'
                            else 'u_video/u_dvi/clock_phy/tmds_serdes_inst0')
        expected_lanes = {clock_serializer: ("tmds_clk_p", "tmds_clk_n")}
        data_lanes = [(f'u_video/u_dvi/data_lanes[{i}].serializer/serializer' if lane_layout == 'native'
                       else f'u_video/u_dvi/gen_enc[{i}].dvi_tx_tmds_phy_inst/tmds_serdes_inst0') for i in range(3)]
        expected_lanes.update({name: (f"tmds_data_p[{i}]", f"tmds_data_n[{i}]")
                               for i, name in enumerate(data_lanes)})
        assert {name for name, _ in serdes} == set(expected_lanes), "TMDS serializer lane inventory changed"
        for name, ports in serdes:
            buffer_name = name.rsplit("/", 1)[0] + ('/differential' if lane_layout == 'native' else '/tmds_bufds_isnt0')
            kind, buffer = cells[buffer_name]
            assert kind == "ELVDS_OBUF" and buffer["I"] == ports["Q"] and \
                (buffer["O"], buffer["OB"]) == expected_lanes[name], \
                f"{name}: serializer no longer directly drives its audited TMDS differential ports"
        clock_ports = cells[clock_serializer][1]
        word = '0000011111' if lane_layout == 'native' else '1111100000'
        for bit in range(10):
            assert clock_ports[f"D{bit}"] in (power if word[9-bit] == '1' else ground), \
                f"TMDS clock D{bit} differs from the audited 10'b{word} clock word"

        ibuf = unique(r"^clk_50m_ibuf$")
        assert cells[ibuf][0] == "IBUF" and cells[ibuf][1]["I"] == "clk_50m" and cells[ibuf][1]["O"] == src["CLK"], \
            "startup source does not use the direct 50MHz input clock"

        def arc(instance, start, end):
            block = sdf_cells[instance]
            values = re.findall(r"\(IOPATH\s+" + re.escape(start) + r"\s+" + re.escape(end) + r"\s*([^\n]+)", block)
            assert values, f"SDF cell arc missing: {instance} {start}->{end}"
            return max(max(numbers(value)) for value in values) * unit

        input_delay = arc(ibuf, "I", "O")
        clock_route = routed[(ibuf + "/O", source + "/CLK")]
        clock_to_q = arc(source, "CLK", "Q")
        paths = []
        for name, _ in sorted(serdes):
            route_delay = routed[(source + "/Q", name + "/RESET")]
            recovery_lines = [line for line in sdf_cells[name].splitlines()
                              if "(RECOVERY (negedge RESET)" in line]
            assert recovery_lines, f"SDF RESET recovery checks missing: {name}"
            recovery = max(max(numbers(line)) for line in recovery_lines) * unit
            total = input_delay + clock_route + clock_to_q + route_delay + recovery
            assert total <= 40.0, f"{name}: startup reset settle+recovery {total:.3f}ns exceeds 40ns budget"
            paths.append({"endpoint": name + "/RESET", "route_max_ns": route_delay,
                          "recovery_max_ns": recovery, "settle_and_recovery_max_ns": total,
                          "margin_to_first_clock_ns": 80.0-total})

        def reset_distribution(reset_source, endpoints):
            assert cells[reset_source][1]["CLK"] == src["CLK"], "reset source must use the audited 50MHz clock"
            clock = routed[(ibuf + "/O", reset_source + "/CLK")]
            cq = arc(reset_source, "CLK", "Q")
            result = []
            for target, reset_pin in sorted(endpoints):
                route = routed[(reset_source + "/Q", target + "/" + reset_pin)]
                lines = [line for line in sdf_cells[target].splitlines()
                         if "(RECOVERY " in line and reset_pin + ")" in line]
                assert lines, f"SDF recovery timing missing: {target}/{reset_pin}"
                recovery = max(max(numbers(line)) for line in lines) * unit
                total = input_delay + clock + cq + route + recovery
                assert total <= 40.0, f"{target}/{reset_pin}: settle+recovery {total:.3f}ns exceeds 40ns startup budget"
                result.append({"endpoint": target + "/" + reset_pin, "route_max_ns": route,
                               "recovery_max_ns": recovery, "settle_and_recovery_max_ns": total,
                               "margin_to_first_clock_ns": 80.0-total})
            return {"source": reset_source, "source_clock_route_max_ns": clock,
                    "source_clock_to_q_max_ns": cq, "paths": result}

        divider_audit = reset_distribution(stages[0], [(divider_name, "RESETN")])
        ddr_distribution = None
        resolved_logic = {}
        if ddr_audit is not None:
            # The separate 108-cell source-netlist audit establishes the 80ns
            # stop window. Here verify its routed reset/gate boundary and every
            # primitive endpoint; normal PHY data paths remain normal STA.
            phy = "u_memory/u_ddr3/gw3_top/u_ddr_phy_top"
            ddr_source = phy + "/ddr_rsti_reg_2_s0"
            reset_ff = cells[ddr_source][1]
            stop = [cells[phy + f"/stop_reg_{i}_s0"][1] for i in range(3)]
            stop_source_name = unique(re.escape(phy) + r'/ddr_sync/cs_memsync_4_s\d+$')
            stop_source_kind, stop_source = cells[stop_source_name]
            assert stop_source_kind == 'DFFCE' and stop_source['Q'] == stop[0]['D'], 'DDR stop first-stage source changed'
            assert stop_source['CLK'] == src['CLK'] and stop_source['CE'] in power and stop_source['CLEAR'] == stop[0]['CLEAR'], 'DDR stop source clock/reset changed'
            assert parameters[(stop_source_name, 'INIT')] == "1'b0", 'DDR stop source initialization changed'
            reset_assert_name = unique(re.escape(phy) + r'/ddr_sync/dll_rst_s\d+$')
            reset_assert_kind, reset_assert = cells[reset_assert_name]
            assert reset_assert_kind == 'DFFPE' and reset_assert['Q'] == cells[phy + '/ddr_rsti_reg_0_s0'][1]['D'], 'DDR reset source changed'
            assert reset_assert['CLK'] == src['CLK'] and reset_assert['D'] in ground and reset_assert['CE'] in power and reset_assert['PRESET'] == stop[0]['CLEAR'], 'DDR reset source clock/reset/polarity changed'
            assert parameters[(reset_assert_name, 'INIT')] == "1'b1", 'DDR reset source initialization changed'
            for i, ports in enumerate(stop):
                name = phy + f'/stop_reg_{i}_s0'
                assert cells[name][0] == 'DFFCE' and parameters[(name, 'INIT')] == "1'b0", 'DDR stop reset primitive changed'
                assert ports["CLK"] == src["CLK"] and ports["CE"] in power and ports['CLEAR'] == stop[0]['CLEAR'], "DDR stop control clock/reset changed"
                if i:
                    assert ports["D"] == stop[i-1]["Q"], "DDR stop pipeline changed"
            ddr_pll_name = 'u_memory/u_pll/u_pll_0/PLL_inst'
            assert cells[ddr_pll_name][0] == 'PLL', 'DDR dedicated PLL missing'
            ddr_pll = cells[ddr_pll_name][1]
            inverter_name = logic_driver(cells, parameters, ddr_pll['ENCLK2'], 'LUT1',
                                         {'I0': stop[2]['Q']}, phy, "2'h1")
            kind, inverter = cells[inverter_name]
            assert ddr_pll["ENCLK2"] == inverter["F"], "DDR PLL output gate bypasses audited stop control"
            gate_fanout = {(name, pin) for name, (_, ports) in cells.items() for pin, net in ports.items()
                           if net == inverter['F'] and (name, pin) != (inverter_name, 'F')}
            assert gate_fanout == {(ddr_pll_name, 'ENCLK2')}, 'DDR stop gate has additional or bypassed fanout'
            stop_fanout = {(name, pin) for name, (_, ports) in cells.items() for pin, net in ports.items()
                           if net == stop[2]['Q'] and (name, pin) != (phy + '/stop_reg_2_s0', 'Q')}
            assert stop_fanout == {(inverter_name, 'I0')}, 'DDR final stop pipeline has additional fanout'
            for index in range(3):
                name = phy + f'/ddr_rsti_reg_{index}_s0'
                reset_kind, pins = cells[name]
                assert reset_kind == ('DFFSE' if index == 0 else 'DFFCE'), 'DDR reset pipeline primitive changed'
                assert pins['CLK'] == src['CLK'] and pins['CE'] in power, 'DDR reset pipeline clock/enable changed'
                assert parameters[(name, 'INIT')] == ("1'b1" if index == 0 else "1'b0"), 'DDR reset pipeline initialization changed'
                if index:
                    assert pins['D'] == cells[phy + f'/ddr_rsti_reg_{index-1}_s0'][1]['Q'] and pins['CLEAR'] in ground, 'DDR reset pipeline changed'
            resolved_logic['pll_stop_inverter'] = dict(cell=inverter_name, input=stop[2]['Q'], output=inverter['F'],
                                                      init="2'h1", unique_fanout=sorted(gate_fanout))
            ui_divider_name = phy + "/fclkdiv"
            ui_divider = cells[ui_divider_name][1]
            assert ui_divider["HCLKIN"] == ddr_pll["CLKOUT2"], "DDR UI clock bypasses gated memory clock"
            assert cells[ui_divider_name][0] == "CLKDIV" and parameters[(ui_divider_name, "DIV_MODE")] == '"4"', \
                "DDR UI clock no longer uses the audited /4 divider"
            divider_reset_name = logic_driver(cells, parameters, ui_divider['RESETN'], 'LUT1',
                                               {'I0': reset_ff['Q']}, phy, "2'h1")
            reset_kind, divider_reset = cells[divider_reset_name]
            assert reset_kind == "LUT1" and parameters[(divider_reset_name, "INIT")] == "2'h1" and \
                divider_reset["I0"] == reset_ff["Q"] and divider_reset["F"] == ui_divider["RESETN"], \
                "DDR UI divider reset no longer follows inverted controller reset"
            resolved_logic['ui_divider_reset_inverter'] = dict(cell=divider_reset_name, input=reset_ff['Q'], output=ui_divider['RESETN'], init="2'h1")
            expected_types = {"OSER8_MEM": 40, "IDES8_MEM": 32, "OSER8": 25, "DQS": 4}
            targets = [(name, kind, ports) for name, (kind, ports) in cells.items()
                       if name.startswith(phy + "/") and kind in expected_types]
            counts = {kind: sum(t == kind for _, t, _ in targets) for kind in expected_types}
            assert counts == expected_types, f"DDR PHY primitive inventory changed: {counts}"
            for name, (kind, ports) in cells.items():
                if name.startswith(phy + "/u_ddr_phy_wds/") and "RESET" in ports and kind not in expected_types:
                    assert kind == "SDPB" and ports["RESET"] in ground, \
                        f"{name}: additional active RESET endpoint under the constrained PHY WDS subtree"
            for name, _, ports in targets:
                assert ports["RESET"] == reset_ff["Q"], f"{name}: reset bypasses audited IP source"
                assert ports["FCLK"] == ddr_pll["CLKOUT2"] and ports["PCLK"] == ui_divider["CLKOUT"], \
                    f"{name}: clocks bypass the audited memory clock gate"
            # CLKDIV /4 holds CLKOUT low until HCLKIN resumes; releasing
            # RESETN alone produces no edge in the official primitive model.
            # These eight FFs see inverted UI clock, so the same 80ns stopped
            # clock window also protects their negative-edge reset release.
            falling_names = [phy + f"/u_ddr_init/read_calibration_logic_gen[{lane}].rburst_neg{suffix}_s0"
                             for lane in range(4) for suffix in ("", "_r")]
            inverted_ui_name = logic_driver(cells, parameters, cells[falling_names[0]][1]['CLK'], 'INV',
                                             {'I': ui_divider['CLKOUT']}, phy)
            inverse_kind, inverse = cells[inverted_ui_name]
            assert inverse_kind == "INV" and inverse["I"] == ui_divider["CLKOUT"], \
                "DDR negative-edge calibration clock bypasses the stopped UI divider"
            resolved_logic['calibration_clock_inverter'] = dict(cell=inverted_ui_name, input=ui_divider['CLKOUT'], output=inverse['O'])
            actual_falling = {name for name in cells if name.startswith(phy + "/u_ddr_init/") and
                              re.search(r"\.rburst_neg(?:_r)?_s\d+$", name)}
            assert actual_falling == set(falling_names), "DDR negative-edge calibration inventory changed"
            for name in falling_names:
                kind, ports = cells[name]
                assert kind == "DFFCE" and parameters[(name, "INIT")] == "1'b0", \
                    f"{name}: negative-edge calibration reset primitive changed"
                assert ports["CLK"] == inverse["O"] and ports["CLEAR"] == reset_ff["Q"] and ports["CE"] in power, \
                    f"{name}: negative-edge calibration reset/clock bypasses the audited sequence"

            # Gowin needs endpoint-only constraints for the DLL output arc.
            # Prove every constrained D pin still has its unique STEP bit,
            # the UI clock, and the one-time LOCK-qualified capture enable.
            dll_name = phy + "/u_dll"
            dll_kind, dll = cells[dll_name]
            assert dll_kind == "DDRDLL" and dll["CLKIN"] == ddr_pll["CLKOUT2"], "DLL source clock changed"
            step_bus = re.fullmatch(r"\{(.+)\[7:0\]\}", dll["STEP"])
            assert step_bus, "DLL STEP output is not the audited eight-bit bus"
            recent_name, old_name = phy + "/ddr_init_st_rr_s0", phy + "/ddr_init_st_rrr_s0"
            recent, old = cells[recent_name][1], cells[old_name][1]
            captures = [phy + f"/dll_step_base_{bit}_s0" for bit in range(8)]
            capture_enable_name = logic_driver(cells, parameters, cells[captures[0]][1]['CE'], 'LUT3',
                                               {'I0': old['Q'], 'I1': recent['Q'], 'I2': dll['LOCK']}, phy, "8'h40")
            ce_kind, ce = cells[capture_enable_name]
            resolved_logic['dll_capture_enable'] = dict(cell=capture_enable_name, init="8'h40", equation='!old && recent && dll_lock')
            for name in (recent_name, old_name):
                kind, ports = cells[name]
                assert kind == "DFFCE" and ports["CLK"] == ui_divider["CLKOUT"] and \
                    ports["CLEAR"] == reset_ff["Q"] and ports["CE"] in power and parameters[(name, "INIT")] == "1'b0", \
                    "DLL capture-enable history no longer uses the audited UI pipeline"
            assert old["D"] == recent["Q"], "DLL capture-enable history pipeline changed"
            assert ce_kind == "LUT3" and parameters[(capture_enable_name, "INIT")] == "8'h40" and \
                ce["I0"] == old["Q"] and ce["I1"] == recent["Q"] and ce["I2"] == dll["LOCK"], \
                "DLL capture enable is not !old && recent && dll_lock"
            actual_captures = {name for name in cells if name.startswith(phy + "/dll_step_base_")}
            assert actual_captures == set(captures), "DLL STEP capture inventory changed"
            step_paths = []
            for bit, name in enumerate(captures):
                kind, ports = cells[name]
                assert kind == "DFFCE" and parameters[(name, "INIT")] == "1'b0" and \
                    ports["D"] == f"{step_bus[1]}[{bit}]", f"{name}: D is not the corresponding DLL STEP bit"
                assert ports["CLK"] == ui_divider["CLKOUT"] and ports["CE"] == ce["F"] and \
                    ports["CLEAR"] == reset_ff["Q"], f"{name}: DLL capture clock/enable/reset changed"
                dll_arc = arc(dll_name, "CLKIN", f"STEP[{bit}]")
                route = routed[(dll_name + f"/STEP[{bit}]", name + "/D")]
                setup_values = re.findall(r"\(SETUPHOLD \((?:pos|neg)edge D\) \(posedge CLK\) \(([^)]+)\)", sdf_cells[name])
                assert len(setup_values) == 2, f"{name}: DLL capture D setup checks missing"
                setup = max(max(numbers(value)) for value in setup_values) * unit
                total = dll_arc + route + setup
                assert total <= 40.0, f"{name}: DLL STEP arc+route+setup {total:.3f}ns exceeds 40ns budget"
                step_paths.append({"source": dll_name + f"/STEP[{bit}]", "endpoint": name + "/D",
                                   "dll_arc_max_ns": dll_arc, "route_max_ns": route,
                                   "setup_max_ns": setup, "arc_route_and_setup_max_ns": total})
            endpoints = [(name, "RESET") for name, _, _ in targets] + [(name, "CLEAR") for name in falling_names]
            ddr_distribution = reset_distribution(ddr_source, endpoints)
            ddr_distribution.update({"source_audit": ddr_audit, "primitive_counts": counts,
                                     "negative_edge_calibration_registers": len(falling_names),
                                     "negative_edge_clock_inverter": inverted_ui_name,
                                     "dll_step_capture": {"enable_equation": "!ddr_init_st_rrr && ddr_init_st_rr && dll_lock",
                                                          "budget_ns": 40.0, "paths": step_paths}})
        reset_constraints = None
        if sdc is not None:
            audited = {path["endpoint"] for path in paths + divider_audit["paths"]}
            if ddr_distribution is not None:
                audited.update(path["endpoint"] for path in ddr_distribution["paths"])
            all_reset_pins = {name + "/" + pin for name, (_, ports) in cells.items()
                              for pin in ports if pin in {"RESET", "RESETN", "CLEAR"}}
            selected, groups = set(), []
            for line in sdc.splitlines():
                if not line.lstrip().startswith("set_false_path "):
                    continue
                match = re.search(r"-to\s+\[get_pins\s+\{([^}]+)\}\]", line)
                if not match:
                    continue
                for pattern in match[1].split():
                    # CLEAR exceptions elsewhere are reset synchronizer entry
                    # points, not covered by the stopped-clock proof. Any
                    # CLEAR selector that reaches this DDR PHY must be audited.
                    phy_clear = pattern.endswith("/CLEAR") and any(
                        pin.startswith("u_memory/u_ddr3/gw3_top/u_ddr_phy_top/") and fnmatchcase(pin, pattern)
                        for pin in all_reset_pins)
                    if not pattern.endswith(("/RESET", "/RESETN")) and not phy_clear:
                        continue
                    pins = {pin for pin in all_reset_pins if fnmatchcase(pin, pattern)}
                    assert pins, f"initialization reset exception matches no routed pins: {pattern}"
                    extra = pins - audited
                    assert not extra, f"reset exception includes unaudited endpoints: {sorted(extra)}"
                    selected.update(pins)
                    groups.append({"selector": pattern, "endpoints": len(pins)})
            # An endpoint without an exception can still pass ordinary STA.
            # Record coverage without requiring every safe reset path be cut.
            reset_constraints = {"groups": groups, "selected_endpoints": len(selected),
                                 "audited_endpoints_without_exception": sorted(audited-selected)}
        return [], {"source": source, "control_period_ns": 20.0, "clock_enable_delay_cycles": 4,
                    "reset_budget_ns": 40.0, "stopped_clock_window_ns": 80.0,
                    "input_buffer_max_ns": input_delay, "source_clock_route_max_ns": clock_route,
                    "source_clock_to_q_max_ns": clock_to_q, "paths": paths,
                    "tmds_clock_lane": {"serializer": clock_serializer, "word_d9_to_d0": word,
                                         "low_unit_intervals": 5, "high_unit_intervals": 5,
                                         "differential_ports": list(expected_lanes[clock_serializer])},
                    "pixel_divider": divider_audit, "ddr_phy": ddr_distribution, 'resolved_logic': resolved_logic,
                    "sdc_reset_exception_coverage": reset_constraints}
    except (AssertionError, KeyError, ValueError) as error:
        return [f"stopped-clock reset VO/SDF audit failed: {error}"], {}


def audit_physical(physical, self_test=False):
    """Read a hash-bound existing candidate; never alter its inputs or reports."""
    from pathlib import Path
    import hashlib
    import json
    from datetime import datetime
    physical = Path(physical).resolve()
    root = Path(__file__).resolve().parents[1]
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    inputs = json.loads((physical / 'physical_inputs.json').read_text())
    for name, expected in inputs['input_sha256'].items():
        if Path(name).name != name or sha(physical / name) != expected:
            raise ValueError('Physical input drift: ' + name)
    prior_file = physical / 'pll-audit.json'
    prior = json.loads(prior_file.read_text())
    parent = json.loads((physical / 'parent_integration_inputs.json').read_text())
    stage = Path(inputs['parent_candidate']) / 'workstation/Prj1'
    source = prior['ddr_source']
    reference = root / 'vendor/ddr3_reference/ddr3_memory_interface.vo'
    encrypted = stage / 'vendor/gowin_ddr3/ddr3_memory_interface.v'
    sequence = physical / 'pll-audit-view/docs/evidence/ddr_reset_sequence.json'
    checker = stage / 'scripts/audit_ddr_reset_sequence.py'
    for path, expected in [(reference, source['source_sha256']), (encrypted, source['encrypted_ip_sha256']),
                           (sequence, source['sequence_evidence_sha256']), (checker, source['sequence_checker_sha256'])]:
        if sha(path) != expected:
            raise ValueError('Previously verified DDR source/sequence evidence changed: ' + str(path))
    if sha(checker) != parent['staged_input_sha256']['scripts/audit_ddr_reset_sequence.py']:
        raise ValueError('DDR source checker detached from parent manifest')
    sequence_data = json.loads(sequence.read_text())
    cases = sequence_data['cases']
    if {case['case'] for case in cases} != {'startup', 'recalibration', 'external_reset', 'lock_loss'}:
        raise ValueError('Incomplete DDR startup/stop cases')
    for case in cases:
        stops = [event for event in case['reset_falls'] if event['pll_enabled'] == 0]
        if not (case['cells'] == 108 and case['clock_period_ns'] == 20 and stops
                and all(event['stopped_cycles'] >= 8 and event['cycles_to_restart'] >= 4 for event in stops)):
            raise ValueError('DDR stopped-clock80ns source window not established')
    base = physical / 'impl/pnr/custom_138k_integration'
    sdf, vo, sdc = (path.read_text() for path in [base.with_suffix('.sdf'), base.with_suffix('.vo'), physical / 'physical.sdc'])
    errors, result = inspect_serializer_startup(sdf, vo, source, sdc)
    if errors:
        raise ValueError('; '.join(errors))
    rejected = {}
    if self_test:
        gate = result['resolved_logic']['pll_stop_inverter']['cell']
        phy = 'u_memory/u_ddr3/gw3_top/u_ddr_phy_top'
        def changed_port(kind, name, pin, value):
            expression = r'^' + kind + r'\s+\\' + re.escape(name) + r'\s*\((.*?)^\);'
            match = re.search(expression, vo, re.M | re.S)
            if match is None:
                raise ValueError('Negative mutation target missing: ' + name)
            changed, count = re.subn(r'(\.' + pin + r'\()([^)]*)', r'\g<1>' + value, match[0])
            if count != 1 or changed == match[0]:
                raise ValueError('Negative mutation was not exact: ' + name)
            return vo[:match.start()] + changed + vo[match.end():]
        def reject(label, changed_vo=vo, changed_sdf=sdf, reason=''):
            bad, unused = inspect_serializer_startup(changed_sdf, changed_vo, source, sdc)
            if not bad or not any(reason in message for message in bad):
                raise ValueError('Mutation did not fail its intended gate: ' + label + ' ' + str(bad))
            rejected[label] = bad
        pattern = r'(^defparam\s+\\' + re.escape(gate) + r'\s*\.INIT\s*=\s*)2\x27h1;'
        bad_polarity, count = re.subn(pattern, r"\g<1>2'h2;", vo, flags=re.M)
        if count != 1:
            raise ValueError('Gate INIT mutation target count')
        reject('gate_polarity', bad_polarity, reason='polarity changed')
        reject('PLL_ENCLK2_bypass', changed_port('PLL', 'u_memory/u_pll/u_pll_0/PLL_inst', 'ENCLK2', 'VCC'), reason='unique logic driver')
        reject('stop_clock_bypass', changed_port('DFFCE', phy + '/stop_reg_2_s0', 'CLK', 'memory_clk'), reason='control clock/reset')
        extra = '\nOBUF extra_stop_consumer (\n.I(\\u_memory/pll_stop ),\n.O(extra_pin)\n);\n'
        reject('additional_gate_fanout', vo + extra, reason='additional or bypassed fanout')
        endpoint = next(path['endpoint'] for path in result['ddr_phy']['paths'] if path['endpoint'].endswith('/RESET'))
        name, pin = endpoint.rsplit('/', 1)
        kind = next(kind for kind in ('OSER8_MEM', 'IDES8_MEM', 'OSER8', 'DQS')
                    if re.search(r'^' + kind + r'\s+\\' + re.escape(name) + r'\s*\(', vo, re.M))
        reject('DDR_endpoint_reset_bypass', changed_port(kind, name, pin, 'GND'), reason='reset bypasses')
        route_source = phy + '/ddr_rsti_reg_2_s0/Q'
        route_matches = [match for match in re.finditer(r'\(INTERCONNECT\s+(\S+)\s+(\S+)\s+([^\n]+)', sdf)
                         if re.sub(r'\\(.)', r'\1', match[1]) == route_source
                         and re.sub(r'\\(.)', r'\1', match[2]) == endpoint]
        if len(route_matches) != 1:
            raise ValueError('Reset delay mutation target count')
        match = route_matches[0]
        bad_sdf = sdf[:match.start(3)] + '(45:45:45))' + sdf[match.end():]
        reject('reset_distribution_over40ns', changed_sdf=bad_sdf, reason='exceeds 40ns')
        reject('stop_first_stage_source_bypass', changed_port('DFFCE', phy + '/stop_reg_0_s0', 'D', 'VCC'), reason='first-stage source')
    paths = [path for group in (result['pixel_divider'], result['ddr_phy']) for path in group['paths']] + result['paths']
    evidence_paths = [Path(__file__), physical / 'physical_inputs.json', physical / 'parent_integration_inputs.json',
                      prior_file, base.with_suffix('.vo'), base.with_suffix('.sdf'), physical / 'physical.sdc',
                      reference, encrypted, sequence, checker]
    return dict(schema=1, recorded_at=datetime.now().astimezone().isoformat(), identity=inputs['identity'],
                scope='Read-only supplemental startup subgate; no frozen audit overwritten and no full physical signoff',
                startup_subgate_passed=True, original_frozen_pll_gate_passed=prior['passed'],
                physical_inputs_changed=False, clocks_or_exceptions_relaxed=False, thresholds_relaxed=False,
                full_pll_gate_reexecution_required=True, all_physical_gates_passed=False,
                serializer_startup=result, source_sequence_cases=[dict(case=case['case'], cells=case['cells'], clock_period_ns=case['clock_period_ns']) for case in cases],
                maximum_settle_and_recovery_ns=max(path['settle_and_recovery_max_ns'] for path in paths),
                audited_reset_endpoints=len(paths), negative_checks=rejected,
                evidence_sha256={str(path): sha(path) for path in evidence_paths},
                implementation_changed=False, new_pnr_executed=False, hardware_tested=False,
                sram_programmed=False, flash_programmed=False,
                remaining_failures='Original F02 DDR hold/setup, audio/USB STA and model-readiness route failures remain unchanged.')


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--physical', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    try:
        result = audit_physical(args.physical, args.self_test)
    except (OSError, ValueError, KeyError, AssertionError) as error:
        parser.exit(2, 'Supplemental startup audit failed: ' + str(error) + '\n')
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('identity', 'startup_subgate_passed', 'audited_reset_endpoints',
                                                'maximum_settle_and_recovery_ns', 'original_frozen_pll_gate_passed',
                                                'all_physical_gates_passed')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
