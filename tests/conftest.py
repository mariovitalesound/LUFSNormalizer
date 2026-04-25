"""
Shared pytest fixtures for LUFS Normalizer tests.

Generates audio test files on the fly so the repository doesn't have to
commit large binary fixtures. Uses deterministic sine tones at known
loudness so measurements can be checked against analytic values.
"""

import numpy as np
import pytest
import soundfile as sf


SR_DEFAULT = 48000
DURATION_DEFAULT = 4.0  # seconds — > 3 s so LRA is computable


def _sine(freq, duration, sample_rate, amplitude=1.0, channels=1, seed=None):
    """Generate a sine tone. Deterministic; no randomness unless `seed` given."""
    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate
    wave = amplitude * np.sin(2 * np.pi * freq * t)
    if channels == 1:
        return wave.astype(np.float64)
    # Stereo: same tone in both channels (L=R)
    return np.column_stack([wave] * channels).astype(np.float64)


def _measure_lufs(data, sample_rate):
    """Helper: integrated loudness via pyloudnorm."""
    import pyloudnorm as pyln
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    return pyln.Meter(sample_rate).integrated_loudness(data)


def _scale_to_lufs(data, sample_rate, target_lufs):
    """Scale audio so its measured integrated loudness equals target_lufs."""
    current = _measure_lufs(data, sample_rate)
    if not np.isfinite(current):
        return data
    gain = 10 ** ((target_lufs - current) / 20)
    return data * gain


@pytest.fixture
def sample_rate():
    return SR_DEFAULT


@pytest.fixture
def make_wav(tmp_path):
    """
    Factory fixture that writes a WAV file to tmp_path and returns its path.

    Usage:
        path = make_wav(name='input.wav', lufs=-23.0, channels=2,
                        sample_rate=48000, duration=4.0, freq=1000,
                        subtype='PCM_24')
    """
    counter = {'i': 0}

    def _factory(name=None, lufs=-23.0, channels=2, sample_rate=SR_DEFAULT,
                 duration=DURATION_DEFAULT, freq=1000.0, subtype='PCM_24',
                 amplitude=None, raw_data=None):
        if name is None:
            counter['i'] += 1
            name = f"test_{counter['i']:03d}.wav"

        if raw_data is not None:
            data = raw_data
        elif amplitude is not None:
            # Caller wants a specific amplitude (used for silence / peak tests)
            data = _sine(freq, duration, sample_rate, amplitude=amplitude,
                         channels=channels)
        else:
            # Start at modest level and scale to target LUFS
            data = _sine(freq, duration, sample_rate, amplitude=0.1,
                         channels=channels)
            data = _scale_to_lufs(data, sample_rate, lufs)

        path = tmp_path / name
        sf.write(str(path), data, sample_rate, subtype=subtype)
        return path

    return _factory


@pytest.fixture
def silent_wav(tmp_path):
    """A short silent WAV file (digital zero)."""
    path = tmp_path / 'silent.wav'
    data = np.zeros((SR_DEFAULT * 2, 2), dtype=np.float32)
    sf.write(str(path), data, SR_DEFAULT, subtype='PCM_24')
    return path


@pytest.fixture
def surround_wav(tmp_path):
    """A 6-channel surround WAV. Used to verify >2 channel rejection."""
    path = tmp_path / 'surround.wav'
    rng = np.random.default_rng(42)
    data = (rng.standard_normal((SR_DEFAULT * 2, 6)) * 0.05).astype(np.float32)
    sf.write(str(path), data, SR_DEFAULT, subtype='PCM_24')
    return path


@pytest.fixture
def hot_wav(tmp_path):
    """A loud stereo file (~ -6 LUFS) used to trigger peak-ceiling logic."""
    path = tmp_path / 'hot.wav'
    data = _sine(1000.0, DURATION_DEFAULT, SR_DEFAULT, amplitude=0.1, channels=2)
    data = _scale_to_lufs(data, SR_DEFAULT, -6.0)
    sf.write(str(path), data, SR_DEFAULT, subtype='PCM_24')
    return path


@pytest.fixture
def peaky_quiet_wav(tmp_path):
    """A file with quiet integrated loudness (~-30 LUFS) but a single near-FS spike.

    Used to force the peak-ceiling logic: normalizing up to a louder target
    requires positive gain that pushes the peak past the ceiling.
    """
    path = tmp_path / 'peaky_quiet.wav'
    sr = SR_DEFAULT
    n = int(DURATION_DEFAULT * sr)
    # Mostly quiet sine
    t = np.arange(n) / sr
    data = 0.005 * np.sin(2 * np.pi * 1000 * t)
    # Insert a brief near-full-scale transient (10 ms)
    spike_n = int(0.01 * sr)
    spike_start = n // 2
    spike = 0.95 * np.sin(2 * np.pi * 1000 * np.arange(spike_n) / sr)
    data[spike_start:spike_start + spike_n] = spike
    stereo = np.column_stack([data, data])
    sf.write(str(path), stereo, sr, subtype='PCM_24')
    return path


@pytest.fixture
def measure_lufs():
    """Expose the LUFS measurement helper to test functions."""
    return _measure_lufs
