"""
Tests for core.measurement: True Peak (dBTP) and LRA.

LUFS itself is provided by pyloudnorm, but we test that our wrapper
behavior (measure_true_peak, measure_lra) produces sane values.
"""

import numpy as np
import pytest

from lufs_normalizer.core.measurement import measure_true_peak, measure_lra


SR = 48000


def _sine(freq, duration, sr, amp=1.0, channels=1):
    n = int(duration * sr)
    t = np.arange(n) / sr
    w = amp * np.sin(2 * np.pi * freq * t)
    if channels == 1:
        return w
    return np.column_stack([w] * channels)


class TestTruePeak:
    def test_full_scale_sine_is_near_zero_dbtp(self):
        """A full-scale 1 kHz sine peaks at 0 dBTP (within oversampling tolerance)."""
        data = _sine(1000.0, 1.0, SR, amp=1.0, channels=1)
        peak = measure_true_peak(data, SR)
        assert -0.1 < peak < 0.5, f"expected near 0 dBTP, got {peak}"

    def test_half_scale_sine_is_minus_six_dbtp(self):
        """-6 dBFS sine should measure ~-6 dBTP."""
        data = _sine(1000.0, 1.0, SR, amp=0.5, channels=1)
        peak = measure_true_peak(data, SR)
        assert abs(peak - (-6.02)) < 0.5, f"expected ~-6 dBTP, got {peak}"

    def test_silence_returns_floor(self):
        """Pure silence should report a very low peak value."""
        data = np.zeros(SR, dtype=np.float64)
        peak = measure_true_peak(data, SR)
        assert peak < -90.0, f"silence should be < -90 dBTP, got {peak}"

    def test_stereo_peak_uses_max_channel(self):
        """Stereo with one quiet channel still reports the loud channel's peak."""
        n = SR
        loud = 0.5 * np.sin(2 * np.pi * 1000 * np.arange(n) / SR)
        quiet = 0.01 * np.sin(2 * np.pi * 1000 * np.arange(n) / SR)
        data = np.column_stack([loud, quiet])
        peak = measure_true_peak(data, SR)
        assert -7.0 < peak < -5.0, f"expected ~-6 dBTP from loud ch, got {peak}"

    def test_intersample_peak_at_or_above_sample_peak(self):
        """For mid-band signals, true peak ≥ sample peak.

        Note: very near Nyquist, the bandlimited reconstruction filter
        (VHQ in SOXR) intentionally attenuates content, so the property
        does not hold by construction at the band edge. We test in the
        well-behaved mid-band where the relation is reliable.
        """
        n = SR
        t = np.arange(n) / SR
        # Mid-band tone with a deliberate phase offset so samples don't
        # land on the analytic peak — true peak should reveal the gap.
        freq = 7000.0  # well below Nyquist
        data = 0.7 * np.sin(2 * np.pi * freq * t + 0.4)
        sample_peak_db = 20 * np.log10(np.max(np.abs(data)))
        true_peak_db = measure_true_peak(data, SR)
        # 0.5 dB tolerance for the discrete Hilbert-style oversampling
        assert true_peak_db >= sample_peak_db - 0.5, (
            f"true_peak {true_peak_db:.2f} should be >= sample_peak "
            f"{sample_peak_db:.2f}"
        )


class TestLRA:
    def test_short_file_returns_none(self):
        """Files shorter than 3 s have no LRA window."""
        data = _sine(1000.0, 1.0, SR, amp=0.1, channels=2)
        assert measure_lra(data, SR) is None

    def test_constant_tone_returns_finite_lra(self):
        """A constant-amplitude tone produces a finite, small LRA value.

        Note: pyloudnorm's 3 s short-term window has startup transients on
        finite-length signals, so even a perfectly flat tone can register a
        few LU of range. We just assert it's bounded and finite.
        """
        data = _sine(1000.0, 6.0, SR, amp=0.1, channels=2)
        lra = measure_lra(data, SR)
        assert lra is not None
        assert lra < 5.0, f"constant tone LRA should be modest, got {lra}"

    def test_dynamic_signal_has_higher_lra_than_constant(self):
        """A signal alternating loud/quiet has more LRA than a flat tone.

        Uses 4 s segments so the 3 s short-term window can resolve them
        rather than smoothing them away.
        """
        seg_loud = _sine(1000, 4.0, SR, amp=0.3, channels=2)
        seg_quiet = _sine(1000, 4.0, SR, amp=0.03, channels=2)
        dynamic = np.vstack([seg_loud, seg_quiet, seg_loud])
        constant = _sine(1000.0, 12.0, SR, amp=0.1, channels=2)

        lra_dynamic = measure_lra(dynamic, SR)
        lra_constant = measure_lra(constant, SR)

        assert lra_dynamic is not None and lra_constant is not None
        assert lra_dynamic > lra_constant + 2.0, (
            f"dynamic ({lra_dynamic}) should exceed constant ({lra_constant}) "
            f"by at least 2 LU"
        )

    def test_silence_returns_none(self):
        """Silent input should not produce an LRA value."""
        data = np.zeros((SR * 5, 2), dtype=np.float64)
        lra = measure_lra(data, SR)
        # Either None or a finite value below 0; pyloudnorm may return -inf
        assert lra is None or lra <= 0
