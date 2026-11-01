"""Strict reversible source binding for the private TF read-buffer preload.

Simulation/proof support only. Production uses the maintained RTL directly.
"""
import hashlib

SOURCE_SHA256 = '5fc0fd0930fcaedf9a5b2e43f8f0b04a8fd085ba7261f68feefe80539ad5ef3f'
REFERENCE_SHA256 = '1baa71464c9180f13fa03a281c81d9cd7d8cb3ace0c538b674e610604d6f25e7'
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


def before_read_preload(text):
    """Invert only the pinned complete 5fc0 source and recover all 1baa bytes."""
    if digest(text) != SOURCE_SHA256:
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
    return text.replace(ACCEPT_ANCHOR, PRELOAD_BLOCK + ACCEPT_ANCHOR, 1).replace(
        OLD_RESPONSE_ANCHOR, RESPONSE_ANCHOR, 1)
