#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 "$project_dir/generate_init.py" --check
exec python3 "$project_dir/tools/gowin_build.py" "$project_dir/build.tcl"
