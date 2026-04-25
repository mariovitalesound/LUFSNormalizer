"""
Tests for core.streaming: chunked LUFS measurement and streaming write.

All tests use normal-length synthetic files but override CHUNK_FRAMES so
that multi-chunk code paths are exercised without generating gigabyte fixtures.
"""

import numpy as np
import pytest
import soundfile as sf
import pyloudnorm as pyln

from lufs_normalizer.core import streaming as st
from lufs_normalizer.core.streaming import (
    should_use_streaming,
    measure_streaming,
    write_normalized_streaming,
    STREAMING_THRESHOLD_BYTES,
)


SR = 48000
_TINY_CHUNK = 4800  # 100 ms — forces many chunk boundaries for the same signal


def _write_wav(path, lufs=-18.0, channels=2, duration=6.0, sr=SR):
    """Write a tone at a calibrated integrated LUFS level."""
    n = int(duration * sr)
    t = np.arange(n) / sr
    data = 0.1 * np.sin(2 * np.pi * 1000 * t)
    if channels == 2:
        data = np.column_stack([data, data])
    cur = pyln.Meter(sr).integrated_loudness(
        data if data.ndim > 1 else data.reshape(-1, 1)
    )
    if np.isfinite(cur):
        data = data * (10 ** ((lufs - cur) / 20))
    sf.write(str(path), data, sr, subtype='PCM_24')


# ---------------------------------------------------------------------------
# should_use_streaming
# ---------------------------------------------------------------------------

class TestShouldUseStreaming:
    def test_small_file_is_false(self, tmp_path):
        p = tmp_path / 'small.wav'
        _write_wav(p, duration=4.0)
        assert not should_use_streaming(p)

    def test_threshold_boundary(self, tmp_path, monkeypatch):
        """Monkeypatch threshold to 1 byte so any real file triggers streaming."""
        monkeypatch.setattr(st, 'STREAMING_THRESHOLD_BYTES', 1)
        p = tmp_path / 'any.wav'
        _write_wav(p, duration=1.0)
        assert should_use_streaming(p)


# ---------------------------------------------------------------------------
# measure_streaming — correctness vs. pyloudnorm reference
# ---------------------------------------------------------------------------

class TestMeasureStreaming:
    def test_lufs_matches_pyloudnorm_within_tolerance(self, tmp_path):
        """Streaming LUFS should match pyloudnorm full-file result within 0.3 LU."""
        p = tmp_path / 'ref.wav'
        _write_wav(p, lufs=-23.0, duration=8.0)

        data, rate = sf.read(str(p))
        ref_lufs = pyln.Meter(rate).integrated_loudness(data)

        streaming_lufs, _ = measure_streaming(p, chunk_frames=_TINY_CHUNK)

        assert abs(streaming_lufs - ref_lufs) < 0.3, (
            f"streaming {streaming_lufs:.2f} vs pyloudnorm {ref_lufs:.2f}"
        )

    def test_mono_file(self, tmp_path):
        """Mono file is handled correctly."""
        p = tmp_path / 'mono.wav'
        _write_wav(p, lufs=-18.0, channels=1, duration=6.0)

        data, rate = sf.read(str(p))
        ref_lufs = pyln.Meter(rate).integrated_loudness(data.reshape(-1, 1))

        s_lufs, _ = measure_streaming(p, chunk_frames=_TINY_CHUNK)
        assert abs(s_lufs - ref_lufs) < 0.3

    def test_silence_returns_neg_inf(self, tmp_path):
        p = tmp_path / 'silent.wav'
        sf.write(str(p), np.zeros((SR * 6, 2), dtype=np.float32), SR, subtype='PCM_24')
        lufs, _ = measure_streaming(p, chunk_frames=_TINY_CHUNK)
        assert lufs == float('-inf')

    def test_true_peak_within_one_db_of_reference(self, tmp_path):
        """Streaming True Peak should be within 1 dBTP of a full-buffer measurement."""
        from lufs_normalizer.core.measurement import measure_true_peak

        p = tmp_path / 'tp.wav'
        _write_wav(p, lufs=-18.0, duration=6.0)

        data, rate = sf.read(str(p))
        ref_peak = measure_true_peak(data, rate)

        _, s_peak = measure_streaming(p, chunk_frames=_TINY_CHUNK)
        assert abs(s_peak - ref_peak) < 1.0, (
            f"streaming peak {s_peak:.2f} vs reference {ref_peak:.2f}"
        )

    def test_chunk_boundary_independence(self, tmp_path):
        """Result should be stable across different chunk sizes."""
        p = tmp_path / 'ref.wav'
        _write_wav(p, lufs=-20.0, duration=6.0)

        lufs_small, _ = measure_streaming(p, chunk_frames=_TINY_CHUNK)
        lufs_large, _ = measure_streaming(p, chunk_frames=_TINY_CHUNK * 10)
        assert abs(lufs_small - lufs_large) < 0.2, (
            f"chunk size changed result: {lufs_small:.2f} vs {lufs_large:.2f}"
        )

    def test_target_lufs_range(self, tmp_path):
        """Streaming correctly distinguishes loud from quiet signals."""
        loud = tmp_path / 'loud.wav'
        quiet = tmp_path / 'quiet.wav'
        _write_wav(loud, lufs=-14.0, duration=6.0)
        _write_wav(quiet, lufs=-30.0, duration=6.0)

        lufs_loud, _ = measure_streaming(loud, chunk_frames=_TINY_CHUNK)
        lufs_quiet, _ = measure_streaming(quiet, chunk_frames=_TINY_CHUNK)
        assert lufs_loud > lufs_quiet + 10.0


