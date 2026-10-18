#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 "$project_dir/vendor/rtl8723ds_ble/scripts/verify_package.py"
python3 "$project_dir/tests/simulate.py"
python3 "$project_dir/tests/simulate.py" --adapted
