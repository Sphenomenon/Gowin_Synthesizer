#!/usr/bin/env python3
"""Build immutable CH569 firmware, ISP utility, and an isolated FPGA UART bridge."""
from pathlib import Path
from datetime import datetime
import hashlib, json, os, shutil, subprocess

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / "ch569_midi_probe/sources_20260911_130856_118335"
SDK = SOURCE / "wch/EVT/EXAM/SRC"
HS = SOURCE / "wch/EVT/EXAM/USBSS/USBH/HOST_SS/User/Host_HS"
GCC = Path(os.environ.get("CH569_GCC", str(Path.home()/".local/opt/amd/2025.2.1/gnu/riscv/lin/bin/riscv64-unknown-elf-gcc")))

def main():
    out = BASE / "results" / datetime.now().strftime("build_%Y%m%d_%H%M%S_%f")
    out.mkdir(parents=True)
    fw = out / "firmware"
    shutil.copytree(BASE/"firmware", fw)
    # WCH's Windows project includes an uppercase extension on a lowercase file.
    (fw/"CH56xSFR.H").write_text('#include "CH56xSFR.h"\n')
    # Use the board's supplied enhanced CH569 firmware's startup convention:
    # retain the ROM loader's privilege-mode bits when enabling interrupt state.
    startup = (SDK/"Startup/startup_CH56x.S").read_text()
    assert "csrw mstatus, t0" in startup
    (fw/"startup_CH56x.S").write_text(startup.replace("csrw mstatus, t0", "csrs mstatus, t0"))
    # Keep vendor originals untouched; audit two narrowly scoped low-level changes.
    host = (HS/"CH56x_host_hs.c").read_text()
    old = "R16_UH_EP_PID = endp_pid;\n        R8_USB_INT_FG = RB_USB_IF_TRANSFER;"
    assert old in host
    host = host.replace(old, "/* Clear stale completion BEFORE triggering the next transaction. */\n        R8_USB_INT_FG = RB_USB_IF_TRANSFER;\n        R16_UH_EP_PID = endp_pid;")
    (fw/"CH56x_host_hs.c").write_text(host)
    link = (SDK/"Ld/Link.ld").read_text()
    link = link.replace("LENGTH = 448K", "LENGTH = 32K")
    link = link.replace(".DMADATA :", ".DMADATA (NOLOAD) :")
    link = link.replace("*(.dmadata*)", "*(.DMADATA*)\n        *(.dmadata*)")
    link += '\nASSERT(_ebss <= _susrstack, "RAM globals overlap stack")\n'
    link += 'ASSERT(_start == 0, "CH569 reset must start at flash address zero")\n'
    (fw/"Link.ld").write_text(link)
    commands = []
    def run(args, name, cwd=out):
        commands.append([str(x) for x in args])
        p = subprocess.run([str(x) for x in args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (out/name).write_bytes(p.stdout)
        if p.returncode:
            print(p.stdout.decode(errors="replace")); raise RuntimeError(name)
    flags = ["-march=rv32imac_zicsr", "-mabi=ilp32", "-Os", "-msmall-data-limit=0",
             "-ffunction-sections", "-fdata-sections", "-fno-builtin", "-fno-common", "-g",
             "-DFREQ_SYS=120000000", "-I"+str(SDK/"Peripheral/inc"),
             "-I"+str(SDK/"RVMSIS"), "-I"+str(HS), "-I"+str(fw)]
    src = [fw/"main.c", fw/"midi_descriptor.c", fw/"CH56x_host_hs.c",
           SDK/"Peripheral/src/CH56x_sys.c", SDK/"Peripheral/src/CH56x_clk.c",
           SDK/"Peripheral/src/CH56x_uart.c", fw/"startup_CH56x.S"]
    run([GCC, *flags, "-nostdlib", "-Wl,--build-id=none", "-Wl,--gc-sections", "-Wl,-Map="+str(out/"probe.map"),
         "-T", fw/"Link.ld", *src, "-lgcc", "-o", out/"probe.elf"], "firmware_build.log")
    prefix = str(GCC).removesuffix("gcc")
    run([prefix+"objcopy", "-O", "binary", out/"probe.elf", out/"probe.bin"], "objcopy.log")
    run([prefix+"size", "-A", out/"probe.elf"], "size.txt")
    run([prefix+"readelf", "-lS", out/"probe.elf"], "elf_layout.txt")
    assert 0 < (out/"probe.bin").stat().st_size < 32768
    isp = (SOURCE/"isp/wch-ch56x-isp.c").read_text()
    # Upstream writes a fixed entire high byte. Preserve non-memory configuration bits.
    needle = "/* If flash size config already set avoid to set it again */"
    assert needle in isp
    isp = isp.replace(needle, "/* Preserve all non-USER_MEM bits from the chip. */\n\tflash_size_config = (flash_size_config & 0xc0) | (buf[13] & 0x3f);\n\t"+needle)
    (out/"wch-ch56x-isp-preserve.c").write_text(isp)
    usb_flags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "libusb-1.0"], text=True).split()
    run(["cc", "-Wall", "-O2", '-DVERSION="0.3.1-probe-preserve"',
         "-I"+str(SOURCE/"isp"), "-I"+str(SOURCE/"isp/cargs/include"),
         out/"wch-ch56x-isp-preserve.c", SOURCE/"isp/cargs/src/cargs.c", *usb_flags,
         "-o", out/"wch-ch56x-isp"], "isp_build.log")
    run([out/"wch-ch56x-isp", "-h"], "isp_help.txt")
    inputs = src + [SDK/"Ld/Link.ld", SDK/"Startup/startup_CH56x.S", HS/"CH56x_host_hs.c", Path(__file__)]
    inputs += list(fw.glob("*"))
    inputs += list((SDK/"Peripheral/inc").glob("*.h")) + list((SDK/"RVMSIS").glob("*.h"))
    inputs += list((SOURCE/"isp").rglob("*.c")) + list((SOURCE/"isp").rglob("*.h"))
    manifest = {"commands": commands, "inputs": {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                "outputs": {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [out/"probe.bin", out/"probe.elf", out/"wch-ch56x-isp"]},
                "hardware_tested": False}
    (out/"build.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(out)
    print((out/"size.txt").read_text())

if __name__ == "__main__": main()
