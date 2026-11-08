"""Compose existing DIRECT TF crossing proofs for the explicit preboard M.

This is a synthesis boundary gate. Routed pin/arc resolution, RAM timing,
recovery/removal, application regressions and hardware acceptance remain
separate. Partial subreports retain their original scope and false flags.
"""
from pathlib import Path


def audit(n,*,stage,root,status,sdc):
    from tools.workstation_task3_receipt_audit import audit_direct_receipt
    from tools.workstation_task3_tf_startup_audit import audit_tf_startup_releases
    from tools.workstation_task3_tf_sdc_audit import validate_tf_mailbox_sdc
    from tools.workstation_task3_tf_frame_cdc_audit import audit_tf_frame_cdc
    from tools.workstation_task3_tf_frame_arithmetic import audit as arithmetic
    from tools.workstation_task3_tf_tail_cdc_audit import audit_tf_tail_cdc,validate_tf_tail_sdc
    from tools.workstation_task3_tf_tail_retirement_audit import audit_tf_tail_retirement
    from tools.workstation_tf_compute_local_release import audit_mapped
    def require(ok,message):
        if not ok:raise ValueError('DIRECT TF boundary composition: '+message)
    local=audit_mapped(n,stage=stage,root=root)
    require(local is not None,'explicit functional local release required')
    startup=audit_tf_startup_releases(n,root=root)
    receipt=audit_direct_receipt(n,root=root,stage=stage)
    require(receipt['source_event_condition_semantics_proven'] and
            receipt['source_data_semantics_proven'] and
            receipt['all_reset_inclusive_next_q_proven'] and
            receipt['busy_prevents_source_overwrite'],
            'receipt lifecycle/source or local capture proof incomplete')
    mailbox_sdc=validate_tf_mailbox_sdc(sdc,n,status=status,receipt=receipt)
    frame=audit_tf_frame_cdc(n,sdc=sdc,stage=stage,root=root)
    require(not frame['missing_finite_boundaries'], 'RAM finite bounds incomplete')
    publishers=arithmetic(n)
    tail=audit_tf_tail_cdc(n,root=root,stage=stage)
    retirement=audit_tf_tail_retirement(n,root=root,stage=stage)
    require(tail['request_busy_no_overwrite_proven'] and
            retirement['reply_retirement_next_q_proven'] and
            retirement['held_reply_no_overwrite_outside_retirement_or_root_clear'] and
            retirement['cancellation_gray_arithmetic_proven'],
            'tail publication/retirement/cancellation proof incomplete')
    tail_sdc=validate_tf_tail_sdc(sdc,n,tail=tail)
    return dict(policy='task3_preboard_composed_DIRECT_TF_crossings_v1',
        synthesis_crossing_gate_passed=True,
        scope='actual held status/receipt and tail mailboxes, synchronizers, local reset consumers, registered Gray publishers and FIFO ownership control; exact finite SDC inventories',
        startup=startup,functional_local_release=local,receipt=receipt,
        mailbox_sdc=mailbox_sdc,frame=frame,frame_arithmetic=publishers,
        tail=tail,tail_retirement=retirement,tail_sdc=tail_sdc,
        source_policy_bound_by_parent_prepared_inventory=True,
        business_and_physical_event_semantics_owned_by_functional_regressions=True,
        routed_pin_resolution_and_delays_required=True,
        routed_timing_verified=False,physical_CDC_accepted=False,hardware_tested=False)
