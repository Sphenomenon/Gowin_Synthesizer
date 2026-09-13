"""Audit routed video/DDR reset release and DLL capture using Gowin VO/SDF.

Gowin 1.9.12.03 can omit these OSER10 RESET paths from report_exceptions even
when a matching max-delay constraint is active. Do not treat that as evidence
of zero delay: verify actual primitive connections and all 114 reset endpoints.
"""
import re
from fnmatch import fnmatchcase


def inspect_serializer_startup(sdf, netlist, ddr_audit=None, sdc=None):
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
        clock_serializer = "u_video/u_dvi/clock_phy/tmds_serdes_inst0"
        expected_lanes = {clock_serializer: ("tmds_clk_p", "tmds_clk_n")}
        expected_lanes.update({f"u_video/u_dvi/gen_enc[{i}].dvi_tx_tmds_phy_inst/tmds_serdes_inst0":
                               (f"tmds_data_p[{i}]", f"tmds_data_n[{i}]") for i in range(3)})
        assert {name for name, _ in serdes} == set(expected_lanes), "TMDS serializer lane inventory changed"
        for name, ports in serdes:
            buffer_name = name.rsplit("/", 1)[0] + "/tmds_bufds_isnt0"
            kind, buffer = cells[buffer_name]
            assert kind == "ELVDS_OBUF" and buffer["I"] == ports["Q"] and \
                (buffer["O"], buffer["OB"]) == expected_lanes[name], \
                f"{name}: serializer no longer directly drives its audited TMDS differential ports"
        clock_ports = cells[clock_serializer][1]
        for bit in range(10):
            assert clock_ports[f"D{bit}"] in (ground if bit < 5 else power), \
                f"TMDS clock D{bit} differs from the audited 10'b1111100000 clock word"

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
        if ddr_audit is not None:
            # The separate 108-cell source-netlist audit establishes the 80ns
            # stop window. Here verify its routed reset/gate boundary and every
            # primitive endpoint; normal PHY data paths remain normal STA.
            phy = "u_memory/u_ddr3/gw3_top/u_ddr_phy_top"
            ddr_source = phy + "/ddr_rsti_reg_2_s0"
            reset_ff = cells[ddr_source][1]
            stop = [cells[phy + f"/stop_reg_{i}_s0"][1] for i in range(3)]
            for i, ports in enumerate(stop):
                assert ports["CLK"] == src["CLK"] and ports["CE"] in power, "DDR stop control clock changed"
                if i:
                    assert ports["D"] == stop[i-1]["Q"], "DDR stop pipeline changed"
            inverter_name = phy + "/pll_stop_s0"
            kind, inverter = cells[inverter_name]
            assert kind == "LUT1" and parameters[(inverter_name, "INIT")] == "2'h1", "DDR clock gate polarity changed"
            assert inverter["I0"] == stop[2]["Q"], "DDR PLL gate no longer follows audited stop pipeline"
            ddr_pll = cells["u_memory/u_pll/u_pll_0/PLL_inst"][1]
            assert ddr_pll["ENCLK2"] == inverter["F"], "DDR PLL output gate bypasses audited stop control"
            ui_divider_name = phy + "/fclkdiv"
            ui_divider = cells[ui_divider_name][1]
            assert ui_divider["HCLKIN"] == ddr_pll["CLKOUT2"], "DDR UI clock bypasses gated memory clock"
            assert cells[ui_divider_name][0] == "CLKDIV" and parameters[(ui_divider_name, "DIV_MODE")] == '"4"', \
                "DDR UI clock no longer uses the audited /4 divider"
            divider_reset_name = phy + "/n809_6_s0"
            reset_kind, divider_reset = cells[divider_reset_name]
            assert reset_kind == "LUT1" and parameters[(divider_reset_name, "INIT")] == "2'h1" and \
                divider_reset["I0"] == reset_ff["Q"] and divider_reset["F"] == ui_divider["RESETN"], \
                "DDR UI divider reset no longer follows inverted controller reset"
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
            inverted_ui_name = phy + "/u_ddr_init/n2497_6_s0"
            inverse_kind, inverse = cells[inverted_ui_name]
            assert inverse_kind == "INV" and inverse["I"] == ui_divider["CLKOUT"], \
                "DDR negative-edge calibration clock bypasses the stopped UI divider"
            falling_names = [phy + f"/u_ddr_init/read_calibration_logic_gen[{lane}].rburst_neg{suffix}_s0"
                             for lane in range(4) for suffix in ("", "_r")]
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
            capture_enable_name = phy + "/n2474_s0"
            ce_kind, ce = cells[capture_enable_name]
            recent_name, old_name = phy + "/ddr_init_st_rr_s0", phy + "/ddr_init_st_rrr_s0"
            recent, old = cells[recent_name][1], cells[old_name][1]
            for name in (recent_name, old_name):
                kind, ports = cells[name]
                assert kind == "DFFCE" and ports["CLK"] == ui_divider["CLKOUT"] and \
                    ports["CLEAR"] == reset_ff["Q"] and ports["CE"] in power and parameters[(name, "INIT")] == "1'b0", \
                    "DLL capture-enable history no longer uses the audited UI pipeline"
            assert old["D"] == recent["Q"], "DLL capture-enable history pipeline changed"
            assert ce_kind == "LUT3" and parameters[(capture_enable_name, "INIT")] == "8'h40" and \
                ce["I0"] == old["Q"] and ce["I1"] == recent["Q"] and ce["I2"] == dll["LOCK"], \
                "DLL capture enable is not !old && recent && dll_lock"
            captures = [phy + f"/dll_step_base_{bit}_s0" for bit in range(8)]
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
                    "tmds_clock_lane": {"serializer": clock_serializer, "word_d9_to_d0": "1111100000",
                                         "low_unit_intervals": 5, "high_unit_intervals": 5,
                                         "differential_ports": list(expected_lanes[clock_serializer])},
                    "pixel_divider": divider_audit, "ddr_phy": ddr_distribution,
                    "sdc_reset_exception_coverage": reset_constraints}
    except (AssertionError, KeyError, ValueError) as error:
        return [f"stopped-clock reset VO/SDF audit failed: {error}"], {}
