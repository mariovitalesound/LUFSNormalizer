"""Generate 5 test WAV files for LUFS Normalizer testing."""

import numpy as np
import soundfile as sf
import pyloudnorm as pyln
from pathlib import Path

RATE = 48000
DURATION = 10
SAMPLES = RATE * DURATION

output_dir = Path("test_input")
output_dir.mkdir(exist_ok=True)


def make_tone(freq=440, channels=1):
    """Generate a sine tone."""
    t = np.arange(SAMPLES) / RATE
    tone = np.sin(2 * np.pi * freq * t)
    if channels == 2:
        # Slightly different freq in right channel for realism
        tone2 = np.sin(2 * np.pi * 554 * t)
        tone = np.column_stack([tone, tone2])
    return tone


def scale_to_lufs(audio, target_lufs):
    """Scale audio to hit a target integrated LUFS."""
    meter = pyln.Meter(RATE)
    if audio.ndim == 1:
        measured = meter.integrated_loudness(audio.reshape(-1, 1))
    else:
        measured = meter.integrated_loudness(audio)
    gain_db = target_lufs - measured
    return audio * (10 ** (gain_db / 20))


def write_24bit(path, data):
    sf.write(str(path), data, RATE, subtype='PCM_24')
    # Verify
    meter = pyln.Meter(RATE)
    readback, _ = sf.read(str(path))
    if readback.ndim == 1:
        lufs = meter.integrated_loudness(readback.reshape(-1, 1))
    else:
        lufs = meter.integrated_loudness(readback)
    peak = 20 * np.log10(np.max(np.abs(readback))) if np.max(np.abs(readback)) > 0 else -100
    print(f"  {path.name}: {lufs:.1f} LUFS, peak {peak:.1f} dBFS, {readback.shape}")


# 1. Loud file: -12 LUFS mono
print("Generating test files...")
audio = scale_to_lufs(make_tone(440), -12.0)
audio = np.clip(audio, -1.0, 1.0)
write_24bit(output_dir / "loud_-12LUFS.wav", audio)

# 2. Quiet file: -24 LUFS mono
audio = scale_to_lufs(make_tone(440), -24.0)
write_24bit(output_dir / "quiet_-24LUFS.wav", audio)

# 3. Hot file: -6 LUFS (will clip/exceed peak ceiling when normalized)
audio = scale_to_lufs(make_tone(440), -6.0)
audio = np.clip(audio, -1.0, 1.0)
write_24bit(output_dir / "hot_-6LUFS.wav", audio)

# 4. Silent file
audio = np.zeros(SAMPLES)
write_24bit(output_dir / "silent.wav", audio)

# 5. Stereo -18 LUFS
audio = scale_to_lufs(make_tone(440, channels=2), -18.0)
audio = np.clip(audio, -1.0, 1.0)
write_24bit(output_dir / "stereo_-18LUFS.wav", audio)

print("\nDone. Files in test_input/")
