"""Build-time validation for immutable data used without runtime checking."""


def validate_cues(path, count):
    words = [int(line.split('//')[0].strip(), 16) for line in path.read_text().splitlines()
             if line.split('//')[0].strip()]
    if len(words) < count:
        raise ValueError('cue ROM is shorter than CUE_COUNT')
    previous = 0
    for index, word in enumerate(words[:count]):
        time, event = word >> 32, word & 0xffffffff
        kind, payload = event >> 14, event & 0x7f
        if event >> 18 or kind not in (0, 1, 2, 4) or (kind == 1 and payload == 0) or time < previous:
            raise ValueError(f'illegal static cue at {index}')
        previous = time
