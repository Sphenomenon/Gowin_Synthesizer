#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "${1:-}" in
    '') build_script=build_gao.tcl ;;
    --normal) build_script=build.tcl ;;
    *) echo 'Usage: sh build.sh [--normal]' >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
    echo 'Usage: sh build.sh [--normal]' >&2
    exit 2
fi
exec python3 "$project_dir/tools/gowin_build.py" "$project_dir/$build_script"
