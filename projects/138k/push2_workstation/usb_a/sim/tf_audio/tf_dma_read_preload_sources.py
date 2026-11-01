"""Strict source binding for TF private preload and response-size cofactors.

Simulation/proof support only. Production uses the maintained RTL directly.
"""
import hashlib

SOURCE_SHA256 = '31dcbf5f65d7e7f16aca1cca6189f5975a7adec46c4b2ef03514f5ad2cce07b7'
PRELOAD_SOURCE_SHA256 = '5fc0fd0930fcaedf9a5b2e43f8f0b04a8fd085ba7261f68feefe80539ad5ef3f'
REFERENCE_SHA256 = '1baa71464c9180f13fa03a281c81d9cd7d8cb3ace0c538b674e610604d6f25e7'
ORIGINAL_ACCEPTED_LINES = '''    wire [31:0] accepted_after_read = add_occupancy_delta(accepted_used, occupancy_read_delta);
    wire [31:0] accepted_after_input_read = add_occupancy_delta(accepted_used, occupancy_input_read_delta);
'''
ACCEPTED_RESPONSE_BLOCK = '''    // Precompute accepted-occupancy response sizes before the late full/partial
    // classification, retaining the generic result for unknown controls.
    wire [31:0] accepted_read_generic = add_occupancy_delta(accepted_used, occupancy_read_delta);
    wire [31:0] accepted_input_read_generic = add_occupancy_delta(accepted_used, occupancy_input_read_delta);
    wire [31:0] accepted_full_read = add_occupancy_delta(accepted_used, 7'd96);
    wire [31:0] accepted_full_input_read = add_occupancy_delta(accepted_used, 7'd97);
    wire [31:0] accepted_pending_read = add_occupancy_delta(accepted_used, 7'd0 - {1'b0, read_pending_bytes});
    wire [31:0] accepted_pending_input_read = add_occupancy_delta(accepted_used, 7'd1 - {1'b0, read_pending_bytes});
    wire [31:0] accepted_partial_read = add_occupancy_delta(accepted_used, 7'd0 - {1'b0, available_bytes[5:0]});
    wire [31:0] accepted_partial_input_read = add_occupancy_delta(accepted_used, 7'd1 - {1'b0, available_bytes[5:0]});
    reg [31:0] accepted_after_read, accepted_after_input_read;
    always @* begin
        accepted_after_read = accepted_read_generic;
        accepted_after_input_read = accepted_input_read_generic;
        case (read_pending)
            1'b0: begin
                case (eof_finalized && !read_has_full_beat)
                    1'b0: begin
                        accepted_after_read = accepted_full_read;
                        accepted_after_input_read = accepted_full_input_read;
                    end
                    1'b1: begin
                        accepted_after_read = accepted_partial_read;
                        accepted_after_input_read = accepted_partial_input_read;
                    end
                    default: begin end
                endcase
            end
            1'b1: begin
                accepted_after_read = accepted_pending_read;
                accepted_after_input_read = accepted_pending_input_read;
            end
            default: begin end
        endcase
    end
'''
PRELOAD_BLOCK = '''                // Data is private until the unchanged response publishes it.
                // A valid beat stays fixed while the byte FIFO consumes it.
                // Keep the original procedural behavior for unknown validity.
                case (read_buf_valid)
                    1'b0: read_buf <= app_rdata;
                    1'b1: begin end
                    default: if (read_response) read_buf <= app_rdata;
                endcase
'''
ACCEPT_ANCHOR = '                if (read_accept) begin\n'
RESPONSE_ANCHOR = "                if (read_response) begin\n                    read_pending <= 1'b0;\n"
OLD_RESPONSE_ANCHOR = RESPONSE_ANCHOR + '                    read_buf <= app_rdata;\n'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def before_accepted_response_sizes(text):
    """Invert only the pinned 31dcb hunk and recover every original 5fc byte."""
    if digest(text) != SOURCE_SHA256 or text.count(ACCEPTED_RESPONSE_BLOCK) != 1:
        raise ValueError('maintained TF accepted-response source identity changed')
    restored = text.replace(ACCEPTED_RESPONSE_BLOCK, ORIGINAL_ACCEPTED_LINES, 1)
    if digest(restored) != PRELOAD_SOURCE_SHA256:
        raise ValueError('exact pre-accepted-response reconstruction changed')
    return restored


def before_read_preload(text):
    """Peel the pinned later hunk, then retain the exact 5fc-to-1baa inverse."""
    if digest(text) != PRELOAD_SOURCE_SHA256:
        text = before_accepted_response_sizes(text)
    if digest(text) != PRELOAD_SOURCE_SHA256:
        raise ValueError('maintained TF private-preload source identity changed')
    if text.count(PRELOAD_BLOCK) != 1 or text.count(RESPONSE_ANCHOR) != 1:
        raise ValueError('TF private-preload inverse anchor drift')
    restored = text.replace(PRELOAD_BLOCK, '', 1).replace(RESPONSE_ANCHOR, OLD_RESPONSE_ANCHOR, 1)
    if digest(restored) != REFERENCE_SHA256:
        raise ValueError('exact pre-private-preload reconstruction changed')
    return restored


def apply_read_preload_to_test_mutant(text):
    """Retain the reviewed hunk after an older runner's intentional mutation.

    Callers first invert the strictly pinned actual module. This function is
    used only to reapply this exact unchanged hunk to their derived mutant.
    """
    if text.count(ACCEPT_ANCHOR) != 1 or text.count(OLD_RESPONSE_ANCHOR) != 1:
        raise ValueError('TF private-preload test-mutant anchor drift')
    restored = text.replace(ACCEPT_ANCHOR, PRELOAD_BLOCK + ACCEPT_ANCHOR, 1).replace(
        OLD_RESPONSE_ANCHOR, RESPONSE_ANCHOR, 1)
    if restored.count(ORIGINAL_ACCEPTED_LINES) != 1:
        raise ValueError('TF accepted-response test-mutant anchor drift')
    return restored.replace(ORIGINAL_ACCEPTED_LINES, ACCEPTED_RESPONSE_BLOCK, 1)
