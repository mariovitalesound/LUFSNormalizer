"""
Tests for core.dither: TPDF dithering.

Verifies dither magnitude, determinism with a seeded RNG, no-op for 32-bit,
and that the noise distribution is triangular (not rectangular).
"""

import numpy as np
import pytest

from lufs_normalizer.core.dither import apply_tpdf_dither


class TestTPDFDither:
    def test_no_op_for_32_bit(self):
        """32-bit target returns the input unchanged."""
        data = np.linspace(-0.5, 0.5, 1000)
        out = apply_tpdf_dither(data, 32)
        np.testing.assert_array_equal(out, data)

    def test_no_op_for_higher_bit_depths(self):
        """Bit depths >= 32 are pass-through."""
        data = np.array([0.1, -0.2, 0.3])
        np.testing.assert_array_equal(apply_tpdf_dither(data, 64), data)

    def test_dither_magnitude_for_16_bit(self):
        """16-bit dither peak should be near ±1 LSB16 (~ ±3.05e-5)."""
        rng = np.random.default_rng(0)
        data = np.zeros(100_000)
        out = apply_tpdf_dither(data, 16, rng=rng)
        lsb = 2.0 / (2 ** 16)
        # TPDF range is ±1 LSB (peak), produced by sum of two ±0.5 LSB uniforms
        peak = np.max(np.abs(out))
        assert 0.5 * lsb < peak < 1.05 * lsb, f"peak {peak} not within ±1 LSB ({lsb})"

    def test_dither_magnitude_for_24_bit(self):
        """24-bit dither is 256x smaller than 16-bit."""
        rng = np.random.default_rng(0)
        data = np.zeros(100_000)
        out16 = apply_tpdf_dither(data.copy(), 16, rng=np.random.default_rng(0))
        out24 = apply_tpdf_dither(data.copy(), 24, rng=np.random.default_rng(0))
        ratio = np.std(out16) / np.std(out24)
        # 16-bit LSB / 24-bit LSB = 256
        assert 200 < ratio < 320, f"std ratio {ratio} far from expected 256"

    def test_seeded_rng_is_deterministic(self):
        """Same seed → identical dither, regardless of when it's run."""
        data = np.zeros(1000)
        out_a = apply_tpdf_dither(data.copy(), 16, rng=np.random.default_rng(42))
        out_b = apply_tpdf_dither(data.copy(), 16, rng=np.random.default_rng(42))
        np.testing.assert_array_equal(out_a, out_b)

    def test_different_seeds_produce_different_output(self):
        """Different seeds → different dither realizations."""
        data = np.zeros(1000)
        out_a = apply_tpdf_dither(data.copy(), 16, rng=np.random.default_rng(1))
        out_b = apply_tpdf_dither(data.copy(), 16, rng=np.random.default_rng(2))
        assert not np.array_equal(out_a, out_b)

    def test_distribution_is_triangular_not_uniform(self):
        """TPDF: sum of two uniforms → triangular PDF, peaked at zero.

        For TPDF with peak ±1 LSB, the variance is (LSB^2)/6.
        For RPDF (one uniform) with same peak, variance would be (LSB^2)/3.
        So TPDF std should be ~70% of RPDF std at the same peak.
        """
        rng = np.random.default_rng(0)
        data = np.zeros(200_000)
        out = apply_tpdf_dither(data, 16, rng=rng)
        lsb = 2.0 / (2 ** 16)
        # Expected std of TPDF noise = LSB / sqrt(6)
        expected_std = lsb / np.sqrt(6)
        actual_std = np.std(out)
        rel_err = abs(actual_std - expected_std) / expected_std
        assert rel_err < 0.05, (
            f"std {actual_std} (rel err {rel_err:.3f}) not consistent with TPDF; "
            f"expected ~{expected_std}"
        )

    def test_zero_mean(self):
        """TPDF dither has zero mean."""
        rng = np.random.default_rng(0)
        out = apply_tpdf_dither(np.zeros(200_000), 16, rng=rng)
        lsb = 2.0 / (2 ** 16)
        # Mean should be < 1% of LSB on a large sample
        assert abs(np.mean(out)) < 0.01 * lsb

    def test_preserves_signal_shape(self):
        """Dither is added to, not multiplied by, the signal."""
        data = np.linspace(-0.5, 0.5, 10000)
        out = apply_tpdf_dither(data, 16, rng=np.random.default_rng(0))
        # Difference should be tiny noise, not scaled signal
        diff = out - data
        assert np.max(np.abs(diff)) < 1e-4
        # Mean of diff should be ~0 (additive noise, not gain)
        assert abs(np.mean(diff)) < 1e-6

    def test_2d_input_dithered_per_sample(self):
        """Stereo input gets independent dither per sample / channel."""
        data = np.zeros((1000, 2))
        out = apply_tpdf_dither(data, 16, rng=np.random.default_rng(0))
        assert out.shape == (1000, 2)
        # Two channels should not be identical (different random samples)
        assert not np.array_equal(out[:, 0], out[:, 1])
