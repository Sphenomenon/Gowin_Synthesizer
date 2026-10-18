"""Host ownership for voice slots, avoiding stale releases after reassignment."""
from instrument_backend import VOICE_COUNT


class VoiceAllocator:
    def __init__(self, voice_count=VOICE_COUNT):
        if type(voice_count) is not int or not 1 <= voice_count <= VOICE_COUNT:
            raise ValueError("voice_count must be in 1..32")
        self.voice_count = voice_count
        self.next_voice = 0
        self.owners = {}  # input token -> (voice, MIDI note)

    def press(self, token, note, preferred=None, active_mask=0):
        if token in self.owners:
            return None
        occupied = {voice for voice, _ in self.owners.values()}
        order = [(self.next_voice + offset) % self.voice_count for offset in range(self.voice_count)]
        free = [voice for voice in order if voice not in occupied]
        quiet = [voice for voice in free if not active_mask & (1 << voice)]
        voice = preferred if preferred is not None else next(iter(quiet or free), None)
        if voice is None:
            return None
        if type(voice) is not int or voice not in range(self.voice_count):
            raise ValueError(f"voice must be in 0..{self.voice_count - 1}")
        # A manual card may reuse a slot. The prior key-up must not stop its new note.
        self.owners = {key: value for key, value in self.owners.items() if value[0] != voice}
        self.owners[token] = voice, note
        if preferred is None:
            self.next_voice = (voice + 1) % self.voice_count
        return voice

    def release(self, token):
        return self.owners.pop(token, None)

    def release_voice(self, voice):
        self.owners = {key: value for key, value in self.owners.items() if value[0] != voice}

    def clear(self):
        self.owners.clear()
        self.next_voice = 0

    def set_note(self, voice, note):
        self.owners = {key: (v, note if v == voice else old_note)
                       for key, (v, old_note) in self.owners.items()}

    @property
    def notes(self):
        return [note for _, note in self.owners.values()]

    def note_for_voice(self, voice):
        return next((note for v, note in self.owners.values() if v == voice), None)
