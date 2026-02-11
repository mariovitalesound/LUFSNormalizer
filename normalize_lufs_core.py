#!/usr/bin/env python3
"""
LUFS Normalizer Core Engine v2.5.1
Professional broadcast-grade audio normalization

Changes in v2.5.1:
- BUGFIX: LUFS meter now uses correct sample rate after resampling
- BUGFIX: FAILED error dicts now include 'reason' field for uniform CSV schema

Changes in v2.5.0:
- Expanded preset system (10 presets covering broadcast, streaming, podcast, game, film, music)
- Strict vs Drift mode toggle for peak handling
- CSV reason column for automation/QC workflows
- Updated preset structure with name, description, and standard fields

Features:
- ITU-R BS.1770-4 LUFS measurement (pyloudnorm)
- True Peak detection (dBTP) - EBU R128 compliant
- TPDF dithering for bit depth reduction
- SOXR VHQ resampling (mastering-grade)
- Upsample prevention (professional behavior)
- Strict LUFS mode: Skip files exceeding peak ceiling
- Drift mode: Reduce gain to protect peak (LUFS may undershoot)

Author: Mario Vitale
Version: 2.5.1
"""

import soundfile as sf
import pyloudnorm as pyln
import numpy as np
import logging
import csv
import shutil
import re
from pathlib import Path
from datetime import datetime

VERSION = "2.5.1"

# LUFS presets for common standards
LUFS_PRESETS = {
    # Primary/Common
    'broadcast_us': {
        'lufs': -24.0,
        'peak': -2.0,
        'name': 'Broadcast (US)',
        'description': 'ATSC A/85 — US Television',
        'standard': 'ATSC A/85'
    },
    'broadcast_eu': {
        'lufs': -23.0,
        'peak': -1.0,
        'name': 'Broadcast (EU)',
        'description': 'EBU R128 — European Television',
        'standard': 'EBU R128'
    },
    'streaming': {
        'lufs': -14.0,
        'peak': -1.0,
        'name': 'Streaming',
        'description': 'Spotify / YouTube / Amazon',
        'standard': 'Spotify/YouTube'
    },
    'podcast': {
        'lufs': -16.0,
        'peak': -1.0,
        'name': 'Podcast',
        'description': 'Apple Podcasts / Spoken Word',
        'standard': 'Apple Podcasts'
    },

    # Game Audio (ASWG)
    'game_console': {
        'lufs': -24.0,
        'peak': -1.0,
        'name': 'Game (Console)',
        'description': 'ASWG Home — Console/PC Games',
        'standard': 'ASWG-R001 Home'
    },
    'game_mobile': {
        'lufs': -18.0,
        'peak': -1.0,
        'name': 'Game (Mobile)',
        'description': 'ASWG Portable — Mobile Games',
        'standard': 'ASWG-R001 Portable'
    },

    # Film/Cinema
    'film': {
        'lufs': -24.0,
        'peak': -2.0,
        'name': 'Film / Cinema',
        'description': 'Theatrical Reference (not dialog-gated)',
        'standard': 'SMPTE RP 200'
    },

    # Music
    'music_dynamic': {
        'lufs': -14.0,
        'peak': -1.0,
        'name': 'Music (Dynamic)',
        'description': 'Balanced loudness with dynamics',
        'standard': 'Streaming optimized'
    },
    'music_loud': {
        'lufs': -9.0,
        'peak': -1.0,
        'name': 'Music (Loud)',
        'description': 'Modern competitive loudness',
        'standard': 'Contemporary pop/EDM'
    },

    # Reference
    'reference_cinema': {
        'lufs': -27.0,
        'peak': -2.0,
        'name': 'Cinema Dialog Ref',
        'description': 'Netflix-style dialog reference',
        'standard': 'Netflix 5.1'
    }
}

# Default favorites (user can customize)
DEFAULT_FAVORITES = ['broadcast_us', 'streaming', 'podcast']

def apply_lufs_preset(preset_name):
    """Return LUFS and peak values for a preset"""
    if preset_name in LUFS_PRESETS:
        return LUFS_PRESETS[preset_name]['lufs'], LUFS_PRESETS[preset_name]['peak']
    return -23.0, -1.0  # Default to broadcast