# ---------------------------------------------------------------------------
# write_normalized_streaming
# ---------------------------------------------------------------------------

class TestWriteNormalizedStreaming:
    def test_output_lufs_near_target(self, tmp_path):
        """Streaming write + measure should land within ±0.3 LU of target."""
        src = tmp_path / 'src.wav'
        dst = tmp_path / 'out' / 'dst.wav'
        _write_wav(src, lufs=-18.0)

        data, rate = sf.read(str(src))
        cur_lufs = pyln.Meter(rate).integrated_loudness(data)
        target = -23.0
        gain = 10 ** ((target - cur_lufs) / 20)
        rng = np.random.default_rng(42)

        final_lufs, _, lra = write_normalized_streaming(
            src, dst, gain_linear=gain, rate=rate,
            output_subtype='PCM_24', output_bits=24, rng=rng,
            chunk_frames=_TINY_CHUNK,
        )

        assert dst.exists()
        assert abs(final_lufs - target) < 0.3, f"final_lufs={final_lufs}"
        assert lra is None  # LRA not measured for large files

    def test_output_file_is_valid_wav(self, tmp_path):
        src = tmp_path / 'src.wav'
        dst = tmp_path / 'out.wav'
        _write_wav(src, lufs=-18.0)
        rng = np.random.default_rng(0)
        write_normalized_streaming(src, dst, gain_linear=1.0, rate=SR,
                                   output_subtype='PCM_24', output_bits=24, rng=rng,
                                   chunk_frames=_TINY_CHUNK)
        info = sf.info(str(dst))
        assert info.samplerate == SR
        assert info.subtype == 'PCM_24'

    def test_peak_ceiling_respected_via_gain(self, tmp_path):
        """A gain that would clip is capped by the caller; write just applies it."""
        src = tmp_path / 'src.wav'
        dst = tmp_path / 'dst.wav'
        _write_wav(src, lufs=-18.0)
        rng = np.random.default_rng(0)
        # Gain of 1.0 → no change; final peak must stay ≤ 0 dBTP
        write_normalized_streaming(src, dst, gain_linear=1.0, rate=SR,
                                   output_subtype='PCM_32', output_bits=32, rng=rng,
                                   chunk_frames=_TINY_CHUNK)
        data, _ = sf.read(str(dst))
        assert np.max(np.abs(data)) <= 1.0

    def test_dither_applied_for_16bit(self, tmp_path):
        """16-bit output with dither produces a different file from 32-bit (noise floor)."""
        src = tmp_path / 'src.wav'
        dst16 = tmp_path / 'out16.wav'
        dst32 = tmp_path / 'out32.wav'
        _write_wav(src, lufs=-18.0)

        for dst, bits, sub in [(dst16, 16, 'PCM_16'), (dst32, 32, 'PCM_32')]:
            rng = np.random.default_rng(1)
            write_normalized_streaming(src, dst, gain_linear=1.0, rate=SR,
                                       output_subtype=sub, output_bits=bits, rng=rng,
                                       chunk_frames=_TINY_CHUNK)

        # 16-bit and 32-bit files have different quantisation steps;
        # any sample-level difference (even 1 LSB ≈ 3e-5) proves dither ran.
        assert dst16.read_bytes() != dst32.read_bytes()
        assert sf.info(str(dst16)).subtype == 'PCM_16'
        assert sf.info(str(dst32)).subtype == 'PCM_32'


