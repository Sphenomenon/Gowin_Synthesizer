#!/usr/bin/env python3
"""Original, deterministic 1024-frame stereo tone, looped for a 1s test slot."""
from pathlib import Path
import hashlib, json, math, struct, wave, zlib
p=Path(__file__).resolve().parents[1]
frames=[(round(10000*math.sin(2*math.pi*11*n/1024)),round(8000*math.sin(2*math.pi*7*n/1024))) for n in range(1024)]
rom=''.join(f'{(r&65535):04x}{(l&65535):04x}\n' for l,r in frames)
(p/'audio/test_tone.mem').write_text(rom)
pcm=b''.join(struct.pack('<hh',*frames[n%1024]) for n in range(48000))
with wave.open(str(p/'audio/test_tone_1s.wav'),'wb') as f:
 f.setnchannels(2);f.setsampwidth(2);f.setframerate(48000);f.writeframes(pcm)
(p/'audio/manifest.json').write_text(json.dumps({'source':'Generated original stereo sine test signal; no external recording','sample_rate':48000,'channels':2,'bits':16,'loop_frames':1024,'capacity_frames':48000,'pcm_bytes':len(pcm),'pcm_crc32':zlib.crc32(pcm),'left_hz':515.625,'right_hz':328.125,'wav_sha256':hashlib.sha256((p/'audio/test_tone_1s.wav').read_bytes()).hexdigest(),'rom_sha256':hashlib.sha256(rom.encode()).hexdigest()},indent=2)+'\n')
