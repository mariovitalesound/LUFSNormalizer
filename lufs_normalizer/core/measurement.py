"""
Audio measurement functions: True Peak (dBTP) and Loudness Range (LRA).

True Peak uses 4x oversampling per ITU-R BS.1770-4.
LRA implements EBU R128 s1 loudness range measurement.
"""

import numpy as np
import logging


def measure_true_peak(audio_data, sample_rate):
    """
    Measure True Peak (dBTP) using 4x oversampling via SOXR.

    True Peak accounts for inter-sample peaks that occur during
    D/A conversion. Required for EBU R128 broadcast compliance.
    """
    try:
        import soxr
        target_rate = sample_rate * 4
        oversampled = soxr.resample(audio_data, sample_rate, target_rate, quality='VHQ')
        true_peak_linear = np.max(np.abs(oversampled))

    except ImportError:
        try:
            from scipy import signal
            oversample_factor = 4

            if audio_data.ndim == 1:
                oversampled = signal.resample(audio_data, len(audio_data) * oversample_factor)
            else:
                oversampled_channels = []
                for ch in range(audio_data.shape[1]):
                    resampled = signal.resample(audio_data[:, ch], len(audio_data) * oversample_factor)
                    oversampled_channels.append(resampled)
                oversampled = np.column_stack(oversampled_channels)

            true_peak_linear = np.max(np.abs(oversampled))

        except ImportError:
            logging.warning("Neither SOXR nor scipy available - using sample peak")
            true_peak_linear = np.max(np.abs(audio_data))

    if true_peak_linear > 0:
        return 20 * np.log10(true_peak_linear)
    return -100.0


def measure_lra(audio_data, sample_rate):
    """
    Measure EBU R128 Loudness Range (LRA) in LU.

    Uses pyloudnorm's built-in loudness_range() which computes proper
    ungated short-term loudness with K-weighting per EBU R128 s1.

    Args:
        audio_data: numpy array of audio samples (mono or multi-channel)
        sample_rate: sample rate in Hz

    Returns:
        LRA value in LU, or None if measurement fails
    """
    try:
        import pyloudnorm as pyln

        # Ensure 2D array for pyloudnorm
        if audio_data.ndim == 1:
            data_2d = audio_data.reshape(-1, 1)
        else:
            data_2d = audio_data

        # Need at least 3 seconds for short-term loudness window
        min_samples = int(3.0 * sample_rate)
        if len(data_2d) < min_samples:
            return None

        meter = pyln.Meter(sample_rate)
        lra = meter.loudness_range(data_2d)

        if lra == float('-inf') or lra == float('inf') or np.isnan(lra):
            return None

        return round(lra, 1)

    except Exception as e:
        logging.warning(f"LRA measurement failed: {e}")
        return None
