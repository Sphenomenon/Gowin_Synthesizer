"""Strict simulation-only inverse for the maintained TF epoch comparison.

Builds consume the maintained RTL directly. This inverse keeps the existing
complete-owner reference and failure-admission lineage independently testable.
"""
import hashlib

BEFORE_SHA256 = '90618bda686a82e9e4d61f4ef94feac72efa50723322acfbadb48c025421765f'
GROUPED_SHA256 = '9dce45ba47ed58314ce4d30a308b6869bbcb815d382777ec868e936cab3fc848'
BEFORE = '    wire epoch_mismatch=|(runtime_epoch_i ^ launched_epoch);\n'
GROUPED = '''    // Bound each comparison before the immediate cancel/stop path. The
    // complete epoch still participates on this edge, including unknown bits.
    (* syn_keep=1 *) wire [3:0] epoch_mismatch_groups;
    for(genvar epoch_group=0;epoch_group<4;epoch_group=epoch_group+1)begin:g_epoch_identity
        assign epoch_mismatch_groups[epoch_group]=
            |(runtime_epoch_i[epoch_group*8+:8] ^ launched_epoch[epoch_group*8+:8]);
    end
    wire epoch_mismatch=|epoch_mismatch_groups;
'''


def digest(source):
    return hashlib.sha256(source.encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('TF epoch groups source: ' + message)


def before_epoch_groups(source):
    require(digest(source) == GROUPED_SHA256, 'maintained complete source identity')
    require(source.count(GROUPED) == 1, 'exact inverse group boundary')
    before = source.replace(GROUPED, BEFORE, 1)
    require(digest(before) == BEFORE_SHA256, 'complete previous source identity')
    return before


def with_epoch_groups(source):
    require(digest(source) == BEFORE_SHA256, 'previous complete source identity')
    require(source.count(BEFORE) == 1, 'exact forward comparison boundary')
    grouped = source.replace(BEFORE, GROUPED, 1)
    require(digest(grouped) == GROUPED_SHA256, 'complete grouped source identity')
    return grouped
