"""Explicit DEMO retirement of absent timing endpoints, preserving live members.

This does not waive endpoint resolution or routed CDC/timing checks.  The
separate synthesis audit must prove that each retired hierarchy is absent.
"""
import hashlib
import re

LEGACY_POLICY = 'independent_demo_retired_endpoints_v1'
POLICY = 'independent_demo_endpoint_adaptation_v2'
LOCAL_RETIRED = ('u_recording/', 'u_service_push_cdc/',
                 'u_managed/media_stop/compute_failure_s',
                 'u_managed/media_stop/failed_50_0_s')
LEGACY_RETIRED = {
    'M': LOCAL_RETIRED + ('u_bluetooth/', 'u_ble_pcm_cdc/'),
    'W': LOCAL_RETIRED + ('u_tf_audio/', 'u_tf_control_cdc/',
          'tf_format_meta50', 'tf_source_meta50'),
}
RETIRED = dict(LEGACY_RETIRED, W=LEGACY_RETIRED['W'] + (
    'u_display_push_cdc/', 'u_playlist_bridge/fifo/',
    'u_native_usb/input_owner/settled_sync_0',
    'u_runtime/u_cpu_cdc/source_release', 'u_runtime/u_cpu_cdc/destination_release',
    'u_managed/pcm_apb/commands/p_release', 'u_managed/pcm_apb/commands/a_release',
))
# Gowin preserves these generate scopes using a dot.  Rebind the exact known
# scopes; no wildcard, timing budget, clock or query kind changes here.
W_SCOPE_BINDINGS = (
    ('u_managed/pcm_apb/commands/', 'u_managed/pcm_apb.commands/'),
    ('u_managed/runtime/cpu_pcm/session/', 'u_managed/runtime/cpu_pcm.session/'),
    ('u_managed/runtime/cpu_pcm/switch_inhibit_compute',
     'u_managed/runtime/cpu_pcm.switch_inhibit_compute'),
)
W_PRESET_SELECTORS = (
    'u_managed/runtime/cpu_pcm.switch_inhibit_compute*/CLEAR',
    'u_managed/runtime/pcm_hold_serial*/CLEAR',
)
QUERY = re.compile(r'\[(get_regs|get_pins|get_ports|get_clocks) \{([^{}]+)\}\]')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def adapt_constraints(sdc, role):
    return _adapt(sdc, role, legacy=False)


def _adapt(sdc, role, *, legacy):
    retired = LEGACY_RETIRED if legacy else RETIRED
    if role not in retired:
        raise ValueError('unknown independent DEMO role')
    prefixes = retired[role]
    selected, changes = [], []
    for index, line in enumerate(sdc.splitlines()):
        removed, empty, rebound = [], [], []

        def select(match):
            members = match[2].split()
            keep = [member for member in members if not member.startswith(prefixes)]
            removed.extend(member for member in members if member not in keep)
            if role == 'W' and not legacy:
                for at, member in enumerate(keep):
                    selected_member = member
                    for old, new in W_SCOPE_BINDINGS:
                        if selected_member.startswith(old):
                            selected_member = new + selected_member[len(old):]
                            break
                    if selected_member in W_PRESET_SELECTORS:
                        selected_member = selected_member[:-len('CLEAR')] + 'PRESET'
                    if selected_member != member:
                        rebound.append(dict(query=match[1], original=member, selected=selected_member))
                        keep[at] = selected_member
            if not keep:
                empty.append(match[1])
            return '[' + match[1] + ' {' + ' '.join(keep) + '}]'

        adapted = QUERY.sub(select, line)
        if removed or rebound:
            change = dict(line_index=index, original=line,
                selected=None if empty else adapted, removed_selectors=removed,
                empty_query_sides=empty)
            if rebound:
                change['rebound_selectors'] = rebound
            changes.append(change)
            if not empty:
                selected.append(adapted)
        else:
            selected.append(line)
    result = '\n'.join(selected) + ('\n' if selected else '')
    return result, dict(policy=LEGACY_POLICY if legacy else POLICY,
        role=role, retired_prefixes=list(prefixes),
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
    policy = evidence.get('policy')
    if policy not in (LEGACY_POLICY, POLICY):
        raise ValueError('unknown DEMO endpoint policy')
    selected, expected = _adapt(original, role, legacy=policy == LEGACY_POLICY)
    if selected != sdc or evidence != expected:
        raise ValueError('DEMO retirement no longer matches the exact source policy')
    return original
