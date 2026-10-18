#!/bin/sh
# Build on each invocation; do not keep host binaries in the example.
set -eu

if [ "$(uname -s)" != Darwin ]; then
    echo "This helper requires macOS and Xcode Command Line Tools." >&2
    exit 2
fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/usb1-reenumerate.XXXXXXXX")
trap 'rm -rf "$build_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

xcrun clang -std=c11 -Wall -Wextra -Werror \
    "$script_dir/reenumerate_macos.c" -framework IOKit -framework CoreFoundation \
    -o "$build_dir/reenumerate_macos"
"$build_dir/reenumerate_macos" "$@"