def get_preset_for_lufs(lufs_value, peak_value=None):
    """Return preset name if LUFS (and optionally peak) value matches a preset, else None"""
    try:
        lufs = float(lufs_value)
        peak = float(peak_value) if peak_value is not None else None

        for name, preset in LUFS_PRESETS.items():
            if abs(preset['lufs'] - lufs) < 0.01:  # Float comparison tolerance
                # If peak is provided, also check peak match
                if peak is not None:
                    if abs(preset['peak'] - peak) < 0.01:
                        return name
                else:
                    return name
    except (ValueError, TypeError):
        pass
    return None


def get_preset_info(preset_name):
    """Return full preset info dict, or None if not found"""
    return LUFS_PRESETS.get(preset_name, None)


def get_output_filename(original_name, target_lufs):
    """
    Generate output filename with smart LUFS suffix handling.
    
    - If file has existing LUFS suffix (e.g., _-18LUFS), replace it
    - If file has _normalized suffix, replace with LUFS suffix
    - Otherwise, append LUFS suffix
    
    Examples:
        audio.wav -> audio_-23LUFS.wav
        audio_-18LUFS.wav -> audio_-23LUFS.wav
        audio_normalized.wav -> audio_-23LUFS.wav
    """
    stem = Path(original_name).stem
    suffix = Path(original_name).suffix
    
    # Pattern to match existing LUFS suffix (e.g., _-23LUFS, _-18LUFS, _-14LUFS)
    lufs_pattern = r'_-?\d+(\.\d+)?LUFS$'
    
    # Pattern to match _normalized suffix
    normalized_pattern = r'_normalized$'
    
    # Remove existing LUFS suffix if present
    stem = re.sub(lufs_pattern, '', stem, flags=re.IGNORECASE)
    
    # Remove _normalized suffix if present
    stem = re.sub(normalized_pattern, '', stem, flags=re.IGNORECASE)
    
    # Create new filename with LUFS suffix
    lufs_str = f"{int(target_lufs)}" if target_lufs == int(target_lufs) else f"{target_lufs}"
    new_name = f"{stem}_{lufs_str}LUFS{suffix}"
    
    return new_name


def apply_tpdf_dither(audio_data, target_bits):
    """
    Apply TPDF (Triangular Probability Density Function) dithering.
    
    Required for professional bit depth reduction to eliminate 
    quantization distortion when going from 32-bit float to 16/24-bit.
    """
    if target_bits >= 32:
        return audio_data
    
    lsb = 2.0 / (2 ** target_bits)
    dither = (np.random.uniform(-0.5, 0.5, audio_data.shape) + 
              np.random.uniform(-0.5, 0.5, audio_data.shape)) * lsb
    
    return audio_data + dither


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


