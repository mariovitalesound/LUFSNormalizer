"""
TPDF (Triangular Probability Density Function) dithering.

Required for professional bit depth reduction to eliminate
quantization distortion when going from 32-bit float to 16/24-bit.
"""

import numpy as np


def apply_tpdf_dither(audio_data, target_bits, rng=None):
    """
    Apply TPDF dithering for bit depth reduction.

    Args:
        audio_data: numpy array of audio samples
        target_bits: target bit depth (16, 24, 32)
        rng: optional numpy random Generator for deterministic output

    Returns:
        Dithered audio data
    """
    if target_bits >= 32:
        return audio_data

    if rng is None:
        rng = np.random.default_rng()

    lsb = 2.0 / (2 ** target_bits)
    dither = (rng.uniform(-0.5, 0.5, audio_data.shape) +
              rng.uniform(-0.5, 0.5, audio_data.shape)) * lsb

    return audio_data + dither
