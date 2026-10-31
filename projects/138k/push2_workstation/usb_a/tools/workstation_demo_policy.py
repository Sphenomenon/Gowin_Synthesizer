"""Explicit DEMO retirement of absent timing endpoints, preserving live members.

This does not waive endpoint resolution or routed CDC/timing checks.  The
separate synthesis audit must prove that each retired hierarchy is absent.
"""
import hashlib
import re

POLICY = 'independent_demo_retired_endpoints_v1'
LOCAL_RETIRED = ('u_recording/', 'u_service_push_cdc/',
                 'u_managed/media_stop/compute_failure_s',
                 'u_managed/media_stop/failed_50_0_s')
RETIRED = {
    'M': LOCAL_RETIRED + ('u_bluetooth/', 'u_ble_pcm_cdc/'),
    'W': LOCAL_RETIRED + ('u_tf_audio/', 'u_tf_control_cdc/',
          'tf_format_meta50', 'tf_source_meta50'),
}
QUERY = re.compile(r'\[(get_regs|get_pins|get_ports|get_clocks) \{([^{}]+)\}\]')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def adapt_constraints(sdc, role):
    if role not in RETIRED:
        raise ValueError('unknown independent DEMO role')
    prefixes = RETIRED[role]
    selected, changes = [], []
    for index, line in enumerate(sdc.splitlines()):
        removed, empty = [], []

        def select(match):
            members = match[2].split()
            keep = [member for member in members if not member.startswith(prefixes)]
            removed.extend(member for member in members if member not in keep)
            if not keep:
                empty.append(match[1])
            return '[' + match[1] + ' {' + ' '.join(keep) + '}]'

        adapted = QUERY.sub(select, line)
        if removed:
            changes.append(dict(line_index=index, original=line,
                selected=None if empty else adapted, removed_selectors=removed,
                empty_query_sides=empty))
            if not empty:
                selected.append(adapted)
        else:
            selected.append(line)
    result = '\n'.join(selected) + ('\n' if selected else '')
    return result, dict(policy=POLICY, role=role, retired_prefixes=list(prefixes),
        input_sha256=digest(sdc), output_sha256=digest(result), changes=changes,
        clocks_or_live_exceptions_relaxed=False,
        retirement_verified_in_synthesized_netlist=False)


def verify_constraints(sdc, evidence, role):
    """Recover exact upstream input and repeat the role-specific transformation."""
    if not isinstance(evidence, dict) or evidence.get('role') != role:
        raise ValueError('DEMO constraint retirement role missing or changed')
    if digest(sdc) != evidence.get('output_sha256'):
        raise ValueError('DEMO selected SDC identity changed')
    lines = sdc.splitlines()
    for change in evidence.get('changes', []):
        index = change['line_index']
        if change['selected'] is None:
            lines.insert(index, change['original'])
        else:
            if index >= len(lines) or lines[index] != change['selected']:
                raise ValueError('DEMO selected mixed query changed')
            lines[index] = change['original']
    original = '\n'.join(lines) + ('\n' if lines else '')
    selected, expected = adapt_constraints(original, role)
    if selected != sdc or evidence != expected:
        raise ValueError('DEMO retirement no longer matches the exact source policy')
    return original