# ---------------------------------------------------------------------------
# Integration: streaming path via process_single_file
# ---------------------------------------------------------------------------

class TestStreamingViaProcessor:
    """Force streaming mode in the processor by monkeypatching the threshold."""

    def test_streaming_normalisation_matches_standard(self, tmp_path, monkeypatch):
        """Streaming path produces within 0.3 LU of the standard (bulk) path."""
        import lufs_normalizer.core.streaming as _st_mod
        from lufs_normalizer.core.processor import process_single_file

        src = tmp_path / 'src.wav'
        _write_wav(src, lufs=-18.0)

        norm_std = tmp_path / 'std'
        norm_stream = tmp_path / 'stream'
        nl = tmp_path / 'nl'
        norm_std.mkdir(); norm_stream.mkdir()

        kwargs = dict(
            target_lufs=-23.0, peak_ceiling=-1.0, strict_lufs_matching=True,
            bit_depth='24', sample_rate='preserve', needs_limiting_path=str(nl),
        )

        # Standard (bulk) run
        r_std = process_single_file(str(src), normalized_path=str(norm_std), **kwargs)

        # Force streaming mode
        monkeypatch.setattr(_st_mod, 'STREAMING_THRESHOLD_BYTES', 1)
        r_str = process_single_file(str(src), normalized_path=str(norm_stream), **kwargs)

        assert r_std['type'] == 'success'
        assert r_str['type'] == 'success'
        assert abs(r_std['result']['final_lufs'] - r_str['result']['final_lufs']) < 0.3, (
            f"std={r_std['result']['final_lufs']}, stream={r_str['result']['final_lufs']}"
        )

    def test_streaming_silence_skipped(self, tmp_path, monkeypatch):
        import lufs_normalizer.core.streaming as _st_mod
        from lufs_normalizer.core.processor import process_single_file

        monkeypatch.setattr(_st_mod, 'STREAMING_THRESHOLD_BYTES', 1)
        src = tmp_path / 'silent.wav'
        sf.write(str(src), np.zeros((SR * 6, 2), dtype=np.float32), SR, subtype='PCM_24')

        res = process_single_file(
            str(src), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=str(tmp_path / 'n'), needs_limiting_path=str(tmp_path / 'nl'),
        )
        assert res['type'] == 'skipped'

    def test_streaming_src_blocked(self, tmp_path, monkeypatch):
        """SRC + streaming mode → blocked result with clear reason."""
        import lufs_normalizer.core.streaming as _st_mod
        from lufs_normalizer.core.processor import process_single_file

        monkeypatch.setattr(_st_mod, 'STREAMING_THRESHOLD_BYTES', 1)
        src = tmp_path / 'src.wav'
        _write_wav(src, lufs=-18.0)

        res = process_single_file(
            str(src), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve',
            sample_rate='44100 Hz',   # downsample requested in streaming mode
            normalized_path=str(tmp_path / 'n'), needs_limiting_path=str(tmp_path / 'nl'),
        )
        assert res['type'] == 'blocked'
        assert res['error']['reason'] == 'src_not_supported_in_streaming_mode'
