"""Locate an installed Gowin toolchain without assuming a host or drive letter."""
from pathlib import Path
import os
import shutil


def gowin_shell(explicit=None):
    requested = explicit or os.environ.get("GOWIN_SHELL")
    found = shutil.which(str(requested)) if requested else shutil.which("gw_sh") or shutil.which("gw_sh.exe")
    if found:
        # Keep a PATH wrapper: it may set native library compatibility variables.
        return Path(found).absolute()
    raise FileNotFoundError("Gowin shell not found; put gw_sh on PATH or set GOWIN_SHELL / --gowin-shell")


def gowin_simlib(explicit=None):
    requested = explicit or os.environ.get("GOWIN_SIMLIB")
    if requested:
        candidates = [Path(requested).expanduser()]
    else:
        candidates = []
        if os.environ.get("GOWIN_HOME"):
            home = Path(os.environ["GOWIN_HOME"]).expanduser()
            candidates += [home / "simlib/gw5a", home / "IDE/simlib/gw5a"]
        try:
            candidates.append(gowin_shell().resolve().parents[1] / "simlib/gw5a")
        except FileNotFoundError:
            pass
        # Include native Linux user/system installs and existing Windows/WSL
        # installs. Explicit configuration takes precedence over discovery.
        bases = [Path.home() / ".local/opt", Path("/opt"), Path("C:/Gowin"), Path("/mnt/c/Gowin")]
        for base in bases:
            if base.is_dir():
                for pattern in ("*/IDE/simlib/gw5a", "*/simlib/gw5a"):
                    candidates.extend(sorted(base.glob(pattern), reverse=True))
    for candidate in candidates:
        if (candidate / "prim_sim.v").is_file():
            return candidate.resolve()
    raise FileNotFoundError("Gowin gw5a models not found; set GOWIN_SIMLIB or pass --simlib")
