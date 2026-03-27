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

    Implements EBU R128 s1:
    1. Compute short-term loudness (3s window, 200ms hop)
    2. Apply absolute gate at -70 LUFS
    3. Apply relative gate at -20 LU below ungated mean
    4. LRA = difference between 95th and 10th percentile of gated distribution

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

        # Short-term loudness: 3 second window, 200ms hop
        window_samples = int(3.0 * sample_rate)
        hop_samples = int(0.2 * sample_rate)

        if len(data_2d) < window_samples:
            return None

        meter = pyln.Meter(sample_rate)

        short_term_loudness = []
        pos = 0
        while pos + window_samples <= len(data_2d):
            block = data_2d[pos:pos + window_samples]
            loudness = meter.integrated_loudness(block)
            if loudness != float('-inf'):
                short_term_loudness.append(loudness)
            pos += hop_samples

        if len(short_term_loudness) < 2:
            return None

        st_array = np.array(short_term_loudness)

        # Absolute gate: -70 LUFS
        abs_gated = st_array[st_array > -70.0]
        if len(abs_gated) < 2:
            return None

        # Relative gate: -20 LU below mean of absolute-gated values
        # Convert LUFS to linear, compute mean, convert back
        abs_gated_linear = 10 ** (abs_gated / 10.0)
        mean_linear = np.mean(abs_gated_linear)
        mean_lufs = 10 * np.log10(mean_linear)
        relative_threshold = mean_lufs - 20.0

        rel_gated = abs_gated[abs_gated > relative_threshold]
        if len(rel_gated) < 2:
            return None

        # LRA = 95th percentile - 10th percentile
        p95 = np.percentile(rel_gated, 95)
        p10 = np.percentile(rel_gated, 10)
        lra = p95 - p10

        return round(lra, 1)

    except Exception as e:
        logging.warning(f"LRA measurement failed: {e}")
        return None
