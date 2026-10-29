"""Strict board timing acceptance, including the optional GAO JTAG clock."""
import math


def timing_passed(timing, usb2_debug=False):
    expected = {'clk_50mhz': 50.000, 'clk_ulpi60': 60.002}
    if usb2_debug:
        expected['tck_pad_i'] = 20.000
    clocks = timing.get('clocks', [])
    return (timing.get('setup_violated_endpoints') == 0
            and timing.get('hold_violated_endpoints') == 0
            and all(math.isfinite(timing.get(kind+'_worst_slack_ns', -1))
                    and timing.get(kind+'_worst_slack_ns', -1) >= 0
                    for kind in ('setup', 'hold', 'recovery', 'removal'))
            and len(clocks) == len(expected)
            and {clock['name'] for clock in clocks} == set(expected)
            and all(math.isclose(clock['constraint_mhz'], expected[clock['name']],
                                 rel_tol=0, abs_tol=0.0005)
                    and math.isfinite(clock['actual_fmax_mhz'])
                    and clock['actual_fmax_mhz'] >= clock['constraint_mhz']
                    for clock in clocks))
