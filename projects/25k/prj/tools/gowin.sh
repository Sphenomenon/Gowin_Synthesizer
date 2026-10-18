#!/bin/sh
set -eu
GW25K_IDE_DIR=${GW25K_IDE_DIR:-/Applications/GowinIDE.app/Contents/Resources/Gowin_EDA/IDE}
export DYLD_LIBRARY_PATH="$GW25K_IDE_DIR/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
export DYLD_FRAMEWORK_PATH="$GW25K_IDE_DIR/lib${DYLD_FRAMEWORK_PATH:+:$DYLD_FRAMEWORK_PATH}"
if [ "$#" -eq 1 ]; then
    # Every build variant uses the safe flow. New descriptive build names
    # must not silently fall back to gw_sh's vulnerable same-process run all.
    case "${1##*/}" in
        build*.tcl)
            exec python3 "$(dirname "$0")/gowin_build.py" "$1"
            ;;
    esac
fi
exec "$GW25K_IDE_DIR/bin/gw_sh" "$@"