class LUFSNormalizer:
    """
    Professional LUFS batch normalizer with broadcast-grade features.
    
    v2.4.3 Behavior:
    - Files that would exceed peak ceiling after normalization are SKIPPED
    - Skipped files are copied to 'needs_limiting/' folder for manual processing
    - All processed files are guaranteed to be at target LUFS
    - Result callback for live GUI updates
    """
    
    def __init__(self, config_path=None):
        self.config_path = config_path
        self.progress_callback = None
        self.result_callback = None  # Called after each file with result
        self.stop_requested = False
        self.results = []
        self.errors = []
        self.skipped_files = []
        
    def set_progress_callback(self, callback):
        """Set callback for progress updates: callback(current, total, filename)"""
        self.progress_callback = callback
    
    def set_result_callback(self, callback):
        """Set callback for result updates: callback(filename, status, details)"""
        self.result_callback = callback
        
    def request_stop(self):
        """Request graceful stop of batch processing"""
        self.stop_requested = True
        
    def normalize_batch(self, input_dir, output_dir, target_lufs=-23.0, peak_ceiling=-1.0,
                       bit_depth='preserve', sample_rate='preserve',
                       use_batch_folders=True, generate_log=True, generate_csv=True,
                       strict_lufs_matching=True):
        """
        Normalize a batch of audio files to target LUFS.

        Args:
            input_dir: Path to input folder containing WAV/AIFF files
            output_dir: Path to output folder
            target_lufs: Target integrated loudness in LUFS
            peak_ceiling: Maximum True Peak in dBTP (-1.0 for broadcast)
            bit_depth: Output bit depth ('preserve', '16', '24', '32')
            sample_rate: Output sample rate ('preserve', '44100 Hz', '48000 Hz')
            use_batch_folders: If True, create timestamped batch folder structure
            generate_log: If True, create processing.log file
            generate_csv: If True, create CSV report
            strict_lufs_matching: If True, skip files exceeding peak (exact LUFS).
                                  If False, reduce gain to protect peak (LUFS may undershoot).

        Returns:
            tuple: (success_count, total_count, log_path, csv_path, output_path)
        """
        self.stop_requested = False
        self.results = []
        self.errors = []
        self.skipped_files = []
        
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        
        # Find audio files
        wav_files = list(input_path.glob('*.wav')) + list(input_path.glob('*.WAV'))
        aiff_files = (list(input_path.glob('*.aiff')) + list(input_path.glob('*.AIFF')) +
                      list(input_path.glob('*.aif')) + list(input_path.glob('*.AIF')))
        audio_files = sorted(wav_files + aiff_files)
        
        if not audio_files:
            logging.warning("No WAV or AIFF files found in input directory")
            return 0, 0, None, None, None
        
        total_files = len(audio_files)
        
        # Setup output structure
        if use_batch_folders:
            # Timestamped batch folder structure
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            batch_name = f"batch_{timestamp}_{int(target_lufs)}LUFS"
            batch_path = output_path / batch_name
            normalized_path = batch_path / 'normalized'
            needs_limiting_path = batch_path / 'needs_limiting'
            logs_path = batch_path / 'logs'
        else:
            # Flat output - files go directly to output folder
            batch_path = output_path
            normalized_path = output_path
            needs_limiting_path = output_path / 'needs_limiting'
            logs_path = output_path
        
        normalized_path.mkdir(parents=True, exist_ok=True)
        if generate_log or generate_csv:
            logs_path.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        log_file = logs_path / 'processing.log' if generate_log else None
        
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        handlers = [logging.StreamHandler()]
        if generate_log:
            handlers.append(logging.FileHandler(log_file))
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=handlers
        )
        
        # Log header
        logging.info("=" * 70)
        logging.info(f"LUFS NORMALIZER v{VERSION} - BATCH PROCESSING")
        logging.info("=" * 70)
        logging.info(f"Target LUFS: {target_lufs}")
        logging.info(f"Peak Ceiling: {peak_ceiling} dBTP")
        logging.info(f"Bit Depth: {bit_depth}")
        logging.info(f"Sample Rate: {sample_rate}")
        logging.info(f"Files to process: {total_files}")
        logging.info("-" * 70)
        
        # Process each file
        for idx, audio_path in enumerate(audio_files, 1):
            if self.stop_requested:
                logging.info("Processing stopped by user")
                break
            
            if self.progress_callback:
                self.progress_callback(idx, total_files, audio_path.name)
            
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
                
                # Check for silence
                if original_lufs == float('-inf') or original_lufs < -70:
                    logging.warning(f"[{idx}/{total_files}] SKIPPED: {audio_path.name} | Too quiet/silent")
                    self.errors.append({
                        'filename': audio_path.name,
                        'error': 'Too quiet/silent',
                        'status': 'SKIPPED',
                        'reason': 'too_quiet'
                    })
                    if self.result_callback:
                        self.result_callback(audio_path.name, 'SKIPPED', 'Too quiet/silent')
                    continue
                
                # Calculate gain needed
                gain_db = target_lufs - original_lufs
                gain_linear = 10 ** (gain_db / 20)
                
                # Simulate normalization to check peak
                test_normalized = data * gain_linear
                predicted_peak = measure_true_peak(test_normalized, rate)
                
                # Check if file would exceed peak ceiling
                if predicted_peak > peak_ceiling:
                    if strict_lufs_matching:
                        # STRICT LUFS MODE: Skip file, preserve exact LUFS target
                        # Copy to needs_limiting/ folder for manual processing
                        needs_limiting_path.mkdir(exist_ok=True)

                        dest_file = needs_limiting_path / audio_path.name
                        shutil.copy2(str(audio_path), str(dest_file))

                        logging.error(
                            f"[{idx}/{total_files}] NEEDS LIMITING: {audio_path.name} | "
                            f"Would peak at {predicted_peak:.1f}dBTP (ceiling: {peak_ceiling}dBTP) | "
                            f"Copied to needs_limiting/"
                        )

                        self.skipped_files.append({
                            'filename': audio_path.name,
                            'original_lufs': round(original_lufs, 2),
                            'predicted_peak_dBTP': round(predicted_peak, 2),
                            'gain_needed_db': round(gain_db, 2),
                            'reason': 'would_exceed_peak_ceiling'
                        })
                        if self.result_callback:
                            self.result_callback(audio_path.name, 'NEEDS_LIMITING',
                                               f'Would peak at {predicted_peak:.1f}dBTP')
                        continue
                    else:
                        # STRICT PEAK MODE (Drift): Reduce gain to protect peak ceiling
                        # Calculate maximum safe gain based on original peak
                        original_peak = measure_true_peak(data, rate)
                        headroom = peak_ceiling - original_peak
                        max_safe_gain_db = headroom
                        actual_gain_db = min(gain_db, max_safe_gain_db)
                        actual_gain_linear = 10 ** (actual_gain_db / 20)

                        # Apply reduced gain
                        normalized_data = data * actual_gain_linear

                        logging.warning(
                            f"[{idx}/{total_files}] PEAK LIMITED: {audio_path.name} | "
                            f"Gain reduced from {gain_db:+.1f}dB to {actual_gain_db:+.1f}dB to protect peak"
                        )

                        # Update gain_db for reporting
                        gain_db = actual_gain_db
                        gain_linear = actual_gain_linear
                else:
                    # File is safe to process - apply full normalization
                    normalized_data = data * gain_linear
                
                # Sample rate conversion (downsampling only)
                output_rate = rate
                if sample_rate != 'preserve':
                    target_rate = int(sample_rate.split()[0])
                    
                    if target_rate > rate:
                        logging.error(f"[{idx}/{total_files}] BLOCKED: {audio_path.name} | Cannot upsample")
                        self.errors.append({
                            'filename': audio_path.name,
                            'error': f'Cannot upsample {rate}Hz to {target_rate}Hz',
                            'status': 'BLOCKED',
                            'reason': 'upsample_blocked'
                        })
                        if self.result_callback:
                            self.result_callback(audio_path.name, 'BLOCKED',
                                               f'Cannot upsample {rate}Hz to {target_rate}Hz')
                        continue
                    elif target_rate < rate:
                        try:
                            import soxr
                            normalized_data = soxr.resample(
                                normalized_data, rate, target_rate, quality='VHQ'
                            )
                            output_rate = target_rate
                            logging.info(f"  Resampled: {rate}Hz → {target_rate}Hz (SOXR VHQ)")
                        except ImportError:
                            logging.warning("SOXR not installed, skipping resampling")
                
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
                    normalized_data = apply_tpdf_dither(normalized_data, output_bits)
                
                # Final safety clip (should rarely trigger since we checked peak)
                normalized_data = np.clip(normalized_data, -1.0, 1.0)
                
                # Measure final values
                final_true_peak = measure_true_peak(normalized_data, output_rate)

                # Use correct sample rate for LUFS measurement after resampling
                final_meter = pyln.Meter(output_rate) if output_rate != rate else meter

                if normalized_data.ndim == 1:
                    final_lufs = final_meter.integrated_loudness(normalized_data.reshape(-1, 1))
                else:
                    final_lufs = final_meter.integrated_loudness(normalized_data)
                
                # Export with smart filename
                output_filename = get_output_filename(audio_path.name, target_lufs)
                output_file = normalized_path / output_filename
                sf.write(str(output_file), normalized_data, output_rate, subtype=output_subtype)
                
                # Determine if this was a peak-limited (drift) result
                lufs_undershoot = abs(final_lufs - target_lufs) > 0.5  # More than 0.5 dB off target

                if lufs_undershoot and not strict_lufs_matching:
                    # Drift mode: file was peak-limited, LUFS undershoots target
                    status = 'OK_UNDERSHOOT'
                    reason = 'peak_limited'
                    logging.info(
                        f"[{idx}/{total_files}] SUCCESS (UNDERSHOOT): {audio_path.name} | "
                        f"Gain: {gain_db:+.1f}dB | Peak: {final_true_peak:.1f}dBTP | "
                        f"LUFS: {final_lufs:.1f} (target: {target_lufs})"
                    )
                    if self.result_callback:
                        self.result_callback(audio_path.name, 'SUCCESS_UNDERSHOOT',
                                           f'LUFS: {final_lufs:.1f} (target was {target_lufs})')
                else:
                    # Normal success
                    status = 'OK'
                    reason = 'ok'
                    logging.info(
                        f"[{idx}/{total_files}] SUCCESS: {audio_path.name} | "
                        f"Gain: {gain_db:+.1f}dB | Peak: {final_true_peak:.1f}dBTP | "
                        f"LUFS: {final_lufs:.1f}"
                    )
                    if self.result_callback:
                        self.result_callback(audio_path.name, 'SUCCESS',
                                           f'Gain: {gain_db:+.1f}dB | Peak: {final_true_peak:.1f}dBTP')

                self.results.append({
                    'filename': audio_path.name,
                    'status': status,
                    'reason': reason,
                    'sample_rate': output_rate,
                    'bit_depth': output_bits,
                    'original_lufs': round(original_lufs, 2),
                    'target_lufs': target_lufs,
                    'final_lufs': round(final_lufs, 2),
                    'gain_applied_db': round(gain_db, 2),
                    'true_peak_dBTP': round(final_true_peak, 2)
                })
                
            except Exception as e:
                logging.error(f"[{idx}/{total_files}] FAILED: {audio_path.name} | {str(e)}")
                self.errors.append({
                    'filename': audio_path.name,
                    'error': str(e),
                    'status': 'FAILED',
                    'reason': 'exception'
                })
                if self.result_callback:
                    self.result_callback(audio_path.name, 'FAILED', str(e))
                continue
        
        # Generate CSV reports (if enabled)
        csv_path = None
        if generate_csv and self.results:
            csv_path = logs_path / 'normalization_report.csv'
            with open(csv_path, 'w', newline='') as f:
                fieldnames = ['filename', 'status', 'reason', 'sample_rate', 'bit_depth',
                            'original_lufs', 'target_lufs', 'final_lufs', 'gain_applied_db', 'true_peak_dBTP']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.results)
        
        # Generate skipped files report (if there are any)
        if generate_csv and self.skipped_files:
            skipped_csv = logs_path / 'needs_limiting_report.csv'
            with open(skipped_csv, 'w', newline='') as f:
                fieldnames = ['filename', 'original_lufs', 'predicted_peak_dBTP', 
                            'gain_needed_db', 'reason']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.skipped_files)
        
        # Final summary
        success_count = len(self.results)
        skipped_count = len(self.skipped_files)
        error_count = len(self.errors)
        
        logging.info("=" * 70)
        logging.info("BATCH COMPLETE")
        logging.info(f"Processed: {success_count}/{total_files} files at {target_lufs} LUFS")
        
        if skipped_count > 0:
            logging.warning(f"NEEDS LIMITING: {skipped_count} files exceeded peak ceiling")
            logging.warning(f"  → Copied to: {needs_limiting_path}")
            logging.warning(f"  → Apply a limiter in your DAW, then re-process")
        
        if error_count > 0:
            logging.error(f"Errors: {error_count} files failed")
        
        logging.info(f"Output: {normalized_path}")
        logging.info("=" * 70)
        
        return success_count, total_files, str(log_file) if log_file else None, str(csv_path) if csv_path else None, str(normalized_path)


# CLI interface
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description=f'LUFS Normalizer v{VERSION}',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Files that would exceed peak ceiling are SKIPPED and copied to a
'needs_limiting/' folder. Apply a limiter in your DAW, then re-process.
        """
    )
    parser.add_argument('input', help='Input directory')
    parser.add_argument('output', help='Output directory')
    parser.add_argument('-t', '--target', type=float, default=-23.0, help='Target LUFS')
    parser.add_argument('-p', '--peak', type=float, default=-1.0, help='Peak ceiling dBTP')
    parser.add_argument('-b', '--bits', choices=['preserve', '16', '24', '32'], default='preserve')
    parser.add_argument('-r', '--rate', choices=['preserve', '44100', '48000'], default='preserve')
    
    args = parser.parse_args()
    
    normalizer = LUFSNormalizer()
    sr = 'preserve' if args.rate == 'preserve' else f'{args.rate} Hz'
    
    normalizer.normalize_batch(
        input_dir=args.input,
        output_dir=args.output,
        target_lufs=args.target,
        peak_ceiling=args.peak,
        bit_depth=args.bits,
        sample_rate=sr
    )
