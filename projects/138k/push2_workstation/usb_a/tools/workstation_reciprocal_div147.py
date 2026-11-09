"""Explicit native source alternative for the task3 M fixed-latency divider.

The accepted restoring source stays unchanged. No RTL is text-generated: the
prepare selects a complete versioned implementation at the existing compile
path. Keep this selection experimental until paired physical gates pass;
then consolidate the source option in the owning runtime profile.
"""
from pathlib import Path
import hashlib

KEY = 'runtime_div147_policy'
POLICY = 'task3_M_exact_reciprocal_fixed_latency_v1'
SOURCE = 'rtl/audio/workstation_runtime_div147.sv'
ALTERNATE = 'rtl/audio/workstation_runtime_div147_reciprocal.sv'
TOOL = 'tools/workstation_reciprocal_div147.py'
PARENT_SHA256 = 'baf45bdf6374bdaf96bd20cd15269653103130bf803e36e588c81e904f966bf9'
ALTERNATE_SHA256 = 'dc2e434f603ec35a36e4fb6472936df86651c99d64a7ab7c3b55640566a95670'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('reciprocal div147: ' + message)


def configured(configuration):
    value = configuration.get(KEY)
    require(value in (None, POLICY), 'unknown policy')
    require(not value or configuration.get('demo_role') == 'M', 'requires paired M')
    return bool(value)


def integer_proof():
    """For n=147q+r, prove q <= n*M/2^S < q+1 over every input.

    n*M=q*2^S+q*error+r*M. The independent rectangular q/r bound
    below is stricter than the reachable input set. All arithmetic is exact.
    """
    rows = {}
    for width in (32, 42):
        shift = width + 8
        scale = 1 << shift
        magic = (scale + 146) // 147
        error = 147 * magic - scale
        maximum_q = ((1 << width) - 1) // 147
        upper = maximum_q * error + 146 * magic
        require(0 <= error and upper < scale, 'universal reciprocal bound failed')
        rows[str(width)] = dict(width=width, magic=magic, shift=shift,
            error=error, maximum_q=maximum_q, strict_upper=upper,
            scale=scale, all_unsigned_inputs_proven=True,
            latency_cycles=(width-6)//2+1)
    return rows


def select(stage, configuration):
    if not configured(configuration):
        return None
    stage = Path(stage)
    require(sha(stage/SOURCE) == PARENT_SHA256, 'restoring input drift')
    require(sha(stage/ALTERNATE) == ALTERNATE_SHA256, 'native alternative drift')
    (stage/SOURCE).write_bytes((stage/ALTERNATE).read_bytes())
    return evidence(stage, configuration)


def evidence(stage, configuration):
    if not configured(configuration):
        return None
    stage = Path(stage)
    require(sha(stage/SOURCE) == ALTERNATE_SHA256 and
            sha(stage/ALTERNATE) == ALTERNATE_SHA256, 'selected source drift')
    return dict(policy=POLICY, source=SOURCE, native_alternative=ALTERNATE,
        parent_sha256=PARENT_SHA256, selected_sha256=ALTERNATE_SHA256,
        integer_proof=integer_proof(), output_latency_changed=False,
        input_throughput_per_clock=1, tag_and_flush_schedule_changed=False,
        routed_timing_verified=False, hardware_tested=False)


def verify(stage, configuration, metadata):
    require(evidence(stage, configuration) == metadata, 'selection receipt drift')
    if metadata:
        root = Path(__file__).resolve().parents[1]
        require(sha(root/SOURCE) == PARENT_SHA256 and
                sha(root/ALTERNATE) == ALTERNATE_SHA256, 'versioned source drift')
