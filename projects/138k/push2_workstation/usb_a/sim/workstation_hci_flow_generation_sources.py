"""Exact source pins and reversible ACL generation comparison rewrite.

This helper reconstructs the reviewed reference only for simulation. Production
builds consume maintained RTL directly; neither a cache nor generated RTL is a
production source. Any unreviewed source byte or anchor drift fails closed.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]
FLOW = ROOT / 'rtl/bluetooth/hci_owner/workstation_hci_flow_owner.sv'
BENCH = ROOT / 'sim/tb_workstation_hci_flow_owner.sv'
PRE_FLOW_GENERATION_SHA256 = '51fb7a96487b4aa27fdf9fce38901c6ee3a5403ce29292bac51ab3c7901fa2c8'
FLOW_GENERATION_SHA256 = 'e32a9ef62a527907da7baeaaf4ec592b38261483f9f6f7d7fa3429cbd32b9dc8'
ANCHOR = "    wire special_command = command_owner_i == 3 && command_opcode_i == 16'h0c35;"
BEFORE = 'else if (acl_generation_i != generations[acl_slot]) acl_error_o=3;'
AFTER = 'else if (acl_generation_changed[acl_slot]) acl_error_o=3;'
GROUPS = '''    // Compare generations before the handle lookup selects one result.
    // Kept byte groups bound the combinational reduction; no extra cycle.
    (* syn_keep=1 *) wire [HANDLE_SLOTS*4-1:0] acl_generation_changed_groups;
    wire [HANDLE_SLOTS-1:0] acl_generation_changed;
    for(genvar generation_slot=0;generation_slot<HANDLE_SLOTS;generation_slot=generation_slot+1)begin:acl_generation_identity
        for(genvar generation_group=0;generation_group<4;generation_group=generation_group+1)begin:byte_group
            assign acl_generation_changed_groups[generation_slot*4+generation_group]=
                |(acl_generation_i[generation_group*8+:8]^
                  generations[generation_slot][generation_group*8+:8]);
        end
        assign acl_generation_changed[generation_slot]=
            |acl_generation_changed_groups[generation_slot*4+:4];
    end
'''


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError('HCI flow generation source: ' + message)


def apply_generation_groups(text):
    require(digest(text) == PRE_FLOW_GENERATION_SHA256, 'pre-group source identity')
    require(text.count(ANCHOR) == text.count(BEFORE) == 1, 'forward exact anchors')
    result = text.replace(ANCHOR, GROUPS + ANCHOR, 1).replace(BEFORE, AFTER, 1)
    require(digest(result) == FLOW_GENERATION_SHA256, 'complete grouped source identity')
    return result


def reverse_generation_groups(text):
    require(digest(text) == FLOW_GENERATION_SHA256, 'grouped source identity')
    require(text.count(GROUPS) == text.count(AFTER) == 1, 'inverse exact anchors')
    result = text.replace(GROUPS, '', 1).replace(AFTER, BEFORE, 1)
    require(digest(result) == PRE_FLOW_GENERATION_SHA256, 'complete pre-group source identity')
    return result
