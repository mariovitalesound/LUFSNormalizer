"""
Single-file audio processing function.

This module contains process_single_file() as a standalone, module-level function
so it can be serialized and used with ProcessPoolExecutor for parallel processing.
"""

import soundfile as sf
import pyloudnorm as pyln
import numpy as np
import shutil
import logging
from pathlib import Path

from .measurement import measure_true_peak, measure_lra
from .dither import apply_tpdf_dither
from .metadata import inject_bext_chunk, inject_ixml_chunk, build_ixml_for_normalization
from .. import get_output_filename, VERSION


def process_single_file(audio_path, target_lufs, peak_ceiling, strict_lufs_matching,
                        bit_depth, sample_rate, normalized_path, needs_limiting_path,
                        embed_bwf=False, rng_seed=None):
    """
    Process a single audio file for LUFS normalization.

    This is a standalone function (not a method) so it can be pickled
    for use with ProcessPoolExecutor.

    Args:
        audio_path: Path to input audio file
        target_lufs: Target integrated loudness in LUFS
        peak_ceiling: Maximum True Peak in dBTP
        strict_lufs_matching: If True, skip files exceeding peak
        bit_depth: Output bit depth ('preserve', '16', '24', '32')
        sample_rate: Output sample rate ('preserve', '44100 Hz', '48000 Hz')
        normalized_path: Path to normalized output directory
        needs_limiting_path: Path to needs_limiting output directory
        embed_bwf: If True, embed BWF BEXT + iXML metadata in output WAV
        rng_seed: Optional seed for deterministic TPDF dithering

    Returns:
        dict with keys:
            type: 'success' | 'skipped' | 'needs_limiting' | 'blocked' | 'error'
            filename: str
            result: dict (for success — CSV fields)
            skipped: dict (for needs_limiting — skipped report fields)
            error: dict (for error tracking)
            output_file: str (path to output file, if any)
            log_messages: list of (level, message) tuples
    """
    audio_path = Path(audio_path)
    normalized_path = Path(normalized_path)
    needs_limiting_path = Path(needs_limiting_path)

    log_messages = []
    rng = np.random.default_rng(rng_seed) if rng_seed is not None else np.random.default_rng()

    def log(level, msg):
        log_messages.append((level, msg))

    try:
        # Read audio file
        data, rate = sf.read(str(audio_path))
        original_format = sf.info(str(audio_path)).subtype

        # Measure original LUFS
        meter = pyln.Meter(rate)
        if data.ndim == 1:
            original_lufs = meter.integrated_loudness(data.reshape(-1, 1))
        else:
            original_lufs = meter.integrated_loudness(data)

        # Measure LRA
        lra_lu = measure_lra(data, rate)

        # Check for silence
        if original_lufs == float('-inf') or original_lufs < -70:
            log('warning', f"SKIPPED: {audio_path.name} | Too quiet/silent")
            return {
                'type': 'skipped',
                'filename': audio_path.name,
                'error': {
                    'filename': audio_path.name,
                    'error': 'Too quiet/silent',
                    'status': 'SKIPPED',
                    'reason': 'too_quiet'
                },
                'output_file': None,
                'log_messages': log_messages,
            }

        # Calculate gain needed
        gain_db = target_lufs - original_lufs
        gain_linear = 10 ** (gain_db / 20)

        # Simulate normalization to check peak
        test_normalized = data * gain_linear
        predicted_peak = measure_true_peak(test_normalized, rate)

        # Check if file would exceed peak ceiling
        if predicted_peak > peak_ceiling:
            if strict_lufs_matching:
                # STRICT LUFS MODE: Skip file, copy to needs_limiting/
                needs_limiting_path.mkdir(parents=True, exist_ok=True)
                dest_file = needs_limiting_path / audio_path.name
                shutil.copy2(str(audio_path), str(dest_file))

                log('error', f"NEEDS LIMITING: {audio_path.name} | "
                    f"Would peak at {predicted_peak:.1f}dBTP (ceiling: {peak_ceiling}dBTP) | "
                    f"Copied to needs_limiting/")

                return {
                    'type': 'needs_limiting',
                    'filename': audio_path.name,
                    'skipped': {
                        'filename': audio_path.name,
                        'original_lufs': round(original_lufs, 2),
                        'predicted_peak_dBTP': round(predicted_peak, 2),
                        'gain_needed_db': round(gain_db, 2),
                        'lra_lu': lra_lu if lra_lu is not None else '',
                        'reason': 'would_exceed_peak_ceiling'
                    },
                    'output_file': str(dest_file),
                    'log_messages': log_messages,
                }
            else:
                # DRIFT MODE: Reduce gain to protect peak ceiling
                original_peak = measure_true_peak(data, rate)
                headroom = peak_ceiling - original_peak
                max_safe_gain_db = headroom
                actual_gain_db = min(gain_db, max_safe_gain_db)
                actual_gain_linear = 10 ** (actual_gain_db / 20)

                normalized_data = data * actual_gain_linear

                log('warning', f"PEAK LIMITED: {audio_path.name} | "
                    f"Gain reduced from {gain_db:+.1f}dB to {actual_gain_db:+.1f}dB to protect peak")

                gain_db = actual_gain_db
                gain_linear = actual_gain_linear
        else:
            normalized_data = data * gain_linear

        # Sample rate conversion (downsampling only)
        output_rate = rate
        if sample_rate != 'preserve':
            target_rate = int(sample_rate.split()[0])

            if target_rate > rate:
                log('error', f"BLOCKED: {audio_path.name} | Cannot upsample {rate}Hz to {target_rate}Hz")
                return {
                    'type': 'blocked',
                    'filename': audio_path.name,
                    'error': {
                        'filename': audio_path.name,
                        'error': f'Cannot upsample {rate}Hz to {target_rate}Hz',
                        'status': 'BLOCKED',
                        'reason': 'upsample_blocked'
                    },
                    'output_file': None,
                    'log_messages': log_messages,
                }
            elif target_rate < rate:
                try:
                    import soxr
                    normalized_data = soxr.resample(
                        normalized_data, rate, target_rate, quality='VHQ'
                    )
                    output_rate = target_rate
                    log('info', f"  Resampled: {rate}Hz -> {target_rate}Hz (SOXR VHQ)")
                except ImportError:
                    log('warning', "SOXR not installed, skipping resampling")

        # Determine output bit depth
        if bit_depth == 'preserve':
            if 'PCM_16' in original_format:
                output_subtype = 'PCM_16'
                output_bits = 16
            elif 'PCM_24' in original_format:
                output_subtype = 'PCM_24'
                output_bits = 24
            elif 'PCM_32' in original_format or 'FLOAT' in original_format:
                output_subtype = 'PCM_32'
                output_bits = 32
            else:
                output_subtype = 'PCM_24'
                output_bits = 24
        elif bit_depth == '16':
            output_subtype = 'PCM_16'
            output_bits = 16
        elif bit_depth == '24':
            output_subtype = 'PCM_24'
            output_bits = 24
        else:
            output_subtype = 'PCM_32'
            output_bits = 32

        # Apply TPDF dithering for bit depth reduction
        if output_bits < 32:
            normalized_data = apply_tpdf_dither(normalized_data, output_bits, rng=rng)

        # Final safety clip
        normalized_data = np.clip(normalized_data, -1.0, 1.0)

        # Measure final values
        final_true_peak = measure_true_peak(normalized_data, output_rate)
        final_meter = pyln.Meter(output_rate) if output_rate != rate else meter
        if normalized_data.ndim == 1:
            final_lufs = final_meter.integrated_loudness(normalized_data.reshape(-1, 1))
        else:
            final_lufs = final_meter.integrated_loudness(normalized_data)

        # Measure LRA of output
        output_lra = measure_lra(normalized_data, output_rate)

        # Export with smart filename
        output_filename = get_output_filename(audio_path.name, target_lufs)
        output_file = normalized_path / output_filename

        # Prevent overwriting the source file (e.g. flat output mode with same dir)
        if output_file.resolve() == audio_path.resolve():
            output_file = normalized_path / (Path(output_filename).stem + '_norm' + Path(output_filename).suffix)

        sf.write(str(output_file), normalized_data, output_rate, subtype=output_subtype)

        # Embed BWF metadata if requested (WAV only)
        if embed_bwf and output_file.suffix.lower() == '.wav':
            bext_meta = {
                'description': f"Normalized to {target_lufs} LUFS by LUFS Normalizer v{VERSION}",
                'originator': 'LUFS Normalizer',
                'originator_reference': f'LN{VERSION.replace(".", "")}',
                'loudness_value': final_lufs,
                'loudness_range': output_lra,
                'max_true_peak': final_true_peak,
            }
            inject_bext_chunk(str(output_file), bext_meta)

            ixml = build_ixml_for_normalization(target_lufs, round(final_lufs, 2),
                                                 output_lra, round(final_true_peak, 2), VERSION)
            inject_ixml_chunk(str(output_file), ixml)

        # Determine status
        lufs_undershoot = abs(final_lufs - target_lufs) > 0.5
        if lufs_undershoot and not strict_lufs_matching:
            status = 'OK_UNDERSHOOT'
            reason = 'peak_limited'
            log('info', f"SUCCESS (UNDERSHOOT): {audio_path.name} | "
                f"Gain: {gain_db:+.1f}dB | Peak: {final_true_peak:.1f}dBTP | "
                f"LUFS: {final_lufs:.1f} (target: {target_lufs})")
        else:
            status = 'OK'
            reason = 'ok'
            log('info', f"SUCCESS: {audio_path.name} | "
                f"Gain: {gain_db:+.1f}dB | Peak: {final_true_peak:.1f}dBTP | "
                f"LUFS: {final_lufs:.1f}")

        return {
            'type': 'success',
            'filename': audio_path.name,
            'result': {
                'filename': audio_path.name,
                'status': status,
                'reason': reason,
                'sample_rate': output_rate,
                'bit_depth': output_bits,
                'original_lufs': round(original_lufs, 2),
                'target_lufs': target_lufs,
                'final_lufs': round(final_lufs, 2),
                'gain_applied_db': round(gain_db, 2),
                'true_peak_dBTP': round(final_true_peak, 2),
                'lra_lu': output_lra if output_lra is not None else '',
            },
            'output_file': str(output_file),
            'log_messages': log_messages,
        }

    except Exception as e:
        log('error', f"FAILED: {audio_path.name} | {str(e)}")
        return {
            'type': 'error',
            'filename': audio_path.name,
            'error': {
                'filename': audio_path.name,
                'error': str(e),
                'status': 'FAILED',
                'reason': 'exception'
            },
            'output_file': None,
            'log_messages': log_messages,
        }
