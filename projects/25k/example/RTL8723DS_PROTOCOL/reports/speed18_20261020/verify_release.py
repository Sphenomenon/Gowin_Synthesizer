"""Read-only release identity/evidence check; no BLE access or programming."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(name):
    return json.loads((HERE / name).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


checks = {}
for name, key, root in (
    ("firmware_inputs.json", "files", ROOT),
    ("android_inputs.json", "sha256", ROOT / "clients/android"),
    ("simulation.json", "source_sha256", ROOT),
):
    files = read(name)[key]
    mismatches = [
        name for name, expected in files.items()
        if sha(root / name) != (expected["sha256"] if isinstance(expected, dict) else expected)
    ]
    checks[name] = {"count": len(files), "mismatches": mismatches}
    assert not mismatches, checks[name]

candidate = read("candidate_final.json")
assert candidate["passed"]
artifact = candidate["artifacts"][0]
checks["bitstream_sha256"] = sha(Path(artifact["path"]))
assert checks["bitstream_sha256"] == artifact["sha256"]
apk = read("android_inputs.json")["apk"]
checks["apk_sha256"] = sha(ROOT / apk["path"])
assert checks["apk_sha256"] == apk["sha256"]
checks["apk_bytes"] = (ROOT / apk["path"]).stat().st_size
assert checks["apk_bytes"] == apk["bytes"]
assert apk["signature_v2_verified"]

for name in (
    "simulation", "android_checks", "paired_speed", "recording_sram",
    "encoder_second/result", "encoder_legacy/result", "codec_fuzz",
    "compression", "flash", "speed_flash", "profile_resume_flash",
    "second_replay_flash", "lossless_replay_flash", "extended_replay_flash",
    "protocol_flash", "kotlin_old_sram", "kotlin_second_sram",
    "kotlin_second_flash", "wire_audit", "complete_wav_check",
):
    assert read(name + ".json")["passed"], name
checks["accepted_evidence"] = True
assert len(read("simulation.json")["cases"]) == 50
assert all(case["passed"] for case in read("simulation.json")["cases"].values())
assert len(read("wire_audit.json")["captures"]) == 12
for profile in ("second", "legacy"):
    assert len(read(f"encoder_{profile}/result.json")["cases"]) == 38
reference = (ROOT / "audio/test_tone_1s.wav").read_bytes()
for name in ("kotlin_old_sram.wav", "kotlin_second_sram.wav", "kotlin_second_flash.wav"):
    assert (HERE / name).read_bytes() == reference, name
checks["wav_sha256"] = hashlib.sha256(reference).hexdigest()
identity = (HERE / "final_device_identity.log").read_text()
assert "User Code is: 0x0000A25D" in identity
assert "Status Code is: 0x70022020" in identity
checks["user_code"] = "A25D"
checks["status_code"] = "70022020"
checks["passed"] = True
(HERE / "final_identity_check.json").write_text(json.dumps(checks, indent=2) + "\n")
print(json.dumps(checks, indent=2))
