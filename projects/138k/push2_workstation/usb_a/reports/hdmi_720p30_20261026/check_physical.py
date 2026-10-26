"""Keep the original physical checks intact, binding only the explicit 720p30 mode."""

from pathlib import Path
import argparse
import hashlib
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
ORIGINALS = dict(
    timing=('check_timing.py', '86fe99e9a448fae12a30090ad6c6ee05bb7b8a92462f015596bb3c208a0a7628'),
    pll=('check_pll.py', '41d0a89a353e3c017b315740f5cd9bed1f73d2d2c0b08e83caea33fc3135e24d'),
    routes=('check_routes.py', 'd6e334a69d9a4ca357c5141350c03925ddcc96887939dafae1173b49780b1156'),
    cdc=('check_common_cdc.py', 'dc872759ce7968371fcd2b21d6fc281dde0cdc217eff3e6387cc752863f3a328'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(text, original, replacement, count=1):
    if text.count(original) != count:
        raise ValueError('720p30 checker anchor drift: ' + original)
    return text.replace(original, replacement)


def adapt(kind, text):
    if kind == 'timing':
        text = replace(text, 'from workstation_custom_clocks import EXPECTED_HZ',
                       "from workstation_custom_clocks import clock_bundle\n"
                       "bundle = clock_bundle(ROOT, '720p30')\n"
                       "EXPECTED_HZ = {entry['name']: entry['frequency_hz'] for entry in "
                       "[*bundle['plan']['primary'], *bundle['plan']['generated']]}\n")
        text = replace(text, "'video_pixel148'", "'video_pixel74'", 3)
        text = replace(text, "'video_serial742'", "'video_serial371'")
    elif kind == 'routes':
        text = replace(text, "if parent['identity'].endswith('-a23'):",
                       "if parent['identity'].endswith(('-a23', '-a24')):")
    elif kind == 'pll':
        anchor = 'from check_video_pll_init import inspect_video_pll_init, RoutedDesign\n'
        addition = '''
from tools.workstation_video_mode import IDENTITY_720, ADAPTED_PLL
assert parent['identity'] == IDENTITY_720
assert hashlib.sha256((stage / ADAPTED_PLL).read_bytes()).hexdigest() == parent['hdmi']['adapted'][ADAPTED_PLL]
checker = stage / 'scripts/check_video_pll_init.py'
checker_text = checker.read_text()
divider_anchor = '("u_tmds", "49.5", 15, 0, 1)):'
assert checker_text.count(divider_anchor) == 1, '720p30 PLL checker anchor changed'
checker_text = checker_text.replace(divider_anchor, '("u_tmds", "49.5", 15, 0, 2)):')
video_namespace = dict(__file__=str(checker), __name__='native_720p30_pll_audit')
exec(compile(checker_text, str(checker) + ':720p30-output-divider', 'exec'), video_namespace)
inspect_video_pll_init = video_namespace['inspect_video_pll_init']
'''
        text = replace(text, anchor, anchor + addition)
    elif kind != 'cdc':
        raise ValueError('unsupported physical check')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('check', choices=ORIGINALS)
    parser.add_argument('physical', type=Path)
    args = parser.parse_args()
    physical = args.physical.resolve()
    sys.path.insert(0, str(ROOT))
    from tools.workstation_video_mode import IDENTITY_720
    parent = json.loads((physical / 'parent_integration_inputs.json').read_text())
    if parent['identity'] != IDENTITY_720 or parent.get('hdmi', {}).get('mode') != '720p30':
        raise ValueError('720p30 physical checker requires the explicit native mode identity')
    filename, expected = ORIGINALS[args.check]
    source = ROOT / 'reports/workstation_physical_20261025' / filename
    if digest(source) != expected:
        raise ValueError('original dated checker changed: ' + filename)
    text = adapt(args.check, source.read_text())
    adapter = dict(original_checker=str(source), original_checker_sha256=expected,
                   adapter_sha256=digest(__file__), adapted_code_sha256=hashlib.sha256(text.encode()).hexdigest(),
                   mode='720p30', parent_identity=parent['identity'],
                   scope='Same routed checks and bounds; bind actual 74.25/371.25 MHz clocks and PLL output divider 2; retain DDR hold-path audit.',
                   retirement='Replace the checked in-memory adapter with a parameterized native physical checker after the display profile is integrated.',
                   board_accessed=False)
    (physical / ('checker_adapter_' + args.check + '.json')).write_text(json.dumps(adapter, indent=2) + '\n')
    sys.argv = [str(source), str(physical)]
    exec(compile(text, str(source) + ':720p30-profile', 'exec'),
         dict(__file__=str(source), __name__='__main__'))


if __name__ == '__main__':
    main()
