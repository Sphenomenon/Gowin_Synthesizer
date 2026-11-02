"""Reproduce this offline experiment through the shared preparation entry point.

The parent a27 source snapshot must match its recorded hashes; a working tree
with later edits is not an interchangeable audit source.
"""
from pathlib import Path
import argparse
import importlib.util
import sys
import json

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--user-code', required=True)
    parser.add_argument('--place-option', type=int, default=2, choices=range(5))
    parser.add_argument('--route-option', type=int, default=0, choices=(0, 1))
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    spec = importlib.util.spec_from_file_location('physical_preparer',
        ROOT/'tools/workstation_custom_board_implementation.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.prepare_reference(args.source, args.output, args.user_code,
        Path(__file__).resolve().parent/'reference_F6.cst',
        '9604f198c36ea89da98154958c95aa59f188e06b84161de9386a276f80c7b639',
        ['clk_16m9344'], args.place_option, args.route_option)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
