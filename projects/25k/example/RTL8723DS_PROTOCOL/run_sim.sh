#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 "$project_dir/vendor/rtl8723ds_ble/scripts/verify_package.py"
python3 "$project_dir/prepare_adapted.py"
exec python3 "$project_dir/tests/run.py"
