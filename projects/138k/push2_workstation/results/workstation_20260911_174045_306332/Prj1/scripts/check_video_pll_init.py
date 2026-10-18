#!/usr/bin/env python3
"""Audit the two routed video PLL_INIT configuration/reset propagation paths.

API: inspect_video_pll_init(sdf_text, netlist_text, root=None) -> (errors, evidence).
The 10 ns bound covers the 50 MHz IBUF, source clock route, FF C2Q, every
combinational cell arc and every net route, within the helper's 20 ns state
window. It is a digital distribution check, not an analog PLL/jitter model.
Run --self-test for retained synthetic positive/negative checker regressions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "u_video/u_clock/g_hardware.u_pll"
SOURCE_HASHES = {
    "vendor/sipeed_dvi/video_pll_1080p_gw5a.v":
        "0807a7d45aa095e327a6da3ba119fac727d982cdb99b6da02bdf11f6858fdad3",
    "vendor/sipeed_dvi/video_pll_init.v":
        "ca1e667fe6f5e9c67e566a8acbd215039b027743bd105d32e1bf91ac380e0453",
}
OFFICIAL_HELPER_SHA256 = "3ef05a1ba92157d73e3c54ed9d589645508a4ae332d8bcf133a0457cc3e866c8"
BUDGET_NS = 10.0


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unescape(value):
    return re.sub(r"\\(.)", r"\1", value)


def normalize(value):
    return re.sub(r"\s+|\\", "", value)


def numbers(value):
    return [float(item) for item in re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", value)]


class RoutedDesign:
    def __init__(self, sdf, netlist):
        scale = re.search(r"\(TIMESCALE\s+([\d.]+)\s*(ns|ps|us)\)", sdf)
        require(scale is not None, "SDF timescale missing or unsupported")
        self.unit = float(scale[1]) * {"ns": 1, "ps": .001, "us": 1000}[scale[2]]
        self.routes = {}
        for match in re.finditer(r"\(INTERCONNECT\s+(\S+)\s+(\S+)\s+([^\n]+)", sdf):
            key = (unescape(match[1]), unescape(match[2]))
            require(key not in self.routes, f"duplicate SDF interconnect: {key}")
            values = numbers(match[3])
            require(bool(values), f"empty SDF route delay: {key}")
            self.routes[key] = max(values) * self.unit
        self.sdf_cells = {}
        for block in re.split(r"\n\s*\(CELL\s*\n", sdf)[1:]:
            instance = re.search(r"\(INSTANCE\s+(\S+)\)", block)
            if instance:
                name = unescape(instance[1])
                require(name not in self.sdf_cells, f"duplicate SDF cell: {name}")
                self.sdf_cells[name] = block
        self.cells = {}
        for match in re.finditer(r"^(\w+)\s+(\\\S+|\w+)\s+\((.*?)^\);", netlist, re.M | re.S):
            name = match[2].lstrip("\\")
            require(name not in self.cells, f"duplicate VO cell: {name}")
            ports = {p[1]: normalize(p[2]) for p in re.finditer(r"\.(\w+)\s*\(([^)]*)\)", match[3])}
            self.cells[name] = (match[1], ports)
        self.parameters = {(m[1].lstrip("\\"), m[2]): m[3].strip() for m in
                           re.finditer(r"^defparam\s+(\\\S+|\w+)\s*\.(\w+)\s*=\s*([^;]+);", netlist, re.M)}
        self.widths = {normalize(m[3]): (int(m[1]), int(m[2])) for m in
                       re.finditer(r"(?m)^\s*(?:wire|input|output)\s+\[(\d+):(\d+)\]\s+([^;]+);", netlist)}
        self.drivers = {}
        self.constants = {"1'b0": 0, "1'b1": 1, "1'h0": 0, "1'h1": 1}
        for name, (kind, ports) in self.cells.items():
            if kind in ("GND", "VCC"):
                pin = "G" if kind == "GND" else "V"
                self.constants[ports[pin]] = int(kind == "VCC")
            elif kind.startswith("DFF"):
                self.add_driver(ports["Q"], name, "Q")
            elif kind.startswith("LUT"):
                self.add_driver(ports["F"], name, "F")
            elif kind in ("INV", "IBUF", "OBUF"):
                self.add_driver(ports["O"], name, "O")
        require("clk_50m_ibuf" in self.cells, "direct 50 MHz input IBUF missing")
        kind, ports = self.cells["clk_50m_ibuf"]
        require(kind == "IBUF" and ports["I"] == "clk_50m", "50 MHz IBUF input changed")
        self.clock_net = ports["O"]
        self.input_delay = self.arc("clk_50m_ibuf", "I", "O")

    def add_driver(self, net, name, pin):
        require(net not in self.drivers, f"multiple scalar VO drivers: {net}")
        self.drivers[net] = (name, pin)

    def bits(self, expression):
        # Gowin emits scalar concatenations and descending bus slices. Accept
        # nested concatenations and sized constants, reject unknown expressions.
        if expression.startswith("{") and expression.endswith("}"):
            inner = expression[1:-1]
            repeat = re.fullmatch(r"(\d+)\{(.+)\}", inner)
            if repeat:
                return self.bits(repeat[2]) * int(repeat[1])
            pieces, start, depth = [], 0, 0
            for i, char in enumerate(inner):
                depth += (char == "{") - (char == "}")
                if char == "," and depth == 0:
                    pieces.append(inner[start:i]); start = i+1
            pieces.append(inner[start:])
            return [bit for piece in pieces for bit in self.bits(piece)]
        literal = re.fullmatch(r"(\d+)'([bhd])([0-9a-fA-F]+)", expression)
        if literal:
            width = int(literal[1]); value = int(literal[3], {"b": 2, "h": 16, "d": 10}[literal[2]])
            return ["1'b" + str((value >> i) & 1) for i in range(width-1, -1, -1)]
        sliced = re.fullmatch(r"(.+)\[(\d+):(\d+)\]", expression)
        if sliced:
            base, high, low = sliced[1], int(sliced[2]), int(sliced[3])
        elif expression in self.widths:
            base, (high, low) = expression, self.widths[expression]
        else:
            require(bool(expression) and not re.search(r"[{},:]", expression), f"unsupported VO expression: {expression}")
            return [expression]
        step = -1 if high >= low else 1
        return [f"{base}[{i}]" for i in range(high, low+step, step)]

    def arc(self, name, start, end):
        require(name in self.sdf_cells, f"SDF cell missing: {name}")
        values = re.findall(r"\(IOPATH\s+" + re.escape(start) + r"\s+" + re.escape(end) + r"\s*([^\n]+)", self.sdf_cells[name])
        require(bool(values), f"SDF cell arc missing: {name} {start}->{end}")
        return max(max(numbers(value)) for value in values) * self.unit

    def route(self, source, target):
        require((source, target) in self.routes, f"SDF route missing: {source} -> {target}")
        return self.routes[(source, target)]

    def trace(self, net, endpoint, helper, role, visiting=None):
        if net in self.constants:
            return {"constant": self.constants[net], "total_ns": 0.0, "sources": [], "segments": []}
        visiting = set() if visiting is None else visiting
        require(net not in visiting, f"combinational loop in PLL control: {net}")
        require(net in self.drivers, f"unresolved PLL control source: {net}")
        name, output = self.drivers[net]
        kind, ports = self.cells[name]
        route = self.route(name + "/" + output, endpoint)
        segment = {"kind": "route", "from": name + "/" + output, "to": endpoint, "max_ns": route}
        if kind.startswith("DFF"):
            require(name.startswith(helper + "/"), f"{endpoint}: source {name} is outside corresponding helper {helper}")
            require(ports["CLK"] == self.clock_net, f"helper FF is not on direct 50 MHz: {name}")
            if role == "RESET":
                require(re.search(r"/(?:state|enable_r)[^/]*$", name) is not None,
                        f"PLL RESET does not originate in helper state/enable FF: {name}")
            else:
                index = int(re.search(r"\[(\d+)\]", role)[1]) + (8 if role.startswith("LPFRES") else 0)
                require(re.search(rf"/RomDreg_{index}_s\d+$", name) is not None,
                        f"{role}: wrong helper ROM data bit source {name}")
            clock_route = self.route("clk_50m_ibuf/O", name + "/CLK")
            cq = self.arc(name, "CLK", "Q")
            return {"total_ns": self.input_delay + clock_route + cq + route, "sources": [name],
                    "segments": [
                        {"kind": "cell", "from": "clk_50m_ibuf/I", "to": "clk_50m_ibuf/O", "max_ns": self.input_delay},
                        {"kind": "route", "from": "clk_50m_ibuf/O", "to": name + "/CLK", "max_ns": clock_route},
                        {"kind": "cell", "from": name + "/CLK", "to": name + "/Q", "max_ns": cq}, segment]}
        require(kind == "INV" or re.fullmatch(r"LUT[1-6]", kind), f"unsupported PLL control primitive: {name} ({kind})")
        input_pins = ["I"] if kind == "INV" else [f"I{i}" for i in range(int(kind[3:]))]
        candidates, sources = [], set()
        for pin in input_pins:
            child = self.trace(ports[pin], name + "/" + pin, helper, role, visiting | {net})
            if not child["sources"]:
                continue
            sources.update(child["sources"])
            delay = self.arc(name, pin, output)
            candidates.append({"total_ns": child["total_ns"] + delay + route,
                               "segments": child["segments"] + [
                                   {"kind": "cell", "from": name + "/" + pin, "to": name + "/" + output, "max_ns": delay}, segment]})
        require(bool(candidates), f"constant combinational control cone needs explicit review: {name}")
        worst = max(candidates, key=lambda item: item["total_ns"])
        return {**worst, "sources": sorted(sources)}


def inspect_video_pll_init(sdf, netlist, root=None):
    """Return errors and evidence without mutating source or build files."""
    root = ROOT if root is None else Path(root)
    errors, evidence = [], {"budget_ns": BUDGET_NS, "state_window_ns": 20.0,
                            "official_helper_sha256": OFFICIAL_HELPER_SHA256, "stages": []}
    try:
        actual = {name: sha((root / name).read_bytes()) for name in SOURCE_HASHES}
        for name, expected in SOURCE_HASHES.items():
            require(actual[name] == expected, f"audited PLL_INIT source hash changed: {name}")
        evidence["source_sha256"] = actual
        evidence["routed_netlist_sha256"] = sha(netlist.encode())
        evidence["sdf_sha256"] = sha(sdf.encode())
        design = RoutedDesign(sdf, netlist)
        previous_output = design.clock_net
        for stage, input_mhz, multiply, eighths, divisor in (
                ("u_reference", "50", 24, 6, 25), ("u_tmds", "49.5", 15, 0, 1)):
            pll = PREFIX + "/" + stage + "/PLL_inst"
            helper = PREFIX + "/" + stage + "/u_pll_init"
            require(pll in design.cells and design.cells[pll][0] == "PLL", f"expected PLL_inst hierarchy missing: {pll}")
            ports = design.cells[pll][1]
            require(ports["CLKIN"] == previous_output, f"video PLL cascade input changed: {pll}")
            previous_output = ports["CLKOUT0"]
            expected_params = {"FCLKIN": f'"{input_mhz}"', "MDIV_SEL": str(multiply),
                               "MDIV_FRAC_SEL": str(eighths), "ODIV0_SEL": str(divisor),
                               "ODIV0_FRAC_SEL": "0", "IDIV_SEL": "1", "FBDIV_SEL": "1",
                               "CLKOUT0_EN": '"TRUE"', "CLKFB_SEL": '"INTERNAL"',
                               "DYN_ICP_SEL": '"TRUE"', "DYN_LPF_SEL": '"TRUE"',
                               "DYN_MDIV_SEL": '"FALSE"', "DYN_IDIV_SEL": '"FALSE"',
                               "DYN_FBDIV_SEL": '"FALSE"', "DYN_ODIV0_SEL": '"FALSE"'}
            for parameter, expected in expected_params.items():
                require(design.parameters.get((pll, parameter)) == expected,
                        f"{pll}: {parameter} differs from audited {expected}")
            helper_ff = [name for name, (kind, _) in design.cells.items()
                         if name.startswith(helper + "/") and kind.startswith("DFF")]
            require(bool(helper_ff), f"PLL_INIT helper registers missing: {helper}")
            require(all(design.cells[name][1]["CLK"] == design.clock_net for name in helper_ff),
                    f"PLL_INIT helper has a clock other than direct 50 MHz: {helper}")
            entry = {"pll": pll, "helper": helper, "init_clock_mhz": 50, "clk_period_ns": 20,
                     "multi_fac": multiply, "parameters": expected_params, "helper_ff_count": len(helper_ff), "paths": []}
            evidence["stages"].append(entry)
            for bus, width in (("ICPSEL", 6), ("LPFRES", 3), ("LPFCAP", 2), ("RESET", 1)):
                bits = design.bits(ports[bus])
                require(len(bits) == width, f"{pll}/{bus}: unexpected bus width {len(bits)}")
                for index, net in enumerate(reversed(bits)):
                    role = bus if bus == "RESET" else f"{bus}[{index}]"
                    expected_constant = bus == "LPFCAP" or (bus == "ICPSEL" and index >= (2 if multiply == 24 else 1))
                    if expected_constant:
                        require(design.constants.get(net) == 0, f"{pll}/{role}: expected constant zero")
                        path = {"constant": 0, "total_ns": 0.0, "sources": [], "segments": []}
                    else:
                        require(net not in design.constants, f"{pll}/{role}: dynamic helper output replaced by constant")
                        path = design.trace(net, pll + "/" + role, helper, role)
                        require(path["total_ns"] <= BUDGET_NS,
                                f"{pll}/{role}: full propagation {path['total_ns']:.3f} ns exceeds {BUDGET_NS:.3f} ns")
                    entry["paths"].append({"endpoint": pll + "/" + role, **path,
                                           "margin_to_state_window_ns": 20.0-path["total_ns"]})
        dynamic = [p for stage in evidence["stages"] for p in stage["paths"] if p["sources"]]
        evidence["dynamic_endpoint_count"] = len(dynamic)
        evidence["maximum_propagation_ns"] = max(p["total_ns"] for p in dynamic)
        evidence["boundaries"] = [
            "Conservative combinational max-delay sum; all nonconstant fanins must terminate at audited helper FFs.",
            "Source hashes bind CLK_PERIOD=20, MULTI_FAC=24/15 and the vendor state sequence; ordinary helper FF setup/hold remains in STA.",
            "Static zero pins are checked by topology and excluded from changing-signal delay sums.",
            "PLL analog settling, reset pulse analog requirements and output jitter are not modeled by the Gowin PLL SDF cell.",
            "The separate serializer startup audit verifies ENCLK0 and the 80 ns stopped-clock reset sequence."]
    except (OSError, KeyError, ValueError, TypeError, RecursionError) as error:
        errors.append(f"video PLL_INIT VO/SDF audit failed: {error}")
    return errors, evidence


def _fixture():
    """Small routed-form fixture with LUT+INV paths, two clocks and real pins."""
    vo, sdf, routes = [], ["(DELAYFILE", " (TIMESCALE 1 ns)"], []
    def cell(kind, name, ports, arcs=(), params=None):
        vo.append(kind + " \\" + name + "  (\n" + ",\n".join(" ."+p+"("+n+")" for p,n in ports.items()) + "\n);")
        for key,value in (params or {}).items(): vo.append(f"defparam \\{name} .{key}={value};")
        sdf.append(" (CELL\n  (CELLTYPE \""+kind+"\")\n  (INSTANCE "+name+")\n  (DELAY (ABSOLUTE\n" +
                   "\n".join(f"   (IOPATH {a} {b} ({delay}:{delay}:{delay}))" for a,b,delay in arcs) + "\n  ))\n )")
    def route(source, target, delay=.4): routes.append(f"  (INTERCONNECT {source} {target} ({delay}:{delay}:{delay}))")
    cell("GND","gnd",{"G":"GND"}); cell("VCC","vcc",{"V":"VCC"})
    cell("IBUF","clk_50m_ibuf",{"I":"clk_50m","O":"clk_50m_d"},[("I","O",.5)])
    previous="clk_50m_d"
    for stage,mul,frac,div,fin in (("u_reference",24,6,25,"50"),("u_tmds",15,0,1,"49.5")):
        base=PREFIX+"/"+stage; helper=base+"/u_pll_init"; pll=base+"/PLL_inst"
        nets={}
        for index in ([0,1] if mul==24 else [0])+[8,9,10]:
            name=helper+f"/RomDreg_{index}_s0"; net=base+f"_rom{index}"; nets[index]=net
            cell("DFFCE",name,{"D":"GND","CLK":"clk_50m_d","CE":"VCC","CLEAR":"GND","Q":net},[("CLK","Q",.3)])
            route("clk_50m_ibuf/O",name+"/CLK",1.1)
            pin=f"ICPSEL[{index}]" if index<6 else f"LPFRES[{index-8}]"
            route(name+"/Q",pll+"/"+pin)
        state=helper+"/state_0_s0"; invert=helper+"/reset_inverter"; lut=helper+"/reset_decode"
        cell("DFFCE",state,{"D":"VCC","CLK":"clk_50m_d","CE":"VCC","CLEAR":"GND","Q":base+"_state"},[("CLK","Q",.3)])
        route("clk_50m_ibuf/O",state+"/CLK",1.1)
        cell("INV",invert,{"I":base+"_state","O":base+"_inverted"},[("I","O",.6)])
        route(state+"/Q",invert+"/I")
        cell("LUT2",lut,{"I0":base+"_inverted","I1":"GND","F":base+"_reset"},[("I0","F",.7),("I1","F",.8)])
        route(invert+"/O",lut+"/I0"); route(lut+"/F",pll+"/RESET")
        ports={"CLKIN":previous,"CLKOUT0":base+"_clock","RESET":base+"_reset",
               "ICPSEL":"{"+",".join(nets.get(i,"GND") for i in range(5,-1,-1))+"}",
               "LPFRES":"{"+",".join(nets[i] for i in [10,9,8])+"}","LPFCAP":"{GND,GND}"}
        params={"FCLKIN":f'"{fin}"',"MDIV_SEL":str(mul),"MDIV_FRAC_SEL":str(frac),"ODIV0_SEL":str(div),
                "ODIV0_FRAC_SEL":"0","IDIV_SEL":"1","FBDIV_SEL":"1","CLKOUT0_EN":'"TRUE"',"CLKFB_SEL":'"INTERNAL"',
                "DYN_ICP_SEL":'"TRUE"',"DYN_LPF_SEL":'"TRUE"',"DYN_MDIV_SEL":'"FALSE"',"DYN_IDIV_SEL":'"FALSE"',
                "DYN_FBDIV_SEL":'"FALSE"',"DYN_ODIV0_SEL":'"FALSE"'}
        cell("PLL",pll,ports,params=params); previous=ports["CLKOUT0"]
    sdf.append(" (CELL\n  (CELLTYPE \"prj1_top\")\n  (INSTANCE)\n  (DELAY (ABSOLUTE\n"+"\n".join(routes)+"\n  ))\n )\n)")
    return "\n".join(sdf),"\n".join(vo)+"\n"


def self_test(root=None):
    sdf,vo=_fixture(); errors,good=inspect_video_pll_init(sdf,vo,root)
    require(not errors, f"positive checker fixture failed: {errors}")
    require(abs(good["maximum_propagation_ns"]-4.4)<1e-9, "fixture must include IBUF, clock route, C2Q, INV, LUT and three routes")
    ref=PREFIX+"/u_reference"; pll=ref+"/PLL_inst"; rom=ref+"/u_pll_init/RomDreg_0_s0"
    cases={
        "dynamic_ICP_disabled": (sdf,vo.replace(f"defparam \\{pll} .DYN_ICP_SEL=\"TRUE\";",f"defparam \\{pll} .DYN_ICP_SEL=\"FALSE\";",1)),
        "wrong_ICP_source": (sdf.replace(rom,ref+"/u_pll_init/RomDreg_1_s9"),vo.replace(rom,ref+"/u_pll_init/RomDreg_1_s9")),
        "settings_route_over_budget": (sdf.replace(f"{rom}/Q {pll}/ICPSEL[0] (0.4:0.4:0.4)",f"{rom}/Q {pll}/ICPSEL[0] (12:12:12)"),vo),
        "reset_LUT_arc_over_budget": (sdf.replace("(IOPATH I0 F (0.7:0.7:0.7))","(IOPATH I0 F (12:12:12))",1),vo),
        "helper_clock_changed": (sdf,vo.replace(".CLK(clk_50m_d)",".CLK(other_clock)",1)),
        "settings_source_constant": (sdf,vo.replace(".ICPSEL({GND,GND,GND,GND,"+ref+"_rom1,"+ref+"_rom0})",".ICPSEL({GND,GND,GND,GND,"+ref+"_rom1,GND})",1)),
    }
    result=[]
    for name,(bad_sdf,bad_vo) in cases.items():
        require((bad_sdf,bad_vo)!=(sdf,vo),f"negative fixture mutation did not apply: {name}")
        rejected,_=inspect_video_pll_init(bad_sdf,bad_vo,root)
        require(bool(rejected),f"negative checker fixture was accepted: {name}")
        result.append({"case":name,"rejected":True,"errors":rejected})
    return {"positive_maximum_propagation_ns":good["maximum_propagation_ns"],"negative_cases":result}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--sdf",type=Path)
    parser.add_argument("--netlist",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if args.self_test:
        result={"errors":[],"self_test":self_test(args.root)}
    else:
        sdf_path=args.sdf or args.root/"impl/pnr/Prj1.sdf"
        vo_path=args.netlist or args.root/"impl/pnr/Prj1.vo"
        errors,evidence=inspect_video_pll_init(sdf_path.read_text(encoding="utf-8"),vo_path.read_text(encoding="utf-8"),args.root)
        result={"errors":errors,"evidence":evidence}
    encoded=json.dumps(result,indent=2)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(encoded,encoding="utf-8")
        print(("FAIL" if result["errors"] else "PASS")+": "+str(args.output))
    else: print(encoded,end="")
    raise SystemExit(bool(result["errors"]))


if __name__=="__main__":
    main()
